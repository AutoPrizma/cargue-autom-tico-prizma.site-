"""Vista de un reporte Moodle guardado (cargue o auditoría de curso).

Se abre desde /moodle-reportes con el botón «Ver» y muestra las filas del
JSON guardado con búsqueda, filtros y paginación del marco común (app.js),
sin necesidad de descargar el CSV.
"""

import html
import os

from auto_prizma.web.course_audit_views import (
    _CSS_AUDITORIA,
    _RENDER_LABELS,
    _estado_badge,
    _resumen_tarjetas,
)
from auto_prizma.web.icons import icon
from auto_prizma.web.layout import render_page
from auto_prizma.web.moodle_views import _CSS_MOODLE, _KIND_LABELS, _RESULT_STATUS


def _e(value):
    return html.escape(str(value if value is not None else ""), quote=True)


# Estados de la auditoría para el filtro (clave guardada en el JSON -> texto visible).
_AUDIT_FILTER = (
    ("ok", "Completo"),
    ("revisar", "Revisar"),
    ("falta", "Sin recurso"),
    ("no procesado", "No procesado"),
)

_CSS_REPORT_VIEW = """
.reporte-vista { display: grid; gap: 20px; }
.reporte-vista .encabezado { margin: 0; }
.reporte-vista .tabla-panel { padding: 22px 24px; }
.reporte-vista .herramientas { margin: 0; }
.reporte-vista .celda-sub { display: block; color: var(--muted); font-size: 11.5px; margin-top: 3px; }
.reporte-detalle { color: var(--muted); font-size: 12px; overflow-wrap: anywhere; min-width: 200px; max-width: 380px; }
.reporte-detalle details { margin-top: 6px; }
.reporte-detalle summary { cursor: pointer; color: var(--acento-texto); font-weight: 600; }
.reporte-detalle pre { margin: 6px 0 0; padding: 8px 10px; max-height: 260px; overflow: auto; white-space: pre-wrap; border: 1px solid var(--borde); border-radius: 8px; background: var(--panel-2); font-size: 11px; }
"""


_DETAIL_PREVIEW_CHARS = 160


def _detail_cell(text):
    """Detalle con la primera línea visible; el resto (p. ej. el call log de Playwright) se despliega."""
    text = str(text or "").strip()
    if not text:
        return '<td class="reporte-detalle">—</td>'
    first_line = text.splitlines()[0]
    if len(first_line) <= _DETAIL_PREVIEW_CHARS and first_line == text:
        return '<td class="reporte-detalle">' + _e(text) + "</td>"
    preview = first_line[:_DETAIL_PREVIEW_CHARS] + ("…" if len(first_line) > _DETAIL_PREVIEW_CHARS else "")
    return (
        '<td class="reporte-detalle">' + _e(preview)
        + '<details><summary>Ver detalle completo</summary><pre>' + _e(text) + "</pre></details></td>"
    )


def _options(pairs, label_all):
    return '<option value="">' + _e(label_all) + "</option>" + "".join(
        '<option value="' + _e(value) + '">' + _e(text) + "</option>" for value, text in pairs
    )


def _select(table_id, field, aria, options_html, icon_name):
    return (
        '<label class="campo">' + icon(icon_name)
        + '<select data-control-tabla="' + table_id + '" data-tipo="filtro" data-campo="' + field
        + '" aria-label="' + _e(aria) + '">' + options_html + "</select>"
        + icon("chevron", "icono icono-chevron") + "</label>"
    )


def _tools(table_id, status_options, weeks):
    week_options = _options(((week, week) for week in weeks), "Todas las semanas")
    return (
        '<div class="panel herramientas dos">'
        '<label class="campo">' + icon("buscar") + '<span class="sr-only">Buscar</span>'
        '<input type="search" placeholder="Buscar recurso, semana o detalle..." data-control-tabla="'
        + table_id + '" data-tipo="buscar"></label>'
        + _select(table_id, "estado", "Estado", status_options, "alerta-circulo")
        + _select(table_id, "semana", "Semana", week_options, "calendario")
        + "</div>"
    )


def _table(table_id, headers, rows_html, empty_text):
    columns = len(headers)
    return (
        '<section class="panel tabla-panel" id="' + table_id + '" data-tabla data-unidad="recursos" data-por-pagina="25">'
        '<div class="tabla-scroll"><table class="tabla"><thead><tr>'
        + "".join("<th>" + _e(header) + "</th>" for header in headers)
        + "</tr></thead><tbody>"
        + (rows_html or '<tr class="fila-vacia"><td colspan="' + str(columns) + '">' + _e(empty_text) + "</td></tr>")
        + "</tbody></table></div>"
        '<div class="tabla-pie"><span data-tabla-resumen></span>'
        '<div class="tabla-pie-derecha"><label><span class="sr-only">Filas por página</span><select data-tabla-tamano>'
        '<option value="10">10 por página</option><option value="25" selected>25 por página</option>'
        '<option value="50">50 por página</option><option value="100">100 por página</option>'
        '</select></label><nav class="paginas" data-tabla-paginas aria-label="Páginas"></nav></div></div></section>'
    )


def _row_attrs(status, week, *texts):
    search = " ".join(str(text or "") for text in (week, status) + texts).lower()
    return (
        '<tr data-fila data-estado="' + _e(status) + '" data-semana="' + _e(week)
        + '" data-busqueda="' + _e(search) + '">'
    )


def _weeks(rows, key):
    seen = []
    for row in rows:
        week = str(row.get(key) or "")
        if week and week not in seen:
            seen.append(week)
    return seen


def _audit_body(report, table_id):
    rows = report.get("rows") or []
    rows_html = []
    for item in rows:
        coincide = item.get("coincide")
        coincide_text, tone = ("Sí", "verde") if coincide is True else ("No", "rojo") if coincide is False else ("—", "gris")
        rows_html.append(
            _row_attrs(item.get("estado"), item.get("semana"), item.get("actividad"), item.get("titulo_interno"),
                       item.get("matriz_recurso"), item.get("matriz_estado"), item.get("detalle"))
            + "<td>" + _e(item.get("semana")) + "</td>"
            + "<td><strong>" + _e(item.get("actividad")) + "</strong></td>"
            + "<td>" + _e((item.get("tipo") or "").upper()) + "</td>"
            + "<td>" + _estado_badge(item.get("estado")) + "</td>"
            + "<td>" + _e(_RENDER_LABELS.get(item.get("renderiza"), item.get("renderiza"))) + "</td>"
            + '<td class="auditoria-titulo">' + _e(item.get("titulo_interno") or "—") + "</td>"
            + '<td><span class="badge badge-' + tone + '">' + _e(coincide_text) + "</span></td>"
            + "<td>" + _e(item.get("matriz_recurso") or "—") + "</td>"
            + "<td>" + _e(item.get("matriz_estado") or "—") + "</td>"
            + _detail_cell(item.get("detalle")) + "</tr>"
        )
    headers = ("Semana", "Recurso", "Tipo", "Estado", "Renderiza", "Título interno",
               "Coincide con actividad", "Nombre en matriz", "Comparación matriz", "Detalle")
    return (
        _resumen_tarjetas(report.get("summary") or {})
        + _tools(table_id, _options(_AUDIT_FILTER, "Todos los estados"), _weeks(rows, "semana"))
        + _table(table_id, headers, "".join(rows_html), "El reporte no tiene filas.")
    )


def _upload_body(report, table_id):
    rows = report.get("rows") or []
    summary = report.get("summary") or {}
    cards = (
        (summary.get("uploaded", 0), "Cargados", "verde", "subir"),
        (summary.get("alreadyPresent", 0), "Ya estaban", "azul", "ver"),
        (int(summary.get("notLoaded", 0) or 0) + int(summary.get("needsReview", 0) or 0), "Con problemas", "ambar", "alerta-circulo"),
        (summary.get("notProcessed", 0), "No procesados", "gris", "info"),
    )
    tiles = '<section class="mosaicos" aria-label="Resumen del cargue">' + "".join(
        '<div class="mosaico"><span class="icono-tile ' + tone + '">' + icon(icon_name) + '</span><div><strong class="num">'
        + str(int(value or 0)) + "</strong><span>" + _e(label) + "</span></div></div>"
        for value, label, tone, icon_name in cards
    ) + "</section>"
    rows_html = []
    for item in rows:
        status = str(item.get("status") or "")
        tone, help_text = _RESULT_STATUS.get(status, ("badge-gris", ""))
        kind = _KIND_LABELS.get(item.get("kind") or "", "")
        rows_html.append(
            _row_attrs(status, item.get("week"), item.get("title"), kind, item.get("detail"))
            + "<td>" + _e(item.get("week")) + "</td>"
            + "<td><strong>" + _e(item.get("title")) + "</strong>"
            + ('<span class="celda-sub">' + _e(kind) + "</span>" if kind else "") + "</td>"
            + '<td><span class="badge ' + tone + '">' + _e(status) + "</span>"
            + ('<span class="celda-sub">' + _e(help_text) + "</span>" if help_text else "") + "</td>"
            + '<td class="moodle-file">' + _e(os.path.basename(item.get("file") or "")) + "</td>"
            + _detail_cell(item.get("detail")) + "</tr>"
        )
    status_options = _options(((status, status) for status in _RESULT_STATUS), "Todos los resultados")
    labels = report.get("labels") or []
    labels_html = ""
    if labels:
        labels_html = (
            '<section class="panel tabla-panel"><div class="tabla-cabecera"><div><h2>Etiquetas sin uso</h2>'
            "<p>Etiquetas de bloque que la matriz no usa en cada semana.</p></div></div>"
            '<div class="tabla-scroll"><table class="tabla"><thead><tr><th>Semana</th><th>Etiqueta</th>'
            "<th>Resultado</th><th>Detalle</th></tr></thead><tbody>"
            + "".join(
                "<tr><td>" + _e(item.get("week")) + "</td><td>" + _e(item.get("label")) + "</td><td>"
                + _e(item.get("status")) + '</td><td class="reporte-detalle">' + _e(item.get("detail")) + "</td></tr>"
                for item in labels
            )
            + "</tbody></table></div></section>"
        )
    return (
        tiles
        + _tools(table_id, status_options, _weeks(rows, "week"))
        + _table(table_id, ("Semana", "Recurso", "Resultado", "Archivo", "Detalle"), "".join(rows_html),
                 "El reporte no tiene filas.")
        + labels_html
    )


def render_moodle_saved_report(filename, report):
    """Página con el contenido de un reporte Moodle guardado (auditoría o cargue)."""
    is_audit = filename.startswith("moodle-auditoria-")
    stamp = str(report.get("createdAt") or "").replace("T", " ").replace("+00:00", " UTC")
    stopped = str(report.get("stoppedReason") or "")
    title = "Reporte de auditoría" if is_audit else "Reporte de cargue"
    safe_filename = _e(filename)
    header = (
        '<header class="encabezado"><div class="encabezado-titulo"><span class="icono-tile grande">'
        + icon("documento") + "</span><div><h1>" + title + "</h1><p>"
        + _e(stamp or filename) + " · " + safe_filename
        + ("<br>Detenido: " + _e(stopped) if stopped else "") + "</p></div></div>"
        '<div class="encabezado-acciones">'
        '<a class="boton secundario" href="/moodle-reportes">' + icon("anterior") + "Volver a reportes</a>"
        '<a class="boton secundario" href="/moodle-reportes/' + safe_filename + '?formato=csv">'
        + icon("descargar") + "CSV</a>"
        '<a class="boton secundario" href="/moodle-reportes/' + safe_filename + '?formato=json">'
        + icon("descargar") + "JSON</a></div></header>"
    )
    table_id = "tabla-reporte-moodle"
    body = _audit_body(report, table_id) if is_audit else _upload_body(report, table_id)
    return render_page(
        title,
        '<div class="reporte-vista">' + header + body + "</div>",
        active="moodle-reportes",
        page_css=(_CSS_AUDITORIA if is_audit else _CSS_MOODLE) + _CSS_REPORT_VIEW,
    )


__all__ = ["render_moodle_saved_report"]
