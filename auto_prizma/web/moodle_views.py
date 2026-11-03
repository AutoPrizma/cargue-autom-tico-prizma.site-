"""Vistas del apartado Moodle, construidas con el marco común."""

import html
import json
import os

from auto_prizma.domain.moodle_resources import BLOCK_LABELS, BLOCK_ORDER, RESOURCE_KINDS, publish_order
from auto_prizma.web.icons import icon
from auto_prizma.web.layout import render_page


_CSS_MOODLE = """
.moodle-page{display:grid;grid-template-columns:minmax(0,1fr);gap:18px}.moodle-heading{display:flex;align-items:flex-start;gap:16px;margin:4px 0 2px}.moodle-heading .icono-tile{flex:0 0 56px}.moodle-heading h1{margin:0;font-size:30px;font-weight:800;letter-spacing:-.02em}.moodle-heading p{margin:6px 0 0;color:var(--muted);font-size:15px}.moodle-heading .moodle-files{display:flex;flex-wrap:wrap;gap:6px 14px;margin-top:8px;font-size:13px;color:var(--texto-2)}.moodle-files span{display:inline-flex;align-items:center;gap:6px;min-width:0;overflow-wrap:anywhere}.moodle-files .icono{width:15px;height:15px;flex:0 0 15px}
.moodle-panel{padding:24px}.moodle-panel h2{margin:0 0 4px}.moodle-form{display:grid;grid-template-columns:1fr 1fr;gap:18px}.moodle-field{display:grid;gap:7px;min-width:0}.moodle-field label{font-weight:700;color:var(--texto-2)}.moodle-field input[type=url]{width:100%;min-height:48px;border:1px solid var(--borde-2);border-radius:11px;background:var(--panel);padding:10px 12px}.moodle-field.full,.moodle-form-actions{grid-column:1/-1}.moodle-form-actions{display:flex;gap:10px;flex-wrap:wrap}.moodle-help{color:var(--muted);font-size:12px}.moodle-file-drop{display:grid;justify-items:center;gap:6px;text-align:center;min-height:170px;padding:22px 16px;border:2px dashed var(--acento-borde);border-radius:14px;background:var(--panel-2);cursor:pointer;transition:border-color .15s,background .15s}.moodle-file-drop:hover,.moodle-file-drop.dragover{border-color:var(--acento);background:var(--acento-suave)}.moodle-file-drop input{display:none}.moodle-file-drop .icono{width:32px;height:32px;color:var(--acento-texto)}.moodle-file-drop strong{font-size:14px}.moodle-file-drop small{color:var(--muted)}.moodle-file-ready{display:flex;align-items:center;gap:10px;min-width:0;padding:10px 12px;border:1px solid var(--borde);border-radius:12px;background:var(--panel)}.moodle-file-ready[hidden]{display:none}.moodle-file-ready span:nth-child(2){min-width:0;flex:1;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;font-size:13px}.moodle-file-ready button{border:0;background:none;color:var(--muted);cursor:pointer;font:inherit}
.moodle-overview{display:grid;gap:12px;padding:18px 24px}.moodle-stats{display:flex;flex-wrap:wrap;gap:10px 28px}.moodle-stat{display:flex;align-items:baseline;gap:8px}.moodle-stat strong{font-size:26px;font-weight:800;color:var(--texto)}.moodle-stat span{color:var(--texto-2);font-size:14px;font-weight:600}.moodle-stat.verde strong{color:var(--verde)}.moodle-stat.ambar strong{color:var(--ambar)}.moodle-stat.azul strong{color:var(--azul)}.moodle-stat.gris strong{color:var(--muted)}.moodle-ignored summary{cursor:pointer;color:var(--muted);font-size:13px}.moodle-ignored p{margin:8px 0 0;color:var(--texto-2);font-size:12px;line-height:1.6}
.moodle-attention h2{display:flex;align-items:center;gap:8px;color:var(--ambar)}.moodle-attention h2 .icono{width:20px;height:20px}.moodle-attention-list{display:grid;gap:8px;margin:12px 0 0;padding:0;list-style:none}.moodle-attention-list li{display:grid;grid-template-columns:auto minmax(0,1fr);gap:4px 12px;align-items:start;padding:10px 12px;border:1px solid var(--borde);border-radius:10px;background:var(--ambar-suave)}.moodle-attention-list strong{display:block;font-size:13px}.moodle-attention-list small{display:block;color:var(--texto-2);font-size:12px;overflow-wrap:anywhere}
.moodle-weeks{display:grid;gap:10px}.moodle-weeks-head{display:flex;flex-wrap:wrap;justify-content:space-between;align-items:flex-end;gap:8px 20px;margin-top:6px}.moodle-weeks-head h2{margin:0}.moodle-weeks-head .moodle-toolbar{margin:0}.moodle-check-inline{display:inline-flex;align-items:center;gap:6px;font-size:13px;color:var(--texto-2);white-space:nowrap}.moodle-check-inline input{margin:0;width:auto;min-height:0;accent-color:var(--acento)}
.moodle-week{padding:0;overflow:hidden}.moodle-week>summary{display:flex;flex-wrap:wrap;align-items:center;gap:8px 12px;padding:14px 20px;cursor:pointer;list-style:none}.moodle-week>summary::-webkit-details-marker{display:none}.moodle-week>summary::before{content:"▸";color:var(--muted);transition:transform .15s}.moodle-week[open]>summary::before{transform:rotate(90deg)}.moodle-week>summary strong{font-size:16px}.moodle-week-count{color:var(--muted);font-size:13px}.moodle-week-body{display:grid;gap:12px;padding:0 20px 18px}
.moodle-block{border:1px solid var(--borde);border-radius:12px;overflow:hidden}.moodle-block h4{margin:0;padding:9px 14px;background:var(--acento-suave);color:var(--acento-texto);font-size:13px}.moodle-block.manual h4{background:var(--panel-2);color:var(--texto-2)}.moodle-block.sin-uso{border-style:dashed}.moodle-block.sin-uso h4{background:var(--panel-2);color:var(--muted);text-decoration:line-through}.moodle-block.sin-uso p{margin:0;padding:10px 14px;color:var(--muted);font-size:12px}.moodle-block ul{margin:0;padding:0;list-style:none}
.moodle-item{display:grid;grid-template-columns:22px minmax(0,1fr) auto;gap:12px;align-items:start;padding:10px 14px;border-top:1px solid var(--borde)}.moodle-item:first-child{border-top:0}.moodle-item input{margin:3px 0 0;accent-color:var(--acento)}.moodle-item.problema{background:var(--ambar-suave)}.moodle-item-text strong{display:block;font-size:14px;line-height:1.35}.moodle-item-text small{display:flex;flex-wrap:wrap;align-items:center;gap:6px;margin-top:4px;color:var(--muted);font-size:12px;overflow-wrap:anywhere}.moodle-h5p-check{display:grid;gap:4px;margin-top:7px;color:var(--texto-2);font-size:12px;overflow-wrap:anywhere}.moodle-h5p-check>span{display:flex;align-items:center;gap:6px;flex-wrap:wrap}.moodle-h5p-check .badge{font-size:10px}.moodle-manual-upload{display:flex;align-items:center;gap:8px;flex-wrap:wrap;margin-top:8px;font-size:12px;color:var(--texto-2)}.moodle-manual-upload input{display:inline-block!important;width:auto;max-width:230px;min-height:0!important;font-size:12px}.moodle-manual-upload .boton{padding:6px 10px;font-size:12px}.moodle-nocheck{color:var(--muted);text-align:center}.moodle-why{color:var(--texto-2)}
.moodle-labels-option{display:grid;gap:8px;padding:14px;border:1px solid var(--borde);border-radius:12px;background:var(--panel-2)}.moodle-check{display:flex;gap:10px;align-items:flex-start;cursor:pointer}.moodle-check input{margin-top:3px;accent-color:var(--acento)}.moodle-check strong{display:block;font-size:14px}.moodle-check small{display:block;color:var(--muted);font-size:12px;margin-top:2px}.moodle-labels-option summary{cursor:pointer;font-size:13px;font-weight:700;color:var(--acento-texto)}.moodle-labels-option ul{margin:8px 0;padding-left:18px;font-size:13px}
.moodle-counts{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:12px}.moodle-count{display:grid;gap:2px;padding:14px 16px;border:1px solid var(--borde);border-radius:14px;background:var(--panel);text-align:left;font:inherit;color:inherit;cursor:pointer}.moodle-count:hover,.moodle-count[aria-pressed=true]{border-color:var(--acento)}.moodle-count[aria-pressed=true]{box-shadow:0 0 0 2px var(--acento-suave)}.moodle-count strong{font-size:23px;color:var(--texto)}.moodle-count span{color:var(--texto-2);font-size:13px;font-weight:700}.moodle-count small{color:var(--muted);font-size:12px}.moodle-count[disabled]{cursor:default}
.moodle-select{display:grid;gap:14px}.moodle-select-group{display:grid;gap:8px}.moodle-select-group>span{font-weight:700;color:var(--texto-2);font-size:13px}.moodle-chips{display:flex;flex-wrap:wrap;gap:8px}.moodle-chip{display:inline-flex;align-items:center;gap:8px;padding:7px 12px;border:1px solid var(--borde-2);border-radius:999px;background:var(--panel);font-size:13px;font-weight:600;color:var(--texto);cursor:pointer;user-select:none}.moodle-chip:has(input:checked){border-color:var(--acento);background:var(--acento-suave);color:var(--acento-texto)}.moodle-chip input{margin:0;accent-color:var(--acento)}.moodle-chip small{color:var(--muted);font-weight:600}.moodle-chip.disabled{opacity:.55;cursor:not-allowed}
.moodle-selection-bar{display:flex;flex-wrap:wrap;align-items:center;gap:10px 14px;padding-top:14px;border-top:1px solid var(--borde)}.moodle-selection-bar .moodle-selected{font-weight:700}.moodle-selection-bar .moodle-test-target{flex-basis:100%;color:var(--muted);font-size:12px}.moodle-link-button{border:0;background:none;padding:0;color:var(--acento-texto);font:inherit;font-size:13px;font-weight:700;cursor:pointer;text-decoration:underline}
.moodle-toolbar{display:flex;flex-wrap:wrap;gap:10px;align-items:center;margin:12px 0}.moodle-toolbar input[type=search],.moodle-toolbar select{min-height:38px;border:1px solid var(--borde-2);border-radius:10px;background:var(--panel);color:var(--texto);padding:6px 10px;font:inherit;font-size:13px}.moodle-toolbar input[type=search]{flex:1 1 220px;min-width:0}.moodle-toolbar .moodle-visible{color:var(--muted);font-size:12px}
.moodle-table-wrap{overflow:auto}.moodle-table{min-width:900px}.moodle-table td{vertical-align:top}.moodle-file{max-width:300px;overflow-wrap:anywhere;font-size:13px}.moodle-file small,.moodle-subcell{display:block;color:var(--muted);font-size:12px;margin-top:3px}.moodle-file .moodle-why{color:var(--texto-2)}.moodle-empty{padding:30px;text-align:center;color:var(--muted)}
.moodle-actions{display:flex;gap:10px;flex-wrap:wrap;align-items:center}.moodle-note{margin:0}.moodle-report-links{display:flex;gap:12px;flex-wrap:wrap}
.moodle-label-info{padding:0;overflow:hidden}.moodle-label-info>summary{display:flex;align-items:center;gap:10px;padding:20px 24px;cursor:pointer;font-size:18px;font-weight:800;list-style:none}.moodle-label-info>summary::-webkit-details-marker{display:none}.moodle-label-info>summary:after{content:"＋";margin-left:auto;color:var(--acento-texto)}.moodle-label-info[open]>summary:after{content:"−"}.moodle-label-content{display:grid;gap:18px;padding:0 24px 24px}.moodle-label-content>p{margin:0;color:var(--muted);font-size:13px;line-height:1.55}.moodle-label-tool{display:grid;grid-template-columns:minmax(220px,.8fr) minmax(0,1.2fr);gap:18px;align-items:start}.moodle-label-controls{display:grid;gap:14px}.moodle-label-controls label{display:grid;gap:7px;font-size:13px;font-weight:700;color:var(--texto-2)}.moodle-label-controls select,.moodle-label-controls input[type=url],.moodle-label-code{width:100%;border:1px solid var(--borde-2);border-radius:10px;background:var(--panel);color:var(--texto);padding:10px 12px;font:inherit}.moodle-label-file{display:block!important;padding:12px;border:1px dashed var(--acento-borde);border-radius:10px;background:var(--panel-2);cursor:pointer}.moodle-label-file input{width:100%;font:inherit}.moodle-label-output{display:grid;gap:10px;min-width:0}.moodle-label-output h3{margin:0;font-size:14px}.moodle-label-code{min-height:230px;resize:vertical;font:12px/1.5 ui-monospace,SFMono-Regular,monospace;overflow-wrap:anywhere}.moodle-label-preview{max-width:100%;max-height:300px;object-fit:contain;border:1px solid var(--borde);border-radius:8px;background:var(--panel-2)}.moodle-label-preview[hidden]{display:none}.moodle-label-actions{display:flex;gap:10px;flex-wrap:wrap;align-items:center}.moodle-label-message{margin:0;color:var(--muted);font-size:12px}.moodle-label-examples{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}.moodle-label-example{padding:14px;border:1px solid var(--borde);border-radius:12px;background:var(--panel-2);min-width:0}.moodle-label-example h3{margin:0 0 8px;font-size:13px}.moodle-label-example pre{margin:0;white-space:pre-wrap;overflow-wrap:anywhere;color:var(--texto-2);font:11px/1.5 ui-monospace,SFMono-Regular,monospace}
.moodle-label-file{display:grid!important;justify-items:center;gap:8px;padding:24px 14px;border:2px dashed var(--acento-borde);border-radius:12px;background:var(--panel-2);text-align:center;cursor:pointer;transition:border-color .15s,background .15s}.moodle-label-file.dragover,.moodle-label-file:hover{border-color:var(--acento);background:var(--acento-suave)}.moodle-label-file input{width:100%;font:inherit}.moodle-label-file strong{color:var(--acento-texto)}
.moodle-label-file input[type=file]{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);clip-path:inset(50%);white-space:nowrap;border:0}.moodle-label-file:focus-within{outline:3px solid var(--foco);outline-offset:3px}.moodle-label-file-button{pointer-events:none}.moodle-label-file-name{max-width:100%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--muted);font-size:12px}
.moodle-label-info{padding:24px}.moodle-label-code-details{border:1px solid var(--borde);border-radius:10px;overflow:hidden}.moodle-label-code-details>summary{padding:10px 12px;cursor:pointer;color:var(--acento-texto);font-size:13px;font-weight:700}.moodle-label-code-details .moodle-label-code{display:block;width:calc(100% - 20px);margin:0 10px 10px;min-height:130px}.moodle-label-code-note{margin:0;color:var(--muted);font-size:12px;line-height:1.45}
.moodle-label-cards{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.moodle-label-card{display:grid;align-content:start;gap:10px;padding:16px;border:1px solid var(--borde);border-radius:12px;background:var(--panel-2);min-width:0}.moodle-label-card.activa{border-color:var(--acento);box-shadow:0 0 0 2px var(--acento-suave)}.moodle-label-card h3{margin:0;font-size:16px}.moodle-label-card p{margin:0;color:var(--muted);font-size:12px;line-height:1.45}.moodle-label-card>label:not(.moodle-label-file){display:grid;gap:7px;color:var(--texto-2);font-size:13px;font-weight:700}.moodle-label-card input[type=url]{width:100%;border:1px solid var(--borde-2);border-radius:9px;background:var(--panel);color:var(--texto);padding:10px;font:inherit}.moodle-label-card>.boton{justify-self:start}.moodle-label-preview{max-width:100%;max-height:240px;object-fit:contain;border:1px solid var(--borde);border-radius:8px;background:var(--panel-2)}
.moodle-run{display:grid;gap:18px}.moodle-progress-head{display:flex;flex-wrap:wrap;justify-content:space-between;gap:12px 20px;align-items:center}.moodle-run-title{display:flex;gap:14px;align-items:center}.moodle-run-title h1{margin:0 0 4px;font-size:24px;font-weight:800}.moodle-run-percent{color:var(--muted);font-size:14px}.moodle-run-percent strong{font-size:20px;color:var(--acento-texto)}.moodle-run-head progress{display:block;width:100%;height:12px;margin:20px 0 12px;accent-color:var(--acento)}.moodle-run-message{color:var(--acento-texto);font-size:14px;font-weight:600;line-height:1.45;overflow-wrap:anywhere}
.moodle-run-numbers{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}.moodle-run-number{display:flex;align-items:center;gap:14px;padding:18px}.moodle-run-number span:not(.icono-tile){display:block;color:var(--muted);font-size:13px}.moodle-run-number strong{display:block;font-size:26px;font-weight:800;color:var(--texto)}
.moodle-run-zone{display:grid;grid-template-columns:minmax(0,1.55fr) minmax(260px,.75fr);gap:18px;align-items:start}.moodle-run-side{display:grid;gap:14px}.moodle-run-box{display:grid;gap:4px;padding:14px;border:1px solid var(--borde);border-radius:12px;background:var(--panel-2)}.moodle-run-box span{color:var(--muted);font-size:12px}.moodle-run-box strong{font-size:15px;overflow-wrap:anywhere}.moodle-run-box small{color:var(--texto-2);font-size:12px}.moodle-run-controls .boton{flex:1 1 auto}
.moodle-queue{display:grid;max-height:560px;overflow:auto;margin:12px 0;padding:0;list-style:none;border:1px solid var(--borde);border-radius:12px}.moodle-queue-item{display:grid;grid-template-columns:28px minmax(0,1fr) auto;gap:10px;align-items:start;padding:11px 13px;border-bottom:1px solid var(--borde);background:var(--panel)}.moodle-queue-item:last-child{border-bottom:0}.moodle-queue-item strong{display:block;font-size:13px;line-height:1.4;color:var(--texto)}.moodle-queue-item small{display:block;color:var(--muted);font-size:12px}.moodle-queue-item .moodle-queue-detail{margin-top:3px;color:var(--texto-2);overflow-wrap:anywhere}.moodle-queue-num{color:var(--muted);font-size:12px;font-weight:700;padding-top:2px}.moodle-queue-item.ok{background:var(--verde-suave)}.moodle-queue-item.error{background:var(--rojo-suave)}.moodle-queue-item.procesando{background:var(--acento-suave);box-shadow:inset 3px 0 0 var(--acento)}.moodle-queue-item.pendiente .badge{opacity:.8}
.moodle-legend summary,.moodle-issues summary{cursor:pointer;font-weight:700}.moodle-legend dl{display:grid;grid-template-columns:auto 1fr;gap:8px 14px;margin:12px 0 0;align-items:start}.moodle-legend dd{margin:0;color:var(--texto-2);font-size:13px}.moodle-issues ul{margin:8px 0 0;padding-left:18px;font-size:13px}.moodle-issues li{margin:3px 0}
@media(max-width:1000px){.moodle-run-zone{grid-template-columns:1fr}.moodle-run-numbers{grid-template-columns:repeat(2,minmax(0,1fr))}}
@media(max-width:800px){.moodle-form{grid-template-columns:1fr}.moodle-field.full,.moodle-form-actions{grid-column:auto}.moodle-counts{grid-template-columns:repeat(2,minmax(0,1fr))}.moodle-steps{grid-template-columns:1fr}.moodle-panel{padding:18px}.moodle-heading h1{font-size:25px}.moodle-legend dl{grid-template-columns:1fr}}
@media(max-width:800px){.moodle-label-tool{grid-template-columns:1fr}.moodle-label-cards{grid-template-columns:1fr 1fr}}
@media(max-width:520px){.moodle-form-actions,.moodle-actions{display:grid}.moodle-form-actions .boton,.moodle-actions .boton{width:100%}}
@media(max-width:520px){.moodle-label-info{padding:16px}.moodle-label-content{padding:0}.moodle-label-cards{grid-template-columns:1fr}.moodle-label-actions .boton{width:100%}}
"""

# Estado de cada fila en la vista previa: (texto, badge, qué significa y qué hacer).
_TEXT_STATUS = {
    "matched": ("Listo para publicar", "badge-verde", "Hay un único archivo en el ZIP con ese nombre y el tipo correcto. Se puede publicar."),
    "missing": ("Falta el archivo", "badge-ambar", "No hay en el ZIP un archivo con ese nombre. Revisa que el nombre del archivo coincida con el de la matriz o agrégalo al ZIP."),
    "ambiguous": ("Varios archivos posibles", "badge-rojo", "Más de un archivo del ZIP coincide con el nombre. Deja solo uno para que no se publique el equivocado."),
    "extension-mismatch": ("Tipo de archivo distinto", "badge-ambar", "Se encontró el archivo, pero con otra extensión (por ejemplo, un PDF donde la matriz pide un H5P)."),
    "unsupported": ("Se publica a mano", "badge-gris", "Este tipo de recurso no tiene un destino automático en Moodle (por ejemplo, videos a cámara). Súbelo manualmente."),
    "title-review": ("Título H5P por revisar", "badge-ambar", "No se verificó una coincidencia exacta del título dentro del contenido. Adjunta manualmente el archivo correcto para habilitar esta fila."),
    "invalid-file": ("Archivo inválido", "badge-rojo", "El recurso está vacío, no se puede leer o el PDF no es válido. Corrige el archivo antes de publicarlo."),
}

# Resultado de cada recurso tras publicar: (badge, qué significa y qué hacer).
_RESULT_STATUS = {
    "Cargado": ("badge-verde", "Publicado y verificado en la semana del curso."),
    "Ya estaba cargado": ("badge-azul", "Ya existía en la semana; no se duplicó."),
    "No cargado": ("badge-ambar", "No se guardó nada en Moodle (paquete H5P rechazado o bloque de la semana no disponible). Corrige el detalle y reintenta."),
    "Revisar en Prizma": ("badge-rojo", "Algo falló a mitad del proceso. Abre la semana en Moodle y comprueba si el recurso aparece antes de reintentar."),
    "No procesado": ("badge-gris", "No se intentó porque la publicación se canceló o se detuvo antes."),
}
_RETRY_STATUSES = ("No cargado", "Revisar en Prizma", "No procesado")

_KIND_LABELS = dict(RESOURCE_KINDS)
_KIND_BADGES = {
    "h5p": "badge-h5p",
    "infografia": "badge-morado",
    "video-avatar": "badge-azul",
    "pdf": "badge-pdf",
    "reto": "badge-ambar",
    "otro": "badge-gris",
}
_RUNNING = {"queued", "logging_in", "publishing", "paused"}
_RUNNING_LABELS = {
    "queued": "En cola",
    "logging_in": "Esperando inicio de sesión",
    "publishing": "Publicando",
    "paused": "En pausa",
}


def _e(value):
    return html.escape(str(value or ""), quote=True)


def _alert(message, tone="error", title=""):
    if not message and not title:
        return ""
    body = ("<strong>" + _e(title) + "</strong><p>" + _e(message) + "</p>") if title else "<strong>" + _e(message) + "</strong>"
    return '<div class="aviso ' + tone + '" role="alert">' + icon("alerta-circulo") + "<div>" + body + "</div></div>"


def _header(job=None):
    if job:
        files = (
            '<div class="moodle-files"><span>' + icon("hoja") + _e(job.get("matrix_filename")) + '</span>'
            + '<span>' + icon("zip") + _e(job.get("zip_filename")) + '</span>'
            + '<span>' + icon("enlace") + '<a href="' + _e(job.get("course_url")) + '" target="_blank" rel="noopener">Abrir el curso en Moodle</a></span></div>'
        )
        return (
            '<header class="moodle-heading"><div class="icono-tile">' + icon("moodle")
            + '</div><div><h1>Vista previa Moodle</h1><p>Elige qué recursos publicar, prueba con uno y luego publica el resto.</p>'
            + files + '</div></header>'
        )
    return (
        '<header class="moodle-heading"><div class="icono-tile">' + icon("moodle")
        + '</div><div><h1>Cargue Moodle</h1><p>Prepara recursos PDF y H5P para un curso de Prizma.</p></div></header>'
    )


def _upload_form(error=""):
    return (
        '<section class="panel moodle-panel"><h2>Preparar recursos</h2>' + _alert(error)
        + '<p class="sub">Carga una matriz exportada y un ZIP con los archivos del curso. La matriz original no se modifica.</p>'
        + '<form class="moodle-form" action="/moodle/analizar" method="post" enctype="multipart/form-data">'
        + '<div class="moodle-field"><label for="moodle-matrix">Matriz CSV o XLSX</label>'
        + '<label class="moodle-file-drop" data-moodle-drop for="moodle-matrix">' + icon("subir")
        + '<strong>Selecciona o arrastra la matriz</strong><small>Archivo .csv o .xlsx</small><span class="boton">Seleccionar archivo</span>'
        + '<input id="moodle-matrix" name="matriz_archivo" type="file" accept=".csv,.xlsx" required></label>'
        + '<div class="moodle-file-ready" id="moodle-ready-matrix" hidden><span class="icono-tile chico">' + icon("hoja") + '</span><span></span><button type="button" data-moodle-clear="moodle-matrix" aria-label="Quitar matriz">×</button></div>'
        + '<span class="moodle-help">Se usa la primera hoja. Columnas necesarias: Semana correspondiente, Unidad, Nombre del recurso, Categoría, Tipo de recurso y Enlace.</span></div>'
        + '<div class="moodle-field"><label for="moodle-zip">ZIP de recursos</label>'
        + '<label class="moodle-file-drop" data-moodle-drop for="moodle-zip">' + icon("subir")
        + '<strong>Selecciona o arrastra el ZIP</strong><small>Un archivo .zip con los recursos</small><span class="boton">Seleccionar archivo</span>'
        + '<input id="moodle-zip" name="recursos_zip" type="file" accept=".zip" required></label>'
        + '<div class="moodle-file-ready" id="moodle-ready-zip" hidden><span class="icono-tile chico">' + icon("zip") + '</span><span></span><button type="button" data-moodle-clear="moodle-zip" aria-label="Quitar ZIP">×</button></div>'
        + '<span class="moodle-help">Solo se usan los PDF y H5P. Cada archivo se empareja por su nombre con el «Nombre del recurso» de la matriz.</span></div>'
        + '<div class="moodle-field full"><label for="moodle-course">Enlace del curso</label>'
        + '<input id="moodle-course" name="course_url" type="url" placeholder="https://prizma.americana.edu.co/course/view.php?id=…" required>'
        + '<span class="moodle-help">Se publican automáticamente: PDF (OVI), Recurso H5P, Infografía, Video interactivo (avatar) y Reto evaluativo.</span></div>'
        + '<div class="moodle-form-actions"><button class="boton grande" type="submit">'
        + icon("ver") + 'Generar vista previa</button></div></form>'
        + '<script>(function(){document.querySelectorAll("[data-moodle-drop]").forEach(function(z){var i=document.getElementById(z.htmlFor),r=document.getElementById("moodle-ready-"+(i.id==="moodle-matrix"?"matrix":"zip"));function show(){if(!i.files||!i.files[0]){r.hidden=true;return}r.querySelector("span:nth-child(2)").textContent=i.files[0].name+" · "+Math.max(1,Math.round(i.files[0].size/1024))+" KB";r.hidden=false}i.addEventListener("change",show);["dragenter","dragover"].forEach(function(e){z.addEventListener(e,function(v){v.preventDefault();z.classList.add("dragover")})});["dragleave","drop"].forEach(function(e){z.addEventListener(e,function(v){v.preventDefault();z.classList.remove("dragover")})});z.addEventListener("drop",function(e){if(e.dataTransfer.files.length){var d=new DataTransfer();d.items.add(e.dataTransfer.files[0]);i.files=d.files;i.dispatchEvent(new Event("change"))}})});document.querySelectorAll("[data-moodle-clear]").forEach(function(b){b.addEventListener("click",function(){var i=document.getElementById(b.dataset.moodleClear);i.value="";i.dispatchEvent(new Event("change"))})})})()</script></section>'
    )


def _label_info_section():
    return (
        '<section class="panel moodle-label-info"><div class="moodle-label-content"><p>Elige el tipo de etiqueta. La plantilla HTML se selecciona internamente; al cargar la imagen se inserta automáticamente en <code>src</code>. La imagen queda incrustada como Data URL; no se sube a Moodle ni a un servidor.</p>'
        + '<div class="moodle-label-cards">'
        + '<article class="moodle-label-card" data-label-card="banner"><h3>Banners imágenes</h3><p>Arrastra o selecciona la imagen para generar el código del banner.</p>'
        + '<label class="moodle-label-file" data-label-drop for="moodle-label-image-banner">' + icon("subir") + '<strong>Arrastra la imagen aquí</strong><small>o haz clic para seleccionarla · máx. 5 MB</small><span class="boton secundario moodle-label-file-button">Seleccionar imagen</span><span class="moodle-label-file-name" data-label-filename>Ninguna imagen seleccionada</span><input id="moodle-label-image-banner" data-label-image-kind="banner" type="file" accept="image/png,image/jpeg,image/gif,image/webp"></label></article>'
        + '<article class="moodle-label-card" data-label-card="infografia"><h3>Infografía</h3><p>Arrastra o selecciona la imagen de la infografía.</p>'
        + '<label class="moodle-label-file" data-label-drop for="moodle-label-image-infografia">' + icon("subir") + '<strong>Arrastra la imagen aquí</strong><small>o haz clic para seleccionarla · máx. 5 MB</small><span class="boton secundario moodle-label-file-button">Seleccionar imagen</span><span class="moodle-label-file-name" data-label-filename>Ninguna imagen seleccionada</span><input id="moodle-label-image-infografia" data-label-image-kind="infografia" type="file" accept="image/png,image/jpeg,image/gif,image/webp"></label></article>'
        + '<article class="moodle-label-card" data-label-card="video"><h3>Videos</h3><p>Pega el enlace del video para insertarlo en el código fuente.</p>'
        + '<label for="moodle-label-video-url">Enlace del video<input id="moodle-label-video-url" type="url" placeholder="https://…" autocomplete="url"></label>'
        + '<button class="boton secundario" id="moodle-label-generate-video" type="button">Generar HTML de video</button></article></div>'
        + '<p class="moodle-label-message" id="moodle-label-message" aria-live="polite">Elige una tarjeta: al cargar la imagen el código se genera automáticamente.</p>'
        + '<img class="moodle-label-preview" id="moodle-label-preview" alt="Vista previa de la imagen" hidden>'
        + '<div class="moodle-label-output"><h3>HTML generado</h3><p class="moodle-label-code-note">El código completo se copia con el botón. El <code>src</code> queda largo porque contiene la imagen.</p>'
        + '<details class="moodle-label-code-details"><summary>Ver HTML completo</summary><textarea class="moodle-label-code" id="moodle-label-code" readonly aria-label="HTML generado" placeholder="El código aparecerá aquí."></textarea></details>'
        + '<div class="moodle-label-actions"><button class="boton" id="moodle-label-copy" type="button" disabled>' + icon("copiar") + 'Copiar HTML</button>'
        + '<button class="boton secundario" id="moodle-label-download" type="button" disabled>' + icon("descargar") + 'Descargar .html</button></div></div></section>'
    )


_JS_LABEL_INFO = r"""
(function(){
  var imageInputs=Array.prototype.slice.call(document.querySelectorAll('[data-label-image-kind]'));if(!imageInputs.length)return;
  var videoUrl=document.getElementById('moodle-label-video-url'),videoButton=document.getElementById('moodle-label-generate-video');
  var output=document.getElementById('moodle-label-code'),preview=document.getElementById('moodle-label-preview');
  var message=document.getElementById('moodle-label-message'),copy=document.getElementById('moodle-label-copy'),download=document.getElementById('moodle-label-download');
  function escapeAttr(value){return value.replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;').replace(/>/g,'&gt;');}
  function template(type,src){
    if(type==='banner')return '<p><img class="img-fluid align-top" role="presentation" src="'+src+'" alt="" width="2780" height="386"></p>';
    if(type==='infografia')return '<p><img class="img-fluid align-top" style="display: block; margin-left: auto; margin-right: auto;" role="presentation" src="'+src+'" alt="" width="720" height="1015"></p>';
    return '<p dir="ltr" style="text-align: left;">&nbsp;&nbsp;&nbsp;<video width="800" height="800" controls="true"><source src="'+src+'"></video></p>';
  }
  function activate(type){document.querySelectorAll('[data-label-card]').forEach(function(card){card.classList.toggle('activa',card.dataset.labelCard===type);});}
  function setOutput(code,text,imageData){output.value=code||'';message.textContent=text;preview.hidden=!imageData;if(imageData)preview.src=imageData;else preview.removeAttribute('src');var ready=!!code;copy.disabled=!ready;download.disabled=!ready;
  }
  function readImage(file,input,type){activate(type);if(!file){setOutput('','Selecciona una imagen para generar el HTML.','');return;}
    if(!/^image\/(png|jpeg|gif|webp)$/.test(file.type)){input.value='';var invalidName=input.closest('[data-label-drop]').querySelector('[data-label-filename]');if(invalidName)invalidName.textContent='Ninguna imagen seleccionada';setOutput('','Elige una imagen PNG, JPG, GIF o WebP.','');return;}
    if(file.size>5*1024*1024){input.value='';var largeName=input.closest('[data-label-drop]').querySelector('[data-label-filename]');if(largeName)largeName.textContent='Ninguna imagen seleccionada';setOutput('','La imagen supera el límite de 5 MB.','');return;}
    var reader=new FileReader();reader.onload=function(){var data=String(reader.result||'');setOutput(template(type,data),'HTML de '+(type==='banner'?'banner':'infografía')+' listo; la imagen quedó insertada en src.',data);};reader.onerror=function(){setOutput('','No se pudo leer la imagen.','');};reader.readAsDataURL(file);
  }
  imageInputs.forEach(function(input){var drop=input.closest('[data-label-drop]'),type=input.dataset.labelImageKind,name=drop.querySelector('[data-label-filename]');input.addEventListener('change',function(){var file=input.files&&input.files[0];if(name)name.textContent=file?file.name:'Ninguna imagen seleccionada';readImage(file,input,type);});
    ['dragenter','dragover'].forEach(function(name){drop.addEventListener(name,function(event){event.preventDefault();event.stopPropagation();drop.classList.add('dragover');});});
    ['dragleave','drop'].forEach(function(name){drop.addEventListener(name,function(event){event.preventDefault();event.stopPropagation();drop.classList.remove('dragover');});});
    drop.addEventListener('drop',function(event){var file=event.dataTransfer&&event.dataTransfer.files&&event.dataTransfer.files[0];if(file)readImage(file,input,type);});
  });
  videoButton.addEventListener('click',function(){activate('video');var value=videoUrl.value.trim(),valid=false;try{var parsed=new URL(value);valid=parsed.protocol==='https:'||parsed.protocol==='http:';}catch(_){}if(!valid){setOutput('','Pega un enlace HTTP o HTTPS del video.','');return;}setOutput(template('video',escapeAttr(value)),'HTML de video listo para copiar.','');});
  copy.addEventListener('click',async function(){try{await navigator.clipboard.writeText(output.value);message.textContent='HTML copiado.';}catch(_){output.focus();output.select();document.execCommand('copy');message.textContent='HTML copiado.';}});
  download.addEventListener('click',function(){var blob=new Blob([output.value],{type:'text/html;charset=utf-8'});var url=URL.createObjectURL(blob);var a=document.createElement('a');a.href=url;a.download='etiqueta-moodle.html';a.click();URL.revokeObjectURL(url);});
  setOutput('','Elige una tarjeta: al cargar la imagen el código se genera automáticamente.','');
})();
"""


_PROBLEM_STATUSES = {"missing", "ambiguous", "extension-mismatch", "title-review", "invalid-file"}


def _ordered_entries(job):
    return sorted(job.get("entries") or [], key=publish_order)


def _incomplete_rows(job):
    return [item for item in job.get("matrix_issues") or [] if item.get("reason") != "section-heading"]


def _overview(job):
    """Resumen corto del análisis: cuántos se pueden publicar, cuántos corregir y qué se ignoró."""
    summary = job.get("summary") or {}
    entries = job.get("entries") or []
    weeks = {entry.get("week") or "Sin semana" for entry in entries}
    to_fix = sum(int(summary.get(status, 0)) for status in _PROBLEM_STATUSES) + len(_incomplete_rows(job))
    stats = (
        (summary.get("matched", 0), "listos para publicar", "verde"),
        (to_fix, "por corregir", "ambar" if to_fix else "gris"),
        (summary.get("unsupported", 0), "se suben a mano", "gris"),
        (len(weeks), "semanas", "azul"),
    )
    headings = [item for item in job.get("matrix_issues") or [] if item.get("reason") == "section-heading"]
    ignored = ""
    if headings:
        ignored = (
            '<details class="moodle-ignored"><summary>Se ignoraron ' + str(len(headings))
            + (' título de tema' if len(headings) == 1 else ' títulos de tema') + ' de la matriz (no son recursos)</summary><p>'
            + _e(" · ".join(str(item.get("title")) for item in headings)) + '</p></details>'
        )
    return (
        '<section class="panel moodle-panel moodle-overview"><div class="moodle-stats">' + "".join(
            '<div class="moodle-stat ' + tone + '"><strong>' + str(int(count)) + '</strong><span>' + _e(label) + '</span></div>'
            for count, label, tone in stats
        ) + '</div>' + ignored + '</section>'
    )


def _attention(job):
    """Lo que hay que corregir antes de publicar, en una sola lista."""
    items = []
    for entry in _ordered_entries(job):
        if entry.get("status") in _PROBLEM_STATUSES:
            label = _TEXT_STATUS[entry["status"]][0]
            items.append(
                '<li><span class="badge ' + _TEXT_STATUS[entry["status"]][1] + '">' + _e(label) + '</span>'
                + '<div><strong>' + _e(entry.get("title")) + '</strong><small>' + _e(entry.get("week"))
                + ' · fila ' + str(int(entry.get("sourceRow") or 0)) + ' · ' + _row_detail(entry) + '</small></div></li>'
            )
    for item in _incomplete_rows(job):
        items.append(
            '<li><span class="badge badge-ambar">Fila incompleta</span><div><strong>' + _e(item.get("title") or "Sin nombre") + '</strong>'
            + '<small>' + _e(item.get("week") or "Sin semana") + ' · fila ' + str(int(item.get("sourceRow") or 0))
            + ' · falta ' + _e(", ".join(item.get("missing") or ["un dato obligatorio"])) + '</small></div></li>'
        )
    if not items:
        return ""
    return (
        '<section class="panel moodle-panel moodle-attention"><h2>' + icon("alerta") + ' Necesitan atención (' + str(len(items)) + ')</h2>'
        + '<p class="sub">Estos recursos no se pueden publicar todavía. Corrige el ZIP o la matriz y vuelve a generar la vista previa.</p>'
        + '<ul class="moodle-attention-list">' + "".join(items) + '</ul></section>'
    )


def _row_detail(entry):
    status = entry.get("status")
    destination = entry.get("destination") or {}
    extension = destination.get("extension") or ""
    candidates = [os.path.basename(item) for item in entry.get("candidates") or []]
    if status == "matched":
        return _e(entry.get("manual_filename") or os.path.basename(entry.get("path") or ""))
    if status == "missing":
        return '<span class="moodle-why">Ningún ' + _e(extension or "archivo") + ' del ZIP se llama «' + _e(entry.get("title")) + '»</span>'
    if status == "ambiguous":
        return '<span class="moodle-why">Coinciden ' + str(len(candidates)) + ' archivos: ' + _e(", ".join(candidates[:4])) + ('…' if len(candidates) > 4 else '') + '</span>'
    if status == "extension-mismatch":
        return '<span class="moodle-why">Se encontró ' + _e(", ".join(candidates[:2])) + ', pero este recurso necesita ' + _e(extension) + '</span>'
    if status == "title-review":
        return '<span class="moodle-why">' + _e((entry.get("h5p_preview") or {}).get("detail") or "El título del H5P necesita revisión.") + '</span>'
    if status == "unsupported":
        return '<span class="moodle-why">«' + _e(entry.get("resourceType")) + '» no tiene destino automático</span>'
    return "—"


def _item(entry, order, locked):
    status = entry.get("status")
    kind = entry.get("kind") or "otro"
    week = entry.get("week") or "Sin semana"
    if status == "matched":
        check = (
            '<input type="checkbox" name="entry_keys" value="' + _e(entry.get("key")) + '" checked'
            + ' data-kind="' + _e(kind) + '" data-week="' + _e(week) + '" data-order="' + str(order) + '"'
            + ' data-title="' + _e(entry.get("title")) + '"' + (' disabled' if locked else '')
            + ' aria-label="Incluir ' + _e(entry.get("title")) + '">'
        )
        badge = '<span class="badge badge-verde" title="' + _e(_TEXT_STATUS["matched"][2]) + '">Listo</span>'
    else:
        label, tone, help_text = _TEXT_STATUS.get(status, ("Por revisar", "badge-gris", ""))
        check = '<span class="moodle-nocheck" title="Solo se pueden publicar los recursos listos">—</span>'
        badge = '<span class="badge ' + tone + '" title="' + _e(help_text) + '">' + _e(label) + '</span>'
    search = " ".join(str(entry.get(key) or "") for key in ("week", "title", "resourceType", "path"))
    h5p_preview = entry.get("h5p_preview") or {}
    h5p_markup = ""
    if h5p_preview:
        h5p_status = h5p_preview.get("status")
        if h5p_status == "match":
            preview_badge = '<span class="badge badge-verde">Título coincide</span>'
        elif h5p_status == "no-cover":
            preview_badge = '<span class="badge badge-ambar">Sin título verificable</span>'
        else:
            preview_badge = '<span class="badge badge-rojo">Título del contenido distinto</span>'
        visible_titles = " · ".join(str(title) for title in h5p_preview.get("visible_titles") or [])
        h5p_markup = (
            '<span class="moodle-h5p-check">' + preview_badge
            + '<span><strong>Título H5P:</strong> ' + _e(h5p_preview.get("package_title") or "Sin título interno")
            + '</span><span>' + _e(h5p_preview.get("detail")) + '</span>'
            + ('<span><strong>Títulos dentro del contenido:</strong> ' + _e(visible_titles) + '</span>' if visible_titles else '')
            + '</span>'
        )
    manual_markup = ""
    destination = entry.get("destination") or {}
    if status != "matched" and destination.get("extension") in {".pdf", ".h5p"}:
        extension = destination["extension"]
        manual_markup = (
            '<span class="moodle-manual-upload"><label>Adjuntar archivo para esta fila '
            '<input type="file" accept="' + extension + '" data-manual-resource data-entry-key="'
            + _e(entry.get("key")) + '"></label><button type="button" class="boton secundario pequeno" data-manual-attach>'
            'Usar este archivo</button></span>'
        )
    return (
        '<li class="moodle-item' + (' problema' if status in _PROBLEM_STATUSES else '') + '" data-moodle-row data-status="' + _e(status)
        + '" data-search="' + _e(search.lower()) + '">' + check
        + '<div class="moodle-item-text"><strong>' + _e(entry.get("title")) + '</strong>'
        + '<small><span class="badge ' + _KIND_BADGES.get(kind, "badge-gris") + '">' + _e(_KIND_LABELS.get(kind, kind)) + '</span> '
        + _row_detail(entry) + '</small>' + h5p_markup + manual_markup + '</div>' + badge + '</li>'
    )


def _week_cards(job, locked):
    """Recursos agrupados por semana y, dentro de cada semana, por bloque del curso (como en Moodle)."""
    plan = {item["week"]: item for item in job.get("label_plan") or []}
    ordered = _ordered_entries(job)
    order = {id(entry): position for position, entry in enumerate(ordered)}
    weeks = {}
    for entry in ordered:
        weeks.setdefault(entry.get("week") or "Sin semana", []).append(entry)
    cards = []
    for week, entries in weeks.items():
        ready = sum(entry.get("status") == "matched" for entry in entries)
        problems = sum(entry.get("status") in _PROBLEM_STATUSES for entry in entries)
        week_plan = plan.get(week) or {}
        unused = week_plan.get("delete") or []
        blocks = []
        for block in BLOCK_ORDER:
            block_entries = [entry for entry in entries if (entry.get("destination") or {}).get("block") == block]
            if block_entries:
                blocks.append(
                    '<div class="moodle-block"><h4>' + _e(BLOCK_LABELS[block]) + '</h4><ul>'
                    + "".join(_item(entry, order[id(entry)], locked) for entry in block_entries) + '</ul></div>'
                )
            elif block in unused:
                blocks.append(
                    '<div class="moodle-block sin-uso"><h4>' + _e(BLOCK_LABELS[block]) + '</h4>'
                    + '<p>La matriz no tiene recursos de este bloque: la etiqueta no se usa en esta semana.</p></div>'
                )
        manual = [entry for entry in entries if not entry.get("destination")]
        if manual:
            blocks.append(
                '<div class="moodle-block manual"><h4>Se suben a mano</h4><ul>'
                + "".join(_item(entry, order[id(entry)], locked) for entry in manual) + '</ul></div>'
            )
        tags = ['<span class="moodle-week-count">' + str(ready) + ' de ' + str(len(entries)) + ' listos</span>']
        if problems:
            tags.append('<span class="badge badge-ambar">' + str(problems) + ' por corregir</span>')
        for block in unused:
            tags.append('<span class="badge badge-gris" title="La matriz no usa este bloque en esta semana">Sin uso: ' + _e(BLOCK_LABELS[block]) + '</span>')
        if week_plan.get("uncertain"):
            tags.append('<span class="badge badge-gris" title="Hay filas que no se pueden clasificar; sus etiquetas no se tocan">Etiquetas: no se tocan</span>')
        cards.append(
            '<details class="panel moodle-week" data-moodle-week' + (' open' if problems else '') + '>'
            + '<summary><strong>' + _e(week) + '</strong>' + "".join(tags) + '</summary>'
            + '<div class="moodle-week-body">' + "".join(blocks) + '</div></details>'
        )
    if not cards:
        return '<p class="moodle-help">No hay filas de recursos para mostrar.</p>'
    return "".join(cards)


def _chip_group(title, attribute, groups, locked):
    chips = []
    for value, label, ready, total in groups:
        disabled = locked or not ready
        chips.append(
            '<label class="moodle-chip' + (' disabled' if disabled else '') + '"><input type="checkbox" ' + attribute + '="' + _e(value) + '"'
            + ('' if not ready else ' checked') + (' disabled' if disabled else '') + '>'
            + _e(label) + ' <small>' + str(ready) + (' de ' + str(total) if total != ready else '') + '</small></label>'
        )
    return '<div class="moodle-select-group"><span>' + _e(title) + '</span><div class="moodle-chips">' + "".join(chips) + '</div></div>'


def _labels_option(job):
    """Opción de borrar las etiquetas que la matriz no usa, con la lista exacta de lo que se borrará."""
    plan = job.get("label_plan") or []
    deletions = [(item["week"], BLOCK_LABELS[block]) for item in plan for block in item.get("delete") or []]
    if not deletions:
        return ""
    by_week = {}
    for week, label in deletions:
        by_week.setdefault(week, []).append(label)
    uncertain = [item["week"] for item in plan if item.get("uncertain")]
    return (
        '<div class="moodle-labels-option"><label class="moodle-check"><input type="checkbox" name="clean_labels" value="1" id="moodle-clean-labels" data-count="'
        + str(len(deletions)) + '"><span><strong>Al terminar, borrar las etiquetas que la matriz no usa (hasta ' + str(len(deletions)) + ')</strong>'
        + '<small>Solo en las semanas que publiques y solo con «Publicar seleccionados», nunca en la prueba. En cada etiqueta: ⋮ → Borrar → confirmar. No se puede deshacer.</small></span></label>'
        + '<details><summary>Ver qué etiquetas se borrarán</summary><ul>' + "".join(
            '<li><strong>' + _e(week) + ':</strong> ' + _e(", ".join(labels)) + '</li>' for week, labels in by_week.items()
        ) + '</ul>' + (
            '<p class="moodle-help">No se tocan las etiquetas de ' + _e(", ".join(uncertain))
            + ' porque tienen filas que no se pueden clasificar.</p>' if uncertain else ''
        ) + '<p class="moodle-help">Los videos a cámara, intro y cierre se suben a mano; por precaución su semana conserva «Recurso educativo audiovisual».</p></details></div>'
    )


def _selection_panel(job, locked):
    entries = _ordered_entries(job)
    kinds, weeks = {}, {}
    for entry in entries:
        ready = entry.get("status") == "matched"
        kind = entry.get("kind") or "otro"
        week = entry.get("week") or "Sin semana"
        for bucket, key in ((kinds, kind), (weeks, week)):
            counts = bucket.setdefault(key, [0, 0])
            counts[0] += int(ready)
            counts[1] += 1
    kind_groups = [(key, label, kinds[key][0], kinds[key][1]) for key, label in RESOURCE_KINDS if key in kinds and key != "otro"]
    week_groups = [(week, week, counts[0], counts[1]) for week, counts in weeks.items()]
    matched = int((job.get("summary") or {}).get("matched", 0))

    if matched:
        bar = (
            '<div class="moodle-selection-bar"><span class="moodle-selected" id="moodle-selected-count">' + str(matched) + ' de ' + str(matched) + ' recursos listos seleccionados</span>'
            + '<button type="button" class="moodle-link-button" data-moodle-select="all">Seleccionar todos</button>'
            + '<button type="button" class="moodle-link-button" data-moodle-select="none">Quitar todos</button>'
            + '<div class="moodle-actions" style="margin-left:auto"><button class="boton secundario" type="submit" name="publish_mode" value="test">'
            + icon("matraz") + 'Probar con 1 recurso</button><button class="boton" type="submit" name="publish_mode" value="batch" id="moodle-publish-button">'
            + icon("subir") + 'Publicar ' + str(matched) + ' seleccionados</button>'
            + '<a class="boton neutro" href="/moodle">Cambiar archivos</a></div>'
            + '<span class="moodle-test-target" id="moodle-test-target"></span></div>'
        )
    else:
        bar = (
            '<div class="moodle-selection-bar"><span class="moodle-help">No hay recursos listos para publicar. Revisa el ZIP y la matriz y vuelve a generar la vista previa.</span>'
            + '<a class="boton neutro" href="/moodle">Cambiar archivos</a></div>'
        )
    return (
        '<section class="panel moodle-panel moodle-select"><div><h2>¿Qué quieres publicar?</h2>'
        + '<p class="sub">Marca tipos de recurso y semanas, o recursos sueltos en la lista de abajo. Se publica desde la semana 1 y lo que ya esté en el curso no se duplica.</p></div>'
        + _chip_group("Tipo de recurso", "data-sel-kind", kind_groups, locked)
        + _chip_group("Semanas", "data-sel-week", week_groups, locked)
        + (_labels_option(job) if matched else '')
        + bar + '</section>'
    )


def _weeks_section(job, locked):
    return (
        '<section class="moodle-weeks"><div class="moodle-weeks-head"><div><h2>Recursos por semana</h2>'
        + '<p class="sub">Como en el curso: cada semana con sus bloques. Abre una semana para ver sus recursos.</p></div>'
        + '<div class="moodle-toolbar"><input type="search" placeholder="Buscar recurso o archivo" data-moodle-filter="search" aria-label="Buscar recursos">'
        + '<label class="moodle-check-inline"><input type="checkbox" data-moodle-filter="problems"> Solo lo que necesita atención</label>'
        + '<button type="button" class="moodle-link-button" data-moodle-expand="open">Abrir todas</button>'
        + '<button type="button" class="moodle-link-button" data-moodle-expand="close">Cerrar todas</button></div></div>'
        + _week_cards(job, locked) + '</section>'
    )


def _legend():
    preview = "".join(
        '<dt><span class="badge ' + badge + '">' + _e(label) + '</span></dt><dd>' + _e(help_text) + '</dd>'
        for label, badge, help_text in _TEXT_STATUS.values()
    )
    results = "".join(
        '<dt><span class="badge ' + badge + '">' + _e(label) + '</span></dt><dd>' + _e(help_text) + '</dd>'
        for label, (badge, help_text) in _RESULT_STATUS.items()
    )
    return (
        '<section class="panel moodle-panel moodle-legend"><details><summary>¿Qué significa cada estado?</summary>'
        + '<dl>' + preview + '</dl><h3 style="margin:18px 0 0;font-size:15px">Después de publicar</h3><dl>' + results + '</dl></details></section>'
    )


def _queue_items(job):
    """Lista de recursos del cargue con su estado: resultado, en curso o pendiente."""
    results = {item.get("previewKey"): item for item in job.get("live_results") or []}
    progress = job.get("progress") or {}
    current = int(progress.get("index") or 0)
    items = []
    for position, item in enumerate(job.get("queue") or [], start=1):
        result = results.get(item.get("previewKey"))
        if result:
            status = result.get("status", "")
            tone = _RESULT_STATUS.get(status, ("badge-gris", ""))[0]
            row_class = {"badge-verde": "ok", "badge-azul": "ok", "badge-gris": "pendiente"}.get(tone, "error")
            badge = '<span class="badge ' + tone + '">' + _e(status) + '</span>'
            detail = result.get("detail", "") if status not in {"Cargado", "Ya estaba cargado"} else ""
        elif position == current and job.get("status") in {"publishing", "paused"}:
            row_class, badge, detail = "procesando", '<span class="badge badge-recurso">En curso</span>', progress.get("phase", "")
        else:
            row_class, badge, detail = "pendiente", '<span class="badge badge-gris">Pendiente</span>', ""
        items.append(
            '<li class="moodle-queue-item ' + row_class + '"><span class="moodle-queue-num">' + str(position) + '</span>'
            + '<div><strong>' + _e(item.get("title")) + '</strong><small>' + _e(item.get("week"))
            + (' · ' + _e(_KIND_LABELS.get(item.get("kind") or "", "")) if item.get("kind") else '') + '</small>'
            + ('<small class="moodle-queue-detail">' + _e(detail) + '</small>' if detail else '') + '</div>' + badge + '</li>'
        )
    return "".join(items) or '<li class="moodle-queue-item pendiente"><div>Preparando la lista de recursos…</div></li>'


def _progress(job):
    """Pantalla de cargue en curso (como la del cargue PRIZMA): avance, contadores, lista y controles."""
    progress = job.get("progress") or {}
    status = job.get("status")
    paused = status == "paused"
    total = int(progress.get("total") or len(job.get("queue") or []) or 0)
    done = len(job.get("live_results") or [])
    percent = int(done * 100 / total) if total else 0
    counts = {}
    for item in job.get("live_results") or []:
        counts[item.get("status")] = counts.get(item.get("status"), 0) + 1
    problems = counts.get("No cargado", 0) + counts.get("Revisar en Prizma", 0)
    numbers = (
        ("moodle-n-done", "Procesados", done, "", "girar"),
        ("moodle-n-ok", "Cargados", counts.get("Cargado", 0), "verde", "check-circulo"),
        ("moodle-n-present", "Ya estaban", counts.get("Ya estaba cargado", 0), "azul", "check"),
        ("moodle-n-error", "Con problemas", problems, "rojo", "alerta-circulo"),
    )
    return (
        '<div class="moodle-run" id="moodle-progress" data-job-id="' + _e(job["id"]) + '" data-started="' + _e(job.get("started_at")) + '">'
        + '<section class="panel moodle-panel moodle-run-head"><div class="moodle-progress-head">'
        + '<div class="moodle-run-title"><span class="icono-tile">' + icon("subir") + '</span><div><h1>Cargue Moodle en progreso</h1>'
        + '<span class="badge badge-azul" id="moodle-progress-status">' + _e(_RUNNING_LABELS.get(status, "Publicando")) + '</span></div></div>'
        + '<div class="moodle-run-percent"><strong id="moodle-percent">' + str(percent) + '%</strong> completado</div></div>'
        + '<progress id="moodle-progress-bar" max="' + str(max(1, total)) + '" value="' + str(done) + '"></progress>'
        + '<div class="moodle-run-message" id="moodle-progress-message" aria-live="polite">' + _e(job.get("message")) + '</div></section>'
        + '<div class="moodle-run-numbers">' + "".join(
            '<div class="panel moodle-run-number"><span class="icono-tile ' + tone + '">' + icon(icon_name) + '</span>'
            + '<div><span>' + _e(label) + '</span><strong id="' + element_id + '">' + str(value) + '</strong></div></div>'
            for element_id, label, value, tone, icon_name in numbers
        ) + '</div>'
        + '<div class="moodle-run-zone"><section class="panel moodle-panel"><h2>Recursos del cargue</h2>'
        + '<p class="sub">En orden de publicación, desde la semana 1.</p>'
        + '<ol class="moodle-queue" id="moodle-queue">' + _queue_items(job) + '</ol>'
        + '<p class="moodle-help">El progreso se actualiza automáticamente.</p></section>'
        + '<aside class="panel moodle-panel moodle-run-side"><h2>Estado del proceso</h2>'
        + '<div class="moodle-run-box"><span>Recurso actual</span><strong id="moodle-progress-current">'
        + _e(progress.get("title") or "Preparando…") + '</strong><small id="moodle-progress-detail">'
        + _e(" · ".join(str(progress.get(key)) for key in ("week", "phase") if progress.get(key))) + '</small></div>'
        + '<div class="moodle-run-box"><span>Avance</span><strong id="moodle-progress-count">' + str(done) + ' de ' + str(total) + '</strong>'
        + '<small id="moodle-progress-time"></small></div>'
        + _labels_box(job)
        + '<div class="moodle-actions moodle-run-controls">'
        + '<button type="button" class="boton secundario" data-moodle-control="pausar"' + (' hidden' if paused else '') + '>Pausar</button>'
        + '<button type="button" class="boton" data-moodle-control="reanudar"' + ('' if paused else ' hidden') + '>' + icon("play") + 'Reanudar</button>'
        + '<button type="button" class="boton peligro" data-moodle-control="cancelar">' + icon("cerrar") + 'Cancelar</button></div>'
        + '<p class="moodle-help">Si es la primera vez, inicia sesión en la ventana de Chromium de este equipo (se espera hasta 2 minutos) y no la cierres hasta terminar. «Pausar» y «Cancelar» esperan a que termine el recurso que se está subiendo.</p>'
        + '</aside></div></div>'
    )


def _labels_box(job):
    if not job.get("clean_labels"):
        return ""
    planned = sum(len(item.get("delete") or []) for item in job.get("label_plan") or [])
    done = len(job.get("label_results") or [])
    return (
        '<div class="moodle-run-box"><span>Etiquetas sin uso</span><strong id="moodle-labels-count">'
        + (str(done) + ' de ' + str(planned) + ' revisadas' if done else 'Se borrarán ' + str(planned) + ' al final')
        + '</strong><small>Después de publicar los recursos.</small></div>'
    )


def _retry_form(job, report):
    allowed = {entry.get("key") for entry in job.get("entries") or [] if entry.get("status") == "matched"}
    keys = [row.get("previewKey") for row in report.get("rows", []) if row.get("status") in _RETRY_STATUSES and row.get("previewKey") in allowed]
    if not keys:
        return ""
    hidden = "".join('<input type="hidden" name="entry_keys" value="' + _e(key) + '">' for key in keys)
    return (
        '<form action="/moodle/' + _e(job["id"]) + '/publicar" method="post" data-moodle-retry="' + str(len(keys)) + '">' + hidden
        + '<button class="boton" type="submit" name="publish_mode" value="batch">' + icon("girar")
        + ('Reintentar el recurso que no se cargó' if len(keys) == 1 else 'Reintentar los ' + str(len(keys)) + ' que no se cargaron')
        + '</button></form>'
    )


def _report(job):
    report = job.get("report")
    if not report:
        return ""
    summary = report.get("summary") or {}
    paths = job.get("report_paths") or {}
    cards = (
        (summary.get("uploaded", 0), "Cargados"),
        (summary.get("alreadyPresent", 0), "Ya estaban"),
        (summary.get("notLoaded", 0) + summary.get("needsReview", 0), "Con problemas"),
        (summary.get("notProcessed", 0), "No procesados"),
    )
    counts = '<div class="moodle-counts">' + "".join(
        '<article class="moodle-count" style="cursor:default"><strong>' + str(int(count)) + '</strong><span>' + _e(label) + '</span></article>'
        for count, label in cards
    ) + '</div>'
    rows = []
    for item in report.get("rows", []):
        status = item.get("status", "")
        tone, help_text = _RESULT_STATUS.get(status, ("badge-gris", ""))
        kind = item.get("kind") or ""
        rows.append(
            '<tr><td>' + _e(item.get("week")) + '</td><td><strong>' + _e(item.get("title")) + '</strong>'
            + ('<small class="moodle-subcell">' + _e(_KIND_LABELS.get(kind, "")) + '</small>' if kind else '') + '</td>'
            + '<td><span class="badge ' + tone + '">' + _e(status) + '</span><small class="moodle-subcell">' + _e(help_text) + '</small></td>'
            + '<td class="moodle-file">' + _e(os.path.basename(item.get("file") or "")) + '</td><td class="moodle-file">' + _e(item.get("detail")) + '</td></tr>'
        )
    downloads = (
        '<div class="moodle-report-links"><a class="enlace-accion" href="/moodle/' + _e(job["id"])
        + '/reporte?formato=csv">' + icon("descargar") + 'Descargar CSV</a><a class="enlace-accion" href="/moodle/' + _e(job["id"])
        + '/reporte?formato=json">' + icon("descargar") + 'Descargar JSON</a></div>' if paths else ""
    )
    stopped = report.get("stoppedReason") or ""
    return (
        '<section class="panel tabla-panel" id="moodle-report"><div class="tabla-cabecera"><div><h2>Resultado de la publicación</h2>'
        + '<p>' + ('Detenido: ' + _e(stopped) if stopped else 'Cada fila indica qué pasó y qué hacer.') + '</p></div>' + downloads + '</div>'
        + counts + '<div class="moodle-actions" style="margin:14px 0">' + _retry_form(job, report) + '</div>'
        + '<div class="tabla-scroll"><table class="tabla moodle-table"><thead><tr><th>Semana</th><th>Recurso</th><th>Resultado</th><th>Archivo</th><th>Detalle</th></tr></thead>'
        + '<tbody>' + ("".join(rows) or '<tr><td colspan="5">No hay filas de reporte.</td></tr>')
        + '</tbody></table></div></section>'
        + _labels_report(report.get("labels") or [])
    )


_LABEL_TONES = {"Borrada": "badge-verde", "No estaba": "badge-azul", "No se pudo borrar": "badge-rojo"}


def _labels_report(labels):
    if not labels:
        return ""
    rows = "".join(
        '<tr><td>' + _e(item.get("week")) + '</td><td>' + _e(item.get("label")) + '</td>'
        + '<td><span class="badge ' + _LABEL_TONES.get(item.get("status"), "badge-gris") + '">' + _e(item.get("status")) + '</span></td>'
        + '<td class="moodle-file">' + _e(item.get("detail")) + '</td></tr>'
        for item in labels
    )
    return (
        '<section class="panel tabla-panel"><div class="tabla-cabecera"><div><h2>Etiquetas sin uso</h2>'
        + '<p>Etiquetas de bloque que la matriz no usa en cada semana.</p></div></div>'
        + '<div class="tabla-scroll"><table class="tabla"><thead><tr><th>Semana</th><th>Etiqueta</th><th>Resultado</th><th>Detalle</th></tr></thead>'
        + '<tbody>' + rows + '</tbody></table></div></section>'
    )


def _job_view(job, error="", local=True, show_preview=False):
    status = job.get("status")
    running = status in _RUNNING
    alert = _alert(error)
    if running:
        # Mientras se publica solo se muestra lo que se está cargando (como en el cargue PRIZMA).
        return '<div class="moodle-page">' + alert + _progress(job) + '</div>'

    finished = bool(job.get("report")) or status in {"error", "cancelled", "completed"}
    if status == "error":
        alert += _alert(job.get("message"), title="La publicación se detuvo")
    elif status == "cancelled":
        alert += '<div class="aviso ambar" role="status">' + icon("info") + '<div><strong>Publicación cancelada.</strong><p>Los recursos que faltaban quedaron como «No procesado». Puedes reintentarlos abajo.</p></div></div>'
    elif status == "completed" and job.get("report"):
        alert += '<div class="aviso ok" role="status">' + icon("check-circulo") + '<div><strong>Publicación terminada.</strong><p>Este es el resultado de cada recurso.</p></div></div>'

    if finished and not show_preview:
        return (
            '<div class="moodle-page">' + _header(job) + alert + _report(job)
            + '<div class="moodle-actions"><a class="boton secundario" href="/moodle/' + _e(job["id"]) + '?vista=previa">'
            + icon("ver") + 'Publicar otros recursos de esta matriz</a>'
            + '<a class="boton neutro" href="/moodle">Preparar otro curso</a></div>'
            + _legend() + '</div>'
        )

    return (
        '<div class="moodle-page">' + _header(job) + alert
        + (('<div class="moodle-actions"><a class="boton neutro" href="/moodle/' + _e(job["id"]) + '">'
            + icon("flecha-izquierda") + 'Volver al resultado de la publicación</a></div>') if finished else '')
        + _overview(job) + _attention(job)
        + '<form action="/moodle/' + _e(job["id"]) + '/publicar" method="post" id="moodle-publish-form">'
        + _selection_panel(job, running) + _weeks_section(job, running) + '</form>'
        + _legend()
        + '<p class="moodle-help">Al publicar se abre Chromium visible en este equipo y se activa el «Modo de edición» del curso. Inicia sesión cuando se solicite; Auto Prizma no guarda tu contraseña.</p>'
        + '</div>'
    )


_JS_MOODLE = """
(function(){
  var form=document.getElementById('moodle-publish-form');
  var boxes=function(){return Array.prototype.slice.call(document.querySelectorAll('input[name="entry_keys"][type="checkbox"]'));};
  var groupOn=function(attr,value){var input=document.querySelector('['+attr+'="'+CSS.escape(value)+'"]');return !input||input.checked;};
  function firstSelected(){var chosen=boxes().filter(function(box){return box.checked&&!box.disabled;});chosen.sort(function(a,b){return Number(a.dataset.order)-Number(b.dataset.order);});return chosen[0];}
  function refreshCount(){
    var all=boxes().filter(function(box){return !box.disabled;});var chosen=all.filter(function(box){return box.checked;});
    var label=document.getElementById('moodle-selected-count');if(label)label.textContent=chosen.length+' de '+all.length+' recursos listos seleccionados';
    var button=document.getElementById('moodle-publish-button');if(button){button.lastChild.textContent='Publicar '+chosen.length+' seleccionados';button.disabled=!chosen.length;}
    var first=firstSelected();var target=document.getElementById('moodle-test-target');
    if(target)target.textContent=first?'«Probar con 1 recurso» publicará: '+first.dataset.title+' ('+first.dataset.week+').':'Marca al menos un recurso.';
  }
  function applyGroups(){boxes().forEach(function(box){if(box.disabled)return;box.checked=groupOn('data-sel-kind',box.dataset.kind)&&groupOn('data-sel-week',box.dataset.week);});refreshCount();}
  document.querySelectorAll('[data-sel-kind],[data-sel-week]').forEach(function(input){input.addEventListener('change',applyGroups);});
  document.querySelectorAll('[data-moodle-select]').forEach(function(button){button.addEventListener('click',function(){var on=button.dataset.moodleSelect==='all';document.querySelectorAll('[data-sel-kind],[data-sel-week]').forEach(function(input){if(!input.disabled)input.checked=on;});applyGroups();});});
  boxes().forEach(function(box){box.addEventListener('change',refreshCount);});
  document.querySelectorAll('[data-manual-attach]').forEach(function(button){button.addEventListener('click',async function(){
    var row=button.closest('[data-moodle-row]');var input=row&&row.querySelector('[data-manual-resource]');
    if(!input||!input.files||!input.files[0]){window.alert('Selecciona primero un archivo para esta fila.');return;}
    var data=new FormData();data.append('entry_key',input.dataset.entryKey);data.append('resource_file',input.files[0]);button.disabled=true;
    try{var response=await fetch(form.action.replace('/publicar','/recurso-manual'),{method:'POST',body:data,headers:{'Accept':'application/json'}});var result=await response.json();if(!response.ok){window.alert(result.error||'No se pudo adjuntar el archivo.');}else{window.location.reload();}}
    catch(_){window.alert('No se pudo contactar con Auto Prizma.');}
    finally{button.disabled=false;}
  });});
  if(form){form.addEventListener('submit',function(event){
    var mode=event.submitter&&event.submitter.value;var count=boxes().filter(function(box){return box.checked;}).length;
    if(!count){event.preventDefault();window.alert('Marca al menos un recurso listo para publicar.');return;}
    var first=firstSelected();
    var labels=document.getElementById('moodle-clean-labels');var cleaning=mode!=='test'&&labels&&labels.checked;
    var message=mode==='test'?'Se abrirá Chromium y se publicará solo: '+(first?first.dataset.title+' ('+first.dataset.week+')':'el primer recurso')+'. No se borra ninguna etiqueta. ¿Continuar?':'Se revisarán '+count+' recursos desde la semana 1. Los que ya estén en el curso no se duplican.'+(cleaning?' Al final se BORRARÁN las etiquetas sin uso de las semanas publicadas (no se puede deshacer).':'')+' ¿Continuar?';
    if(!window.confirm(message))event.preventDefault();});}
  document.querySelectorAll('[data-moodle-retry]').forEach(function(retry){retry.addEventListener('submit',function(event){if(!window.confirm('Se volverán a intentar '+retry.dataset.moodleRetry+' recursos. Los que ya estén en el curso no se duplican. ¿Continuar?'))event.preventDefault();});});
  refreshCount();

  var search=document.querySelector('[data-moodle-filter="search"]');var problemsOnly=document.querySelector('[data-moodle-filter="problems"]');
  var PROBLEMS=['missing','ambiguous','extension-mismatch'];
  function filterRows(){
    var text=(search&&search.value||'').trim().toLowerCase();var onlyProblems=problemsOnly&&problemsOnly.checked;
    document.querySelectorAll('[data-moodle-week]').forEach(function(week){
      var visible=0;
      week.querySelectorAll('[data-moodle-row]').forEach(function(row){var ok=(!text||row.dataset.search.indexOf(text)>=0)&&(!onlyProblems||PROBLEMS.indexOf(row.dataset.status)>=0);row.hidden=!ok;if(ok)visible++;});
      var filtering=!!text||onlyProblems;week.hidden=filtering&&!visible;if(filtering&&visible)week.open=true;
    });
  }
  [search,problemsOnly].forEach(function(input){if(input)input.addEventListener('input',filterRows);});
  if(problemsOnly)problemsOnly.addEventListener('change',filterRows);
  document.querySelectorAll('[data-moodle-expand]').forEach(function(button){button.addEventListener('click',function(){var open=button.dataset.moodleExpand==='open';document.querySelectorAll('[data-moodle-week]').forEach(function(week){if(!week.hidden)week.open=open;});});});

  var progress=document.getElementById('moodle-progress');
  if(!progress)return;
  var id=progress.getAttribute('data-job-id');var base='/moodle/'+encodeURIComponent(id);
  var LABELS={queued:'En cola',logging_in:'Esperando inicio de sesión',publishing:'Publicando',paused:'En pausa'};
  var TONES={'Cargado':'badge-verde','Ya estaba cargado':'badge-azul','No cargado':'badge-ambar','Revisar en Prizma':'badge-rojo','No procesado':'badge-gris'};
  function minutes(ms){var m=Math.round(ms/60000);return m<1?'menos de 1 min':m+' min';}
  function el(tag,cls,text){var node=document.createElement(tag);if(cls)node.className=cls;if(text!=null)node.textContent=text;return node;}
  var KINDS=__KIND_LABELS__;
  var ROWS={'badge-verde':'ok','badge-azul':'ok','badge-gris':'pendiente'};
  function render(job){
    var p=job.progress||{};var results=job.results||[];var queue=job.queue||[];var total=p.total||queue.length||0;
    document.getElementById('moodle-progress-message').textContent=job.message||'';
    document.getElementById('moodle-progress-status').textContent=job.cancel_requested?'Cancelando':(job.pause_requested&&!job.paused?'Pausando':(LABELS[job.status]||'Publicando'));
    document.getElementById('moodle-progress-current').textContent=p.title||'Preparando…';
    document.getElementById('moodle-progress-detail').textContent=[p.week,p.phase].filter(Boolean).join(' · ');
    document.getElementById('moodle-progress-count').textContent=results.length+' de '+total;
    var labelsCount=document.getElementById('moodle-labels-count');var labelResults=job.label_results||[];
    if(labelsCount&&labelResults.length){var removed=labelResults.filter(function(l){return l.status==='Borrada';}).length;labelsCount.textContent=removed+' borradas · '+labelResults.length+' revisadas';}
    document.getElementById('moodle-percent').textContent=(total?Math.floor(results.length*100/total):0)+'%';
    var bar=document.getElementById('moodle-progress-bar');bar.max=Math.max(1,total);bar.value=results.length;
    var counts={};results.forEach(function(r){counts[r.status]=(counts[r.status]||0)+1;});
    document.getElementById('moodle-n-done').textContent=results.length;
    document.getElementById('moodle-n-ok').textContent=counts['Cargado']||0;
    document.getElementById('moodle-n-present').textContent=counts['Ya estaba cargado']||0;
    document.getElementById('moodle-n-error').textContent=(counts['No cargado']||0)+(counts['Revisar en Prizma']||0);
    var pending=Math.max(0,total-results.length);
    var time=document.getElementById('moodle-progress-time');var started=Date.parse(job.started_at||progress.dataset.started||'');
    if(started){var elapsed=Date.now()-started;var text='Tiempo transcurrido: '+minutes(elapsed);if(results.length&&pending&&!job.paused)text+=' · faltan aprox. '+minutes(elapsed/results.length*pending);time.textContent=text;}
    progress.querySelector('[data-moodle-control="pausar"]').hidden=!!(job.paused||job.pause_requested||job.cancel_requested);
    progress.querySelector('[data-moodle-control="reanudar"]').hidden=!(job.paused||job.pause_requested)||!!job.cancel_requested;
    progress.querySelector('[data-moodle-control="cancelar"]').disabled=!!job.cancel_requested;
    var byKey={};results.forEach(function(r){byKey[r.previewKey]=r;});
    var list=document.getElementById('moodle-queue');var current=null;list.textContent='';
    queue.forEach(function(item,index){
      var r=byKey[item.previewKey];var row=el('li','moodle-queue-item');var badge;var detail='';
      if(r){var tone=TONES[r.status]||'badge-gris';row.classList.add(ROWS[tone]||'error');badge=el('span','badge '+tone,r.status);if(r.status!=='Cargado'&&r.status!=='Ya estaba cargado')detail=r.detail||'';}
      else if(index+1===p.index&&(job.status==='publishing'||job.status==='paused')){row.classList.add('procesando');badge=el('span','badge badge-recurso','En curso');detail=p.phase||'';current=row;}
      else{row.classList.add('pendiente');badge=el('span','badge badge-gris','Pendiente');}
      row.appendChild(el('span','moodle-queue-num',String(index+1)));
      var body=el('div');body.appendChild(el('strong',null,item.title));body.appendChild(el('small',null,[item.week,KINDS[item.kind]].filter(Boolean).join(' · ')));
      if(detail)body.appendChild(el('small','moodle-queue-detail',detail));
      row.appendChild(body);row.appendChild(badge);list.appendChild(row);
    });
    if(current&&list.scrollHeight>list.clientHeight){var top=current.offsetTop-list.offsetTop-list.clientHeight/3;if(Math.abs(list.scrollTop-top)>40)list.scrollTop=top;}
  }
  async function control(action,button){
    if(action==='cancelar'&&!window.confirm('¿Cancelar la publicación? Se termina el recurso que se está subiendo y los demás quedan sin procesar.'))return;
    button.disabled=true;
    try{var response=await fetch(base+'/'+action,{method:'POST',headers:{'Accept':'application/json'}});var data=await response.json();if(!response.ok){window.alert(data.error||'No se pudo completar la acción.');}else{render(data);}}
    catch(_){window.alert('No se pudo contactar con Auto Prizma.');}
    finally{if(action!=='cancelar')button.disabled=false;}
  }
  progress.querySelectorAll('[data-moodle-control]').forEach(function(button){button.addEventListener('click',function(){control(button.dataset.moodleControl,button);});});
  async function poll(){try{var response=await fetch(base+'/estado',{headers:{'Accept':'application/json'}});if(!response.ok){window.setTimeout(poll,3000);return;}var job=await response.json();if(job.finished){window.location.reload();return;}render(job);window.setTimeout(poll,1500);}catch(_){window.setTimeout(poll,3000);}}
  poll();
})();
"""


def render_moodle_page(job=None, *, error="", local=True, show_preview=False):
    content = _job_view(job, error=error, local=local, show_preview=show_preview) if job else (
        '<div class="moodle-page">' + _header()
        + (_upload_form(error) if local else
           '<div class="aviso ambar" role="status">' + icon("info") + '<div><strong>Este apartado solo está disponible desde una instancia local.</strong>'
           + '<p>Abre Auto Prizma en el equipo donde se abrirá Chromium: <code>http://127.0.0.1:8000</code>.</p></div></div>')
        + '</div>'
    )
    return render_page(
        "Cargue Moodle",
        content,
        active="moodle",
        page_css=_CSS_MOODLE,
        page_js=_JS_MOODLE.replace("__KIND_LABELS__", json.dumps(_KIND_LABELS, ensure_ascii=False)) if job else "",
    )


def render_moodle_labels_page(*, local=True):
    if local:
        content = (
            '<div class="moodle-page"><header class="moodle-heading"><div class="icono-tile">'
            + icon("codigo") + '</div><div><h1>Información de etiquetas</h1>'
            + '<p>Prepara el HTML de banners, infografías y videos para usarlo en las etiquetas del curso.</p></div></header>'
            + _label_info_section() + '</div>'
        )
    else:
        content = (
            '<div class="moodle-page"><div class="aviso ambar" role="status">' + icon("info")
            + '<div><strong>Esta herramienta solo está disponible desde una instancia local.</strong>'
            + '<p>Abre Auto Prizma desde <code>http://127.0.0.1:8000</code>.</p></div></div></div>'
        )
    return render_page(
        "Etiquetas Moodle", content, active="moodle-etiquetas",
        page_css=_CSS_MOODLE, page_js=_JS_LABEL_INFO if local else "",
    )
