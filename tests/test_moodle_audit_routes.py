"""Pruebas de las rutas de la auditoria de cursos de Moodle.

Solo funcionan desde la instancia local (como todo Moodle): el formulario
abre un trabajo que recorre el curso en el navegador visible y deja su
reporte descargable por su dueño.
"""

import json
import os
import time

from fastapi.testclient import TestClient

from main import app
from auto_prizma.automation.moodle import client as cliente_moodle
from auto_prizma.api.routes import moodle_audit as rutas
from auto_prizma.services import moodle_audit
from auto_prizma.services.auth import SESION_COOKIE, _firmar_sesion


CURSO = "https://prizma.americana.edu.co/course/view.php?id=42"


class _ClienteListo:
    """Curso con un solo recurso que renderiza bien."""

    def list_weeks(self):
        return [{"nombre": "Semana 1", "url": CURSO + "&section=1", "seccion": "1"}]

    def open_week_url(self, url, nombre=""):
        return None

    def list_week_activities(self):
        return [{
            "id": "module-1",
            "titulo": "Lectura guía",
            "url": CURSO + "&a=1",
            "tipo": "page",
            "semana": "Semana 1",
        }]

    def audit_activity(self, url):
        return {
            "encabezados": ["Lectura guía"],
            "texto_cuerpo": "Lectura guía contenido de la pagina",
            "h5p": {"presente": False},
            "pdf": {"presente": False},
        }

    def fetch_bytes(self, url, tope=None):
        raise RuntimeError("no esperado")

    def close(self):
        return None


def _cliente():
    cliente = TestClient(app)
    cliente.cookies.set(SESION_COOKIE, _firmar_sesion("adminlocal"))
    return cliente


def _aislar(monkeypatch, tmp_path, sincrono=True):
    monkeypatch.setattr(rutas, "_request_is_local", lambda request: True)
    monkeypatch.setattr(moodle_audit, "DATA_DIR", str(tmp_path))
    if sincrono:
        monkeypatch.setattr(
            moodle_audit, "_iniciar_hilo",
            lambda job: moodle_audit._run_moodle_audit(job),
        )
    else:
        monkeypatch.setattr(moodle_audit, "_iniciar_hilo", lambda job: None)
    opciones_launch = []
    monkeypatch.setattr(
        cliente_moodle.MoodleClient,
        "launch",
        lambda url, perfil, **kwargs: opciones_launch.append((url, kwargs)) or _ClienteListo(),
    )
    for trabajo_id in list(moodle_audit.MOODLE_AUDIT_JOBS):
        moodle_audit.MOODLE_AUDIT_JOBS.pop(trabajo_id, None)
    return opciones_launch


def test_formulario_y_puerta_local(monkeypatch, tmp_path):
    _aislar(monkeypatch, tmp_path)

    pagina = _cliente().get("/moodle-auditor-curso")
    assert pagina.status_code == 200
    assert "Auditar curso en Moodle" in pagina.text
    assert 'name="course_url"' in pagina.text
    assert 'name="matriz"' in pagina.text
    assert "No adjuntes el syllabus" in pagina.text
    assert "auditoria-matriz-drop" in pagina.text
    assert "Seleccionar archivo" in pagina.text
    assert "align-items: start" in pagina.text
    assert "grid-template-columns:36px minmax(0,1fr) auto" in pagina.text
    assert 'name="usuario"' not in pagina.text
    assert 'name="contrasena"' not in pagina.text
    assert "Chromium visible" in pagina.text
    assert 'href="/moodle-auditor-curso" aria-current="page"' in pagina.text

    monkeypatch.setattr(rutas, "_request_is_local", lambda request: False)
    denegado = _cliente().get("/moodle-auditor-curso")
    assert denegado.status_code == 403
    assert "solo está disponible desde una instancia local" in denegado.text


def test_iniciar_deja_reporte_descargable(monkeypatch, tmp_path):
    _aislar(monkeypatch, tmp_path)

    arranque = _cliente().post(
        "/moodle-auditor-curso/iniciar",
        data={"course_url": CURSO},
        follow_redirects=False,
    )
    assert arranque.status_code == 303

    trabajo = next(iter(moodle_audit.MOODLE_AUDIT_JOBS.values()))
    assert trabajo["finished"] is True
    assert trabajo["status"] == "completed"
    assert trabajo.get("_login_credentials") is None

    pagina = _cliente().get("/moodle-auditor-curso")
    assert "Auditoría del curso terminada" in pagina.text
    assert "Lectura guía" in pagina.text
    assert "Descargar CSV" in pagina.text

    descarga = _cliente().get(
        "/moodle-auditor-curso/" + trabajo["id"] + "/reporte?formato=csv"
    )
    assert descarga.status_code == 200
    assert "Lectura guía" in descarga.text

    estado = _cliente().get("/moodle-auditor-curso/" + trabajo["id"] + "/estado")
    assert estado.status_code == 200
    datos = estado.json()
    assert datos["finished"] is True
    assert datos["summary"]["ok"] == 1


def test_auditoria_abre_enlace_y_usa_login_manual_sin_editar(monkeypatch, tmp_path):
    opciones_launch = _aislar(monkeypatch, tmp_path)
    respuesta = _cliente().post(
        "/moodle-auditor-curso/iniciar", data={"course_url": CURSO},
        follow_redirects=False,
    )

    assert respuesta.status_code == 303
    assert opciones_launch[0][0] == CURSO
    assert opciones_launch[0][1]["enable_edit_mode"] is False


def test_enlace_invalido_muestra_error_en_la_pagina(monkeypatch, tmp_path):
    _aislar(monkeypatch, tmp_path, sincrono=False)

    respuesta = _cliente().post(
        "/moodle-auditor-curso/iniciar",
        data={"course_url": "https://ejemplo.com/curso"},
    )

    assert respuesta.status_code == 400
    assert "ID numérico" in respuesta.text


def test_formulario_rechaza_matriz_con_extension_no_admitida(monkeypatch, tmp_path):
    _aislar(monkeypatch, tmp_path, sincrono=False)

    respuesta = _cliente().post(
        "/moodle-auditor-curso/iniciar",
        data={"course_url": CURSO},
        files={"matriz": ("syllabus.docx", b"no syllabus")},
    )

    assert respuesta.status_code == 400
    assert "CSV o XLSX" in respuesta.text


def test_cancelar_trabajo_en_curso(monkeypatch, tmp_path):
    _aislar(monkeypatch, tmp_path, sincrono=False)

    _cliente().post("/moodle-auditor-curso/iniciar", data={"course_url": CURSO})
    trabajo = next(iter(moodle_audit.MOODLE_AUDIT_JOBS.values()))

    cancelado = _cliente().post("/moodle-auditor-curso/" + trabajo["id"] + "/cancelar")
    assert cancelado.status_code == 200
    assert cancelado.json()["cancel_requested"] is True

    otra_vez = _cliente().post("/moodle-auditor-curso/" + trabajo["id"] + "/cancelar")
    assert otra_vez.status_code == 200


def test_estado_y_reporte_se_aislan_por_persona(monkeypatch, tmp_path):
    _aislar(monkeypatch, tmp_path, sincrono=False)
    _cliente().post("/moodle-auditor-curso/iniciar", data={"course_url": CURSO})
    trabajo = next(iter(moodle_audit.MOODLE_AUDIT_JOBS.values()))

    # Otra persona en el mismo equipo: sus rutas no ven el trabajo ajeno.
    monkeypatch.setattr(rutas, "_owner", lambda: "otra-persona")

    assert _cliente().get("/moodle-auditor-curso/" + trabajo["id"] + "/estado").status_code == 404
    assert _cliente().get("/moodle-auditor-curso/" + trabajo["id"] + "/reporte").status_code == 404
    assert _cliente().post("/moodle-auditor-curso/" + trabajo["id"] + "/cancelar").status_code == 404
    assert _cliente().get("/moodle-auditor-curso").status_code == 200


def test_reportes_de_auditoria_tambien_expiran(monkeypatch, tmp_path):
    viejo = "moodle-auditoria-20261001T120000Z-viejo"
    nuevo = "moodle-auditoria-20261028T120000Z-nuevo"
    for base in (viejo, nuevo):
        (tmp_path / (base + ".json")).write_text(json.dumps({"summary": {}}), encoding="utf-8")
        (tmp_path / (base + ".csv")).write_text("Recurso\nOK\n", encoding="utf-8")
    antiguo = time.time() - 16 * 24 * 60 * 60
    for extension in (".json", ".csv"):
        os.utime(tmp_path / (viejo + extension), (antiguo, antiguo))

    from auto_prizma.api.routes.moodle_resources import _limpiar_reportes_moodle

    _limpiar_reportes_moodle(str(tmp_path))

    assert not (tmp_path / (viejo + ".json")).exists()
    assert not (tmp_path / (viejo + ".csv")).exists()
    assert (tmp_path / (nuevo + ".json")).exists()
    assert (tmp_path / (nuevo + ".csv")).exists()
