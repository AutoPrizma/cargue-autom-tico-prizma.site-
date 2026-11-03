"""Rutas web para analizar y publicar recursos de Moodle desde una instancia local."""

import ipaddress
import hashlib
import html
import json
import os
import time

from fastapi import File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse

from auto_prizma.core.application import app
from auto_prizma.services.auth import _usuario_actual
from auto_prizma.core.config import DATA_DIR, LOCAL_DATA_RETENTION_DAYS
from auto_prizma.services.moodle_resources import (
    cancel_moodle_publish,
    attach_manual_resource,
    create_moodle_preview,
    get_moodle_job,
    MAX_MANUAL_RESOURCE_BYTES,
    pause_moodle_publish,
    public_moodle_status,
    resume_moodle_publish,
    start_moodle_publish,
)
from auto_prizma.web.moodle_views import render_moodle_labels_page, render_moodle_page
from auto_prizma.web.icons import icon
from auto_prizma.web.layout import render_page


def _request_is_local(request):
    host = str(request.client.host if request.client else "").split("%", 1)[0]
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host.lower() == "localhost"


def _owner():
    return str(_usuario_actual() or "")


def _moodle_report_dir():
    owner_hash = hashlib.sha256(_owner().encode("utf-8")).hexdigest()[:24]
    return os.path.join(DATA_DIR, "reportes", "moodle", owner_hash)


def _limpiar_reportes_moodle(report_dir):
    """Elimina pares de reportes locales con más de 15 días."""
    try:
        filenames = os.listdir(report_dir)
    except FileNotFoundError:
        return
    limite = time.time() - LOCAL_DATA_RETENTION_DAYS * 24 * 60 * 60
    bases = {
        os.path.splitext(nombre)[0]
        for nombre in filenames
        if nombre.startswith(("moodle-cargue-", "moodle-auditoria-")) and nombre.endswith((".json", ".csv"))
    }
    for base in bases:
        paths = [os.path.join(report_dir, base + extension) for extension in (".json", ".csv")]
        existentes = [ruta for ruta in paths if os.path.isfile(ruta)]
        if existentes and all(os.path.getmtime(ruta) < limite for ruta in existentes):
            for ruta in existentes:
                try:
                    os.remove(ruta)
                except OSError:
                    pass


@app.get("/moodle-reportes", response_class=HTMLResponse)
def moodle_reports(request: Request):
    if not _request_is_local(request):
        return HTMLResponse(
            render_page("Reportes de Moodle", '<section class="panel panel-contenido"><h1>Reportes de Moodle</h1><p>Disponible solo desde la instancia local.</p></section>', active="moodle-reportes"),
            status_code=403,
        )
    report_dir = _moodle_report_dir()
    _limpiar_reportes_moodle(report_dir)
    rows = []
    report_summaries = []
    try:
        filenames = sorted(
            (name for name in os.listdir(report_dir) if name.startswith("moodle-cargue-") and name.endswith(".json")),
            key=lambda name: os.path.getmtime(os.path.join(report_dir, name)),
            reverse=True,
        )
    except FileNotFoundError:
        filenames = []
    for filename in filenames:
        path = os.path.join(report_dir, filename)
        try:
            with open(path, encoding="utf-8") as stream:
                report = json.load(stream)
        except (OSError, ValueError):
            continue
        summary = report.get("summary") or {}
        stamp_iso = str(report.get("createdAt") or "")
        stamp = stamp_iso.replace("T", " ").replace("+00:00", " UTC")
        uploaded = int(summary.get("uploaded", 0) or 0)
        already = int(summary.get("alreadyPresent", 0) or 0)
        pending = int(summary.get("notLoaded", 0) or 0) + int(summary.get("needsReview", 0) or 0) + int(summary.get("notProcessed", 0) or 0)
        state = "pendiente" if pending else "completo"
        report_summaries.append({"uploaded": uploaded, "already": already, "pending": pending})
        safe_filename = html.escape(filename, quote=True)
        links = (
            '<a class="boton secundario chico" href="/moodle-reportes/' + safe_filename + '?formato=csv">CSV</a> '
            '<a class="boton secundario chico" href="/moodle-reportes/' + safe_filename + '?formato=json">JSON</a>'
        )
        search_text = " ".join((filename, stamp, str(uploaded), str(already), str(pending))).lower()
        rows.append(
            '<tr data-fila data-fecha="' + html.escape(stamp_iso, quote=True) + '" data-estado="' + state
            + '" data-busqueda="' + html.escape(search_text, quote=True) + '">'
            '<td class="celda-fecha" data-valor="' + html.escape(stamp_iso, quote=True) + '"><strong>'
            + html.escape(stamp or filename) + '</strong><small>' + safe_filename + '</small></td>'
            '<td data-valor="' + str(uploaded) + '">' + str(uploaded) + '</td>'
            '<td data-valor="' + str(already) + '">' + str(already) + '</td>'
            '<td data-valor="' + str(pending) + '">' + str(pending) + '</td>'
            '<td class="celda-acciones">' + links + '</td></tr>'
        )
    total = len(rows)
    uploaded_total = sum(item["uploaded"] for item in report_summaries)
    already_total = sum(item["already"] for item in report_summaries)
    pending_total = sum(item["pending"] for item in report_summaries)
    if not rows:
        rows.append('<tr class="fila-vacia"><td colspan="5">Aún no hay reportes de Moodle.</td></tr>')
    plural = "" if total == 1 else "s"
    date_options = (
        '<option value="">Todas las fechas</option><option value="hoy">Hoy</option>'
        '<option value="7">Últimos 7 días</option><option value="15">Últimos 15 días</option>'
    )
    body = (
        '<header class="encabezado"><div class="encabezado-titulo"><span class="icono-tile grande">' + icon("documento")
        + '</span><div><h1>Reportes de Moodle</h1><p>Reportes de publicaciones realizadas desde este equipo.</p></div></div>'
        + '<span class="chip grande">' + icon("documento") + f'{total} reporte{plural}</span></header>'
        + '<div class="panel herramientas dos">'
        + '<label class="campo">' + icon("buscar") + '<span class="sr-only">Buscar</span>'
        + '<input type="search" placeholder="Buscar reporte o fecha..." data-control-tabla="tabla-moodle-reportes" data-tipo="buscar"></label>'
        + '<label class="campo">' + icon("alerta-circulo")
        + '<select data-control-tabla="tabla-moodle-reportes" data-tipo="filtro" data-campo="estado" aria-label="Estado del reporte">'
        + '<option value="">Todos los resultados</option><option value="completo">Sin pendientes</option><option value="pendiente">Con pendientes</option></select>'
        + icon("chevron", "icono icono-chevron") + '</label>'
        + '<label class="campo">' + icon("calendario")
        + '<select data-control-tabla="tabla-moodle-reportes" data-tipo="fecha" aria-label="Filtrar por fecha">' + date_options + '</select>'
        + icon("chevron", "icono icono-chevron") + '</label></div>'
        + '<section class="mosaicos" aria-label="Resumen de reportes Moodle">'
        + '<div class="mosaico"><span class="icono-tile">' + icon("documento") + '</span><div><strong class="num">' + str(total) + '</strong><span>Reportes generados</span></div></div>'
        + '<div class="mosaico"><span class="icono-tile verde">' + icon("subir") + '</span><div><strong class="num">' + str(uploaded_total) + '</strong><span>Recursos cargados</span></div></div>'
        + '<div class="mosaico"><span class="icono-tile azul">' + icon("ver") + '</span><div><strong class="num">' + str(already_total) + '</strong><span>Ya estaban cargados</span></div></div>'
        + '<div class="mosaico"><span class="icono-tile ambar">' + icon("alerta-circulo") + '</span><div><strong class="num">' + str(pending_total) + '</strong><span>Pendientes / revisión</span></div></div>'
        + '</section>'
        + '<section class="panel tabla-panel" id="tabla-moodle-reportes" data-tabla data-unidad="reportes" data-por-pagina="10">'
        + '<div class="tabla-scroll"><table class="tabla"><thead><tr>'
        + '<th data-orden="texto" data-orden-inicial="desc"><button type="button" class="orden">Fecha de generación' + icon("ordenar") + '</button></th>'
        + '<th data-orden="numero"><button type="button" class="orden">Cargados' + icon("ordenar") + '</button></th>'
        + '<th data-orden="numero"><button type="button" class="orden">Ya estaban' + icon("ordenar") + '</button></th>'
        + '<th data-orden="numero"><button type="button" class="orden">Pendientes / revisión' + icon("ordenar") + '</button></th>'
        + '<th>Descargar</th></tr></thead><tbody>' + ''.join(rows) + '</tbody></table></div>'
        + '<div class="tabla-pie"><span data-tabla-resumen>' + ('Sin reportes todavía' if not total else f'Mostrando 1 – {min(10, total)} de {total} reportes') + '</span>'
        + '<div class="tabla-pie-derecha"><label><span class="sr-only">Filas por página</span><select data-tabla-tamano>'
        + '<option value="10" selected>10 por página</option><option value="25">25 por página</option><option value="50">50 por página</option>'
        + '</select></label><nav class="paginas" data-tabla-paginas aria-label="Páginas"></nav></div></div></section>'
    )
    return HTMLResponse(render_page("Reportes de Moodle", body, active="moodle-reportes"))


@app.get("/moodle-reportes/{filename}")
def moodle_saved_report(filename: str, request: Request, formato: str = "csv"):
    if not _request_is_local(request):
        return JSONResponse({"error": "Disponible solo desde la instancia local."}, status_code=403)
    _limpiar_reportes_moodle(_moodle_report_dir())
    if formato not in {"csv", "json"} or os.path.basename(filename) != filename or not filename.startswith("moodle-cargue-") or not filename.endswith(".json"):
        return JSONResponse({"error": "Reporte Moodle no válido."}, status_code=404)
    stem = filename[:-5]
    path = os.path.join(_moodle_report_dir(), stem + (".csv" if formato == "csv" else ".json"))
    if not os.path.isfile(path):
        return JSONResponse({"error": "No se encontró el reporte Moodle."}, status_code=404)
    media_type = "text/csv" if formato == "csv" else "application/json"
    return FileResponse(path, media_type=media_type, filename=os.path.basename(path))


@app.get("/moodle", response_class=HTMLResponse)
def moodle_home(request: Request):
    local = _request_is_local(request)
    return HTMLResponse(
        render_moodle_page(local=local),
        status_code=200 if local else 403,
    )


@app.get("/moodle-etiquetas", response_class=HTMLResponse)
def moodle_labels(request: Request):
    local = _request_is_local(request)
    return HTMLResponse(
        render_moodle_labels_page(local=local),
        status_code=200 if local else 403,
    )


@app.post("/moodle/analizar", response_class=HTMLResponse)
async def moodle_analyze(
    request: Request,
    matriz_archivo: UploadFile = File(...),
    recursos_zip: UploadFile = File(...),
    course_url: str = Form(...),
):
    if not _request_is_local(request):
        return HTMLResponse(render_moodle_page(local=False), status_code=403)
    try:
        matrix_bytes = await matriz_archivo.read()
        zip_bytes = await recursos_zip.read()
        if not matrix_bytes or not zip_bytes:
            raise ValueError("Selecciona la matriz y el archivo ZIP de recursos.")
        job = create_moodle_preview(
            _owner(),
            matriz_archivo.filename,
            matrix_bytes,
            recursos_zip.filename,
            zip_bytes,
            course_url,
        )
    except (ValueError, OSError, UnicodeDecodeError) as exc:
        return HTMLResponse(
            render_moodle_page(error=str(exc), local=True),
            status_code=400,
        )
    return RedirectResponse("/moodle/" + job["id"], status_code=303)


@app.get("/moodle/{job_id}", response_class=HTMLResponse)
def moodle_job_page(job_id: str, request: Request, vista: str = ""):
    if not _request_is_local(request):
        return HTMLResponse(render_moodle_page(local=False), status_code=403)
    job = get_moodle_job(job_id, _owner())
    if not job:
        return HTMLResponse(render_moodle_page(error="No se encontró la vista previa Moodle."), status_code=404)
    # ?vista=previa vuelve a mostrar la matriz después de una publicación terminada.
    return HTMLResponse(render_moodle_page(job, local=True, show_preview=vista == "previa"))


@app.post("/moodle/{job_id}/publicar", response_class=HTMLResponse)
def moodle_publish(
    job_id: str,
    request: Request,
    publish_mode: str = Form(...),
    entry_keys: list[str] = Form(default=[]),
    clean_labels: str = Form(default=""),
):
    if not _request_is_local(request):
        return HTMLResponse(render_moodle_page(local=False), status_code=403)
    job = get_moodle_job(job_id, _owner())
    if not job:
        return HTMLResponse(render_moodle_page(error="No se encontró la vista previa Moodle."), status_code=404)
    try:
        start_moodle_publish(job, publish_mode, entry_keys, clean_labels=clean_labels == "1")
    except ValueError as exc:
        return HTMLResponse(render_moodle_page(job, error=str(exc), local=True), status_code=400)
    return RedirectResponse("/moodle/" + job_id, status_code=303)


@app.get("/moodle/{job_id}/estado")
def moodle_job_status(job_id: str, request: Request):
    if not _request_is_local(request):
        return JSONResponse({"error": "Disponible solo desde la instancia local."}, status_code=403)
    job = get_moodle_job(job_id, _owner())
    if not job:
        return JSONResponse({"error": "Vista previa no encontrada."}, status_code=404)
    return public_moodle_status(job)


@app.post("/moodle/{job_id}/recurso-manual")
async def moodle_attach_manual_resource(
    job_id: str,
    request: Request,
    entry_key: str = Form(...),
    resource_file: UploadFile = File(...),
):
    if not _request_is_local(request):
        return JSONResponse({"error": "Disponible solo desde la instancia local."}, status_code=403)
    job = get_moodle_job(job_id, _owner())
    if not job:
        return JSONResponse({"error": "Vista previa no encontrada."}, status_code=404)
    try:
        if job.get("status") in {"queued", "logging_in", "publishing", "paused"}:
            raise ValueError("Espera a que termine la publicación antes de cambiar un archivo.")
        content = await resource_file.read(MAX_MANUAL_RESOURCE_BYTES + 1)
        if len(content) > MAX_MANUAL_RESOURCE_BYTES:
            raise ValueError("El archivo supera el límite de 200 MB para una carga manual.")
        attach_manual_resource(job, entry_key, resource_file.filename, content)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=400)
    except OSError:
        return JSONResponse({"error": "No se pudo guardar el archivo seleccionado."}, status_code=500)
    return JSONResponse({"ok": True, "message": "Archivo asociado a la fila."})


_CONTROL_ACTIONS = {
    "pausar": pause_moodle_publish,
    "reanudar": resume_moodle_publish,
    "cancelar": cancel_moodle_publish,
}


@app.post("/moodle/{job_id}/{action}")
def moodle_control(job_id: str, action: str, request: Request):
    """Pausar, reanudar o cancelar la publicación en curso (lo usa la página con fetch)."""
    if action not in _CONTROL_ACTIONS:
        return JSONResponse({"error": "Acción no válida."}, status_code=404)
    if not _request_is_local(request):
        return JSONResponse({"error": "Disponible solo desde la instancia local."}, status_code=403)
    job = get_moodle_job(job_id, _owner())
    if not job:
        return JSONResponse({"error": "Vista previa no encontrada."}, status_code=404)
    try:
        _CONTROL_ACTIONS[action](job)
    except ValueError as exc:
        return JSONResponse({"error": str(exc)}, status_code=409)
    return public_moodle_status(job)


@app.get("/moodle/{job_id}/reporte")
def moodle_download_report(job_id: str, request: Request, formato: str = "csv"):
    if not _request_is_local(request):
        return JSONResponse({"error": "Disponible solo desde la instancia local."}, status_code=403)
    job = get_moodle_job(job_id, _owner())
    if not job or not job.get("report"):
        return JSONResponse({"error": "Reporte Moodle no disponible."}, status_code=404)
    if formato not in {"json", "csv"}:
        return JSONResponse({"error": "Formato de reporte no válido."}, status_code=400)
    path = str((job.get("report_paths") or {}).get("jsonPath" if formato == "json" else "csvPath") or "")
    if not path or not os.path.isfile(path):
        return JSONResponse({"error": "El reporte Moodle ya no está disponible."}, status_code=404)
    media_type = "application/json" if formato == "json" else "text/csv"
    return FileResponse(path, media_type=media_type, filename=os.path.basename(path))
