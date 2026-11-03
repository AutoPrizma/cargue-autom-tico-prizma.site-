"""Marco comun de todas las paginas: barra lateral, barra superior y recursos compartidos.

- render_page(): paginas con sesion (menu lateral, estado del servicio,
  tema claro/oscuro y menu del usuario).
- render_public_page(): paginas sin sesion (login).

El aspecto comun vive en static/app.css y el comportamiento comun (tema,
menus, copiar, tablas, estado del servicio) en static/app.js. Cada pagina
solo agrega su contenido y, si lo necesita, su CSS/JS propio.
"""

import html
import os

from auto_prizma.core.config import (
    APP_CSS_PATH,
    APP_JS_PATH,
    PRIZMA_ES_PRODUCCION,
    PRIZMA_HOST,
)
from auto_prizma.services.auth import acceso_local_directo, _nombre_visible, _usuario_actual
from auto_prizma.services.health import cached_service_status
from auto_prizma.web.icons import icon

APP_NAME = "Cargue Prizma Pro"
CONTROL_TOWER_URL = (
    "https://script.google.com/a/macros/americana.edu.co/s/"
    "AKfycbzh6DwDAEGJDJ8a56UexlEINc7NzYpS-SoONAf8fRhj1Q8ksuIdRQRm9XtFUp6dwAm-/exec"
)

# (clave, texto, ruta, icono) en el orden del menu lateral.
NAV_ITEMS = (
    ("inicio", "Inicio", "/", "inicio"),
    ("control-tower", "Control Tower", CONTROL_TOWER_URL, "torre"),
    ("matrices", "Matrices", "/matrices-favoritas", "hoja"),
    ("prizma", "Cargue PRIZMA", "/auditor", "subir"),
    ("moodle", "Cargue Moodle", "/moodle-auditor", "moodle"),
    ("n8n", "Automatizaciones", "/automatizaciones-n8n", "codigo"),
)

_PRIZMA_TAB_KEYS = {"prizma", "test", "auditor", "cargue", "cursos", "historial", "reportes", "curso-auditor"}
_WORKSPACE_TABS = {
    "prizma": (
        ("auditor", "Auditor", "/auditor"),
        ("prizma", "Cargue", "/prizma"),
        ("test", "Test", "/tests"),
        ("curso-auditor", "Auditar curso", "/auditor-curso"),
        ("cursos", "Cursos", "/cursos"),
        ("cargue", "En curso", "/cargue-actual"),
        ("historial", "Historial", "/historial"),
        ("reportes", "Reportes", "/reportes"),
    ),
    "moodle": (
        ("moodle-auditor", "Auditor", "/moodle-auditor"),
        ("moodle", "Cargue", "/moodle"),
        ("moodle-etiquetas", "Etiquetas", "/moodle-etiquetas"),
        ("moodle-auditor-curso", "Auditar curso", "/moodle-auditor-curso"),
        ("moodle-reportes", "Reportes", "/moodle-reportes"),
    ),
}

_WORKSPACE_CSS = """
.workspace-tabs{display:flex;gap:7px;align-items:center;overflow-x:auto;margin:0 0 20px;padding:5px;border:1px solid var(--borde);border-radius:14px;background:var(--panel);scrollbar-width:thin}
.workspace-tab{display:inline-flex;align-items:center;justify-content:center;min-height:38px;padding:8px 14px;border-radius:10px;color:var(--texto-2);text-decoration:none;font-size:13px;font-weight:700;white-space:nowrap;transition:background .15s,color .15s}
.workspace-tab:hover{background:var(--acento-suave);color:var(--acento-texto)}.workspace-tab[aria-current="page"]{background:var(--acento);color:var(--boton-texto);box-shadow:inset 0 0 0 1px var(--acento-borde)}
.contenido-pagina{display:grid;gap:18px;align-content:start;min-width:0}
.contenido-pagina>.encabezado{margin:4px 0 0}
.contenido-pagina>.aviso{margin:0}
.workspace-content>.encabezado,.workspace-content>.cursos-page>.encabezado,.workspace-content>.moodle-page>.moodle-heading,.workspace-content>.encabezado-inicio{margin:0!important}
.workspace-content .encabezado-titulo{align-items:center;gap:16px}
.workspace-content .workspace-page-heading .encabezado-titulo>div{min-width:0}
.workspace-content .workspace-page-heading p{max-width:800px;line-height:1.5}
.workspace-content .encabezado .icono-tile.grande{width:56px;height:56px;border-radius:16px}
.workspace-content .encabezado .icono-tile.grande .icono{width:26px;height:26px}
.workspace-content .moodle-heading{align-items:center;margin:0}
.workspace-content>.encabezado h1,.workspace-content>.cursos-page>.encabezado h1,.workspace-content>.moodle-page>.moodle-heading h1,.workspace-content>.encabezado-inicio h1,.workspace-content>h1{margin:0;font-size:30px;line-height:1.2;font-weight:800;letter-spacing:-.02em;text-align:left}
.workspace-content>h1+p{margin:6px 0 0;color:var(--muted);font-size:15px;text-align:left}
.workspace-content>.panel.vacio{display:grid;grid-template-columns:56px minmax(0,1fr);gap:10px 16px;align-items:start;padding:28px;text-align:left}
.workspace-content>.panel.vacio>.icono-tile{grid-column:1;grid-row:1/4}
.workspace-content>.panel.vacio>h1{grid-column:2;grid-row:1;align-self:center;margin:0;font-size:30px;line-height:1.2;font-weight:800;letter-spacing:-.02em;text-align:left}
.workspace-content>.panel.vacio>p{grid-column:2;grid-row:2;margin:0;color:var(--muted);text-align:left}
.workspace-content>.panel.vacio>.boton{grid-column:2;justify-self:start;margin-top:6px}
@media(max-width:700px){.workspace-content>.encabezado h1,.workspace-content>.cursos-page>.encabezado h1,.workspace-content>.moodle-page>.moodle-heading h1,.workspace-content>.encabezado-inicio h1,.workspace-content>h1,.workspace-content>.panel.vacio>h1{font-size:26px}}
"""

# Se ejecuta antes de pintar para que el tema oscuro no parpadee.
_THEME_BOOT = (
    '<script>try{if(localStorage.getItem("autoPrizmaTema")==="dark")'
    'document.documentElement.setAttribute("data-theme","dark")}catch(e){}</script>'
)


def _e(valor):
    return html.escape(str(valor or ""), quote=True)


def asset_url(path, public_path):
    """URL del recurso con su fecha de modificacion, para que el navegador
    descargue la version nueva despues de cada cambio."""
    try:
        version = str(int(os.path.getmtime(path)))
    except OSError:
        version = "0"
    return public_path + "?v=" + version


# ============================================================
# ESTADO DEL SERVICIO
# ============================================================

_TEXTOS_ESTADO = {
    # (indicador, estado): texto. Los mismos textos usa static/app.js.
    ("linea", "ok"): "Servicio activo",
    ("linea", "error"): "Servicio con problemas",
    ("linea", "pendiente"): "Comprobando servicio",
    ("chromium", "ok"): "Chromium",
    ("chromium", "error"): "No disponible",
    ("chromium", "pendiente"): "Comprobando",
    ("prizma", "ok"): "Estable",
    ("prizma", "error"): "Sin respuesta",
    ("prizma", "pendiente"): "Comprobando",
    ("pastilla-chromium", "ok"): "Chromium activo",
    ("pastilla-chromium", "error"): "Chromium no disponible",
    ("pastilla-chromium", "pendiente"): "Comprobando Chromium",
    ("pastilla-prizma", "ok"): "Servicio estable",
    ("pastilla-prizma", "error"): "PRIZMA sin respuesta",
    ("pastilla-prizma", "pendiente"): "Comprobando PRIZMA",
}


def _estado(item):
    """ok / error / pendiente a partir de un resultado de services.health."""
    if not item:
        return "pendiente"
    return "ok" if item.get("ok") else "error"


def _initial_status():
    """Estados y detalles conocidos (sin comprobar nada)."""
    estado = cached_service_status() or {}
    chromium = estado.get("chromium")
    prizma = estado.get("prizma")
    linea = "pendiente"
    if chromium and prizma:
        linea = "ok" if estado.get("ok") else "error"
    elif (chromium and not chromium.get("ok")) or (prizma and not prizma.get("ok")):
        linea = "error"
    return {
        "linea": (linea, ""),
        "chromium": (_estado(chromium), (chromium or {}).get("detalle", "")),
        "prizma": (_estado(prizma), (prizma or {}).get("detalle", "")),
    }


def _service_card():
    estado = _initial_status()
    linea, _ = estado["linea"]
    chromium, detalle_chromium = estado["chromium"]
    prizma, detalle_prizma = estado["prizma"]
    return (
        '<div class="estado-servicio" data-estado-servicio>'
        '<div class="servicio-linea" data-servicio="linea" data-estado="' + linea + '">'
        '<i class="punto"></i><span data-texto>' + _TEXTOS_ESTADO[("linea", linea)] + "</span></div>"
        '<div class="servicio-mini"><span>Navegador</span>'
        '<span class="chip" data-servicio="chromium" data-estado="' + chromium + '" title="' + _e(detalle_chromium) + '">'
        '<span data-texto>' + _TEXTOS_ESTADO[("chromium", chromium)] + "</span></span></div>"
        '<div class="servicio-mini"><span>Conexión</span>'
        '<span class="chip" data-servicio="prizma" data-estado="' + prizma + '" title="' + _e(detalle_prizma) + '">'
        '<span data-texto>' + _TEXTOS_ESTADO[("prizma", prizma)] + "</span></span></div>"
        "</div>"
    )


def status_pills():
    """Indicadores de Chromium y PRIZMA.

    Chromium y PRIZMA se pintan con lo que haya en memoria y static/app.js
    los actualiza con /estado-servicio.
    """
    estado = _initial_status()
    chromium, detalle_chromium = estado["chromium"]
    prizma, detalle_prizma = estado["prizma"]
    return (
        '<div class="pastillas">'
        + '<span class="pastilla" data-servicio="pastilla-chromium" data-estado="' + chromium
        + '" title="' + _e(detalle_chromium) + '">' + icon("chromium", "icono icono-chromium")
        + '<span data-texto>' + _TEXTOS_ESTADO[("pastilla-chromium", chromium)] + '</span><i class="punto"></i></span>'
        + '<span class="pastilla" data-servicio="pastilla-prizma" data-estado="' + prizma
        + '" title="' + _e(detalle_prizma) + '">' + icon("wifi", "icono icono-wifi")
        + '<span data-texto>' + _TEXTOS_ESTADO[("pastilla-prizma", prizma)] + '</span><i class="punto"></i></span>'
        + "</div>"
    )


# ============================================================
# PIEZAS DEL MARCO
# ============================================================

def environment_notice():
    """Aviso visible cuando la app apunta a un PRIZMA que no es produccion.

    En produccion devuelve "" para no alterar la pagina.
    """
    if PRIZMA_ES_PRODUCCION:
        return ""

    return (
        '<div class="aviso-ambiente" role="status">' + icon("matraz")
        + "<span><strong>Ambiente de pruebas de PRIZMA:</strong> " + html.escape(PRIZMA_HOST)
        + ". Los cargues de esta instancia no van a producción.</span></div>"
    )


def _initials(nombre):
    partes = [parte for parte in str(nombre or "").split() if parte]
    if len(partes) >= 2:
        return (partes[0][0] + partes[1][0]).upper()
    if partes:
        return partes[0][0].upper()
    return "?"


def _theme_button():
    return (
        '<button type="button" class="boton-tema" data-tema-toggle '
        'aria-label="Cambiar a tema oscuro" title="Cambiar a tema oscuro">'
        + icon("luna", "icono icono-luna") + icon("sol", "icono icono-sol") + "</button>"
    )


def _user_menu():
    if acceso_local_directo():
        return ""
    usuario = _usuario_actual() or ""
    nombre = _nombre_visible(usuario) or usuario or "Usuario"
    return (
        '<div class="menu-usuario" data-menu>'
        '<button type="button" class="boton-usuario" data-menu-boton aria-haspopup="menu" '
        'aria-expanded="false" aria-label="Menú de ' + _e(nombre) + '">'
        '<span class="avatar" aria-hidden="true">' + _e(_initials(nombre)) + "</span>"
        + icon("chevron") + "</button>"
        '<div class="menu-desplegable" role="menu" data-menu-lista hidden>'
        '<div class="menu-cabecera"><strong>' + _e(nombre) + "</strong><span>" + _e(usuario) + "</span></div>"
        + "</div></div>"
    )


def _sidebar(active, *, nested=False):
    enlaces = []
    for clave, texto, ruta, nombre_icono in NAV_ITEMS:
        actual = clave == active
        es_externo = clave == "control-tower"
        enlaces.append(
            '<a class="nav-item' + (" activo" if actual else "") + '" href="' + ruta + '"'
            + (' target="_blank" rel="noopener noreferrer" aria-label="Control Tower (abre en una pestaña nueva)"' if es_externo else "")
            + (' aria-current="location"' if actual and nested else (' aria-current="page"' if actual else "")) + ">"
            + icon(nombre_icono) + "<span>" + html.escape(texto) + "</span>"
            + (icon("externo", "icono nav-externo") if es_externo else "") + "</a>"
        )

    return (
        '<aside class="sidebar">'
        '<a class="marca" href="/">'
        '<img src="/auto-prizma-logo.png" alt="" width="46" height="46">'
        '<span class="marca-texto"><strong>' + APP_NAME + "</strong><small>Cargue Prizma</small></span></a>"
        '<nav class="nav" aria-label="Menú principal">' + "".join(enlaces) + "</nav>"
        + _service_card()
        + "</aside>"
    )


def _head(title, page_css):
    return (
        '<!DOCTYPE html><html lang="es"><head><meta charset="UTF-8">'
        '<meta name="viewport" content="width=device-width, initial-scale=1.0">'
        "<title>" + html.escape(title) + " - " + APP_NAME + "</title>"
        '<link rel="icon" type="image/png" href="/auto-prizma-logo.png">'
        + _THEME_BOOT
        + '<link rel="stylesheet" href="' + asset_url(APP_CSS_PATH, "/app.css") + '">'
        + ("<style>" + page_css + "</style>" if page_css else "")
        + "</head>"
    )


def _scripts(page_js):
    return (
        '<script src="' + asset_url(APP_JS_PATH, "/app.js") + '"></script>'
        + ("<script>" + page_js + "</script>" if page_js else "")
    )


# ============================================================
# PAGINAS
# ============================================================

def render_page(title, content, *, active="", page_css="", page_js="", after_main=""):
    """Pagina completa con el marco comun.

    Args:
        title: titulo de la pestana del navegador (sin el nombre de la app).
        content: HTML del contenido principal.
        active: clave de NAV_ITEMS que se marca en el menu ("" = ninguna).
        page_css / page_js: estilos y script propios de la pagina.
        after_main: HTML que va fuera del contenido (dialogos, cargadores).
    """
    workspace = "prizma" if active in _PRIZMA_TAB_KEYS else ("moodle" if active in {"moodle", "moodle-auditor", "moodle-etiquetas", "moodle-auditor-curso", "moodle-reportes"} else "")
    nav_active = workspace or active
    tabs = _WORKSPACE_TABS.get(workspace, ())
    tabs_html = ""
    if tabs:
        tabs_html = '<nav class="workspace-tabs" aria-label="' + ("Herramientas PRIZMA" if workspace == "prizma" else "Herramientas Moodle") + '">'
        tabs_html += "".join(
            '<a class="workspace-tab' + (" activo" if key == active else "") + '" href="' + ruta + '"'
            + (' aria-current="page"' if key == active else "") + '>' + html.escape(label) + '</a>'
            for key, label, ruta in tabs
        ) + '</nav>'
    return (
        _head(title, page_css + (_WORKSPACE_CSS if tabs else ""))
        + '<body><div class="app">'
        + _sidebar(nav_active, nested=bool(tabs))
        + '<div class="principal"><header class="barra-superior">'
        + _theme_button() + _user_menu()
        + '</header><main class="contenido" id="contenido">'
        + environment_notice()
        + tabs_html
        + '<div class="contenido-pagina' + (' workspace-content' if tabs else '') + '">' + content + '</div>'
        + "</main></div></div>"
        + after_main
        + _scripts(page_js)
        + "</body></html>"
    )


def render_public_page(title, content, *, page_css="", page_js=""):
    """Pagina sin sesion (login): sin menu lateral ni menu de usuario."""
    return (
        _head(title, page_css)
        + '<body class="pagina-publica"><header class="barra-superior barra-publica">'
        + _theme_button()
        + "</header><main class=\"contenido-publico\">"
        + environment_notice()
        + content
        + "</main>"
        + _scripts(page_js)
        + "</body></html>"
    )
