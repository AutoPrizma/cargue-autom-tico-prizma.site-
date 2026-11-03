"""Estado en memoria de los tests evaluativos y utilidades de sesion y credenciales de PRIZMA.
"""

from __future__ import annotations

import json
import os
import threading
import uuid

from fastapi import Request

from auto_prizma.core.config import BASE_DIR
from auto_prizma.core.storage import write_json_atomic

from .models import Severity


_JOBS: dict[str, dict] = {}
_JOBS_LOCK = threading.RLock()
_AUTOMATION_JOBS: dict[str, dict] = {}
_AUTOMATION_LOCK = threading.RLock()
_AUTOMATION_SYNC: dict[str, dict] = {}
DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"




def _ruta_token_prizma(usuario: str) -> str:
    # Conserva la ruta historica <raiz>/data/tokens (no usa AUTO_PRIZMA_DATA_DIR).
    tokens_dir = os.path.join(BASE_DIR, "data", "tokens")
    os.makedirs(tokens_dir, exist_ok=True)
    return os.path.join(tokens_dir, f"prizma_{usuario}.json")


def _cargar_credenciales_prizma(usuario: str) -> dict:
    ruta = _ruta_token_prizma(usuario)
    if os.path.exists(ruta):
        try:
            with open(ruta, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"usuario": "", "recordar": True}


def _guardar_credenciales_prizma(usuario: str, creds: dict):
    ruta = _ruta_token_prizma(usuario)
    try:
        write_json_atomic(ruta, creds)
    except Exception:
        pass


def register_test_job(owner: str, document, created_at: str, cascada_datos: dict | None = None) -> str:
    """Registra en memoria un documento de tests ya analizado y devuelve su id.

    Lo usan el modulo /tests y el analisis combinado de la pagina de inicio.

    Args:
        owner: usuario de la aplicacion dueno del analisis.
        document: TestDocument resultado del parser.
        created_at: fecha ISO de creacion.
        cascada_datos: datos academicos (programa, pensum, nivel, asignatura)
            cuando el test viene del formulario de inicio.

    Returns:
        Identificador del job en _JOBS.
    """
    job_id = uuid.uuid4().hex
    job = {
        "owner": owner,
        "document": document,
        "created_at": created_at,
    }
    if cascada_datos is not None:
        job["cascada_datos"] = cascada_datos

    with _JOBS_LOCK:
        _JOBS[job_id] = job

    return job_id


def _user(request: Request) -> str:
    return str(getattr(request.state, "usuario", "") or "").strip().lower()


def _job_for(request: Request, job_id: str) -> dict | None:
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        if not job or job.get("owner") != _user(request):
            return None
        return job


def _issue_counts(issues):
    return {
        "error": sum(issue.severity is Severity.ERROR for issue in issues),
        "warning": sum(issue.severity is Severity.WARNING for issue in issues),
    }
