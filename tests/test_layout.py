"""Pruebas del marco comun de las paginas (web/layout.py y static/app.css/app.js)."""

import re
import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from main import app
from auto_prizma.services.auth import _firmar_sesion
from auto_prizma.web.layout import CONTROL_TOWER_URL, NAV_ITEMS


def _session_client(host="127.0.0.1"):
    client = TestClient(app, client=(host, 50000))
    client.cookies.set("ap_sesion", _firmar_sesion("adminlocal"))
    return client


@pytest.mark.parametrize(
    "ruta",
    ["/", "/matrices-favoritas", "/prizma", "/automatizaciones-n8n", "/tests", "/moodle", "/moodle-reportes", "/cargue-actual", "/historial", "/reportes", "/auditor", "/cursos"],
)
def test_every_page_uses_the_common_frame(ruta, monkeypatch):
    if ruta in {"/moodle", "/moodle-reportes"}:
        monkeypatch.setattr(
            "auto_prizma.api.routes.moodle_resources._request_is_local",
            lambda _request: True,
        )
    respuesta = _session_client().get(ruta)
    html = respuesta.text

    assert respuesta.status_code == 200
    assert 'class="sidebar"' in html
    assert html.count('class="contenido-pagina') == 1
    for _clave, _texto, href, _icono in NAV_ITEMS:
        assert f'href="{href}"' in html
    # Puede haber controles de paginación con aria-current además del menú.
    if ruta == "/":
        assert '<a class="nav-item activo" href="/" aria-current="page">' in html
    elif ruta == "/automatizaciones-n8n":
        assert f'<a class="nav-item activo" href="{ruta}" aria-current="page">' in html
    elif ruta == "/matrices-favoritas":
        assert f'<a class="nav-item activo" href="{ruta}" aria-current="page">' in html
    else:
        workspace = "moodle" if ruta.startswith("/moodle") else "prizma"
        nav_path = "/moodle-auditor" if workspace == "moodle" else "/auditor"
        assert f'<a class="nav-item activo" href="{nav_path}" aria-current="location">' in html
        assert f'class="workspace-tab activo" href="{ruta}" aria-current="page">' in html
        assert 'class="contenido-pagina workspace-content"' in html
    assert re.search(r'href="/app\.css\?v=\d+"', html)
    assert re.search(r'src="/app\.js\?v=\d+"', html)
    if 'class="workspace-tabs"' in html:
        assert '.workspace-tab[aria-current="page"]{background:var(--acento);color:var(--boton-texto)' in html
        assert ".workspace-content .encabezado-titulo{align-items:center;gap:16px}" in html
        assert "font-size:30px;line-height:1.2;font-weight:800;letter-spacing:-.02em;text-align:left" in html
    assert "estilos-responsive.css" not in html and "tema.js" not in html
    assert "data-tema-toggle" in html
    assert 'class="menu-usuario"' not in html
    assert 'data-servicio="linea"' in html


def test_control_tower_sidebar_link_opens_google_app_in_new_tab():
    page = _session_client().get("/").text
    inicio = page.index('<a class="nav-item activo" href="/"')
    control_tower = page.index(f'href="{CONTROL_TOWER_URL}"')
    matrices = page.index('href="/matrices-favoritas"')

    assert inicio < control_tower < matrices
    assert f'href="{CONTROL_TOWER_URL}" target="_blank" rel="noopener noreferrer"' in page
    assert 'aria-label="Control Tower (abre en una pestaña nueva)"' in page
    assert 'class="icono nav-externo"' in page


def test_login_is_public_and_has_no_menu():
    respuesta = TestClient(app, client=("127.0.0.1", 50000)).get("/login", follow_redirects=False)

    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "/"


@pytest.mark.parametrize(
    ("ruta", "tipo"),
    [("/app.css", "text/css"), ("/app.js", "application/javascript")],
)
def test_common_assets_are_public(ruta, tipo):
    respuesta = TestClient(app).get(ruta)

    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"].startswith(tipo)


def test_file_dropzones_have_traveling_border_and_selected_state():
    root = Path(__file__).resolve().parents[1]
    css = (root / "static" / "app.css").read_text(encoding="utf-8")
    js = (root / "static" / "app.js").read_text(encoding="utf-8")

    assert ".moodle-file-drop" in css and ".moodle-label-file" in css
    assert "@keyframes file-border-run" in css
    assert "conic-gradient(from var(--file-border-angle)" in css
    assert "to { --file-border-angle: 360deg; }" in css
    assert "prefers-reduced-motion: reduce" in css
    assert "archivo-listo" in js and "archivo-inactivo" in js


@pytest.mark.parametrize("ruta", ["/estilos-responsive.css", "/tema.js"])
def test_old_assets_no_longer_exist(ruta):
    assert _session_client().get(ruta).status_code == 404


def test_user_menu_shows_remote_profile_without_google_controls():
    client = _session_client("10.0.0.7")
    html = client.get("/reportes").text

    assert '<span class="avatar" aria-hidden="true">AL</span>' in html  # "Admin local"
    assert "Desconectar Google" not in html


def test_landing_separates_prizma_moodle_and_n8n():
    html = _session_client().get("/").text

    assert "Tus herramientas de trabajo," in html
    assert "en un mismo lugar." in html
    assert "Elige tu espacio de trabajo" in html
    assert "4 accesos · En el mismo orden del menú" not in html
    posiciones = [
        html.index("<h3>Matrices</h3>"),
        html.index("<h3>Cargue PRIZMA</h3>"),
        html.index("<h3>Cargue Moodle</h3>"),
        html.index("<h3>Automatizaciones</h3>"),
    ]
    assert posiciones == sorted(posiciones)
    assert html.count('class="panel landing-card"') == 4
    assert "<h3>Control Tower</h3>" not in html
    assert 'href="/matrices-favoritas"' in html
    assert 'href="https://admin.prizma.site/" target="_blank" rel="noopener noreferrer">Entrar a PRIZMA' in html
    assert 'href="/auditor"' in html
    assert 'href="/moodle-auditor"' in html
    assert 'href="/automatizaciones-n8n"' in html
    assert "Control Tower" in html
    assert 'aria-label="Control Tower (abre en una pestaña nueva)"' in html
    assert "prefers-reduced-motion:reduce" in html
    assert 'aria-label="Espacios de trabajo"' in html
    assert 'name="matriz_archivo"' not in html


def test_prizma_page_keeps_the_form_contract_and_status_pills():
    html = _session_client().get("/prizma").text

    assert '<span class="icono-tile">' in html
    assert '<span class="saludo-acento">dev</span>' in html
    assert "@keyframes saludo-color" in html
    assert "@media(prefers-reduced-motion:reduce) { .saludo-acento" in html
    assert "Hola, Admin local" not in html
    for nombre in [
        "matriz_archivo", "recursos", "ovi", "ova", "retos",
        "test_evaluativo", "formato_recurso", "test_archivo_docx",
    ]:
        assert f'name="{nombre}"' in html
    assert 'name="test_semestre"' not in html
    assert 'name="test_datos_academicos"' not in html
    assert 'action="/analizar"' in html
    assert 'data-servicio="pastilla-chromium"' in html
    assert 'data-servicio="pastilla-prizma"' in html
    assert "Google" not in html
    assert "Por link" not in html
    assert 'id="google-sheet-url"' not in html
    assert 'id="dialogo-guia"' in html
    assert 'aria-label="Herramientas PRIZMA"' in html
    assert 'href="/tests"' in html
    assert 'href="/reportes"' in html


def test_prizma_workspace_tabs_are_in_requested_order():
    page = _session_client().get("/prizma").text
    match = re.search(r'<nav class="workspace-tabs" aria-label="Herramientas PRIZMA">(.*?)</nav>', page)
    assert match
    tabs = match.group(1)
    expected = ["/auditor", "/prizma", "/tests", "/auditor-curso", "/cursos", "/cargue-actual", "/historial", "/reportes"]
    positions = [tabs.index('href="' + path + '"') for path in expected]
    assert positions == sorted(positions)


def test_moodle_has_separate_report_tab_and_empty_reports_state(monkeypatch):
    monkeypatch.setattr(
        "auto_prizma.api.routes.moodle_resources._request_is_local",
        lambda _request: True,
    )
    html = _session_client().get("/moodle-reportes").text

    assert "Reportes de Moodle" in html
    assert "Aún no hay reportes de Moodle." in html
    assert '<header class="encabezado"><div class="encabezado-titulo">' in html
    assert 'class="chip grande"' in html
    assert 'class="panel herramientas dos"' in html
    assert 'class="mosaicos" aria-label="Resumen de reportes Moodle"' in html
    assert 'class="panel tabla-panel" id="tabla-moodle-reportes" data-tabla' in html
    assert 'data-tabla-tamano' in html
    assert 'aria-label="Herramientas Moodle"' in html
    assert 'class="workspace-tab activo" href="/moodle-reportes" aria-current="page">Reportes' in html


def test_moodle_reports_populates_shared_summary_and_table(monkeypatch, tmp_path):
    monkeypatch.setattr("auto_prizma.api.routes.moodle_resources._request_is_local", lambda _request: True)
    monkeypatch.setattr("auto_prizma.api.routes.moodle_resources._moodle_report_dir", lambda: str(tmp_path))
    (tmp_path / "moodle-cargue-20261028T120000Z-a1b2c3d4.json").write_text(
        json.dumps({
            "createdAt": "2026-10-28T12:00:00+00:00",
            "summary": {"uploaded": 4, "alreadyPresent": 2, "notLoaded": 1, "needsReview": 1, "notProcessed": 0},
        }),
        encoding="utf-8",
    )

    page = _session_client().get("/moodle-reportes").text
    assert "1 reporte" in page
    assert 'data-estado="pendiente"' in page
    assert 'data-fecha="2026-10-28T12:00:00+00:00"' in page
    assert ">4</strong><span>Recursos cargados</span>" in page
    assert ">2</strong><span>Ya estaban cargados</span>" in page
    assert ">2</strong><span>Pendientes / revisión</span>" in page
    assert "?formato=csv" in page and "?formato=json" in page


def test_moodle_auditor_tab_uses_shared_auditor_form():
    response = _session_client().get("/moodle-auditor")
    assert response.status_code == 200
    assert 'aria-label="Herramientas Moodle"' in response.text
    assert 'href="/moodle-auditor" aria-current="page"' in response.text
    assert 'action="/moodle-auditor"' in response.text
    assert 'id="matriz"' in response.text and 'id="recursos"' in response.text
    tabs = response.text.split('<nav class="workspace-tabs"', 1)[1].split("</nav>", 1)[0]
    assert tabs.index('href="/moodle-auditor"') < tabs.index('href="/moodle"')


def test_moodle_workspace_tabs_order_puts_course_audit_after_labels(monkeypatch):
    monkeypatch.setattr(
        "auto_prizma.api.routes.moodle_resources._request_is_local",
        lambda _request: True,
    )
    page = _session_client().get("/moodle").text
    tabs = page.split('<nav class="workspace-tabs"', 1)[1].split("</nav>", 1)[0]

    expected = ["/moodle-auditor", "/moodle", "/moodle-etiquetas", "/moodle-auditor-curso", "/moodle-reportes"]
    positions = [tabs.index('href="' + path + '"') for path in expected]
    assert positions == sorted(positions)


def test_moodle_upload_form_uses_styled_file_dropzones():
    page = _session_client().get("/moodle").text
    assert "El cargue se ejecuta en tu equipo" not in page
    assert "Abre Auto Prizma desde" not in page
    assert 'class="moodle-file-drop"' in page
    assert "Selecciona o arrastra la matriz" in page
    assert "Selecciona o arrastra el ZIP" in page
    assert 'id="moodle-ready-matrix"' in page
    assert "INFORMACIÓN DE ETIQUETAS" not in page


def test_moodle_labels_has_own_tab_and_generates_droppable_html():
    page = _session_client().get("/moodle-etiquetas").text
    assert 'aria-label="Herramientas Moodle"' in page
    assert 'href="/moodle-etiquetas" aria-current="page"' in page
    assert page.index('href="/moodle-auditor"') < page.index('href="/moodle-etiquetas"')
    assert 'id="moodle-label-kind"' not in page
    assert 'data-label-card="banner"' in page
    assert 'id="moodle-label-image-banner"' in page
    assert 'data-label-card="infografia"' in page
    assert 'id="moodle-label-image-infografia"' in page
    assert page.count('class="boton secundario moodle-label-file-button">Seleccionar imagen</span>') == 2
    assert page.count('data-label-filename>Ninguna imagen seleccionada</span>') == 2
    assert ".moodle-label-file input[type=file]{position:absolute;width:1px" in page
    assert 'data-label-card="video"' in page
    assert "Arrastra la imagen aquí" in page
    assert "addEventListener('drop'" in page
    assert "readAsDataURL" in page
    assert "Copiar HTML" in page
    assert "Código fuente para banners imágenes" not in page
    assert page.count("Información de etiquetas") == 1
    assert '<header class="moodle-heading"><div class="icono-tile">' in page
    assert '<header class="moodle-heading"><div class="icono-tile azul">' not in page
    assert "Ver HTML completo" in page
    assert "El código completo se copia con el botón" in page


def test_n8n_page_lists_flows_and_forms():
    html = _session_client().get("/automatizaciones-n8n").text

    assert "Automatizaciones" in html
    assert "Automatizaciones n8n" not in html
    for texto in [
        "Generar tests JSON", "Descarga de recursos", "Matriz de importación CSV",
        "Generador de plantillas temáticas", "googleDocUrl", "sheetUrl",
        "dividirPorUnidad", "filaInicio", "plantillaUrl", "folderUrl",
        "/automatizaciones-n8n/ejecutar",
    ]:
        assert texto in html
    assert ".n8n-dialog::backdrop{background:var(--superposicion)" in html
    assert ".n8n-dialog{inset:0;width:100%;max-width:none;height:100%" in html
    assert ".n8n-dialog-card{position:relative;width:min(580px,100%)" in html
    assert 'data-configured="' in html


def test_global_theme_uses_navy_in_light_and_violet_in_dark():
    css = _session_client().get("/app.css").text
    assert "--fondo: #f5f6fc" in css
    assert "--panel: #ffffff" in css
    assert "--acento: #101828" in css
    assert "--boton: #101828" in css
    assert "--morado: #1d2939" in css
    assert 'html[data-theme="dark"]' in css
    assert "--acento: #8b5cf6" in css
    assert "--boton: #7c3aed" in css
    assert "--morado: #c4b5fd" in css
    assert "--dialog-backdrop: rgba(0, 0, 0, .72)" in css
    assert ".boton.grande" in css and "background: var(--boton)" in css


def test_global_motion_is_subtle_and_respects_reduced_motion():
    css = _session_client().get("/app.css").text

    assert ".contenido-pagina { animation: app-page-enter" in css
    assert "@keyframes app-page-enter" in css
    assert ".boton:active:not([disabled])" in css
    assert "@media (prefers-reduced-motion: reduce)" in css
    assert "html { scroll-behavior: auto; }" in css


def test_vistas_usan_tokens_tematicos_y_no_colores_heredados():
    tests = _session_client().get("/tests").text
    cursos = _session_client().get("/cursos").text

    assert "var(--foco)" in tests
    assert "var(--rojo)" in tests
    assert "#6366f1" not in tests
    assert "#e11d48" not in tests
    assert "var(--verde)" in cursos
    assert "var(--borde)" in cursos
    assert "var(--exito" not in cursos
    assert "var(--linea" not in cursos
