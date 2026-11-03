"""Pruebas del servicio de auditoria de cursos de Moodle.

El servicio abre el curso con un cliente visible (aqui falso), recorre las
semanas, entra a cada recurso, valida los PDF descargables por dentro y
deja el reporte en data/reportes/moodle/<persona>/ con el prefijo
moodle-auditoria-. Un solo trabajo por persona y cancelacion limpia.
"""

import json
import os
import zlib

import pytest

from auto_prizma.automation.moodle import client as cliente_moodle
from auto_prizma.services import moodle_audit


CURSO = "https://prizma.americana.edu.co/course/view.php?id=42"


class _ClienteFalso:
    def __init__(self, semanas=None, recursos=None, sondas=None, pdf_descargable=None):
        self.semanas = semanas if semanas is not None else [
            {"nombre": "Semana 1", "url": CURSO + "&section=1", "seccion": "1"},
        ]
        self.recursos = recursos if recursos is not None else {}
        self.sondas = sondas or {}
        self.pdf_descargable = pdf_descargable
        self.abiertas = []
        self.cerrado = False

    def list_weeks(self):
        return list(self.semanas)

    def open_week_url(self, url, nombre=""):
        self.abiertas.append(nombre or url)

    def list_week_activities(self):
        return list(self.recursos.get(self.abiertas[-1] if self.abiertas else "", []))

    def audit_activity(self, url):
        return dict(self.sondas.get(url, {"error": "Sonda no preparada"}))

    def fetch_bytes(self, url, tope=None):
        if self.pdf_descargable is None:
            raise RuntimeError("El curso respondió 404 al descargar el archivo.")
        return self.pdf_descargable

    def close(self):
        self.cerrado = True


def _pdf_descargable(con_texto=True):
    stream = b"BT /F1 12 Tf (Contenido) Tj ET" if con_texto else b""
    stream = zlib.compress(stream)
    return (
        b"%PDF-1.4\n1 0 obj\n<< /Type /Page >>\nendobj\n"
        b"2 0 obj\n<< /Length " + str(len(stream)).encode() + b" >>\nstream\n"
        + stream + b"\nendstream\nendobj\n"
    )


def _aislar(monkeypatch, tmp_path, sincrono=True):
    monkeypatch.setattr(moodle_audit, "DATA_DIR", str(tmp_path))
    if sincrono:
        monkeypatch.setattr(
            moodle_audit, "_iniciar_hilo",
            lambda job: moodle_audit._run_moodle_audit(job),
        )
    else:
        monkeypatch.setattr(moodle_audit, "_iniciar_hilo", lambda job: None)
    _limpiar()


def _limpiar():
    for trabajo_id in list(moodle_audit.MOODLE_AUDIT_JOBS):
        moodle_audit.MOODLE_AUDIT_JOBS.pop(trabajo_id, None)


def test_auditoria_completa_recorre_semanas_y_deja_reporte(monkeypatch, tmp_path):
    _aislar(monkeypatch, tmp_path)
    cliente = _ClienteFalso(
        semanas=[
            {"nombre": "Semana 1", "url": CURSO + "&section=1", "seccion": "1"},
            {"nombre": "Semana 2", "url": CURSO + "&section=2", "seccion": "2"},
        ],
        recursos={
            "Semana 1": [
                {"id": "module-1", "titulo": "Video avatar de bienvenida", "url": CURSO + "&a=1", "tipo": "h5pactivity", "semana": "Semana 1"},
            ],
            "Semana 2": [
                {"id": "module-2", "titulo": "Lectura guía", "url": CURSO + "&a=2", "tipo": "url", "semana": "Semana 2"},
            ],
        },
        sondas={
            CURSO + "&a=1": {
                "encabezados": ["Video avatar de bienvenida"],
                "texto_cuerpo": "Video avatar Contenido",
                "h5p": {"presente": True, "alto": 500, "texto": "Bienvenidos", "titulo": "Video avatar de bienvenida"},
                "pdf": {"presente": False},
            },
            CURSO + "&a=2": {
                "encabezados": ["Lectura guía"],
                "texto_cuerpo": "Lectura guía descargar",
                "h5p": {"presente": False},
                "pdf": {"presente": True, "embebido": False, "origen": CURSO + "&file=2.pdf"},
            },
        },
        pdf_descargable=_pdf_descargable(),
    )
    monkeypatch.setattr(cliente_moodle.MoodleClient, "launch", lambda url, perfil, **kwargs: cliente)

    trabajo = moodle_audit.start_moodle_audit("ana", CURSO)

    assert trabajo["finished"] is True
    assert trabajo["status"] == "completed"
    assert cliente.abiertas == ["Semana 1", "Semana 2"]
    assert cliente.cerrado is True

    filas = trabajo["results"]
    assert [fila["actividad"] for fila in filas] == ["Video avatar de bienvenida", "Lectura guía"]
    assert filas[0]["estado"] == "ok"
    assert filas[1]["estado"] == "ok"
    assert filas[1]["renderiza"] == "si"

    rutas = trabajo["report_paths"]
    assert os.path.basename(rutas["csvPath"]).startswith("moodle-auditoria-")
    with open(rutas["jsonPath"], encoding="utf-8") as fh:
        reporte = json.load(fh)
    assert reporte["summary"]["ok"] == 2
    with open(rutas["csvPath"], encoding="utf-8") as fh:
        contenido = fh.read()
    assert "Lectura guía" in contenido


def test_timeout_de_recurso_deja_advertencia_y_continua_con_el_siguiente(monkeypatch, tmp_path):
    _aislar(monkeypatch, tmp_path)
    primer_recurso = CURSO + "&a=1"
    segundo_recurso = CURSO + "&a=2"
    cliente = _ClienteFalso(
        recursos={"Semana 1": [
            {"id": "module-1", "titulo": "Lento", "url": primer_recurso, "tipo": "h5pactivity"},
            {"id": "module-2", "titulo": "Siguiente", "url": segundo_recurso, "tipo": "page"},
        ]},
        sondas={
            primer_recurso: {"error": "Moodle no terminó de abrir el recurso en 30 segundos.", "timeout": True},
            segundo_recurso: {"encabezados": ["Siguiente"], "texto_cuerpo": "Contenido",
                              "h5p": {"presente": False}, "pdf": {"presente": False}},
        },
    )
    monkeypatch.setattr(cliente_moodle.MoodleClient, "launch", lambda url, perfil, **kwargs: cliente)

    trabajo = moodle_audit.start_moodle_audit("ana", CURSO)

    assert [fila["estado"] for fila in trabajo["results"]] == ["revisar", "ok"]
    assert "30 segundos" in trabajo["results"][0]["detalle"]


def test_recurso_pdf_descargado_directamente_se_valida_y_queda_completo(monkeypatch, tmp_path):
    _aislar(monkeypatch, tmp_path)
    url = CURSO + "&file=guia.pdf"
    cliente = _ClienteFalso(
        recursos={"Semana 1": [
            {"id": "module-pdf", "titulo": "Guía", "url": url, "tipo": "resource"},
        ]},
        sondas={url: {"download": {
            "filename": "guia.pdf", "bytes": _pdf_descargable(),
        }}},
    )
    monkeypatch.setattr(cliente_moodle.MoodleClient, "launch", lambda url, perfil, **kwargs: cliente)

    trabajo = moodle_audit.start_moodle_audit("ana", CURSO)

    fila = trabajo["results"][0]
    assert fila["tipo"] == "pdf"
    assert fila["estado"] == "ok"
    assert fila["renderiza"] == "si"


def test_matriz_compara_publicados_y_agrega_recursos_esperados_ausentes(monkeypatch, tmp_path):
    _aislar(monkeypatch, tmp_path)
    url = CURSO + "&activity=1"
    cliente = _ClienteFalso(
        recursos={"Semana 1": [
            {"id": "a", "titulo": "Lectura publicada", "url": url, "tipo": "page"},
        ]},
        sondas={url: {
            "encabezados": ["Lectura publicada"],
            "texto_cuerpo": "Contenido disponible",
        }},
    )
    monkeypatch.setattr(cliente_moodle.MoodleClient, "launch", lambda *args, **kwargs: cliente)
    matriz = (
        "Semana correspondiente,Unidad,Nombre del recurso,Categoría,Tipo de recurso,Enlace\n"
        "Semana 1,Unidad 1,Lectura publicada,OVI,Page,Enlace\n"
        "Semana 1,Unidad 1,Video que falta,OVA,H5P,Enlace\n"
    ).encode()

    job = moodle_audit.start_moodle_audit("ana", CURSO, "matriz.csv", matriz)

    assert job["results"][0]["matriz_estado"] == "coincide"
    assert job["results"][1]["actividad"] == "Video que falta"
    assert job["results"][1]["estado"] == "falta"
    assert job["results"][1]["matriz_estado"] == "no publicado"


def test_matriz_marca_actividad_publicada_que_no_esta_en_plan(monkeypatch, tmp_path):
    results = [{"semana": "Semana 1", "actividad": "Otra lectura", "estado": "ok"}]
    matriz = [{"week": "Semana 1", "title": "Lectura esperada", "sourceRow": 2}]

    moodle_audit._comparar_matriz(results, matriz)

    assert results[0]["matriz_estado"] == "no está en matriz"
    assert results[1]["matriz_estado"] == "no publicado"


def test_auditoria_cancelada_marca_los_que_quedan(monkeypatch, tmp_path):
    _aislar(monkeypatch, tmp_path)
    cliente = _ClienteFalso(
        recursos={
            "Semana 1": [
                {"id": "module-1", "titulo": "Recurso A", "url": CURSO + "&a=1", "tipo": "page", "semana": "Semana 1"},
                {"id": "module-2", "titulo": "Recurso B", "url": CURSO + "&a=2", "tipo": "page", "semana": "Semana 1"},
            ],
        },
        sondas={
            CURSO + "&a=1": {
                "encabezados": ["Recurso A"], "texto_cuerpo": "Contenido A",
                "h5p": {"presente": False}, "pdf": {"presente": False},
            },
        },
    )

    def audit_activity(url):
        # La cancelacion llega en mitad del primer recurso: el resto no se toca.
        enCurso = next(iter(moodle_audit.MOODLE_AUDIT_JOBS.values()))
        enCurso["cancel_requested"] = True
        return cliente.sondas.get(url, {"error": "Sonda no preparada"})

    cliente.audit_activity = audit_activity
    monkeypatch.setattr(cliente_moodle.MoodleClient, "launch", lambda url, perfil, **kwargs: cliente)

    trabajo = moodle_audit.start_moodle_audit("ana", CURSO)

    assert trabajo["status"] == "cancelled"
    assert trabajo["finished"] is True
    estados = [fila["estado"] for fila in trabajo["results"]]
    assert estados == ["ok", "no procesado"]


def test_auditoria_sin_semanas_termina_con_error(monkeypatch, tmp_path):
    _aislar(monkeypatch, tmp_path)
    cliente = _ClienteFalso(semanas=[])
    monkeypatch.setattr(cliente_moodle.MoodleClient, "launch", lambda url, perfil, **kwargs: cliente)

    trabajo = moodle_audit.start_moodle_audit("ana", CURSO)

    assert trabajo["status"] == "error"
    assert "semanas" in trabajo["message"]
    assert cliente.cerrado is True


def test_auditoria_con_fallo_de_navegador_deja_mensaje_amistoso(monkeypatch, tmp_path):
    _aislar(monkeypatch, tmp_path)

    def lanzar_con_fallo(url, perfil, **kwargs):
        raise RuntimeError("Page.goto: Timeout 60000ms exceeded")

    monkeypatch.setattr(cliente_moodle.MoodleClient, "launch", lanzar_con_fallo)

    trabajo = moodle_audit.start_moodle_audit("ana", CURSO)

    assert trabajo["status"] == "error"
    assert "tardó demasiado" in trabajo["message"]


def test_no_se_pueden_dos_auditorias_a_la_vez(monkeypatch, tmp_path):
    _aislar(monkeypatch, tmp_path, sincrono=False)
    cliente = _ClienteFalso()
    monkeypatch.setattr(cliente_moodle.MoodleClient, "launch", lambda url, perfil, **kwargs: cliente)

    moodle_audit.start_moodle_audit("ana", CURSO)

    with pytest.raises(ValueError):
        moodle_audit.start_moodle_audit("ana", CURSO)

    # Otra persona puede auditar su curso al mismo tiempo.
    otro = moodle_audit.start_moodle_audit("luis", CURSO)
    assert otro["owner"] == "luis"


def test_enlace_de_curso_invalido_no_arranca(monkeypatch, tmp_path):
    _aislar(monkeypatch, tmp_path)

    with pytest.raises(ValueError):
        moodle_audit.start_moodle_audit("ana", "https://ejemplo.com/curso")


def test_trabajos_se_aislan_por_persona(monkeypatch, tmp_path):
    _aislar(monkeypatch, tmp_path, sincrono=False)

    trabajo = moodle_audit.start_moodle_audit("ana", CURSO)

    assert moodle_audit.get_moodle_audit_job(trabajo["id"], "ana") is not None
    assert moodle_audit.get_moodle_audit_job(trabajo["id"], "luis") is None
    assert moodle_audit.latest_moodle_audit("luis") is None
    assert moodle_audit.active_moodle_audit("ana") is trabajo


def test_cancelar_trabajo_terminado_no_se_puede(monkeypatch, tmp_path):
    _aislar(monkeypatch, tmp_path)
    cliente = _ClienteFalso(semanas=[])
    monkeypatch.setattr(cliente_moodle.MoodleClient, "launch", lambda url, perfil, **kwargs: cliente)

    trabajo = moodle_audit.start_moodle_audit("ana", CURSO)

    with pytest.raises(ValueError):
        moodle_audit.cancel_moodle_audit(trabajo)
