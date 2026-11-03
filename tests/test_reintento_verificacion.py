"""Pruebas del reintento individual y la verificacion en PRIZMA (/cursos).

- Reintento: sube UN recurso elegido a mano a UNA actividad (sin matriz ni
  ZIP) y deja el resultado en data/estado_cursos.json + un reporte CSV.
- Verificacion: recorre PRIZMA en solo lectura y ajusta el estado a lo que
  aparece ahi (una "subida" que no aparece vuelve a faltar).

Ambos corren en su propio hilo con la pagina de progreso del cargue y
comparten un candado: uno a la vez.
"""

import csv
import os

import pytest
from fastapi.testclient import TestClient

from main import app
from auto_prizma.api.routes import courses
from auto_prizma.automation.prizma import engine
from auto_prizma.services import course_state
from auto_prizma.services.auth import SESION_COOKIE, USUARIO_ACTUAL, _firmar_sesion
from auto_prizma.services.upload_jobs import TRABAJOS


def _lanzar_sincrono(target, args):
    """En vez de un hilo real, ejecuta el trabajo en el momento."""
    target(*args)


@pytest.fixture(autouse=True)
def limpio(monkeypatch, tmp_path):
    """Aísla estado y reportes de prueba de los datos locales del usuario."""
    monkeypatch.setattr(course_state, "ESTADO_CURSOS_PATH", str(tmp_path / "estado_cursos.json"))
    report_dir = str(tmp_path / "reportes")
    os.makedirs(report_dir, exist_ok=True)
    monkeypatch.setattr(course_state, "RESULTADOS_DIR", report_dir)
    monkeypatch.setattr(courses, "RESULTADOS_DIR", report_dir)
    previos = set(TRABAJOS)
    _soltar_candado()
    yield
    for clave in set(TRABAJOS) - previos:
        TRABAJOS.pop(clave, None)
    _soltar_candado()


def _soltar_candado():
    while courses._BLOQUE_MANUAL.locked():
        courses._BLOQUE_MANUAL.release()


def _cliente():
    cliente = TestClient(app)
    cliente.cookies.set(SESION_COOKIE, _firmar_sesion("adminlocal"))
    return cliente


def _sembrar(fila=6, nombre="Lectura guía", curso="Contabilidad I", completo=True):
    actividad = {
        "curso": curso,
        "programa": "Administración de Empresas",
        "hoja": "Curso A",
        "fila_excel": fila,
        "semana": "Semana 2",
        "unidad": "Unidad 1",
        "nombre": nombre,
        "categoria_prizma": "OVI",
        "tipo_recurso": "PDF descargable",
        "tipo_archivo": "PDF",
    }
    if not completo:
        actividad = {
            "curso": curso,
            "programa": "Administración de Empresas",
            "hoja": "Curso A",
            "fila_excel": fila,
            "nombre": nombre,
        }
    token = USUARIO_ACTUAL.set("adminlocal")
    try:
        course_state.registrar_resultado_actividad(
            actividad,
            "ERROR",
            "ERROR_RECURSO_NO_ENCONTRADO",
        )
    finally:
        USUARIO_ACTUAL.reset(token)
    return course_state._clave_curso(curso, "Administración de Empresas", "adminlocal")


def _post_reintento(cliente, id_curso, clave="Curso A|6", archivo=("guia.pdf", b"%PDF-1.4"), **campos_extra):
    campos = {
        "id_curso": id_curso,
        "clave": clave,
        "usuario_prizma": "cesar",
        "contrasena_prizma": "12345678",
    }
    campos.update(campos_extra)
    archivos = None
    if archivo is not None:
        archivos = {"recurso": (archivo[0], archivo[1], "application/octet-stream")}
    return cliente.post("/cursos/reintentar", data=campos, files=archivos)


def _post_verificar(cliente, id_curso, **campos_extra):
    campos = {
        "id_curso": id_curso,
        "usuario_prizma": "cesar",
        "contrasena_prizma": "12345678",
    }
    campos.update(campos_extra)
    return cliente.post("/cursos/verificar", data=campos)


# ============================================================
# REINTENTO INDIVIDUAL
# ============================================================

def test_reintentar_pide_credenciales_en_lenguaje_humano():
    id_curso = _sembrar()
    html = _post_reintento(
        _cliente(), id_curso, usuario_prizma="",
    ).text
    assert "Falta el acceso a PRIZMA" in html


def test_reintentar_pide_el_archivo_del_recurso():
    id_curso = _sembrar()
    html = _post_reintento(_cliente(), id_curso, archivo=("", b"")).text
    assert "Falta el recurso" in html


def test_reintentar_sin_archivo_no_pasa_el_validador():
    # Sin campo "recurso" tampoco: FastAPI lo entrega como None y el aviso
    # sigue siendo humano (no un 422 en JSON).
    id_curso = _sembrar()
    respuesta = _cliente().post(
        "/cursos/reintentar",
        data={
            "id_curso": id_curso,
            "clave": "Curso A|6",
            "usuario_prizma": "cesar",
            "contrasena_prizma": "12345678",
        },
    )
    assert respuesta.status_code == 200
    assert "Falta el recurso" in respuesta.text


def test_reporte_de_cargue_muestra_reintento_en_filas_con_error(tmp_path):
    from auto_prizma.api.routes.reports import _pagina_reporte_html

    ruta = tmp_path / "fallo.csv"
    ruta.write_text(
        "Fila Excel,Hoja,Programa,Curso,Actividad,Resultado,Observación\n"
        "6,Curso A,Administración,Contabilidad I,Lectura guía,ERROR,ERROR_RECURSO_NO_ENCONTRADO\n",
        encoding="utf-8-sig",
    )
    pagina = _pagina_reporte_html("Reporte", "", str(ruta), "/descargar")
    assert "Reintentar recurso" in pagina
    assert 'action="/cursos/reintentar"' in pagina


def test_reporte_permita_reintentar_sin_adjunto_usando_zip_original(monkeypatch, tmp_path):
    id_curso = _sembrar()
    uploads = tmp_path / "uploads"
    zip_job = uploads / "job-original" / "recursos.zip"
    zip_job.parent.mkdir(parents=True)
    zip_job.write_bytes(b"zip")
    monkeypatch.setattr(courses, "UPLOADS_DIR", str(uploads))
    monkeypatch.setattr(courses, "find_user_record", lambda _id: {"id": _id})
    monkeypatch.setattr(courses.motor_prizma, "crear_indice_recursos", lambda _ruta: [{"nombre": "guia.pdf"}])
    recibido = {}

    def _falso_subir(*args, **kwargs):
        recibido["indice"] = kwargs.get("indice_recursos")
        return {"ok": True, "recurso": "guia.pdf"}

    monkeypatch.setattr(courses.motor_prizma, "subir_actividad_manual", _falso_subir)
    monkeypatch.setattr(courses, "_lanzar_hilo", _lanzar_sincrono)
    respuesta = _cliente().post(
        "/cursos/reintentar",
        data={
            "id_curso": id_curso,
            "clave": "Curso A|6",
            "registro_id": "job-original",
            "usuario_prizma": "cesar",
            "contrasena_prizma": "12345678",
        },
    )

    assert respuesta.status_code == 200
    assert "Reintento en progreso" in respuesta.text
    assert recibido["indice"] == [{"nombre": "guia.pdf"}]


def test_cargue_automatico_omite_recurso_que_ya_esta_montado(monkeypatch, tmp_path):
    actividad = {
        "nombre": "Lectura guía", "fila_excel": 6,
        "categoria_prizma": "OVI", "tipo_archivo": "PDF",
    }
    monkeypatch.setattr(
        engine, "resolver_recurso",
        lambda *args: ({"ruta": str(tmp_path / "guia.pdf"), "nombre_original": "guia.pdf"}, None),
    )
    monkeypatch.setattr(engine, "asegurar_listado", lambda _: True)
    monkeypatch.setattr(engine, "entrar_categoria", lambda *args: True)
    monkeypatch.setattr(engine, "buscar_actividad_correcta", lambda *args: (object(), None))
    monkeypatch.setattr(engine, "abrir_edicion", lambda *args: True)
    monkeypatch.setattr(engine, "archivo_visible", lambda *args: True)
    cancelado = []
    monkeypatch.setattr(engine, "cancelar_edicion_segura", lambda _: cancelado.append(True))

    resultado = engine.procesar_actividad(
        object(), actividad, [], str(tmp_path), [], {"activa": False}, [actividad]
    )

    assert resultado == {"ok": True, "omitido": True, "recurso": "guia.pdf"}
    assert cancelado


def test_reintentar_actividad_no_registrada():
    id_curso = _sembrar()
    html = _post_reintento(_cliente(), id_curso, clave="Curso A|999").text
    assert "no esta registrada" in html


def test_reintentar_registro_viejo_pide_rehacer_la_matriz():
    # Curso sin detalle y sin reporte que lo cubra.
    id_curso = _sembrar(fila=3, nombre="Sin detalle", curso="Curso incompleto", completo=False)
    html = _post_reintento(_cliente(), id_curso, clave="Curso A|3").text
    assert "Sube la matriz otra vez" in html


def test_reintentar_sube_el_archivo_y_marca_la_actividad(
    monkeypatch,
):
    id_curso = _sembrar()
    recibido = {}

    def _falso_subir(usuario, contrasena, actividad, ruta_archivo, carpeta_temp, estado):
        recibido["ruta"] = ruta_archivo
        recibido["usuario"] = usuario
        # El archivo quedo guardado con el nombre que subio el usuario.
        with open(ruta_archivo, "rb") as fh:
            recibido["contenido"] = fh.read()
        estado["mensaje"] = "Subiendo el recurso a: " + actividad["nombre"]
        return {"ok": True, "error": "", "recurso": os.path.basename(ruta_archivo)}

    monkeypatch.setattr(courses.motor_prizma, "subir_actividad_manual", _falso_subir)
    monkeypatch.setattr(courses, "_lanzar_hilo", _lanzar_sincrono)

    respuesta = _post_reintento(_cliente(), id_curso, archivo=("guia.pdf", b"%PDF-1.4"))

    assert respuesta.status_code == 200
    html = respuesta.text
    assert "Reintento en progreso" in html
    assert "__TRABAJO_ID__" not in html, "el id del trabajo debe venir inyectado"

    # El archivo se guardo con el nombre elegido y llego al motor.
    assert recibido["contenido"] == b"%PDF-1.4"
    assert recibido["ruta"].endswith("guia.pdf")
    assert recibido["usuario"] == "cesar"

    # El trabajo quedo terminado y la actividad, subida.
    trabajos = [t for t in TRABAJOS.values() if t.get("tipo") == "reintento"]
    assert len(trabajos) == 1
    assert trabajos[0]["terminado"] is True
    assert trabajos[0]["etapa"] == "completado"
    assert "quedó en PRIZMA" in trabajos[0]["mensaje"]

    item = course_state._cargar_estado()[id_curso]["actividades"]["Curso A|6"]
    assert item["ok_en"], "el reintento exitoso debe marcar la actividad"

    # Reporte CSV descargable desde la pagina de progreso.
    assert os.path.isfile(trabajos[0]["ruta_reporte"])
    with open(trabajos[0]["ruta_reporte"], encoding="utf-8-sig") as fh:
        filas = list(csv.DictReader(fh))
    assert filas and filas[0]["Resultado"] == "OK"

    # El candado quedo libre para el proximo proceso.
    assert not courses._BLOQUE_MANUAL.locked()


def test_reintentar_falla_deja_el_motivo_humano_en_el_trabajo(
    monkeypatch,
):
    id_curso = _sembrar()

    def _falso_subir(*args, **kwargs):
        return {
            "ok": False,
            "error": "ERROR_ACTIVIDAD_NO_ENCONTRADA",
            "recurso": "",
        }

    monkeypatch.setattr(courses.motor_prizma, "subir_actividad_manual", _falso_subir)
    monkeypatch.setattr(courses, "_lanzar_hilo", _lanzar_sincrono)

    _post_reintento(_cliente(), id_curso)

    trabajo = next(t for t in TRABAJOS.values() if t.get("tipo") == "reintento")
    assert trabajo["etapa"] == "error"
    assert "No se pudo subir el recurso: Ninguna actividad" in trabajo["mensaje"]

    item = course_state._cargar_estado()[id_curso]["actividades"]["Curso A|6"]
    assert not item["ok_en"], "un reintento fallido no marca la actividad"
    assert item["codigo"] == "ERROR_ACTIVIDAD_NO_ENCONTRADA"
    assert item["motivo"]  # frase humana, no el codigo


def test_reintentar_no_pasa_si_hay_otro_proceso(monkeypatch):
    id_curso = _sembrar()
    monkeypatch.setattr(courses, "_lanzar_hilo", _lanzar_sincrono)

    # Primer proceso toma el candado...
    _post_reintento(_cliente(), id_curso)
    # ...y el segundo se rechaza mientras este corriendo (aqui el hilo
    # sincrono ya libero el candado, asi que se toma otro camino: forzarlo).
    courses._BLOQUE_MANUAL.acquire()
    try:
        html = _post_reintento(_cliente(), id_curso, clave="Curso A|6").text
        assert "Ya hay un proceso en curso" in html
    finally:
        courses._BLOQUE_MANUAL.release()


# ============================================================
# VERIFICACION DEL CURSO
# ============================================================

def test_verificar_pide_credenciales():
    id_curso = _sembrar()
    html = _post_verificar(_cliente(), id_curso, contrasena_prizma="").text
    assert "Falta el acceso a PRIZMA" in html


def test_verificar_curso_desconocido():
    html = _post_verificar(_cliente(), "no-existe").text
    assert "no tiene actividades registradas" in html


def test_verificar_ajusta_el_estado_a_lo_que_aparece(monkeypatch):
    # Subida que ya no aparece, faltante que si aparece y una sin datos.
    _sembrar(fila=5, nombre="Infografía de costos")
    token = USUARIO_ACTUAL.set("adminlocal")
    try:
        course_state.registrar_resultado_actividad(
            {
                "curso": "Contabilidad I",
                "programa": "Administración de Empresas",
                "hoja": "Curso A",
                "fila_excel": 5,
                "semana": "Semana 1",
                "unidad": "Unidad 1",
                "nombre": "Infografía de costos",
                "categoria_prizma": "OVI",
                "tipo_archivo": "H5P",
            },
            "OK",
            "",
        )
    finally:
        USUARIO_ACTUAL.reset(token)
    id_curso = _sembrar(fila=6, nombre="Lectura guía")

    def _falsa_verificacion(usuario, contrasena, actividades, estado):
        assert [a["nombre"] for _, a in actividades] == [
            "Infografía de costos",
            "Lectura guía",
        ]
        return {
            "ok": True,
            "error": "",
            "resultados": [
                {
                    "clave": "Curso A|5",
                    "nombre": "Infografía de costos",
                    "verificacion": "no_esta",
                    "detalle": "Ninguna actividad del curso coincide.",
                },
                {
                    "clave": "Curso A|6",
                    "nombre": "Lectura guía",
                    "verificacion": "existe",
                    "detalle": "Aparece en PRIZMA.",
                },
            ],
        }

    monkeypatch.setattr(courses.motor_prizma, "verificar_actividades_prizma", _falsa_verificacion)
    monkeypatch.setattr(courses, "_lanzar_hilo", _lanzar_sincrono)

    respuesta = _post_verificar(_cliente(), id_curso)

    assert respuesta.status_code == 200
    html = respuesta.text
    assert "Verificación en progreso" in html
    assert "__TRABAJO_ID__" not in html

    trabajo = next(t for t in TRABAJOS.values() if t.get("tipo") == "verificacion")
    assert trabajo["terminado"] is True
    assert "1 de 2 actividades aparecen en PRIZMA" in trabajo["mensaje"]
    assert "1 no aparecen" in trabajo["mensaje"]

    # Estado: la que estaba subida y no aparece volvio a faltar; la otra
    # sigue faltando pero con constancia de que si aparece.
    curso = course_state.resumen_cursos()[0]
    faltantes = {i["nombre"]: i for i in curso["detalle_faltantes"]}
    assert set(faltantes) == {"Infografía de costos", "Lectura guía"}
    assert faltantes["Infografía de costos"]["codigo"] == "ERROR_NO_ESTA_EN_PRIZMA"
    assert faltantes["Lectura guía"]["verificacion"] == "existe"

    # Reporte CSV con lo que encontro.
    assert os.path.isfile(trabajo["ruta_reporte"])
    with open(trabajo["ruta_reporte"], encoding="utf-8-sig") as fh:
        filas = list(csv.DictReader(fh))
    assert [f["Verificación"] for f in filas] == [
        "No aparece en PRIZMA",
        "Aparece en PRIZMA",
    ]

    assert not courses._BLOQUE_MANUAL.locked()


def test_verificar_informa_los_registros_sin_datos(monkeypatch):
    id_curso = _sembrar(fila=4, nombre="Sin detalle", curso="Curso incompleto", completo=False)

    def _falsa_verificacion(usuario, contrasena, actividades, estado):
        return {"ok": True, "error": "", "resultados": []}

    monkeypatch.setattr(courses.motor_prizma, "verificar_actividades_prizma", _falsa_verificacion)
    monkeypatch.setattr(courses, "_lanzar_hilo", _lanzar_sincrono)

    html = _post_verificar(_cliente(), id_curso).text

    assert "Sin datos para verificar" in html
    assert "Sube la matriz otra vez" in html
    # No se tomo el candado ni se creo trabajo.
    assert not courses._BLOQUE_MANUAL.locked()
    assert not [t for t in TRABAJOS.values() if t.get("tipo") == "verificacion"]


def test_verificar_falla_de_login_se_explica_en_humano(monkeypatch):
    id_curso = _sembrar()

    def _falsa_verificacion(usuario, contrasena, actividades, estado):
        return {
            "ok": False,
            "error": "ERROR_LOGIN_PRIZMA: intento",
            "resultados": [],
        }

    monkeypatch.setattr(courses.motor_prizma, "verificar_actividades_prizma", _falsa_verificacion)
    monkeypatch.setattr(courses, "_lanzar_hilo", _lanzar_sincrono)

    _post_verificar(_cliente(), id_curso)

    trabajo = next(t for t in TRABAJOS.values() if t.get("tipo") == "verificacion")
    assert trabajo["terminado"] is True
    assert "no aceptó el usuario o la contraseña" in trabajo["mensaje"]
    assert not courses._BLOQUE_MANUAL.locked()
