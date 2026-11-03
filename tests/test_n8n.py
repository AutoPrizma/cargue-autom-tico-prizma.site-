"""Pruebas del puente privado entre Auto Prizma y n8n."""

import json

from fastapi.testclient import TestClient

from main import app
from auto_prizma.services.auth import _firmar_sesion


def _client():
    client = TestClient(app, client=("127.0.0.1", 50000))
    client.cookies.set("ap_sesion", _firmar_sesion("adminlocal"))
    return client


def test_n8n_execution_requires_valid_payload_and_uses_demo_if_unconfigured(monkeypatch):
    monkeypatch.setattr("auto_prizma.services.n8n.env_str", lambda name: "" if name != "N8N_SHARED_SECRET" else "")
    monkeypatch.setattr("auto_prizma.services.n8n.N8N_WEBHOOK_DEFAULTS", {})
    response = _client().post(
        "/automatizaciones-n8n/ejecutar",
        json={"flowId": "aut-tests", "payload": {"googleDocUrl": "https://docs.google.com/document/d/abc/edit"}},
    )
    assert response.status_code == 200
    assert response.json()["demo"] is True

    invalid = _client().post(
        "/automatizaciones-n8n/ejecutar",
        json={"flowId": "aut-tests", "payload": {"googleDocUrl": "file:///etc/passwd"}},
    )
    assert invalid.status_code == 400


def test_n8n_webhook_is_called_server_side_and_secret_is_not_returned(monkeypatch):
    captured = {}

    class Response:
        status = 200
        headers = {"Content-Type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _size):
            return json.dumps({"message": "Listo", "folderUrl": "https://drive.google.com/drive/folders/abc"}).encode()

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["body"] = json.loads(request.data.decode())
        captured["secret"] = request.get_header("X-n8n-secret")
        captured["timeout"] = timeout
        return Response()

    monkeypatch.setattr(
        "auto_prizma.services.n8n.env_str",
        lambda name: {
            "N8N_WEBHOOK_AUT_TESTS": "https://n8n.example/webhook/secret-path",
            "N8N_SHARED_SECRET": "secret-value",
        }.get(name, ""),
    )
    monkeypatch.setattr("auto_prizma.services.n8n.urlopen", fake_urlopen)
    response = _client().post(
        "/automatizaciones-n8n/ejecutar",
        json={"flowId": "aut-tests", "payload": {"googleDocUrl": "https://docs.google.com/document/d/abc/edit"}},
    )
    assert response.status_code == 200
    assert response.json()["message"] == "Listo"
    assert captured["body"]["googleDocUrl"].endswith("/edit")
    assert captured["secret"] == "secret-value"
    assert "secret-path" not in response.text and "secret-value" not in response.text


def test_resource_download_uses_default_webhook_only_server_side(monkeypatch):
    from auto_prizma.core.config import N8N_WEBHOOK_DEFAULTS

    captured = {}

    class Response:
        status = 200
        headers = {"Content-Type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _size):
            return b'{"message":"Descarga iniciada"}'

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["payload"] = json.loads(request.data.decode("utf-8"))
        return Response()

    monkeypatch.setattr("auto_prizma.services.n8n.env_str", lambda _name: "")
    monkeypatch.setattr("auto_prizma.services.n8n.urlopen", fake_urlopen)

    page = _client().get("/automatizaciones-n8n").text
    assert "Listo para ejecutar" in page
    assert N8N_WEBHOOK_DEFAULTS["descargar-recursos"] not in page

    response = _client().post(
        "/automatizaciones-n8n/ejecutar",
        json={
            "flowId": "descargar-recursos",
            "payload": {
                "sheetUrl": "https://docs.google.com/spreadsheets/d/abc/edit",
                "dividirPorUnidad": "No",
            },
        },
    )
    assert response.status_code == 200
    assert captured["url"] == N8N_WEBHOOK_DEFAULTS["descargar-recursos"]
    assert captured["payload"] == {
        "sheetUrl": "https://docs.google.com/spreadsheets/d/abc/edit",
        "dividirPorUnidad": "No",
    }


def test_n8n_endpoint_rejects_unknown_flow():
    response = _client().post("/automatizaciones-n8n/ejecutar", json={"flowId": "unknown", "payload": {}})
    assert response.status_code == 404


def test_n8n_page_has_prizma_course_weeks_shortcut():
    page = _client().get("/automatizaciones-n8n").text
    api_card = page.index('href="https://api.prizma.site/"')
    weeks_card = page.index('href="https://api.prizma.site/v1/utilities/mydev/001/import-csv-view/"')
    ordered_cards = [
        page.index("<h2>API de PRIZMA</h2>"),
        page.index("<h2>Crear semanas de curso</h2>"),
        page.index("<h2>Descarga de recursos</h2>"),
        page.index("<h2>Matriz de importación CSV</h2>"),
        page.index("<h2>Generar tests JSON</h2>"),
        page.index("<h2>Generador de plantillas temáticas</h2>"),
    ]
    assert "API de PRIZMA" in page
    assert api_card < weeks_card
    assert ordered_cards == sorted(ordered_cards)
    assert 'href="https://api.prizma.site/v1/utilities/mydev/001/import-csv-view/"' in page
    assert 'target="_blank" rel="noopener noreferrer"' in page
    assert "Crear semanas de curso" in page


def test_resource_download_card_uses_the_shared_native_modal():
    page = _client().get("/automatizaciones-n8n").text
    assert 'data-open-n8n="descargar-recursos"' in page
    assert 'id="n8n-descargar-recursos"' in page
    assert 'data-flow-id="descargar-recursos"' in page
    assert 'name="sheetUrl"' in page
    assert 'name="dividirPorUnidad"' in page
    assert '<option value="No" selected>No</option>' in page
    assert "n8n-embed-frame" not in page


def test_resource_download_status_is_polled_server_side(monkeypatch):
    from auto_prizma.core.config import N8N_STATUS_WEBHOOK_DEFAULTS

    captured = {}

    class Response:
        status = 200
        headers = {"Content-Type": "application/json"}

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _size):
            return json.dumps({
                "ok": True,
                "status": "done",
                "message": "Recursos copiados: 24.",
                "folderUrl": "https://drive.google.com/drive/folders/abc",
                "totalArchivos": 24,
            }).encode()

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["method"] = request.get_method()
        return Response()

    monkeypatch.setattr("auto_prizma.services.n8n.env_str", lambda _name: "")
    monkeypatch.setattr("auto_prizma.services.n8n.urlopen", fake_urlopen)

    response = _client().get("/automatizaciones-n8n/estado", params={"flowId": "descargar-recursos", "jobId": "12345"})
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "done"
    assert body["data"]["totalArchivos"] == 24
    assert captured["method"] == "GET"
    assert captured["url"] == N8N_STATUS_WEBHOOK_DEFAULTS["descargar-recursos"] + "?jobId=12345"
    assert N8N_STATUS_WEBHOOK_DEFAULTS["descargar-recursos"] not in response.text


def test_resource_download_status_keeps_processing_and_reports_unknown(monkeypatch):
    replies = iter([
        {"ok": True, "status": "processing", "message": "Cargando recursos…"},
        {"ok": False, "status": "unknown", "message": "No se encontró el proceso de descarga."},
    ])

    class Response:
        status = 200
        headers = {"Content-Type": "application/json"}

        def __init__(self, data):
            self.data = data

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, _size):
            return json.dumps(self.data).encode()

    monkeypatch.setattr("auto_prizma.services.n8n.env_str", lambda _name: "")
    monkeypatch.setattr("auto_prizma.services.n8n.urlopen", lambda request, timeout: Response(next(replies)))

    processing = _client().get("/automatizaciones-n8n/estado", params={"flowId": "descargar-recursos", "jobId": "77"})
    assert processing.status_code == 200
    assert processing.json()["status"] == "processing"

    unknown = _client().get("/automatizaciones-n8n/estado", params={"flowId": "descargar-recursos", "jobId": "77"})
    assert unknown.status_code == 404
    assert unknown.json()["status"] == "unknown"


def test_resource_download_status_validates_flow_and_job_id():
    bad_job = _client().get("/automatizaciones-n8n/estado", params={"flowId": "descargar-recursos", "jobId": "../x"})
    assert bad_job.status_code == 400
    no_status = _client().get("/automatizaciones-n8n/estado", params={"flowId": "aut-tests", "jobId": "1"})
    assert no_status.status_code == 404


def test_n8n_page_shows_loading_state_and_polls_status():
    page = _client().get("/automatizaciones-n8n").text
    assert "/automatizaciones-n8n/estado" in page
    assert "Cargando recursos…" in page
    assert "Enviando solicitud a n8n" not in page


def test_n8n_unavailable_shows_clear_message(monkeypatch):
    from urllib.error import HTTPError

    def fake_urlopen(request, timeout):
        raise HTTPError(request.full_url, 503, "Service Unavailable", {}, None)

    monkeypatch.setattr("auto_prizma.services.n8n.env_str", lambda _name: "")
    monkeypatch.setattr("auto_prizma.services.n8n.urlopen", fake_urlopen)
    response = _client().post(
        "/automatizaciones-n8n/ejecutar",
        json={"flowId": "descargar-recursos", "payload": {"sheetUrl": "https://docs.google.com/spreadsheets/d/abc/edit", "dividirPorUnidad": "No"}},
    )
    assert response.status_code == 503
    assert "no está disponible" in response.json()["message"]


class _JsonResponse:
    status = 200
    headers = {"Content-Type": "application/json"}

    def __init__(self, body):
        self._body = json.dumps(body).encode("utf-8")

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _size):
        return self._body


def test_matrix_and_templates_use_default_webhooks_server_side(monkeypatch):
    from auto_prizma.core.config import N8N_WEBHOOK_DEFAULTS

    captured = []

    def fake_urlopen(request, timeout):
        captured.append((request.full_url, json.loads(request.data.decode("utf-8"))))
        return _JsonResponse({"ok": True, "message": "Listo", "fileName": "x.csv", "folderUrl": "https://drive.google.com/file/d/1/view"})

    monkeypatch.setattr("auto_prizma.services.n8n.env_str", lambda _name: "")
    monkeypatch.setattr("auto_prizma.services.n8n.urlopen", fake_urlopen)

    page = _client().get("/automatizaciones-n8n").text
    assert page.count("Listo para ejecutar") == 4
    assert "matriz-csv-portal" not in page and "plantillas-tematicas-portal" not in page

    matriz = {"codigos": "V4305 43051 05406 Asignatura", "filaInicio": "5", "plantillaUrl": "https://docs.google.com/spreadsheets/d/abc/edit"}
    plantilla = {"folderUrl": "https://drive.google.com/drive/folders/abc"}
    assert _client().post("/automatizaciones-n8n/ejecutar", json={"flowId": "matriz-csv", "payload": matriz}).status_code == 200
    assert _client().post("/automatizaciones-n8n/ejecutar", json={"flowId": "plantillas-tematicas", "payload": plantilla}).status_code == 200
    assert captured == [
        (N8N_WEBHOOK_DEFAULTS["matriz-csv"], matriz),
        (N8N_WEBHOOK_DEFAULTS["plantillas-tematicas"], plantilla),
    ]


def test_n8n_reported_problem_is_shown_as_error(monkeypatch):
    monkeypatch.setattr("auto_prizma.services.n8n.env_str", lambda _name: "")
    monkeypatch.setattr(
        "auto_prizma.services.n8n.urlopen",
        lambda request, timeout: _JsonResponse({"ok": False, "message": "La tabla parece no empezar en la fila 5."}),
    )
    response = _client().post(
        "/automatizaciones-n8n/ejecutar",
        json={"flowId": "matriz-csv", "payload": {"codigos": "A B C D", "filaInicio": "5", "plantillaUrl": "https://docs.google.com/spreadsheets/d/abc"}},
    )
    assert response.status_code == 422
    assert response.json() == {"ok": False, "message": "La tabla parece no empezar en la fila 5.", "data": {"ok": False, "message": "La tabla parece no empezar en la fila 5."}}


def test_n8n_failure_and_timeout_messages_are_clear(monkeypatch):
    from urllib.error import HTTPError

    def falla(request, timeout):
        raise HTTPError(request.full_url, 500, "Error in workflow", {}, None)

    def tarda(request, timeout):
        raise TimeoutError()

    monkeypatch.setattr("auto_prizma.services.n8n.env_str", lambda _name: "")
    payload = {"flowId": "plantillas-tematicas", "payload": {"folderUrl": "https://drive.google.com/drive/folders/abc"}}
    monkeypatch.setattr("auto_prizma.services.n8n.urlopen", falla)
    response = _client().post("/automatizaciones-n8n/ejecutar", json=payload)
    assert response.status_code == 502
    assert "compartidos con la cuenta de automatizaciones" in response.json()["message"]
    monkeypatch.setattr("auto_prizma.services.n8n.urlopen", tarda)
    response = _client().post("/automatizaciones-n8n/ejecutar", json=payload)
    assert response.status_code == 504
    assert "tardando más de lo normal" in response.json()["message"]


def test_n8n_page_renders_download_link_and_warnings():
    page = _client().get("/automatizaciones-n8n").text
    assert "n8nAvisos(box,data.avisos)" in page
    assert '"Descargar archivo"' in page


def test_tests_flow_uses_default_webhook_and_shows_n8n_error_detail(monkeypatch):
    import io
    from urllib.error import HTTPError
    from auto_prizma.core.config import N8N_WEBHOOK_DEFAULTS

    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        body = json.dumps({"ok": False, "message": "Link inválido: No pude extraer el ID del documento.", "recomendacion": "Usa un enlace de Google Docs."}).encode("utf-8")
        raise HTTPError(request.full_url, 400, "Bad Request", {}, io.BytesIO(body))

    monkeypatch.setattr("auto_prizma.services.n8n.env_str", lambda _name: "")
    monkeypatch.setattr("auto_prizma.services.n8n.urlopen", fake_urlopen)
    response = _client().post(
        "/automatizaciones-n8n/ejecutar",
        json={"flowId": "aut-tests", "payload": {"googleDocUrl": "https://docs.google.com/document/d/abc/edit"}},
    )
    assert captured["url"] == N8N_WEBHOOK_DEFAULTS["aut-tests"]
    assert response.status_code == 422
    assert response.json()["message"] == "Link inválido: No pude extraer el ID del documento. Usa un enlace de Google Docs."
