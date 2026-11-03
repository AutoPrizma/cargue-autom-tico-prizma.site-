"""Persistencia del catálogo compartido de matrices y enlaces favoritos."""

import os
import threading
from urllib.parse import urlsplit
from uuid import uuid4

from auto_prizma.core.config import DATA_DIR
from auto_prizma.core.storage import read_json, write_json_atomic


FAVORITES_PATH = os.path.join(DATA_DIR, "matrices_favoritas.json")
_LOCK = threading.RLock()


def _validar(nombre, url):
    nombre = str(nombre or "").strip()
    url = str(url or "").strip()
    if not nombre:
        raise ValueError("Escribe un nombre para la matriz o el recurso.")
    if len(nombre) > 120:
        raise ValueError("El nombre no puede superar 120 caracteres.")
    if len(url) > 2048 or any(character.isspace() for character in url):
        raise ValueError("Escribe un enlace válido que empiece por https:// o http://.")
    try:
        parsed = urlsplit(url)
        valid_port = parsed.port is None or 1 <= parsed.port <= 65535
    except ValueError:
        valid_port = False
        parsed = None
    if (
        not parsed
        or parsed.scheme.lower() not in {"http", "https"}
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or not valid_port
    ):
        raise ValueError("El enlace debe ser una URL HTTP o HTTPS válida, sin usuario ni contraseña.")
    return nombre, url


def list_favorites():
    """Devuelve las tarjetas guardadas en su orden de creación."""
    with _LOCK:
        rows = read_json(FAVORITES_PATH, [], list)
        return [
            dict(row)
            for row in rows
            if isinstance(row, dict)
            and row.get("id")
            and row.get("nombre")
            and row.get("url")
        ]


def get_favorite(favorite_id):
    return next((row for row in list_favorites() if row["id"] == favorite_id), None)


def add_favorite(nombre, url):
    nombre, url = _validar(nombre, url)
    with _LOCK:
        rows = read_json(FAVORITES_PATH, [], list)
        row = {"id": uuid4().hex, "nombre": nombre, "url": url}
        rows = [item for item in rows if isinstance(item, dict)]
        rows.append(row)
        write_json_atomic(FAVORITES_PATH, rows)
        return row


def update_favorite(favorite_id, nombre, url):
    nombre, url = _validar(nombre, url)
    with _LOCK:
        rows = read_json(FAVORITES_PATH, [], list)
        for row in rows:
            if isinstance(row, dict) and row.get("id") == favorite_id:
                row.update(nombre=nombre, url=url)
                write_json_atomic(FAVORITES_PATH, rows)
                return dict(row)
    return None


def delete_favorite(favorite_id):
    with _LOCK:
        rows = read_json(FAVORITES_PATH, [], list)
        kept = [row for row in rows if not isinstance(row, dict) or row.get("id") != favorite_id]
        if len(kept) == len(rows):
            return False
        write_json_atomic(FAVORITES_PATH, kept)
        return True
