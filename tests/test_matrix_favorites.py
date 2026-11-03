"""Pruebas del catálogo compartido de matrices y recursos favoritos."""

import json

from fastapi.testclient import TestClient

from main import app
from auto_prizma.services.auth import _firmar_sesion


def _client():
    client = TestClient(app, client=("127.0.0.1", 50000))
    client.cookies.set("ap_sesion", _firmar_sesion("adminlocal"))
    return client


def test_favorites_sidebar_entry_follows_control_tower(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "auto_prizma.services.matrix_favorites.FAVORITES_PATH",
        str(tmp_path / "matrices_favoritas.json"),
    )
    page = _client().get("/matrices-favoritas").text
    home = page.index('<a class="nav-item" href="/"')
    control_tower = page.index('href="https://script.google.com/a/macros/americana.edu.co/s/')
    favorites = page.index('<a class="nav-item activo" href="/matrices-favoritas"')
    prizma = page.index('<a class="nav-item" href="/auditor"')
    assert home < control_tower < favorites < prizma
    assert "<h1>Matrices</h1>" in page
    assert "Aún no tienes matrices guardadas." in page
    assert "hasta que las elimines manualmente" in page


def test_create_edit_and_delete_favorite_persistently(monkeypatch, tmp_path):
    path = tmp_path / "matrices_favoritas.json"
    monkeypatch.setattr("auto_prizma.services.matrix_favorites.FAVORITES_PATH", str(path))
    client = _client()

    created = client.post(
        "/matrices-favoritas/agregar",
        data={"nombre": "Matriz de control", "url": "https://docs.google.com/spreadsheets/d/abc/edit"},
        follow_redirects=False,
    )
    assert created.status_code == 303
    first_page = client.get(created.headers["location"]).text
    assert "Matriz de control" in first_page
    assert 'class="favorito-card-hitarea" href="https://docs.google.com/spreadsheets/d/abc/edit" target="_blank" rel="noopener noreferrer" aria-label="Abrir matriz: Matriz de control"' in first_page
    assert ">Abrir matriz <svg" in first_page
    assert ".favorito-card-hitarea{position:absolute;inset:0;z-index:1" in first_page
    assert ".favorito-actions{position:relative;z-index:2" in first_page
    assert "docs.google.com" in first_page

    data = json.loads(path.read_text(encoding="utf-8"))
    favorite_id = data[0]["id"]
    edited = client.post(
        f"/matrices-favoritas/{favorite_id}/editar",
        data={"nombre": "Matriz actualizada", "url": "https://docs.google.com/spreadsheets/d/def/edit"},
        follow_redirects=False,
    )
    assert edited.status_code == 303
    updated_page = client.get(edited.headers["location"]).text
    assert "Matriz actualizada" in updated_page
    assert "<h2>Matriz de control</h2>" not in updated_page
    assert "https://docs.google.com/spreadsheets/d/def/edit" in updated_page

    deleted = client.post(f"/matrices-favoritas/{favorite_id}/eliminar", follow_redirects=False)
    assert deleted.status_code == 303
    assert "Aún no tienes matrices guardadas" in client.get(deleted.headers["location"]).text
    assert json.loads(path.read_text(encoding="utf-8")) == []


def test_rejects_unsafe_or_malformed_favorite_urls(monkeypatch, tmp_path):
    path = tmp_path / "matrices_favoritas.json"
    monkeypatch.setattr("auto_prizma.services.matrix_favorites.FAVORITES_PATH", str(path))
    response = _client().post(
        "/matrices-favoritas/agregar",
        data={"nombre": "Enlace no seguro", "url": "javascript:alert(1)"},
    )
    assert response.status_code == 400
    assert "URL HTTP o HTTPS válida" in response.text
    assert not path.exists()


def test_favorite_names_are_html_escaped(monkeypatch, tmp_path):
    monkeypatch.setattr(
        "auto_prizma.services.matrix_favorites.FAVORITES_PATH",
        str(tmp_path / "matrices_favoritas.json"),
    )
    client = _client()
    client.post(
        "/matrices-favoritas/agregar",
        data={"nombre": '<script>alert("x")</script>', "url": "https://example.org/matrix"},
    )
    page = client.get("/matrices-favoritas").text
    assert "<script>alert(\"x\")</script>" not in page
    assert "&lt;script&gt;" in page
