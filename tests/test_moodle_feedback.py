"""Realimentación del apartado Moodle: filas de tema, tipos, pausa/cancelación y vista."""

import io
import threading
import uuid
import zipfile

import pytest
from fastapi.testclient import TestClient

from main import app
from auto_prizma.domain.moodle_resources import resource_kind
from auto_prizma.services import moodle_resources
from auto_prizma.services.auth import _firmar_sesion


def test_matrix_separates_topic_headings_from_incomplete_resource_rows():
    matrix = (
        "Semana correspondiente,Unidad,Nombre del recurso,Categoría,Tipo de recurso,Enlace\n"
        ",,Escritura académica,,,\n"
        "Semana 1,Unidad 1,Recurso sin tipo,OVI,,TEXTO - Recurso sin tipo\n"
        "Semana 1,Unidad 1,Recurso completo,OVI,PDF,TEXTO - Recurso completo\n"
    ).encode("utf-8")
    rows, issues = moodle_resources._read_matrix("matriz.csv", matrix)

    assert [row["title"] for row in rows] == ["Recurso completo"]
    assert issues[0] == {"sourceRow": 2, "reason": "section-heading", "title": "Escritura académica", "week": ""}
    assert issues[1]["reason"] == "missing-required-field"
    assert issues[1]["missing"] == ["Tipo de recurso"]
    assert issues[1]["title"] == "Recurso sin tipo"


def test_resource_kind_groups_matrix_types_for_selection():
    assert resource_kind({"category": "OVA", "resourceType": "Recurso H5P"}) == "h5p"
    assert resource_kind({"category": "OVI", "resourceType": "Recurso H5P"}) == "h5p"
    assert resource_kind({"category": "OVI", "resourceType": "Infografía"}) == "infografia"
    assert resource_kind({"category": "OVA", "resourceType": "Video interactivo Avatar"}) == "video-avatar"
    assert resource_kind({"category": "OVI", "resourceType": "PDF"}) == "pdf"
    assert resource_kind({"category": "CHALLENGE", "resourceType": "Reto evaluativo"}) == "reto"
    assert resource_kind({"category": "OVI", "resourceType": "Video a cámara"}) == "otro"


def _running_job(entries):
    return {
        "id": "job1",
        "owner": "adminlocal",
        # Curso distinto por prueba: el historial local evita repetir lo ya publicado en el mismo curso.
        "course_url": "https://prizma.americana.edu.co/course/view.php?id=" + uuid.uuid4().hex,
        "status": "queued",
        "progress": {"index": 0, "total": len(entries), "week": "", "title": "", "phase": ""},
        "live_results": [],
        "cancel_requested": False,
        "pause_requested": False,
    }


class _FakeClient:
    def __init__(self, on_publish=None):
        self.published = []
        self.on_publish = on_publish

    def open_course(self, url):
        pass

    def open_week(self, week):
        pass

    def find_existing_resource(self, *args):
        return None

    def publish(self, entry, on_before_save=None):
        on_before_save and on_before_save()
        self.published.append(entry["title"])
        if self.on_publish:
            self.on_publish(entry)
        return "101"


class _FakeWorker:
    def __init__(self, client):
        self.client = client

    def get_client(self, *args):
        return self.client


def _entries(*titles):
    return [
        {
            "key": uuid.uuid4().hex + ":" + str(index), "previewKey": str(index), "sourceRow": index, "week": "Semana 1",
            "title": title, "kind": "pdf", "destination": {"module": "file", "block": "digital"},
            "path": title + ".pdf",
        }
        for index, title in enumerate(titles, start=2)
    ]


def test_cancel_finishes_current_resource_and_marks_the_rest_not_processed():
    entries = _entries("Uno", "Dos", "Tres")
    job = _running_job(entries)
    client = _FakeClient(on_publish=lambda entry: moodle_resources.cancel_moodle_publish(job))

    moodle_resources._run_moodle_publish(job, "batch", entries, _FakeWorker(client))

    assert client.published == ["Uno"]
    assert job["status"] == "cancelled"
    assert [item["status"] for item in job["live_results"]] == ["Cargado", "No procesado", "No procesado"]
    assert job["report"]["summary"]["notProcessed"] == 2
    assert job["report"]["rows"][0]["previewKey"] == "2"


def test_pause_waits_before_next_resource_until_resumed(monkeypatch):
    monkeypatch.setattr(moodle_resources, "PAUSE_POLL_SECONDS", 0.01)
    entries = _entries("Uno", "Dos")
    job = _running_job(entries)

    def pause_after_first(entry):
        if entry["title"] == "Uno":
            moodle_resources.pause_moodle_publish(job)

    client = _FakeClient(on_publish=pause_after_first)
    thread = threading.Thread(
        target=moodle_resources._run_moodle_publish,
        args=(job, "batch", entries, _FakeWorker(client)),
    )
    thread.start()
    for _ in range(200):
        if job["status"] == "paused":
            break
        threading.Event().wait(0.01)

    assert job["status"] == "paused"
    assert client.published == ["Uno"]
    assert moodle_resources.public_moodle_status(job)["paused"] is True

    moodle_resources.resume_moodle_publish(job)
    thread.join(2)
    assert client.published == ["Uno", "Dos"]
    assert job["status"] == "completed"


def test_controls_reject_jobs_that_are_not_running():
    job = {"status": "preview"}
    for control in (
        moodle_resources.pause_moodle_publish,
        moodle_resources.resume_moodle_publish,
        moodle_resources.cancel_moodle_publish,
    ):
        with pytest.raises(ValueError):
            control(job)


def _client():
    client = TestClient(app)
    client.cookies.set("ap_sesion", _firmar_sesion("adminlocal"))
    return client


def _preview(tmp_path, monkeypatch, matrix):
    monkeypatch.setattr("auto_prizma.api.routes.moodle_resources._request_is_local", lambda _request: True)
    monkeypatch.setattr(moodle_resources, "UPLOADS_DIR", str(tmp_path / "uploads"))
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("U1-T1-Recurso de analitica.pdf", b"%PDF-1.4 test")
    response = _client().post(
        "/moodle/analizar",
        files={
            "matriz_archivo": ("matriz.csv", matrix.encode("utf-8"), "text/csv"),
            "recursos_zip": ("recursos.zip", output.getvalue(), "application/zip"),
        },
        data={"course_url": "https://prizma.americana.edu.co/course/view.php?id=42"},
        follow_redirects=False,
    )
    return response.headers["location"].rsplit("/", 1)[-1]


def test_preview_explains_topic_rows_and_offers_selection_by_kind_and_week(tmp_path, monkeypatch):
    job_id = _preview(tmp_path, monkeypatch, (
        "Semana correspondiente,Unidad,Nombre del recurso,Categoría,Tipo de recurso,Enlace\n"
        ",,Escritura académica,,,\n"
        "Semana 1,Unidad 1,Recurso de analítica,OVI,PDF,TEXTO - Recurso de analítica\n"
        "Semana 2,Unidad 1,Mapa de ideas,OVA,Recurso H5P,H5P - Mapa de ideas\n"
    ))
    page = _client().get("/moodle/" + job_id).text

    assert "Se ignoraron 1 título de tema" in page
    assert "Filas omitidas por datos incompletos" not in page
    assert 'data-sel-kind="pdf"' in page
    assert 'data-sel-kind="h5p"' in page
    assert 'data-sel-week="Semana 1"' in page
    assert "Falta el archivo" in page
    assert "Ningún .h5p del ZIP se llama «Mapa de ideas»" in page
    # Organizado por semana y bloque; lo que falta corregir aparece aparte.
    assert page.count('class="panel moodle-week"') == 2
    assert "Necesitan atención (1)" in page
    # Cada semana solo usa «Recurso educativo digital»: las otras dos etiquetas quedan como candidatas a borrar.
    assert "Al terminar, borrar las etiquetas que la matriz no usa (hasta 4)" in page
    assert 'name="clean_labels"' in page
    assert "Sin uso: Reto Evaluativo" in page


def test_control_routes_pause_and_cancel_a_running_publish(tmp_path, monkeypatch):
    job_id = _preview(tmp_path, monkeypatch, (
        "Semana correspondiente,Unidad,Nombre del recurso,Categoría,Tipo de recurso,Enlace\n"
        "Semana 1,Unidad 1,Recurso de analítica,OVI,PDF,TEXTO - Recurso de analítica\n"
    ))
    client = _client()
    assert client.post("/moodle/" + job_id + "/pausar").status_code == 409

    job = moodle_resources.get_moodle_job(job_id, "adminlocal")
    job["status"] = "publishing"
    try:
        paused = client.post("/moodle/" + job_id + "/pausar")
        assert paused.status_code == 200
        assert paused.json()["pause_requested"] is True
        assert 'data-moodle-control="cancelar"' in client.get("/moodle/" + job_id).text

        cancelled = client.post("/moodle/" + job_id + "/cancelar").json()
        assert cancelled["cancel_requested"] is True
        assert cancelled["pause_requested"] is False
        assert client.post("/moodle/" + job_id + "/borrar").status_code == 404
    finally:
        job["status"] = "preview"


def test_report_offers_retry_for_resources_that_were_not_loaded():
    from auto_prizma.web.moodle_views import render_moodle_page

    entries = _entries("Uno", "Dos")
    job = {
        "id": "job2", "status": "completed", "course_url": "https://prizma.americana.edu.co/course/view.php?id=1",
        "matrix_filename": "m.csv", "zip_filename": "r.zip", "summary": {"matched": 2},
        "entries": [dict(entry, key=entry["previewKey"], status="matched") for entry in entries],
        "report": moodle_resources.report_from_results([
            {"entry": entries[0], "status": "Cargado", "detail": ""},
            {"entry": entries[1], "status": "No cargado", "detail": "Paquete H5P rechazado"},
        ]),
        "report_paths": {},
    }
    page = render_moodle_page(job)

    assert "Reintentar el recurso que no se cargó" in page
    assert 'name="entry_keys" value="3"' in page
