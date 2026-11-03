"""Acceso local directo y autenticación conservada para accesos remotos."""

from fastapi.testclient import TestClient

from main import app


def _client(host):
    return TestClient(app, client=(host, 50000))


def test_loopback_enters_without_user_or_password():
    client = _client("127.0.0.1")

    response = client.get("/", follow_redirects=False)

    assert response.status_code == 200
    assert "Tus herramientas de trabajo," in response.text
    assert "Control Tower" in response.text
    assert client.get("/automatizaciones-n8n").status_code == 200


def test_login_page_and_submission_are_skipped_on_loopback():
    client = _client("127.0.0.1")

    assert client.get("/login", follow_redirects=False).headers["location"] == "/"
    response = client.post(
        "/login",
        data={"usuario": "no-se-usa", "contrasena": "no-se-usa"},
        follow_redirects=False,
    )
    assert response.status_code == 303
    assert response.headers["location"] == "/"


def test_remote_request_still_requires_authenticated_session():
    client = _client("10.0.0.7")

    response = client.get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    json_response = client.get("/estado/x", headers={"Accept": "application/json"})
    assert json_response.status_code == 401


def test_legacy_local_login_variable_does_not_change_remote_protection(monkeypatch):
    monkeypatch.setenv("AUTO_PRIZMA_SIN_LOGIN", "no-existe")

    assert _client("127.0.0.1").get("/", follow_redirects=False).status_code == 200
    response = _client("10.0.0.7").get("/", follow_redirects=False)
    assert response.status_code == 303
    assert response.headers["location"] == "/login"
