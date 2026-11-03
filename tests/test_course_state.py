"""Pruebas de la traduccion de errores y del estado acumulado por curso.

Cubren:
- error_messages: codigos ERROR_* a frases humanas (y textos libres intactos).
- course_state: acumulacion entre cargues, preseleccion de faltantes y /cursos.
- /analizar: pre-marcado de las actividades que faltaban (reintento).
"""

import json
import pathlib
import re
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from main import app
from auto_prizma.core.config import ZONA_HORARIA_COLOMBIA
from auto_prizma.core.storage import write_json_atomic
from auto_prizma.services import course_state
from auto_prizma.services.auth import SESION_COOKIE, USUARIO_ACTUAL, _firmar_sesion
from auto_prizma.services.error_messages import (
    MENSAJES_ERROR,
    es_codigo_error,
    extraer_codigo_error,
    mensaje_error,
)
from auto_prizma.services.upload_jobs import TRABAJOS

RAIZ = pathlib.Path(__file__).resolve().parent.parent


@pytest.fixture(autouse=True)
def estado_limpio(monkeypatch, tmp_path):
    """Aísla los datos de prueba para no tocar el estado local del usuario."""
    monkeypatch.setattr(course_state, "ESTADO_CURSOS_PATH", str(tmp_path / "estado_cursos.json"))
    monkeypatch.setattr(course_state, "RESULTADOS_DIR", str(tmp_path / "reportes"))
    previos = set(TRABAJOS)
    yield
    for clave in set(TRABAJOS) - previos:
        TRABAJOS.pop(clave, None)


def _cliente():
    cliente = TestClient(app, client=("10.0.0.7", 50000))
    cliente.cookies.set(SESION_COOKIE, _firmar_sesion("adminlocal"))
    return cliente


def _sembrar(entradas, usuario_app=None):
    """entradas: [(fila, nombre, resultado, observacion)] del curso fijo."""
    token = USUARIO_ACTUAL.set(usuario_app)
    try:
        for fila, nombre, resultado, observacion in entradas:
            course_state.registrar_resultado_actividad(
                {
                    "curso": "Contabilidad I",
                    "programa": "Administración de Empresas",
                    "hoja": "Curso A",
                    "fila_excel": fila,
                    "nombre": nombre,
                },
                resultado,
                observacion,
            )
    finally:
        USUARIO_ACTUAL.reset(token)


# ============================================================
# MENSAJES DE ERROR
# ============================================================

def test_codigo_conocido_se_traduce_a_espanol():
    assert mensaje_error("ERROR_CURSO_SIN_PLANTILLA") == (
        "El curso no tiene la plantilla precargada en PRIZMA: la actividad no "
        "existe todavía y hay que crearla antes de cargar."
    )
    assert "columna Recurso" in mensaje_error("ERROR_RECURSO_NO_ENCONTRADO")


def test_codigo_desconocido_o_texto_libre_no_se_toca():
    assert mensaje_error("ERROR_INVENTADO") == "ERROR_INVENTADO"
    assert mensaje_error("Timeout 60000ms exceeded") == "Timeout 60000ms exceeded"
    assert mensaje_error("") == ""


def test_extrae_codigo_de_un_texto_con_detalle():
    texto = 'ERROR_PATCH_HTTP_500: respuesta {"detail": "no"}'
    assert extraer_codigo_error(texto) == "ERROR_PATCH_HTTP_"
    assert "PRIZMA rechazó" in mensaje_error(texto)
    assert es_codigo_error(texto)

    assert extraer_codigo_error("algo raro") == ""
    assert not es_codigo_error("algo raro")


def test_todos_los_codigos_del_motor_tienen_traduccion():
    codigos = set()
    for ruta in (RAIZ / "auto_prizma").rglob("*.py"):
        codigos.update(re.findall(r'"(ERROR_[A-Z0-9_]+)"', ruta.read_text(encoding="utf-8")))

    sin_traduccion = sorted(
        codigo
        for codigo in codigos
        if codigo not in MENSAJES_ERROR
        and not codigo.startswith("ERROR_PATCH_HTTP_")  # prefijo variable, ya cubierto
    )
    assert sin_traduccion == [], f"codigos sin mensaje humano: {sin_traduccion}"


# ============================================================
# ESTADO ACUMULADO POR CURSO
# ============================================================

def test_acumula_ok_y_error_entre_cargues():
    _sembrar([
        (5, "Infografía", "OK", ""),
        (6, "Lectura guía", "ERROR", "ERROR_RECURSO_NO_ENCONTRADO"),
        # Reintento fallido de algo ya subido: NO vuelve a contar como faltante.
        (5, "Infografía", "ERROR", "ERROR_BOTON_GUARDAR"),
    ])

    resumen = course_state.resumen_cursos()
    assert len(resumen) == 1
    curso = resumen[0]
    assert (curso["total"], curso["subidas"], curso["faltantes"]) == (2, 1, 1)
    assert curso["curso"] == "Contabilidad I"
    assert curso["programa"] == "Administración de Empresas"

    faltante = curso["detalle_faltantes"][0]
    assert faltante["fila"] == 6
    assert faltante["codigo"] == "ERROR_RECURSO_NO_ENCONTRADO"
    assert "columna Recurso" in faltante["motivo"]  # mensaje humano, no el codigo


def test_preseleccion_solo_marca_faltantes_con_mismo_nombre():
    _sembrar([
        (5, "Infografía de costos", "OK", ""),
        (6, "Lectura guía", "ERROR", "ERROR_RECURSO_NO_ENCONTRADO"),
    ])

    claves, cursos = course_state.preseleccion_faltantes([
        {
            "hoja": "Curso A",
            "curso": "Contabilidad I",
            "actividades": [
                {"fila": 5, "nombre": "Infografía de costos"},  # ya OK: no marcar
                {"fila": 6, "nombre": "Lectura guía"},          # falta: marcar
                {"fila": 7, "nombre": "Nueva"},                 # nunca vista: no marcar
                {"fila": 8, "nombre": "Otra"},                  # no registrada: no marcar
            ],
        }
    ])

    assert claves == [["Curso A", 6]]
    assert cursos == ["Contabilidad I"]


def test_preseleccion_no_marca_si_la_fila_cambio_de_actividad():
    _sembrar([(6, "Lectura guía", "ERROR", "ERROR_RECURSO_NO_ENCONTRADO")])

    claves, _ = course_state.preseleccion_faltantes([
        {
            "hoja": "Curso A",
            "curso": "Contabilidad I",
            "actividades": [{"fila": 6, "nombre": "Otra actividad ahora"}],
        }
    ])

    assert claves == []  # la fila 6 ya no es la misma actividad


def test_claves_faltantes_ignora_filas_de_test():
    _sembrar([
        (6, "Lectura guía", "ERROR", "ERROR_ACTIVIDAD_NO_ENCONTRADA"),
        ("Test 1", "Test Evaluativo: Examen", "ERROR", "ERROR_BOTON_GUARDAR"),
    ])

    claves = course_state.claves_faltantes()
    assert claves == [["Curso A", 6]]  # la fila de test no es reintentable asi


def test_estado_se_persiste_en_disco():
    _sembrar([(6, "Lectura guía", "ERROR", "ERROR_LIMPIANDO_DESCRIPCION")])

    # Recarga desde disco (simula reinicio de la app).
    recargado = course_state._cargar_estado()
    assert recargado, "debio persistir en estado_cursos.json"
    curso = next(iter(recargado.values()))
    item = curso["actividades"]["Curso A|6"]
    assert item["intentos"] == 1
    assert item["codigo"] == "ERROR_LIMPIANDO_DESCRIPCION"
    assert item["motivo"]  # frase humana


def test_estado_de_curso_purga_registros_con_mas_de_15_dias(monkeypatch, tmp_path):
    ruta = tmp_path / "estado_cursos.json"
    monkeypatch.setattr(course_state, "ESTADO_CURSOS_PATH", str(ruta))
    ahora = datetime(2026, 10, 29, tzinfo=ZONA_HORARIA_COLOMBIA)
    monkeypatch.setattr(course_state, "_ahora_colombia", lambda: ahora)
    viejo = (ahora - timedelta(days=16)).isoformat()
    reciente = (ahora - timedelta(days=14)).isoformat()
    write_json_atomic(str(ruta), {
        "curso-viejo": {"curso": "Antiguo", "actualizado": viejo, "actividades": {}},
        "curso-reciente": {"curso": "Vigente", "actualizado": reciente, "actividades": {}},
    })

    estado = course_state._cargar_estado()

    assert list(estado) == ["curso-reciente"]
    assert json.loads(ruta.read_text(encoding="utf-8")) == estado


# ============================================================
# PAGINA /cursos
# ============================================================

def test_pagina_cursos_vacia():
    html = _cliente().get("/cursos").text
    assert "Todavía no hay cargues registrados" in html
    assert 'class="cursos-page"' in html
    assert 'class="icono-tile cursos-vacio-icon"' in html
    assert 'class="workspace-tab activo" href="/cursos" aria-current="page">Cursos' in html
    assert 'class="boton" href="/">Ir a Inicio</a>' in html


def test_pagina_cursos_muestra_faltantes_con_motivo_humano_y_boton():
    _sembrar([
        (5, "Infografía de costos", "OK", ""),
        (6, "Lectura guía", "ERROR", "ERROR_CURSO_SIN_PLANTILLA"),
        (7, "Reto 1", "ERROR", "ERROR_RECURSO_NO_ENCONTRADO"),
    ], usuario_app="adminlocal")

    html = _cliente().get("/cursos").text

    assert "Contabilidad I" in html
    assert "1 de 3" in html
    assert "Reintentar las 2 pendientes" in html
    # Motivos humanos en la tabla de faltantes...
    assert "plantilla precargada" in html
    assert "columna Recurso" in html
    # ...y los codigos originales visibles (chiquitos) para diagnostico.
    assert "ERROR_CURSO_SIN_PLANTILLA" in html
    assert "Ver las 1 ya subidas" in html


def test_pagina_cursos_marca_curso_completo():
    _sembrar([(5, "Infografía de costos", "OK", "")], usuario_app="adminlocal")

    html = _cliente().get("/cursos").text
    assert "Curso completo" in html
    assert "Todas las actividades de este curso ya quedaron en PRIZMA" in html
    assert "actividad(es) pendientes" not in html  # sin banner de pendientes


def test_pagina_cursos_requiere_sesion():
    cliente = TestClient(app, follow_redirects=False)
    assert cliente.get("/cursos").status_code == 303


# ============================================================
# PRE-SELECCION EN /analizar (reintento sin volver a elegir)
# ============================================================

def _matriz_xlsx():
    from openpyxl import Workbook
    import io

    libro = Workbook()
    hoja = libro.active
    hoja.title = "Curso A"
    hoja["A1"] = "Administración de Empresas"
    hoja["A2"] = "Contabilidad I"
    hoja["A4"] = "Semana correspondiente"
    filas = [
        (1, "Unidad 1", None, "Infografía de costos", "OVI", "Infografía", None),
        (1, "Unidad 1", None, "Lectura guía", "OVI", "PDF descargable", None),
    ]
    for numero_fila, fila in enumerate(filas, start=5):
        for columna, valor in enumerate(fila, start=1):
            if valor is not None:
                hoja.cell(row=numero_fila, column=columna, value=valor)
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


def _zip_recursos():
    import io
    import zipfile

    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w") as archivo:
        archivo.writestr("Infografia_de_costos.h5p", b"h5p")
        archivo.writestr("Lectura guía.pdf", b"%PDF")
    return salida.getvalue()


def _inputs_por_fila(html):
    """{fila: (tag_html, marcada?)} de los checkbox de actividades."""
    salida = {}
    for tag in re.findall(r"<input[^>]*class=\"actividad-seleccion\"[^>]*>", html, re.S):
        clave = re.search(r"value=\"([^\"]+)\"", tag)
        if not clave:
            continue
        import html as _html
        import json
        datos = json.loads(_html.unescape(clave.group(1)))
        salida[int(datos[1])] = ("checked" in tag, tag)
    return salida


def test_analizar_pre_marca_solo_las_que_faltaban():
    _sembrar([
        (5, "Infografía de costos", "OK", ""),            # ya subida
        (6, "Lectura guía", "ERROR", "ERROR_RECURSO_NO_ENCONTRADO"),  # falta
    ], usuario_app="adminlocal")

    cliente = _cliente()
    respuesta = cliente.post(
        "/analizar",
            data={"ovi": "1"},
        files={
            "matriz_archivo": ("matriz.xlsx", _matriz_xlsx(), "application/octet-stream"),
            "recursos": ("recursos.zip", _zip_recursos(), "application/zip"),
        },
    )

    assert respuesta.status_code == 200
    html = respuesta.text
    inputs = _inputs_por_fila(html)
    assert inputs[5][0] is False, "la ya subida no debe quedar marcada"
    assert inputs[6][0] is True, "la que falta debe quedar marcada"
    assert "Reintento de cargues anteriores" in html
    assert "Quedaron 1 actividad(es) pendientes" in html


def test_analizar_sin_faltantes_lo_deja_como_antes():
    html = _cliente().post(
        "/analizar",
        data={"ovi": "1"},
        files={
            "matriz_archivo": ("matriz.xlsx", _matriz_xlsx(), "application/octet-stream"),
            "recursos": ("recursos.zip", _zip_recursos(), "application/zip"),
        },
    ).text

    inputs = _inputs_por_fila(html)
    assert inputs and all(marcada for marcada, _ in inputs.values()), (
        "sin historial, todas deben venir marcadas (comportamiento original)"
    )
    assert "Reintento de cargues anteriores" not in html


def test_cargado_y_omitido_cuentan_como_subidas():
    """Regresion: el flujo de Tests escribe 'Cargado'/'Omitido', no 'OK'.

    Ambos significan que el archivo ya esta en PRIZMA; antes se registraban
    como error y /cursos mostraba faltantes falsas. 'Cancelado' si sigue
    contando como pendiente.
    """
    _sembrar([
        (5, "Balance general", "Cargado", ""),
        (6, "Formato APA", "Omitido", "Ya estaba cargado en PRIZMA · se omite para no duplicar"),
        (7, "Portada", "Cancelado", "Detenido por el usuario"),
    ])

    curso = course_state.resumen_cursos()[0]
    assert (curso["total"], curso["subidas"], curso["faltantes"]) == (3, 2, 1)


def test_mensaje_error_conserva_el_detalle_del_motor():
    """El detalle que anexa el motor (archivo pedido, filas repetidas)
    debe llegar al usuario junto con la frase humana."""
    texto = (
        "ERROR_RECURSO_NO_ENCONTRADO: el Excel pide "
        "'PASO A PASO-Secuencia.h5p' pero no está en el ZIP"
    )
    assert extraer_codigo_error(texto) == "ERROR_RECURSO_NO_ENCONTRADO"
    mensaje = mensaje_error(texto)
    assert mensaje.startswith("La fila no tiene recurso")
    assert "PASO A PASO-Secuencia.h5p" in mensaje

    dup = (
        "ERROR_ACTIVIDAD_DUPLICADA: aparece 2 veces en PRIZMA — "
        "«Formulación del problema Semana 3»"
    )
    assert "Semana 3" in mensaje_error(dup)


# ============================================================
# REINTENTO INDIVIDUAL Y VERIFICACION (detalle por actividad)
# ============================================================

def _actividad_completa(fila=6, nombre="Lectura guía"):
    return {
        "curso": "Contabilidad I",
        "programa": "Administración de Empresas",
        "hoja": "Curso A",
        "fila_excel": fila,
        "semana": "Semana 2",
        "unidad": "Unidad 1",
        "nombre": nombre,
        "categoria_prizma": "OVI",
        "tipo_recurso": "PDF descargable",
        "tipo_archivo": "PDF",
        "enlace": "",
    }


def test_registrar_guarda_el_detalle_que_pide_el_reintento():
    course_state.registrar_resultado_actividad(
        _actividad_completa(),
        "ERROR",
        "ERROR_RECURSO_NO_ENCONTRADO",
    )

    item = course_state._cargar_estado()[
        course_state._clave_curso("Contabilidad I", "Administración de Empresas")
    ]["actividades"]["Curso A|6"]

    assert item["categoria"] == "OVI"
    assert item["tipo_archivo"] == "PDF"
    assert item["semana"] == "Semana 2"
    assert item["unidad"] == "Unidad 1"


def test_actividad_para_reintento_reconstruye_la_actividad_del_motor():
    course_state.registrar_resultado_actividad(
        _actividad_completa(),
        "ERROR",
        "ERROR_RECURSO_NO_ENCONTRADO",
    )

    id_curso = course_state._clave_curso("Contabilidad I", "Administración de Empresas")
    actividad, error = course_state.actividad_para_reintento(id_curso, "Curso A|6")

    assert error is None
    assert actividad["nombre"] == "Lectura guía"
    assert actividad["categoria_prizma"] == "OVI"
    assert actividad["tipo_archivo"] == "PDF"
    assert actividad["semana"] == "Semana 2"
    assert actividad["programa"] == "Administración de Empresas"
    assert actividad["fila_excel"] == 6


def test_actividad_para_reintento_completa_registros_viejos_desde_el_reporte():
    """Los registros antiguos no guardaban categoria/tipo: se regeneran del CSV."""
    _sembrar([(6, "Lectura guía", "ERROR", "ERROR_RECURSO_NO_ENCONTRADO")])

    import csv as _csv
    import os as _os

    RESULTADOS_DIR = course_state.RESULTADOS_DIR
    _os.makedirs(RESULTADOS_DIR, exist_ok=True)
    ruta = _os.path.join(RESULTADOS_DIR, "2026-10-01_10-00-00 - Contabilidad I - x.csv")
    with open(ruta, "w", newline="", encoding="utf-8-sig") as fh:
        escritor = _csv.writer(fh)
        escritor.writerow([
            "Fila Excel", "Hoja", "Programa", "Curso", "Semana", "Unidad",
            "Actividad", "Categoría", "Tipo", "Recurso", "Resultado",
            "Observación", "Motivo",
        ])
        escritor.writerow([
            6, "Curso A", "Administración de Empresas", "Contabilidad I",
            "Semana 2", "Unidad 1", "Lectura guía", "OVI", "PDF",
            "Lectura guia.pdf", "ERROR", "ERROR_RECURSO_NO_ENCONTRADO", "",
        ])

    id_curso = course_state._clave_curso("Contabilidad I", "Administración de Empresas")
    actividad, error = course_state.actividad_para_reintento(id_curso, "Curso A|6")

    assert error is None, error
    assert actividad["categoria_prizma"] == "OVI"
    assert actividad["tipo_archivo"] == "PDF"
    assert actividad["semana"] == "Semana 2"

    # Quedo regenerado en el estado: la proxima vez no vuelve a leer el CSV.
    item = course_state._cargar_estado()[id_curso]["actividades"]["Curso A|6"]
    assert item["categoria"] == "OVI"


def test_actividad_para_reintento_sin_datos_pide_rehacer_la_matriz():
    # Fila sin reporte que la cubra (el CSV del test anterior solo trae la 6).
    _sembrar([(8, "Lectura sin detalle", "ERROR", "ERROR_RECURSO_NO_ENCONTRADO")])

    id_curso = course_state._clave_curso("Contabilidad I", "Administración de Empresas")
    actividad, error = course_state.actividad_para_reintento(id_curso, "Curso A|8")

    assert actividad is None
    assert "Sube la matriz otra vez" in error


def test_actividad_para_reintento_no_entrega_cursos_de_otro_usuario():
    course_state.registrar_resultado_actividad(
        _actividad_completa(),
        "ERROR",
        "ERROR_RECURSO_NO_ENCONTRADO",
    )

    id_curso = course_state._clave_curso("Contabilidad I", "Administración de Empresas")
    datos = course_state._cargar_estado()
    datos[id_curso]["usuario_app"] = "otra_persona"
    write_json_atomic(course_state.ESTADO_CURSOS_PATH, datos)

    actividad, error = course_state.actividad_para_reintento(
        id_curso, "Curso A|6", "adminlocal",
    )

    assert actividad is None
    assert "no pertenece" in error


def test_mismo_curso_se_guarda_por_separado_para_cada_usuario():
    for usuario, nombre in (("ana", "Matriz Ana"), ("beto", "Matriz Beto")):
        token = USUARIO_ACTUAL.set(usuario)
        try:
            actividad = _actividad_completa()
            actividad["nombre"] = nombre
            course_state.registrar_resultado_actividad(actividad, "ERROR", "ERROR_RECURSO_NO_ENCONTRADO")
        finally:
            USUARIO_ACTUAL.reset(token)

    ana = course_state.resumen_cursos("ana")
    beto = course_state.resumen_cursos("beto")
    assert len(ana) == len(beto) == 1
    assert ana[0]["detalle_faltantes"][0]["nombre"] == "Matriz Ana"
    assert beto[0]["detalle_faltantes"][0]["nombre"] == "Matriz Beto"
    assert ana[0]["id"] != beto[0]["id"]


def test_actividades_para_verificar_separa_lo_incompleto():
    course_state.registrar_resultado_actividad(
        _actividad_completa(fila=6, nombre="Lectura guía"),
        "OK",
        "",
    )
    _sembrar([(7, "Sin detalle", "ERROR", "ERROR_BOTON_GUARDAR")])

    id_curso = course_state._clave_curso("Contabilidad I", "Administración de Empresas")
    lista, sin_datos, error = course_state.actividades_para_verificar(id_curso)

    assert error is None
    assert [clave for clave, _ in lista] == ["Curso A|6"]
    assert len(sin_datos) == 1
    assert sin_datos[0]["nombre"] == "Sin detalle"
    assert "Sube la matriz otra vez" in sin_datos[0]["motivo"]


def test_marcar_verificacion_baja_a_las_que_no_aparecen():
    course_state.registrar_resultado_actividad(
        _actividad_completa(fila=5, nombre="Infografía de costos"),
        "OK",
        "",
    )
    course_state.registrar_resultado_actividad(
        _actividad_completa(fila=6, nombre="Lectura guía"),
        "ERROR",
        "ERROR_RECURSO_NO_ENCONTRADO",
    )

    id_curso = course_state._clave_curso("Contabilidad I", "Administración de Empresas")
    course_state.marcar_verificacion(
        id_curso,
        [
            # Subida que ya no aparece: vuelve a faltar.
            {"clave": "Curso A|5", "verificacion": "no_esta"},
            # Faltante que si aparece: sigue faltando (el recurso no esta
            # confirmado), pero deja constancia.
            {"clave": "Curso A|6", "verificacion": "existe"},
        ],
    )

    curso = course_state.resumen_cursos()[0]
    # La que estaba subida y no aparece volvio a faltar: ninguna queda como
    # subida y la otra siempre falto.
    assert (curso["total"], curso["subidas"], curso["faltantes"]) == (2, 0, 2)

    faltantes = {i["nombre"]: i for i in curso["detalle_faltantes"]}
    assert faltantes["Infografía de costos"]["motivo"] == (
        "Verificación: la actividad no aparece en PRIZMA."
    )
    assert faltantes["Infografía de costos"]["codigo"] == "ERROR_NO_ESTA_EN_PRIZMA"
    assert faltantes["Lectura guía"]["verificacion"] == "existe"
    # El motivo original del fallo se conserva.
    assert "columna Recurso" in faltantes["Lectura guía"]["motivo"]


def test_pagina_cursos_ofrece_reintento_individual_y_verificacion():
    _sembrar([
        (5, "Infografía de costos", "OK", ""),
        (6, "Lectura guía", "ERROR", "ERROR_RECURSO_NO_ENCONTRADO"),
    ], usuario_app="adminlocal")

    html = _cliente().get("/cursos").text

    # Reintento individual: boton por fila + formulario con archivo y credenciales.
    assert 'data-reintento' in html
    assert 'action="/cursos/reintentar"' in html
    assert 'name="recurso"' in html
    assert 'data-nombre="Lectura guía"' in html
    # Verificacion del curso.
    assert 'data-verificar' in html
    assert 'action="/cursos/verificar"' in html
    assert "Verificar en PRIZMA" in html
    # El formulario arranca oculto (lo abre el boton).
    assert 'id="form-reintento" class="panel form-manual" hidden' in html
