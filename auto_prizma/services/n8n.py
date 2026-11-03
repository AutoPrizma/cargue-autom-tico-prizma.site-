"""Catálogo y puente servidor-servidor para las automatizaciones n8n."""

import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen

from auto_prizma.core.config import (
    N8N_STATUS_TIMEOUT_SECONDS,
    N8N_STATUS_WEBHOOK_DEFAULTS,
    N8N_TIMEOUT_SECONDS,
    N8N_WEBHOOK_DEFAULTS,
    env_str,
)


FLOWS = (
    {
        "id": "aut-tests",
        "code": "NX-001",
        "name": "Generar tests JSON",
        "description": "Convierte un Google Doc con tests en archivos JSON y entrega la carpeta temporal de Drive.",
        "category": "Tests",
        "action": "Generar tests",
        "footer": "Se creará una carpeta temporal en tu Google Drive con los archivos JSON generados.",
        "webhook_env": "N8N_WEBHOOK_AUT_TESTS",
        "fields": (("googleDocUrl", "Enlace del Google Doc", "url", "https://docs.google.com/document/d/.../edit", ""),),
    },
    {
        "id": "descargar-recursos",
        "code": "NX-002",
        "name": "Descarga de recursos",
        "description": "Descarga los recursos listados en una hoja de Google Sheets, con opción de dividirlos por unidad.",
        "category": "Recursos",
        "action": "Descargar recursos",
        "footer": "La pantalla mostrará «Cargando recursos…» hasta que todos estén copiados en Google Drive; la carpeta estará disponible por 30 minutos.",
        "webhook_env": "N8N_WEBHOOK_DESCARGAR_RECURSOS",
        "status_webhook_env": "N8N_WEBHOOK_DESCARGAR_RECURSOS_ESTADO",
        "fields": (
            ("sheetUrl", "URL de la hoja (Google Sheet)", "url", "https://docs.google.com/spreadsheets/d/.../edit", "Cópiala y pégala tal cual desde la barra del navegador."),
            ("dividirPorUnidad", "Dividir recursos por unidad", "select", "", "Este proceso puede tardar varios minutos."),
        ),
    },
    {
        "id": "matriz-csv",
        "code": "NX-003",
        "name": "Matriz de importación CSV",
        "description": "Genera la matriz de importación a partir de la plantilla de la asignatura y sus códigos.",
        "category": "Matrices",
        "action": "Generar matriz",
        "footer": "Se generará un archivo CSV listo para importar, guardado en tu Google Drive.",
        "webhook_env": "N8N_WEBHOOK_MATRIZ_CSV",
        "fields": (
            ("codigos", "Código Programa (PR) + Pensum (PS) + Asignatura (AS)", "text", "PR PS AS Nombre de la asignatura", "Pega los códigos en ese orden, seguidos del nombre de la asignatura."),
            ("filaInicio", "Fila desde la que inicia la tabla", "select", "5", "Por defecto la plantilla inicia en la fila 5."),
            ("plantillaUrl", "URL de la plantilla de la asignatura", "url", "https://docs.google.com/spreadsheets/d/...", ""),
        ),
    },
    {
        "id": "plantillas-tematicas",
        "code": "NX-004",
        "name": "Generador de plantillas temáticas",
        "description": "Crea las plantillas temáticas a partir de una carpeta principal de Google Drive.",
        "category": "Plantillas",
        "action": "Generar plantilla",
        "footer": "Se creará la plantilla temática en Google Drive a partir de la carpeta indicada.",
        "webhook_env": "N8N_WEBHOOK_PLANTILLAS",
        "fields": (("folderUrl", "Link de la carpeta principal", "url", "https://drive.google.com/drive/folders/...", "Solo la carpeta principal, no una subcarpeta."),),
    },
)

_BY_ID = {flow["id"]: flow for flow in FLOWS}
_NO_DISPONIBLE = {502, 503, 504}
_MENSAJE_NO_DISPONIBLE = (
    "El servidor de automatizaciones no está disponible en este momento. "
    "Espera unos minutos y vuelve a intentarlo; si sigue igual, avisa al administrador."
)
_MENSAJE_FALLO_FLUJO = (
    "n8n no pudo completar el proceso. Verifica que el enlace sea correcto y que el archivo o la carpeta "
    "estén compartidos con la cuenta de automatizaciones, y vuelve a intentarlo."
)
_MENSAJE_TARDANZA = (
    "n8n está tardando más de lo normal en responder. El proceso puede seguir en curso: "
    "revisa la carpeta de destino en Google Drive en unos minutos antes de volver a intentarlo."
)


def public_flow_catalog():
    """Devuelve el catálogo para la vista sin revelar URLs de webhooks."""
    return [
        {**flow, "configured": bool(env_str(flow["webhook_env"]) or N8N_WEBHOOK_DEFAULTS.get(flow["id"]))}
        for flow in FLOWS
    ]


def execute_flow(flow_id, payload):
    """Envía un payload validado al webhook configurado, solo desde el servidor."""
    flow = _BY_ID.get(flow_id)
    if not flow:
        return {"ok": False, "message": "Ese flujo no existe."}, 404

    allowed = {field[0] for field in flow["fields"]}
    if not isinstance(payload, dict) or set(payload) - allowed:
        return {"ok": False, "message": "Los datos enviados no coinciden con el formulario."}, 400
    clean_payload = {key: str(value).strip() for key, value in payload.items() if isinstance(value, (str, int, float))}
    for key, label, kind, _placeholder, _hint in flow["fields"]:
        value = clean_payload.get(key, "")
        if not value:
            return {"ok": False, "message": "Completa el campo «" + label + "»."}, 400
        if kind == "url":
            parsed_value = urlparse(value)
            if parsed_value.scheme not in {"http", "https"} or not parsed_value.netloc:
                return {"ok": False, "message": "Ingresa un enlace válido en «" + label + "»."}, 400
        if key == "dividirPorUnidad" and value not in {"Si", "No"}:
            return {"ok": False, "message": "Elige Sí o No para dividir los recursos por unidad."}, 400
        if key == "filaInicio" and value not in {"3", "4", "5", "6", "7"}:
            return {"ok": False, "message": "La fila de inicio debe estar entre 3 y 7."}, 400

    webhook_url = env_str(flow["webhook_env"]) or N8N_WEBHOOK_DEFAULTS.get(flow_id, "")
    if not webhook_url:
        return {
            "ok": True,
            "demo": True,
            "message": "Este flujo todavía no está configurado. Solicita al administrador que agregue su webhook n8n.",
        }, 200
    parsed = urlparse(webhook_url)
    if parsed.scheme != "https" or not parsed.netloc:
        return {"ok": False, "message": "La URL del webhook no está configurada correctamente (se requiere HTTPS)."}, 503

    headers = {"Content-Type": "application/json"}
    shared_secret = env_str("N8N_SHARED_SECRET")
    if shared_secret:
        headers["x-n8n-secret"] = shared_secret
    request = Request(webhook_url, data=json.dumps(clean_payload).encode("utf-8"), headers=headers, method="POST")

    try:
        with urlopen(request, timeout=N8N_TIMEOUT_SECONDS) as response:
            raw = response.read(2_000_001)
            if len(raw) > 2_000_000:
                return {"ok": False, "message": "La respuesta de n8n excedió el tamaño permitido."}, 502
            content_type = response.headers.get("Content-Type", "")
            data = json.loads(raw.decode("utf-8")) if "json" in content_type else {"raw": raw.decode("utf-8", "replace")}
            if not 200 <= response.status < 300:
                return {"ok": False, "message": _response_message(data, "n8n respondió con un error."), "data": data}, 502
            if isinstance(data, dict) and data.get("ok") is False:
                # El flujo terminó pero detectó un problema con los datos (enlace, tabla, permisos…).
                return {"ok": False, "message": _response_message(data, "n8n no pudo completar el proceso."), "data": data}, 422
            return {"ok": True, "message": _response_message(data, "La automatización terminó correctamente."), "data": data}, 200
    except HTTPError as error:
        if error.code in _NO_DISPONIBLE:
            return {"ok": False, "message": _MENSAJE_NO_DISPONIBLE}, 503
        if error.code == 500:
            return {"ok": False, "message": _MENSAJE_FALLO_FLUJO}, 502
        if 400 <= error.code < 500:
            # Algunos flujos responden 4xx con un JSON {ok:false, message} que explica el problema.
            detalle = _error_message(error)
            if detalle:
                return {"ok": False, "message": detalle}, 422
        return {"ok": False, "message": "n8n respondió con estado " + str(error.code) + "."}, 502
    except TimeoutError:
        return {"ok": False, "message": _MENSAJE_TARDANZA}, 504
    except (URLError, OSError, ValueError) as error:
        if isinstance(getattr(error, "reason", None), TimeoutError):
            return {"ok": False, "message": _MENSAJE_TARDANZA}, 504
        print("Error al contactar n8n:", type(error).__name__)
        return {"ok": False, "message": "No se pudo contactar n8n. Revisa la conexión o la configuración del webhook."}, 502


_JOB_ID = re.compile(r"^[0-9A-Za-z_-]{1,40}$")
_STATUSES = {"processing", "done"}


def get_flow_status(flow_id, job_id):
    """Consulta, solo desde el servidor, el avance de un flujo largo en n8n."""
    flow = _BY_ID.get(flow_id)
    if not flow or not flow.get("status_webhook_env"):
        return {"ok": False, "message": "Ese flujo no tiene consulta de estado."}, 404
    job_id = str(job_id or "").strip()
    if not _JOB_ID.match(job_id):
        return {"ok": False, "message": "El identificador del proceso no es válido."}, 400

    status_url = env_str(flow["status_webhook_env"]) or N8N_STATUS_WEBHOOK_DEFAULTS.get(flow_id, "")
    parsed = urlparse(status_url)
    if parsed.scheme != "https" or not parsed.netloc:
        return {"ok": False, "message": "La consulta de estado no está configurada correctamente (se requiere HTTPS)."}, 503

    headers = {"Accept": "application/json"}
    shared_secret = env_str("N8N_SHARED_SECRET")
    if shared_secret:
        headers["x-n8n-secret"] = shared_secret
    separator = "&" if parsed.query else "?"
    request = Request(status_url + separator + urlencode({"jobId": job_id}), headers=headers, method="GET")

    try:
        with urlopen(request, timeout=N8N_STATUS_TIMEOUT_SECONDS) as response:
            raw = response.read(200_001)
            if len(raw) > 200_000:
                return {"ok": False, "message": "La respuesta de n8n excedió el tamaño permitido."}, 502
            data = json.loads(raw.decode("utf-8"))
    except HTTPError as error:
        if error.code in _NO_DISPONIBLE:
            return {"ok": False, "message": _MENSAJE_NO_DISPONIBLE}, 503
        return {"ok": False, "message": "n8n respondió con estado " + str(error.code) + " al consultar el avance."}, 502
    except (URLError, TimeoutError, OSError, ValueError) as error:
        print("Error al consultar estado en n8n:", type(error).__name__)
        return {"ok": False, "message": "No se pudo consultar el avance en n8n. Se reintentará."}, 502

    if not isinstance(data, dict) or data.get("ok") is False:
        return {"ok": False, "status": "unknown", "message": _response_message(data, "No se encontró el proceso de descarga.")}, 404
    status = data.get("status") if data.get("status") in _STATUSES else "processing"
    return {"ok": True, "status": status, "message": _response_message(data, "Cargando recursos…"), "data": data}, 200


def _error_message(error):
    """Lee el mensaje JSON de una respuesta de error de n8n, si lo trae."""
    try:
        data = json.loads(error.read(200_001).decode("utf-8"))
    except (AttributeError, OSError, TypeError, ValueError):
        return ""
    if not isinstance(data, dict):
        return ""
    message = _response_message(data, "")
    recomendacion = data.get("recomendacion")
    if message and isinstance(recomendacion, str) and recomendacion.strip():
        message += " " + recomendacion.strip()
    return message


def _response_message(data, fallback):
    if isinstance(data, dict) and isinstance(data.get("message"), str) and data["message"].strip():
        return data["message"].strip()
    return fallback
