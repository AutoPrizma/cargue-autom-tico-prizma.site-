"""Pruebas de la auditoria profunda de curso PRIZMA (/auditor-curso).

La auditoria no usa matriz, CSV ni syllabus: entra al curso publicado con
credenciales (headless, como el cargue), recorre las pestañas OVI, OVA y
Retos, y abre cada actividad para validar su recurso. Aqui se prueba el
camino web (formulario, trabajo, reporte CSV) y la lectura del listado.
"""

import csv
import os

import pytest
from fastapi.testclient import TestClient

from main import app
from auto_prizma.api.routes import course_audit
from auto_prizma.automation.prizma import engine
from auto_prizma.services.auth import SESION_COOKIE, _firmar_sesion
from auto_prizma.services.upload_jobs import TRABAJOS


def _ejecutar_en_el_momento(target, args):
    """En vez de un hilo real, corre la auditoria en el momento."""
    target(*args)


@pytest.fixture(autouse=True)
def limpio(monkeypatch, tmp_path):
    report_dir = str(tmp_path / "reportes")
    os.makedirs(report_dir, exist_ok=True)
    monkeypatch.setattr(course_audit, "RESULTADOS_DIR", report_dir)
    monkeypatch.setattr(course_audit, "_lanzar_hilo", _ejecutar_en_el_momento)
    previos = set(TRABAJOS)
    _soltar_candado()
    yield
    for trabajo_id in set(TRABAJOS) - previos:
        TRABAJOS.pop(trabajo_id, None)
    _soltar_candado()


def _soltar_candado():
    while course_audit._BLOQUE_AUDITORIA.locked():
        course_audit._BLOQUE_AUDITORIA.release()


def _cliente():
    cliente = TestClient(app)
    cliente.cookies.set(SESION_COOKIE, _firmar_sesion("adminlocal"))
    return cliente


def _datos_formulario(**cambios):
    datos = {
        "usuario_prizma": "yo",
        "contrasena_prizma": "secreta",
        "linea_academica": "V1130 11301 30S01 COMPETENCIAS MATEMÁTICAS I",
        "nivel_pensum": "1",
        "facultad": "",
        "recordar_credenciales": "1",
        "modo_navegador": "segundo_plano",
    }
    datos.update(cambios)
    return datos


def _resultados_ejemplo():
    return [
        {
            "categoria": "OVI", "nombre": "Lectura guía", "estado": "ok",
            "tipo": "PDF", "archivo": "Lectura guia.pdf", "titulo_interno": "",
            "coincide": None, "detalle": "PDF con 3 hojas y contenido visible.",
        },
        {
            "categoria": "OVA", "nombre": "Video avatar", "estado": "revisar",
            "tipo": "H5P", "archivo": "Video avatar.h5p",
            "titulo_interno": "Título de relleno", "coincide": False,
            "detalle": "REVISAR: el título del H5P no coincide con el curso.",
        },
        {
            "categoria": "CHALLENGE", "nombre": "Reto final", "estado": "sin_recurso",
            "tipo": "", "archivo": "", "titulo_interno": "", "coincide": None,
            "detalle": "La actividad no tiene archivo en el campo Recurso.",
        },
    ]


def test_pagina_trae_formulario_y_pestana_activa():
    course_audit._guardar_credenciales_prizma(
        "adminlocal", {"usuario": "usuario-recordado", "recordar": True}
    )
    pagina = _cliente().get("/auditor-curso")

    assert pagina.status_code == 200
    assert "Auditar curso en PRIZMA" in pagina.text
    assert 'name="usuario_prizma"' in pagina.text
    assert 'name="contrasena_prizma"' in pagina.text
    assert 'name="linea_academica"' in pagina.text
    assert 'name="nivel_pensum"' in pagina.text
    assert 'name="facultad"' in pagina.text
    assert 'name="recordar_credenciales"' in pagina.text
    assert 'value="usuario-recordado"' in pagina.text
    assert 'name="recordar_credenciales" value="1" checked' in pagina.text
    assert 'name="modo_navegador"' in pagina.text
    assert "Visual (ventana Chromium)" in pagina.text
    assert 'class="auditoria-recordar"' in pagina.text
    assert "Vista previa" in pagina.text
    assert 'action="/auditor-curso"' in pagina.text
    assert 'href="/auditor-curso" aria-current="page"' in pagina.text


def test_post_sin_credenciales_pide_el_acceso(monkeypatch):
    respuesta = _cliente().post(
        "/auditor-curso", data=_datos_formulario(usuario_prizma="", contrasena_prizma="")
    )

    assert respuesta.status_code == 400
    assert "usuario y la contraseña" in respuesta.text


def test_post_exige_datos_academicos_y_nivel():
    sin_linea = _cliente().post(
        "/auditor-curso", data=_datos_formulario(linea_academica="")
    )
    assert sin_linea.status_code == 400
    assert "código de programa" in sin_linea.text

    sin_nivel = _cliente().post(
        "/auditor-curso", data=_datos_formulario(nivel_pensum="")
    )
    assert sin_nivel.status_code == 400
    assert "nivel de pensum" in sin_nivel.text


def test_auditoria_guarda_solo_usuario_si_se_marca_recordar(monkeypatch):
    guardados = []
    monkeypatch.setattr(
        course_audit, "_guardar_credenciales_prizma",
        lambda owner, creds: guardados.append((owner, creds)),
    )
    monkeypatch.setattr(
        course_audit.motor_prizma, "auditar_curso_prizma",
        lambda usuario, contrasena, curso, estado: {
            "ok": True, "error": "", "resultados": [],
        },
    )

    _cliente().post("/auditor-curso", data=_datos_formulario())

    assert guardados == [("adminlocal", {"usuario": "yo", "recordar": True})]


def test_auditoria_borra_usuario_recordado_si_se_desmarca(monkeypatch):
    guardados = []
    monkeypatch.setattr(
        course_audit, "_guardar_credenciales_prizma",
        lambda owner, creds: guardados.append((owner, creds)),
    )
    monkeypatch.setattr(
        course_audit.motor_prizma, "auditar_curso_prizma",
        lambda usuario, contrasena, curso, estado: {
            "ok": True, "error": "", "resultados": [],
        },
    )

    _cliente().post(
        "/auditor-curso", data=_datos_formulario(recordar_credenciales="")
    )

    assert guardados == [("adminlocal", {"usuario": "", "recordar": False})]


def test_modo_visual_se_envia_al_motor(monkeypatch):
    cursos = []
    monkeypatch.setattr(
        course_audit.motor_prizma, "auditar_curso_prizma",
        lambda usuario, contrasena, curso, estado: (
            cursos.append(curso) or {"ok": True, "error": "", "resultados": []}
        ),
    )

    respuesta = _cliente().post(
        "/auditor-curso", data=_datos_formulario(modo_navegador="visual")
    )

    assert respuesta.status_code == 200
    assert cursos[0]["modo_navegador"] == "visual"


def test_auditoria_completa_escribe_reporte_y_estado(monkeypatch):
    # La identidad confiable viene de request.state; no de un contextvar que
    # puede perderse entre el middleware async y el endpoint sync.
    monkeypatch.setattr(course_audit, "_usuario_actual", lambda: "identidad-equivocada")
    monkeypatch.setattr(
        course_audit.motor_prizma, "auditar_curso_prizma",
        lambda usuario, contrasena, curso, estado: {
            "ok": True, "error": "", "resultados": _resultados_ejemplo(),
        },
    )

    cliente = _cliente()
    respuesta = cliente.post(
        "/auditor-curso",
        data=_datos_formulario(),
    )

    assert respuesta.status_code == 200
    assert "Auditoría de curso en progreso" in respuesta.text

    trabajo = next(
        TRABAJOS[trabajo_id]
        for trabajo_id in TRABAJOS
        if TRABAJOS[trabajo_id].get("tipo") == "auditor-curso"
    )
    assert f'data-estado-url="/auditor-curso/{trabajo["id"]}/estado"' in respuesta.text
    estado_http = cliente.get(f'/auditor-curso/{trabajo["id"]}/estado')
    assert estado_http.status_code == 200
    assert estado_http.json()["mensaje"] == trabajo["mensaje"]
    assert estado_http.json()["procesadas"] == 3
    assert trabajo["etapa"] == "completado"
    assert trabajo["terminado"] is True
    assert trabajo["total"] == 3
    assert trabajo["exitosas"] == 1
    assert trabajo["errores"] == 2
    assert "1 de 3" in trabajo["mensaje"]
    assert [fila["estado"] for fila in trabajo["detalle_actividades"]] == ["ok", "error", "error"]

    assert os.path.isfile(trabajo["ruta_reporte"])
    assert os.path.basename(trabajo["ruta_reporte"]).startswith("Auditoria curso -")
    with open(trabajo["ruta_reporte"], encoding="utf-8-sig") as fh:
        filas = list(csv.reader(fh))
    assert filas[0] == [
        "Pestaña", "Actividad", "Tipo", "Estado",
        "Título interno", "Coincide con el curso", "Detalle",
    ]
    assert filas[1][0] == "OVI"
    assert filas[1][3] == "Completo"
    assert filas[2][3] == "Revisar"
    assert filas[2][5] == "No"
    assert filas[3][3] == "Sin recurso"

    assert not course_audit._BLOQUE_AUDITORIA.locked()


def test_auditoria_cancelada_libera_el_candado(monkeypatch):
    def cancelada(usuario, contrasena, curso, estado):
        return {"ok": False, "error": "ERROR_CANCELADO", "resultados": []}

    monkeypatch.setattr(course_audit.motor_prizma, "auditar_curso_prizma", cancelada)

    _cliente().post(
        "/auditor-curso",
        data=_datos_formulario(),
    )

    trabajo = next(iter(TRABAJOS.values()))
    assert trabajo["etapa"] == "cancelado"
    assert not course_audit._BLOQUE_AUDITORIA.locked()


def test_fallo_de_login_se_explica_en_lenguaje_humano(monkeypatch):
    def fallo(usuario, contrasena, curso, estado):
        return {
            "ok": False,
            "error": "ERROR_LOGIN_PRIZMA: credenciales rechazadas",
            "resultados": [],
        }

    monkeypatch.setattr(course_audit.motor_prizma, "auditar_curso_prizma", fallo)

    _cliente().post(
        "/auditor-curso",
        data=_datos_formulario(),
    )

    trabajo = next(iter(TRABAJOS.values()))
    assert trabajo["etapa"] == "error"
    assert "PRIZMA" in trabajo["mensaje"]
    assert not course_audit._BLOQUE_AUDITORIA.locked()


def test_curso_sin_actividades_lo_dice(monkeypatch):
    monkeypatch.setattr(
        course_audit.motor_prizma, "auditar_curso_prizma",
        lambda usuario, contrasena, curso, estado: {"ok": True, "error": "", "resultados": []},
    )

    _cliente().post(
        "/auditor-curso",
        data=_datos_formulario(),
    )

    trabajo = next(iter(TRABAJOS.values()))
    assert trabajo["etapa"] == "completado"
    assert "no muestra actividades" in trabajo["mensaje"]


def test_solo_una_auditoria_a_la_vez(monkeypatch):
    course_audit._BLOQUE_AUDITORIA.acquire()

    try:
        respuesta = _cliente().post(
            "/auditor-curso",
            data=_datos_formulario(),
        )
    finally:
        course_audit._BLOQUE_AUDITORIA.release()

    assert respuesta.status_code == 400
    assert "Ya hay una auditoría" in respuesta.text


def test_enumerar_actividades_curso_lee_nombres_del_listado():
    class _PaginaFalsa:
        def evaluate(self, script):
            assert "prizmaScanId" in script
            return [
                {"id": "scan-a", "texto": "OVI\nLectura guía\nSemana 2\n"},
                {"id": "scan-b", "texto": "OVI\nVideo avatar\nSemana 3\n"},
                {"id": "scan-c", "texto": "OVI"},
            ]

    filas = engine.enumerar_actividades_curso(_PaginaFalsa())

    assert filas == [
        {"scan_id": "scan-a", "nombre": "Lectura guía"},
        {"scan_id": "scan-b", "nombre": "Video avatar"},
    ]


def test_enumerar_sin_pagina_no_explota():
    class _PaginaRota:
        def evaluate(self, script):
            raise RuntimeError("pestaña cerrada")

    assert engine.enumerar_actividades_curso(_PaginaRota()) == []


def test_navegacion_programas_adopta_la_pestana_que_abre_prizma():
    class _Pagina:
        def __init__(self, nombre):
            self.nombre = nombre
            self.context = None
            self.cargada = False

        def is_closed(self):
            return False

        def wait_for_load_state(self, estado, timeout):
            assert estado == "domcontentloaded"
            self.cargada = True

    original = _Pagina("inicio")
    nueva = _Pagina("programas")

    class _Contexto:
        pages = [original, nueva]

    original.context = nueva.context = _Contexto()

    pagina = engine._adoptar_pestana_abierta(original, [original])

    assert pagina is nueva
    assert nueva.cargada is True


def test_selector_activa_pestana_programa_y_no_facultad():
    class _Pestana:
        def __init__(self):
            self.clicks = 0

        def is_visible(self):
            return True

        def click(self, **kwargs):
            self.clicks += 1

    class _ListaPestanas:
        def __init__(self, pestaña):
            self.pestaña = pestaña

        def filter(self, has_text):
            assert has_text.search("Programa")
            assert has_text.search("Programas")
            assert not has_text.search("Facultad")
            return self

        def count(self):
            return 1

        def nth(self, indice):
            return self.pestaña

    class _Pagina:
        def __init__(self):
            self.pestaña = _Pestana()

        def locator(self, selector):
            assert selector == "label.tab"
            return _ListaPestanas(self.pestaña)

        def wait_for_timeout(self, tiempo):
            assert tiempo == 800

    pagina = _Pagina()

    assert engine._seleccionar_pestana_programa_prizma(pagina) is True
    assert pagina.pestaña.clicks == 1


def test_encontrar_fila_escaneada_devuelve_none_si_desaparecio():
    class _LocatorFalso:
        first = property(lambda self: self)

        def wait_for(self, **kwargs):
            raise RuntimeError("ya no está")

    class _PaginaFalsa:
        def locator(self, selector):
            assert "data-prizma-scan-id" in selector
            return _LocatorFalso()

    assert engine.encontrar_fila_escaneada(_PaginaFalsa(), "scan-x") is None
    assert engine.encontrar_fila_escaneada(_PaginaFalsa(), "") is None


# ------------------------------------------------------------
# auditar_actividad_curso: apertura, descarga y validacion
# ------------------------------------------------------------


def _h5p_bytes(titulo):
    import io as _io
    import json as _json
    import zipfile as _zipfile

    buffer = _io.BytesIO()
    with _zipfile.ZipFile(buffer, "w") as paquete:
        paquete.writestr("h5p.json", _json.dumps({"title": titulo, "mainLibrary": "H5P.Book"}))
        paquete.writestr("content/content.json", _json.dumps({"title": titulo}))
        paquete.writestr("libraries/H5P.Book-1.0/library.json", "{}")
    return buffer.getvalue()


class _BotonDescarga:
    def __init__(self):
        self.clicks = 0

    def click(self, timeout=None):
        self.clicks += 1


class _Botones:
    def __init__(self, boton):
        self.first = boton

    def count(self):
        return 1


class _TarjetaRecurso:
    def __init__(self, boton):
        self._boton = boton

    def locator(self, selector):
        assert selector == "button"
        return _Botones(self._boton)


class _PaginaAuditable:
    """Falsa pagina de edicion: solo el campo Recurso y su boton de descarga."""

    def __init__(self, nombre_archivo, bytes_descarga=None, descarga_rota=False):
        self.nombre_archivo = nombre_archivo
        self.bytes_descarga = bytes_descarga
        self.descarga_rota = descarga_rota
        self.boton = _BotonDescarga()
        self.ruta_guardada = ""

    def locator(self, selector):
        return _TarjetaRecurso(self.boton)

    def expect_download(self, timeout=None):
        pagina = self

        class _Contexto:
            def __enter__(self):
                if pagina.descarga_rota:
                    raise RuntimeError("download blocked")
                return self

            def __exit__(self, *exc):
                return False

            @property
            def value(self):
                class _Descarga:
                    def save_as(_self, ruta):
                        pagina.ruta_guardada = ruta
                        with open(ruta, "wb") as fh:
                            fh.write(pagina.bytes_descarga or b"")

                return _Descarga()

        return _Contexto()


def _auditar_con(monkeypatch, pagina, nombre_actividad):
    abiertas = []
    canceladas = []
    monkeypatch.setattr(engine, "abrir_edicion", lambda p, fila: abiertas.append(True) or True)
    monkeypatch.setattr(engine, "archivo_en_recurso", lambda p: pagina.nombre_archivo)
    monkeypatch.setattr(engine, "cancelar_edicion_segura", lambda p: canceladas.append(True))
    veredicto = engine.auditar_actividad_curso(pagina, object(), nombre_actividad)
    return veredicto, abiertas, canceladas


def test_auditar_actividad_h5p_con_titulo_correcto(monkeypatch):
    pagina = _PaginaAuditable("Video avatar.h5p", _h5p_bytes("Video avatar de bienvenida"))

    veredicto, abiertas, canceladas = _auditar_con(
        monkeypatch, pagina, "Video avatar de bienvenida"
    )

    assert veredicto["estado"] == "ok"
    assert veredicto["tipo"] == "H5P"
    assert veredicto["coincide"] is True
    assert abiertas and canceladas
    assert pagina.boton.clicks == 1
    assert pagina.ruta_guardada and not os.path.exists(pagina.ruta_guardada)


def test_auditar_actividad_sin_archivo_queda_como_sin_recurso(monkeypatch):
    pagina = _PaginaAuditable("")

    veredicto, _abiertas, canceladas = _auditar_con(monkeypatch, pagina, "Reto final")

    assert veredicto["estado"] == "sin_recurso"
    assert canceladas


def test_auditar_actividad_con_descarga_bloqueada(monkeypatch):
    pagina = _PaginaAuditable("Lectura guia.pdf", descarga_rota=True)

    veredicto, _abiertas, _canceladas = _auditar_con(monkeypatch, pagina, "Lectura guía")

    assert veredicto["estado"] == "no_se_pudo"
    assert "no permitió descargarlo" in veredicto["detalle"]
    assert veredicto["archivo"] == "Lectura guia.pdf"


def test_auditar_actividad_que_no_se_puede_abrir(monkeypatch):
    monkeypatch.setattr(engine, "abrir_edicion", lambda p, fila: False)
    monkeypatch.setattr(engine, "cancelar_edicion_segura", lambda p: None)

    veredicto = engine.auditar_actividad_curso(object(), object(), "Lectura guía")

    assert veredicto["estado"] == "no_se_pudo"
    assert "No se pudo abrir la actividad" in veredicto["detalle"]
