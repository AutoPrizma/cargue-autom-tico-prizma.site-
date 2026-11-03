import io
import json
import os
import time
import zipfile

from fastapi.testclient import TestClient

from main import app
from auto_prizma.services.auth import USUARIO_ACTUAL, _firmar_sesion
from auto_prizma.services import moodle_resources


def _client():
    client = TestClient(app)
    client.cookies.set("ap_sesion", _firmar_sesion("adminlocal"))
    return client


def _resources_zip():
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("U1-T1-Recurso de analitica.pdf", b"%PDF-1.4 test")
    return output.getvalue()


def test_moodle_home_uses_common_frame_and_local_only_gate(monkeypatch):
    monkeypatch.setattr("auto_prizma.api.routes.moodle_resources._request_is_local", lambda _request: True)
    response = _client().get("/moodle")

    assert response.status_code == 200
    assert 'aria-current="page"' in response.text
    assert 'name="matriz_archivo"' in response.text
    assert 'name="recursos_zip"' in response.text
    assert 'href="/app.css?v=' in response.text

    monkeypatch.setattr("auto_prizma.api.routes.moodle_resources._request_is_local", lambda _request: False)
    denied = _client().get("/moodle")
    assert denied.status_code == 403
    assert "solo está disponible desde una instancia local" in denied.text


def test_moodle_reports_are_private_and_expire_after_15_days(monkeypatch, tmp_path):
    monkeypatch.setattr("auto_prizma.api.routes.moodle_resources._request_is_local", lambda _request: True)
    monkeypatch.setattr("auto_prizma.api.routes.moodle_resources._moodle_report_dir", lambda: str(tmp_path))
    old_stem = "moodle-cargue-20261001T120000Z-old"
    new_stem = "moodle-cargue-20261028T120000Z-new"
    for stem in (old_stem, new_stem):
        (tmp_path / f"{stem}.json").write_text(json.dumps({"summary": {}}), encoding="utf-8")
        (tmp_path / f"{stem}.csv").write_text("Resultado\nOK\n", encoding="utf-8")
    old_time = time.time() - 16 * 24 * 60 * 60
    for extension in (".json", ".csv"):
        os.utime(tmp_path / (old_stem + extension), (old_time, old_time))

    response = _client().get("/moodle-reportes")

    assert response.status_code == 200
    assert "1 reporte" in response.text
    assert not (tmp_path / (old_stem + ".json")).exists()
    assert not (tmp_path / (old_stem + ".csv")).exists()
    assert (tmp_path / (new_stem + ".json")).exists()
    assert (tmp_path / (new_stem + ".csv")).exists()


def test_moodle_report_directories_are_separate_per_user(monkeypatch, tmp_path):
    from auto_prizma.api.routes import moodle_resources as routes

    monkeypatch.setattr(routes, "DATA_DIR", str(tmp_path))
    token = USUARIO_ACTUAL.set("ana")
    try:
        ana_dir = routes._moodle_report_dir()
    finally:
        USUARIO_ACTUAL.reset(token)
    token = USUARIO_ACTUAL.set("beto")
    try:
        beto_dir = routes._moodle_report_dir()
    finally:
        USUARIO_ACTUAL.reset(token)

    assert ana_dir != beto_dir
    assert str(tmp_path / "reportes" / "moodle") in ana_dir


def test_moodle_analysis_uploads_matrix_and_zip_then_shows_preview(tmp_path, monkeypatch):
    monkeypatch.setattr("auto_prizma.api.routes.moodle_resources._request_is_local", lambda _request: True)
    monkeypatch.setattr(moodle_resources, "UPLOADS_DIR", str(tmp_path / "uploads"))
    matrix = (
        "Semana correspondiente,Unidad,Nombre del recurso,Categoría,Tipo de recurso,Enlace\n"
        "Semana 1,Unidad 1,Recurso de analítica,OVI,PDF,TEXTO - Recurso de analítica\n"
    ).encode("utf-8")
    response = _client().post(
        "/moodle/analizar",
        files={
            "matriz_archivo": ("matriz.csv", matrix, "text/csv"),
            "recursos_zip": ("recursos.zip", _resources_zip(), "application/zip"),
        },
        data={"course_url": "https://prizma.americana.edu.co/course/view.php?id=42"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    preview = _client().get(response.headers["location"])
    assert preview.status_code == 200
    assert "Recurso de analítica" in preview.text
    assert "Listo para publicar" in preview.text
    job_id = response.headers["location"].rsplit("/", 1)[-1]
    assert moodle_resources.get_moodle_job(job_id, "adminlocal") is not None
    assert moodle_resources.get_moodle_job(job_id, "otro-usuario") is None


def test_moodle_preview_accepts_manual_file_for_missing_row(tmp_path, monkeypatch):
    monkeypatch.setattr("auto_prizma.api.routes.moodle_resources._request_is_local", lambda _request: True)
    monkeypatch.setattr(moodle_resources, "UPLOADS_DIR", str(tmp_path / "uploads"))
    matrix = (
        "Semana correspondiente,Unidad,Nombre del recurso,Categoría,Tipo de recurso,Enlace\n"
        "Semana 1,Unidad 1,Lectura que falta,OVI,PDF,TEXTO - Lectura que falta\n"
    ).encode("utf-8")
    response = _client().post(
        "/moodle/analizar",
        files={
            "matriz_archivo": ("matriz.csv", matrix, "text/csv"),
            "recursos_zip": ("recursos.zip", _resources_zip(), "application/zip"),
        },
        data={"course_url": "https://prizma.americana.edu.co/course/view.php?id=42"},
        follow_redirects=False,
    )
    job_id = response.headers["location"].rsplit("/", 1)[-1]
    job = moodle_resources.get_moodle_job(job_id, "adminlocal")
    entry = job["entries"][0]
    assert entry["status"] == "missing"

    attached = _client().post(
        f"/moodle/{job_id}/recurso-manual",
        data={"entry_key": entry["key"]},
        files={"resource_file": ("lectura.pdf", b"%PDF-manual", "application/pdf")},
    )

    assert attached.status_code == 200
    assert attached.json()["ok"] is True
    assert entry["status"] == "matched"
    preview = _client().get(f"/moodle/{job_id}")
    assert "lectura.pdf" in preview.text
