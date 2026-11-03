"""Rutas de la auditoria profunda de cursos de Moodle (solo lectura).

Solo funcionan desde la instancia local, como todo lo de Moodle: la
auditoria abre Chromium visible en este equipo y el login de Moodle lo hace
la persona. El curso se recorre tal cual esta; nada se sube ni se edita.
"""

import ipaddress
import os

from fastapi import File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse

from auto_prizma.core.application import app
from auto_prizma.services.auth import _usuario_actual
from auto_prizma.services.moodle_audit import (
    active_moodle_audit,
    cancel_moodle_audit,
    get_moodle_audit_job,
    latest_moodle_audit,
    public_moodle_audit_status,
    start_moodle_audit,
)
from auto_prizma.web.course_audit_views import render_moodle_audit_page


def _request_is_local(request):
    host = str(request.client.host if request.client else "").split("%", 1)[0]
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host.lower() == "localhost"


def _owner():
    return str(_usuario_actual() or "")


@app.get("/moodle-auditor-curso", response_class=HTMLResponse)
def moodle_audit_page(request: Request, nueva: bool = False):
    if not _request_is_local(request):
        return HTMLResponse(
            render_moodle_audit_page(local=False),
            status_code=403,
        )
    owner = _owner()
    job = active_moodle_audit(owner) or (None if nueva else latest_moodle_audit(owner))
    return HTMLResponse(render_moodle_audit_page(job, local=True))


@app.post("/moodle-auditor-curso/iniciar", response_class=HTMLResponse)
def moodle_audit_start(
    request: Request,
    course_url: str = Form(""),
    matriz: UploadFile | None = File(None),
    ):
    if not _request_is_local(request):
        return HTMLResponse(
            render_moodle_audit_page(local=False),
            status_code=403,
        )
    owner = _owner()
    try:
        matrix_bytes = matriz.file.read(20 * 1024 * 1024 + 1) if matriz else None
        start_moodle_audit(
            owner,
            course_url,
            matriz.filename if matriz else "",
            matrix_bytes,
        )
    except ValueError as exc:
        return HTMLResponse(
            render_moodle_audit_page(error=str(exc), local=True),
            status_code=400,
        )
    return RedirectResponse("/moodle-auditor-curso", status_code=303)


@app.get("/moodle-auditor-curso/{job_id}/estado")
def moodle_audit_status(job_id: str, request: Request):
    if not _request_is_local(request):
        return JSONResponse(
            {"error": "Disponible solo desde la instancia local."},
            status_code=403,
        )
    job = get_moodle_audit_job(job_id, _owner())
    if not job:
        return JSONResponse({"error": "Auditoría no encontrada."}, status_code=404)
    return JSONResponse(public_moodle_audit_status(job))


@app.post("/moodle-auditor-curso/{job_id}/cancelar")
def moodle_audit_cancel(job_id: str, request: Request):
    if not _request_is_local(request):
        return JSONResponse(
            {"error": "Disponible solo desde la instancia local."},
            status_code=403,
        )
    job = get_moodle_audit_job(job_id, _owner())
    if not job:
        return JSONResponse({"error": "Auditoría no encontrada."}, status_code=404)
    try:
        cancel_moodle_audit(job)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=409)
    return JSONResponse(public_moodle_audit_status(job))


@app.get("/moodle-auditor-curso/{job_id}/reporte")
def moodle_audit_report(job_id: str, request: Request, formato: str = "csv"):
    if not _request_is_local(request):
        return JSONResponse(
            {"error": "Disponible solo desde la instancia local."},
            status_code=403,
        )
    job = get_moodle_audit_job(job_id, _owner())
    if not job or not job.get("report"):
        return JSONResponse(
            {"error": "Reporte de auditoría no disponible."},
            status_code=404,
        )
    if formato not in {"json", "csv"}:
        return JSONResponse(
            {"error": "Formato de reporte no válido."},
            status_code=400,
        )
    clave = "jsonPath" if formato == "json" else "csvPath"
    path = str((job.get("report_paths") or {}).get(clave) or "")
    if not path or not os.path.isfile(path):
        return JSONResponse(
            {"error": "El reporte de auditoría ya no está disponible."},
            status_code=404,
        )
    media_type = "application/json" if formato == "json" else "text/csv"
    return FileResponse(path, media_type=media_type, filename=os.path.basename(path))
