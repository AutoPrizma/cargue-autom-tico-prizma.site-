"""Auditor de recursos: cruza la matriz de recursos del curso con el ZIP.

Es la version web del auditor local `curso-checker`
(~/Documents/curso-checker). La logica de cruce (prefijos de tema,
nombres truncados, copias "(1)", similitud, titulos internos H5P) vive en
auto_prizma/auditor/procesar.py, copiada TAL CUAL del proyecto original.
Aqui solo se suben la matriz (CSV) y los recursos (ZIP) y se pinta el
dictamen. Solo audita: no modifica archivos ni carga nada a PRIZMA.

La vista usa el mismo diseno que el resto de la app: encabezado con
icono-tile, dropzones de Inicio, mosaicos de resumen y colores por
variables (tema claro/oscuro automatico).
"""

import html
import os
import shutil
import uuid
import zipfile

from fastapi import File, UploadFile
from fastapi.responses import HTMLResponse

from auto_prizma.auditor.procesar import ejecutar_auditoria
from auto_prizma.core.application import app
from auto_prizma.core.config import TEMP_DIR
from auto_prizma.web.icons import icon
from auto_prizma.web.layout import render_page
from auto_prizma.web.views import _archivo_listo


def _e(valor):
    return html.escape(str(valor or ""))


def _ubicacion(item):
    partes = []
    if str(item.get("fila") or ""):
        partes.append("Fila " + str(item["fila"]))
    if str(item.get("unidad") or ""):
        partes.append(str(item["unidad"]))
    if str(item.get("semana") or ""):
        partes.append(str(item["semana"]))
    return " · ".join(_e(p) for p in partes)


_BADGES = {
    "ok": ("aud-badge--ok", "OK"),
    "alerta": ("aud-badge--alerta", "Alerta"),
    "faltante": ("aud-badge--faltante", "Faltante"),
    "fuera-de-alcance": ("aud-badge--na", "Fuera de alcance"),
}


def _fila_recurso(item):
    """Fila de un recurso auditado (badge de estado + detalle)."""
    estado = str(item.get("estado") or "")
    clase, texto = _BADGES.get(estado, ("aud-badge--na", estado))
    sugerido = item.get("sugerencia") or {}
    extra = ""
    if sugerido.get("archivo"):
        extra = (
            '<p class="aud-sugerencia">Quizás es: <code>'
            + _e(sugerido["archivo"])
            + "</code> (similitud "
            + _e(f"{round((sugerido.get('similitud') or 0) * 100)}%)")
            + "</p>"
        )
    archivo = ""
    if item.get("archivo"):
        archivo = (
            '<p class="aud-archivo">' + icon("documento") + " <code>"
            + _e(item["archivo"]) + "</code></p>"
        )
    return (
        '<li class="aud-recurso">'
        + '<span class="aud-badge ' + clase + '">' + texto + "</span>"
        + "<div>"
        + "<strong>" + _e(item.get("nombre")) + "</strong>"
        + '<span class="aud-ubicacion">' + _ubicacion(item) + "</span>"
        + archivo
        + '<p class="aud-detalle">' + _e(item.get("detalle")) + "</p>"
        + extra
        + "</div></li>"
    )


def _cabecera(acciones=""):
    """Encabezado estandar de la app: icono-tile grande + titulo + acciones."""
    return (
        '<header class="encabezado"><div class="encabezado-titulo">'
        '<span class="icono-tile grande morado">' + icon("escudo") + "</span>"
        "<div><h1>Auditor de recursos</h1>"
        "<p>Cruza la <strong>matriz de recursos</strong> del curso (CSV) con el "
        "<strong>ZIP de archivos</strong>: nombres, títulos internos H5P, copias "
        "y faltantes. <strong>Solo audita</strong>: no modifica archivos ni carga "
        "nada a PRIZMA.</p></div></div>"
        + (f'<div class="encabezado-acciones">{acciones}</div>' if acciones else "")
        + "</header>"
    )


# ============================================================
# PAGINA
# ============================================================


def _campo(id_input, titulo, pista, nombre_icono, requerido, aceptar):
    return (
        '<div class="aud-campo">'
        '<div class="aud-campo-titulo"><span class="icono-tile chico">'
        + icon(nombre_icono)
        + "</span><div><h2>" + titulo + "</h2><p>" + pista + "</p></div></div>"
        '<label class="dropzone zona-drop" for="' + id_input
        + '" data-input="' + id_input + '">'
        + icon("subir", "icono icono-drop")
        + "<strong>Selecciona o arrastra tu archivo</strong>"
        + "<small>" + aceptar.replace(".", "").replace(",", " · ") + "</small>"
        + '<span class="boton">Seleccionar archivo</span>'
        + '<input id="' + id_input + '" type="file" name="' + id_input
        + '" accept="' + aceptar + '"'
        + (" required" if requerido else "")
        + "></label>"
        + _archivo_listo(id_input, nombre_icono)
        + "</div>"
    )


def _pagina_formulario(error="", advertencias=(), active="auditor", action="/auditor"):
    aviso = ""
    if error:
        aviso = (
            '<div class="aviso error" role="alert">' + icon("alerta-circulo")
            + "<div><strong>No se pudo auditar</strong><p>" + _e(error)
            + "</p></div></div>"
        )
    if advertencias:
        avisos_html = "".join(
            "<li>" + _e(a) + "</li>" for a in advertencias if a
        )
        if avisos_html:
            aviso += (
                '<div class="aviso ambar" role="status">' + icon("alerta")
                + "<div><strong>Avisos de la auditoría</strong><ul>"
                + avisos_html + "</ul></div></div>"
            )

    contenido = (
        _cabecera()
        + aviso
        + '<form class="panel aud-formulario" method="post" action="' + action + '" '
        'enctype="multipart/form-data">'
        '<div class="aud-campos">'
        + _campo(
            "matriz",
            "Matriz de recursos",
            "Exporta la hoja de Excel como CSV UTF-8.",
            "hoja", True, ".csv,.txt",
        )
        + _campo(
            "recursos",
            "ZIP de recursos",
            "Un solo .zip con los archivos del curso.",
            "zip", True, ".zip",
        )
        + _campo(
            "syllabus",
            "Syllabus (opcional)",
            "Cruce opcional con la matriz.",
            "documento", False, ".docx,.pdf,.txt",
        )
        + "</div>"
        '<button class="boton" type="submit">' + icon("escudo")
        + "Auditar</button>"
        "</form>"
    )
    return render_page(
        "Auditor de recursos",
        contenido,
        active=active,
        page_css=_CSS,
        page_js=_JS,
    )


def _pagina_resultado(res, nombre_matriz, active="auditor", action="/auditor"):
    conteo = res["conteo"]
    corregir = [
        r for r in res["resultados"] if r["estado"] in ("alerta", "faltante")
    ]
    oks = [r for r in res["resultados"] if r["estado"] == "ok"]
    fuera = [
        r for r in res["resultados"] if r["estado"] == "fuera-de-alcance"
    ]

    acciones = (
        '<a class="boton secundario" href="' + action + '">' + icon("girar")
        + "Nueva auditoría</a>"
    )

    if corregir:
        veredicto = (
            '<div class="mosaico estado error aud-veredicto" role="alert">'
            '<span class="icono-tile">' + icon("alerta-circulo") + "</span>"
            "<div><strong>" + str(len(corregir)) + "</strong>"
            "<b>recurso(s) por corregir</b>"
            "<small>Revisa las alertas y los faltantes indicados abajo.</small></div></div>"
        )
    else:
        veredicto = (
            '<div class="mosaico estado ok aud-veredicto" role="status">'
            '<span class="icono-tile">' + icon("check-circulo") + "</span>"
            "<div><strong>Todo calza</strong>"
            "<b>" + str(conteo["ok"]) + " recurso(s) correctos</b>"
            "<small>Los nombres y los títulos internos calzan con la "
            "matriz.</small></div></div>"
        )

    fichas = (
        '<section class="mosaicos" aria-label="Resumen">'
        + _ficha("check", "verde", conteo["ok"], "OK")
        + _ficha("alerta", "ambar", conteo["alerta"], "Alertas")
        + _ficha("alerta-circulo", "rojo", conteo["faltante"], "Faltantes")
        + _ficha(
            "play", "naranja", conteo["fuera-de-alcance"], "Fuera de alcance"
        )
        + _ficha("documento", "morado", len(res["huerfanos"]), "Huérfanos")
        + _ficha("zip", "azul", res["total_archivos"], "Archivos en el ZIP")
        + "</section>"
    )

    seccion_corregir = ""
    if corregir:
        seccion_corregir = (
            '<section class="panel aud-panel"><h2>Por corregir ('
            + str(len(corregir))
            + ")</h2><ul class='aud-lista'>"
            + "".join(_fila_recurso(r) for r in corregir)
            + "</ul></section>"
        )

    def _plegable(titulo, items):
        if not items:
            return ""
        return (
            '<details class="panel aud-panel"><summary>'
            + titulo + " (" + str(len(items)) + ")</summary><ul class='aud-lista'>"
            + "".join(_fila_recurso(r) for r in items)
            + "</ul></details>"
        )

    secciones_extra = (
        _plegable("Correctos (OK)", oks)
        + _plegable("Fuera de alcance (video/otros, no se auditan)", fuera)
    )

    huerfanos = ""
    if res["huerfanos"]:
        huerfanos = (
            '<details class="panel aud-panel"><summary>Huérfanos ('
            + str(len(res["huerfanos"]))
            + ") — archivos sin fila en la matriz</summary><ul class='aud-lista'>"
            + "".join(
                "<li class='aud-recurso'><span class='aud-badge aud-badge--na'>"
                "—</span><div><code>" + _e(rel) + "</code></div></li>"
                for rel in res["huerfanos"]
            )
            + "</ul></details>"
        )

    revision = ""
    if res["archivos_detalle"]:
        filas = "".join(
            "<tr><td>" + ("✓" if f.get("abre") == "ok" else "✗") + "</td>"
            "<td><code>" + _e(f.get("archivo")) + "</code></td>"
            "<td>" + _e(f.get("ext")) + "</td>"
            "<td>" + _e(f.get("nota")) + "</td></tr>"
            for f in res["archivos_detalle"]
        )
        revision = (
            '<details class="panel aud-panel">'
            "<summary>Revisión 1 a 1 — todos los archivos ("
            + str(len(res["archivos_detalle"]))
            + ")</summary><div class='tabla-scroll'><table class='tabla'>"
            "<thead><tr><th>Abre</th><th>Archivo</th><th>Ext</th>"
            "<th>Al abrir / título</th></tr></thead><tbody>"
            + filas + "</tbody></table></div></details>"
        )

    advertencias = ""
    if res["advertencias"]:
        advertencias = (
            '<details class="panel aud-panel"><summary>Advertencias ('
            + str(len(res["advertencias"])) + ")</summary><ul>"
            + "".join("<li>" + _e(a) + "</li>" for a in res["advertencias"])
            + "</ul></details>"
        )

    syllabus = ""
    sy = res.get("syllabus")
    if sy:
        if sy.get("error"):
            cuerpo = "No se pudo leer: " + str(sy["error"])
            clase, ico = "error", "alerta-circulo"
        elif sy.get("ok"):
            cuerpo = "El syllabus es consistente con la matriz."
            clase, ico = "ok", "check-circulo"
        else:
            cuerpo = (
                str(sy.get("avisos", 0))
                + " aviso(s): revisa las filas de la auditoría para el detalle."
            )
            clase, ico = "ambar", "alerta"
        syllabus = (
            '<div class="aviso ' + clase + '" role="status">' + icon(ico)
            + "<div><strong>Syllabus: " + _e(sy.get("nombre") or "")
            + "</strong><p>" + html.escape(cuerpo) + "</p></div></div>"
        )

    contenido = (
        _cabecera(acciones=acciones)
        + '<p class="aud-linea">' + icon("zip") + " "
        + str(res["total_archivos"]) + " archivo(s) en el ZIP · "
        + str(res["total_auditables"]) + " recurso(s) auditables en <code>"
        + _e(nombre_matriz) + "</code></p>"
        + veredicto + fichas + syllabus + seccion_corregir
        + secciones_extra + huerfanos + revision + advertencias
    )
    return render_page(
        "Auditor de recursos",
        contenido,
        active=active,
        page_css=_CSS,
        page_js=_JS,
    )


def _ficha(nombre_icono, color, valor, texto):
    return (
        '<div class="mosaico"><span class="icono-tile ' + color + '">'
        + icon(nombre_icono)
        + '</span><div><strong class="num">' + str(valor) + "</strong><span>"
        + _e(texto) + "</span></div></div>"
    )


_CSS = r"""
/* Encabezado y tarjeta del formulario */
.aud-formulario { padding: 26px; display: grid; gap: 22px; }
.aud-campos { display: grid; grid-template-columns: repeat(auto-fit, minmax(280px, 1fr)); gap: 20px; }
.aud-campo { display: grid; gap: 12px; align-content: start; min-width: 0; }
.aud-campo-titulo { display: flex; gap: 12px; align-items: center; }
.aud-campo-titulo h2 { margin: 0; font-size: 16px; font-weight: 800; }
.aud-campo-titulo p { margin: 3px 0 0; font-size: 13px; color: var(--muted); }
.aud-formulario > .boton { justify-self: start; }

/* Dropzones y archivo listo (mismo diseno de Inicio) */
.dropzone {
  display: grid; justify-items: center; gap: 6px; text-align: center;
  padding: 24px 18px; border: 2px dashed var(--acento-borde); border-radius: 14px;
  background: var(--panel-2); cursor: pointer;
  transition: border-color .15s ease, background .15s ease;
}
.dropzone:hover, .dropzone.arrastrando { border-color: var(--acento); background: var(--acento-suave); }
.dropzone input { display: none; }
.dropzone .icono-drop { width: 34px; height: 34px; color: var(--acento-texto); }
.dropzone strong { font-size: 15px; color: var(--texto); }
.dropzone small { font-size: 13px; color: var(--muted); }
.dropzone .boton { margin-top: 10px; padding: 10px 26px; }

.archivo-listo {
  display: flex; align-items: center; gap: 14px; min-width: 0;
  padding: 12px 14px; border: 1px solid var(--borde); border-radius: 14px;
  background: var(--panel);
}
.archivo-listo-texto { flex: 1; min-width: 0; }
.archivo-listo-texto strong {
  display: block; font-size: 15px; color: var(--texto);
  overflow: hidden; text-overflow: ellipsis; white-space: nowrap;
}
.archivo-listo-texto small { display: block; margin-top: 2px; font-size: 13.5px; color: var(--muted); }
.icono-listo { width: 28px; height: 28px; }
.icono-listo circle { fill: var(--verde); stroke: var(--verde); }
.icono-listo path { stroke: var(--boton-texto); stroke-width: 2.4; }
.archivo-listo .boton-icono { border-left: 1px solid var(--borde); border-radius: 0 10px 10px 0; }

/* Resultado */
.aud-linea { display: flex; align-items: center; gap: 8px; color: var(--muted); font-size: 14px; margin: 0 0 18px; }
.aud-veredicto { margin: 0 0 18px; }
.aud-panel { padding: 22px 26px; }
.aud-panel > h2 { margin: 0 0 6px; font-size: 19px; font-weight: 800; }
.aud-panel summary { cursor: pointer; font-weight: 700; font-size: 15px; }

/* Filas de recursos */
.aud-lista { list-style: none; margin: 0; padding: 0; }
.aud-recurso { display: flex; gap: 12px; align-items: flex-start; padding: 12px 0; border-top: 1px solid var(--borde); }
.aud-recurso:first-child { border-top: 0; padding-top: 4px; }
.aud-recurso > div { min-width: 0; }
.aud-ubicacion { margin-left: 8px; font-size: 12px; color: var(--muted); }
.aud-archivo { margin: 3px 0; font-size: 13px; color: var(--muted); display: flex; gap: 6px; align-items: center; }
.aud-detalle { margin: 3px 0 0; font-size: 13px; color: var(--texto-2); }
.aud-sugerencia { margin: 3px 0 0; font-size: 13px; color: var(--ambar); }
.aud-badge {
  flex: none; display: inline-block; border-radius: 999px; padding: 5px 10px;
  font-size: 11px; font-weight: 800; text-transform: uppercase; letter-spacing: .3px;
}
.aud-badge--ok { background: var(--verde-suave); color: var(--verde); }
.aud-badge--alerta { background: var(--ambar-suave); color: var(--ambar); }
.aud-badge--faltante { background: var(--rojo-suave); color: var(--rojo); }
.aud-badge--na { background: var(--panel-2); color: var(--muted); }

/* Historial */
.aud-historial { list-style: none; margin: 8px 0 0; padding: 0; display: grid; gap: 8px; }
.aud-historial a { display: flex; gap: 8px; align-items: center; color: var(--acento-texto); font-weight: 600; font-size: 14px; }
"""

_JS = r"""
  function tamanoLegible(bytes) {
    if (bytes >= 1024 * 1024) {
      return (bytes / 1024 / 1024).toLocaleString('es-CO', { maximumFractionDigits: 1 }) + ' MB';
    }
    return Math.max(1, Math.round(bytes / 1024)).toLocaleString('es-CO') + ' KB';
  }

  function mostrarArchivo(input) {
    var fila = document.getElementById('listo-' + input.id);
    if (!fila) return;
    var archivo = input.files && input.files[0];
    if (!archivo) { fila.hidden = true; return; }
    var nombre = fila.querySelector('[data-nombre]');
    nombre.textContent = archivo.name;
    nombre.title = archivo.name;
    fila.querySelector('[data-detalle]').textContent = tamanoLegible(archivo.size) + ' · Listo para auditar';
    fila.hidden = false;
  }

  document.querySelectorAll('.zona-drop').forEach(function (zona) {
    var input = document.getElementById(zona.dataset.input);
    if (!input) return;
    input.addEventListener('change', function () { mostrarArchivo(input); });

    ['dragenter', 'dragover'].forEach(function (tipo) {
      zona.addEventListener(tipo, function (evento) {
        evento.preventDefault();
        evento.stopPropagation();
        zona.classList.add('arrastrando');
      });
    });
    ['dragleave', 'drop'].forEach(function (tipo) {
      zona.addEventListener(tipo, function (evento) {
        evento.preventDefault();
        evento.stopPropagation();
        zona.classList.remove('arrastrando');
      });
    });
    zona.addEventListener('drop', function (evento) {
      var archivos = evento.dataTransfer.files;
      if (!archivos || !archivos.length || input.disabled) return;
      var transferencia = new DataTransfer();
      transferencia.items.add(archivos[0]);
      input.files = transferencia.files;
      input.dispatchEvent(new Event('change', { bubbles: true }));
    });
  });

  document.querySelectorAll('[data-quitar]').forEach(function (boton) {
    boton.addEventListener('click', function () {
      var input = document.getElementById(boton.getAttribute('data-quitar'));
      if (!input) return;
      input.value = '';
      input.dispatchEvent(new Event('change', { bubbles: true }));
    });
  });
"""


# ============================================================
# RUTAS
# ============================================================

@app.get("/auditor", response_class=HTMLResponse)
def pagina_auditor():
    return _pagina_formulario()


@app.post("/auditor", response_class=HTMLResponse)
async def auditar_curso(
    matriz: UploadFile = File(...),
    recursos: UploadFile = File(...),
    syllabus: UploadFile | None = File(default=None),
):
    return await _auditar_archivos(matriz, recursos, syllabus)


async def _auditar_archivos(matriz, recursos, syllabus, *, active="auditor", action="/auditor"):
    nombre_matriz = os.path.basename(matriz.filename or "matriz.csv")
    if not nombre_matriz.lower().endswith((".csv", ".txt")):
        return _pagina_formulario(
            error="La matriz debe ser un CSV. Si es de Excel: "
            "Archivo → Guardar como → CSV UTF-8.", active=active, action=action
        )

    texto_matriz = (await matriz.read()).decode("utf-8-sig", errors="replace")

    os.makedirs(TEMP_DIR, exist_ok=True)
    ruta_zip = os.path.join(TEMP_DIR, "auditoria_" + uuid.uuid4().hex + ".zip")
    res = None
    try:
        with open(ruta_zip, "wb") as fh:
            shutil.copyfileobj(recursos.file, fh)
        if not zipfile.is_zipfile(ruta_zip):
            return _pagina_formulario(
                error="El archivo de recursos no es un ZIP válido.", active=active, action=action
            )
        syllabus_bytes = await syllabus.read() if syllabus else None
        res = ejecutar_auditoria(
            ruta_zip,
            None,
            None,
            matriz_texto=texto_matriz,
            matriz_nombre=nombre_matriz,
            syllabus=syllabus_bytes,
            syllabus_nombre=os.path.basename(syllabus.filename or "")
            if syllabus else "",
        )
    finally:
        if os.path.exists(ruta_zip):
            os.remove(ruta_zip)

    if not res.get("ok"):
        return _pagina_formulario(
            error=res.get("error") or "Error desconocido al auditar.",
            advertencias=res.get("advertencias") or [],
            active=active, action=action,
        )
    return _pagina_resultado(res, nombre_matriz, active=active, action=action)


@app.get("/moodle-auditor", response_class=HTMLResponse)
def pagina_auditor_moodle():
    return _pagina_formulario(active="moodle-auditor", action="/moodle-auditor")


@app.post("/moodle-auditor", response_class=HTMLResponse)
async def auditar_curso_moodle(
    matriz: UploadFile = File(...),
    recursos: UploadFile = File(...),
    syllabus: UploadFile | None = File(default=None),
):
    return await _auditar_archivos(
        matriz, recursos, syllabus, active="moodle-auditor", action="/moodle-auditor"
    )
