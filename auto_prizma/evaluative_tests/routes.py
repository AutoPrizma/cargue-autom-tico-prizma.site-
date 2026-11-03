"""Rutas web del modulo de tests evaluativos (/tests/...).
"""

from __future__ import annotations

import html
import io
import json
import threading
import zipfile
from datetime import datetime, timezone

from fastapi import APIRouter, File, Form, Request, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response

from auto_prizma.core.config import PRIZMA_HOST
from auto_prizma.web.icons import icon

from .models import Severity, document_from_dict
from .parser import parse_docx_bytes
from .serializer import serialize_test
from .validation import validate_document
from .state import (
    _AUTOMATION_JOBS,
    _AUTOMATION_LOCK,
    _AUTOMATION_SYNC,
    _guardar_credenciales_prizma,
    _job_for,
    _user,
    register_test_job,
)
from .views import (
    _layout,
    _render_review,
    _render_tarjeta_estado_test,
)
from .execution import ejecutar_test_job


router = APIRouter()


@router.get("/tests", response_class=HTMLResponse)
def tests_home(request: Request):
    user = _user(request)
    info_activo = _obtener_estado_test_activo(user)
    tarjeta_activo = _render_tarjeta_estado_test(info_activo)

    body = f'''<header class="encabezado workspace-page-heading"><div class="encabezado-titulo">
        <span class="icono-tile grande">{icon("test")}</span>
        <div><h1>Nuevo Test</h1>
        <p>Asistente para convertir evaluaciones académicas en tests auditados y JSON compatibles para PRIZMA de manera 100% automatizada.</p></div>
    </div></header>
    <div class="pasos">
        <span class="paso">1 Entrada</span>
        <span class="paso">2 Revisión</span>
        <span class="paso">3 PRIZMA bloqueado</span>
        <span class="paso">4 Pendiente</span>
    </div>

    {tarjeta_activo}

    <div class="layout-tests">
        <section class="panel">
            <h2>Suministrar evaluación</h2>
            <p>Selecciona el documento Word (.docx) con las preguntas del test:</p>

            <form id="form-analizar" action="/tests/analizar" method="post" enctype="multipart/form-data">
                <div id="bloque-archivo">
                    <label class="dropzone" id="dropzone-box" for="archivo_docx">
                        <div id="dropzone-vacio">
                            <div style="font-size:36px;margin-bottom:8px;">📄</div>
                            <strong style="font-size:15px;">Arrastra tu archivo Word aquí</strong>
                            <span class="muted" style="display:block;margin-top:4px;">o haz clic para buscarlo en tu equipo (.docx)</span>
                        </div>
                        <div id="dropzone-seleccionado" style="display:none;padding:10px 0;">
                            <div style="font-size:36px;color:var(--verde);">✓</div>
                            <strong id="nombre-archivo-seleccionado" style="font-size:15px;display:block;margin:6px 0 4px;"></strong>
                            <span id="peso-archivo-seleccionado" class="badge ok" style="margin-bottom:8px;"></span>
                            <div style="margin-top:8px;">
                                <span style="font-size:12px;color:var(--morado);text-decoration:underline;">Haz clic aquí para seleccionar otro archivo</span>
                            </div>
                        </div>
                        <input id="archivo_docx" name="archivo_docx" type="file" accept=".docx" hidden>
                    </label>
                </div>

                <div class="acciones">
                    <button type="submit" id="btn-analizar">🚀 Analizar documento</button>
                </div>
            </form>
        </section>

        <aside class="panel-ayuda">
            <h3>¿Cómo funciona?</h3>
            <div class="paso-ayuda"><b>1</b><span>Selecciona un documento Word (.docx).</span></div>
            <div class="paso-ayuda"><b>2</b><span>El sistema extraerá automáticamente el <strong>Título</strong>, <strong>Semana</strong>, <strong>Corte</strong> y preguntas.</span></div>
            <div class="paso-ayuda"><b>3</b><span>Audita y ajusta las preguntas en la pantalla de revisión con semáforo pedagógico.</span></div>
            <div class="paso-ayuda"><b>4</b><span>Descarga el respaldo en JSON o déjalos preparados para la inyección desatendida en PRIZMA.</span></div>

            <div class="ayuda-separador"></div>

            <h3 class="titulo-consejos">Consejos</h3>
            <p class="consejo">✓ Cada test debe incluir su Semana, Corte y Título correspondiente.</p>
            <p class="consejo">✓ Las preguntas cerradas deben incluir su clave (ej: <code>[R: Verdadero]</code> o <code>[R: b]</code>).</p>
            <p class="consejo">✓ Si el documento contiene varios tests evaluativos, se dividirán automáticamente en tarjetas independientes.</p>
        </aside>
    </div>

    <script>
    const inputFile = document.getElementById('archivo_docx');
    const dropzoneBox = document.getElementById('dropzone-box');
    const dropVacio = document.getElementById('dropzone-vacio');
    const dropSeleccionado = document.getElementById('dropzone-seleccionado');
    const nombreArchivo = document.getElementById('nombre-archivo-seleccionado');
    const pesoArchivo = document.getElementById('peso-archivo-seleccionado');
    const btnAnalizar = document.getElementById('btn-analizar');

    function mostrarArchivo(file) {{
        if (!file) return;
        nombreArchivo.textContent = file.name;
        const kb = (file.size / 1024).toFixed(1);
        const mb = (file.size / (1024 * 1024)).toFixed(2);
        pesoArchivo.textContent = file.size > 1024 * 1024 ? `${{mb}} MB` : `${{kb}} KB`;
        dropVacio.style.display = 'none';
        dropSeleccionado.style.display = 'block';
    }}

    inputFile.addEventListener('change', (e) => {{
        if (e.target.files && e.target.files.length > 0) {{
            mostrarArchivo(e.target.files[0]);
        }}
    }});

    ['dragenter', 'dragover'].forEach(eventName => {{
        dropzoneBox.addEventListener(eventName, (e) => {{
            e.preventDefault();
            e.stopPropagation();
            dropzoneBox.classList.add('dragover');
        }}, false);
    }});

    ['dragleave', 'drop'].forEach(eventName => {{
        dropzoneBox.addEventListener(eventName, (e) => {{
            e.preventDefault();
            e.stopPropagation();
            dropzoneBox.classList.remove('dragover');
        }}, false);
    }});

    dropzoneBox.addEventListener('drop', (e) => {{
        const dt = e.dataTransfer;
        if (dt && dt.files && dt.files.length > 0) {{
            inputFile.files = dt.files;
            mostrarArchivo(dt.files[0]);
        }}
    }});

    document.getElementById('form-analizar').addEventListener('submit', () => {{
        btnAnalizar.disabled = true;
        btnAnalizar.textContent = '⏳ Analizando documento...';
    }});
    </script>'''
    if info_activo and info_activo.get("estado") in ["en_ejecucion", "esperando_asignatura"]:
        body += '''<script>
        (function() {
            function refrescarEstadoCard() {
                fetch('/tests/estado-activo/json')
                    .then(r => r.json())
                    .then(data => {
                        if (!data || !data.activo) {
                            // El test ya no esta activo (termino mientras
                            // mirabamos): recargar para que la tarjeta
                            // desaparezca sola, sin quedar congelada.
                            setTimeout(() => window.location.reload(), 1200);
                            return;
                        }
                        const elPct = document.getElementById('card-txt-pct');
                        const elBar = document.getElementById('card-barra-progreso');
                        const elMsg = document.getElementById('card-mensaje');
                        const elAvance = document.getElementById('card-txt-avance');
                        const elStats = document.getElementById('card-stats');
                        if (elPct) elPct.textContent = (data.progreso_porcentaje || 0) + '%';
                        if (elBar) elBar.style.width = (data.progreso_porcentaje || 0) + '%';
                        if (elMsg && data.mensaje) elMsg.textContent = '💬 ' + data.mensaje;
                        if (elAvance) elAvance.textContent = `${data.exitosos || 0} de ${data.total || 0} tests guardados exitosamente`;
                        if (elStats) elStats.textContent = `Exitosos: ${data.exitosos || 0} · Fallidos: ${data.fallidos || 0} · Total: ${data.total || 0}`;
                        if (data.estado !== 'en_ejecucion' && data.estado !== 'esperando_asignatura') {
                            setTimeout(() => window.location.reload(), 1500);
                        } else {
                            setTimeout(refrescarEstadoCard, 2000);
                        }
                    })
                    .catch(() => setTimeout(refrescarEstadoCard, 4000));
            }
            setTimeout(refrescarEstadoCard, 2000);
        })();
        </script>'''
    return HTMLResponse(_layout("Nuevo Test", body))


@router.post("/tests/analizar")
async def analyze_tests(
    request: Request,
    archivo_docx: UploadFile | None = File(default=None),
):
    if not archivo_docx or not archivo_docx.filename:
        return HTMLResponse(
            _layout("Test", '<section class="panel"><div class="issue error">Selecciona un archivo Word (.docx).</div><div class="acciones"><a class="boton" href="/tests">Volver</a></div></section>'),
            status_code=400,
        )
    if not archivo_docx.filename.lower().endswith(".docx"):
            return HTMLResponse(
                _layout("Test", '<section class="panel"><div class="issue error">El archivo debe tener formato Microsoft Word (.docx).</div><div class="acciones"><a class="boton" href="/tests">Volver</a></div></section>'),
                status_code=400,
            )
    content = await archivo_docx.read()
    source_name = archivo_docx.filename

    if not content:
        return HTMLResponse(
            _layout("Test", '<section class="panel"><div class="issue error">El documento seleccionado está vacío o no contiene datos procesables.</div><div class="acciones"><a class="boton" href="/tests">Volver</a></div></section>'),
            status_code=400,
        )

    try:
        document = parse_docx_bytes(content, source_name=source_name)
    except Exception as exc:
        return HTMLResponse(
            _layout("Test", f'<section class="panel"><div class="issue error">Error al procesar el archivo Word: {html.escape(str(exc))}</div><div class="acciones"><a class="boton" href="/tests">Volver</a></div></section>'),
            status_code=400,
        )

    job_id = register_test_job(
        _user(request),
        document,
        datetime.now(timezone.utc).isoformat(),
    )
    return RedirectResponse(f"/tests/{job_id}/revision", status_code=303)


@router.get("/tests/{job_id}/revision", response_class=HTMLResponse)
def review_tests(request: Request, job_id: str):
    job = _job_for(request, job_id)
    if not job:
        return HTMLResponse(_layout("Test", '<section class="panel"><div class="issue error">⚠️ Este análisis ya no existe en el servidor. Normalmente pasa si el servidor se reinició con la página abierta (los análisis se guardan solo en memoria, no en disco). Sube el documento de nuevo para generar un análisis nuevo.</div><a class="boton" href="/tests">Volver</a></section>'), status_code=404)
    return HTMLResponse(_render_review(job_id, job))


@router.post("/tests/{job_id}/guardar")
def save_review(request: Request, job_id: str, payload: str = Form(...)):
    job = _job_for(request, job_id)
    if not job:
        return HTMLResponse(_layout("Test", '<section class="panel"><div class="issue error">⚠️ Este análisis ya no existe en el servidor. Normalmente pasa si el servidor se reinició con la página abierta (los análisis se guardan solo en memoria, no en disco). Sube el documento de nuevo para generar un análisis nuevo.</div></section>'), status_code=404)
    try:
        data = json.loads(payload)
        document = document_from_dict(data)
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        return HTMLResponse(_render_review(job_id, job, f"No se pudieron guardar las correcciones: {exc}"), status_code=400)
    job["document"] = document
    return HTMLResponse(_render_review(job_id, job, "Correcciones guardadas y validadas."))


@router.get("/tests/{job_id}/descargar")
def download_tests(request: Request, job_id: str, indice: int | None = None):
    job = _job_for(request, job_id)
    if not job:
        return JSONResponse({"error": "Este análisis ya no existe en el servidor. Normalmente pasa si el servidor se reinició con la página abierta (los análisis se guardan solo en memoria, no en disco). Sube el documento de nuevo para generar un análisis nuevo."}, status_code=404)
    document: TestDocument = job["document"]
    if indice is not None:
        if indice < 0 or indice >= len(document.tests):
            return JSONResponse({"error": "Test no encontrado"}, status_code=404)
        payload = json.dumps(serialize_test(document.tests[indice]), ensure_ascii=False, indent=2).encode("utf-8")
        return Response(payload, media_type="application/json", headers={"Content-Disposition": f'attachment; filename="test_{indice + 1}.json"'})
    if len(document.tests) == 1:
        payload = json.dumps(serialize_test(document.tests[0]), ensure_ascii=False, indent=2).encode("utf-8")
        return Response(payload, media_type="application/json", headers={"Content-Disposition": 'attachment; filename="test.json"'})
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED) as bundle:
        for index, test in enumerate(document.tests, start=1):
            bundle.writestr(f"{index:02d}_{test.title[:60] or 'test'}.json", json.dumps(serialize_test(test), ensure_ascii=False, indent=2))
    return Response(archive.getvalue(), media_type="application/zip", headers={"Content-Disposition": 'attachment; filename="tests_json.zip"'})


@router.post("/tests/{job_id}/ejecutar-prizma")
async def ejecutar_prizma(
    request: Request,
    job_id: str,
    prizma_usuario: str = Form(...),
    prizma_clave: str = Form(...),
    recordar_credenciales: str | None = Form(default=None),
    ver_navegador: str | None = Form(default=None),
    solo_simulacion: str | None = Form(default=None),
    cascada_facultad: str = Form(default=""),
    linea_academica: str = Form(default=""),
    cascada_nivel: str = Form(default=""),
):
    job = _job_for(request, job_id)
    if not job:
        return HTMLResponse(_layout("Test", '<section class="panel"><div class="issue error">⚠️ Este análisis ya no existe en el servidor. Normalmente pasa si el servidor se reinició con la página abierta (los análisis se guardan solo en memoria, no en disco). Sube el documento de nuevo para generar un análisis nuevo.</div></section>'), status_code=404)

    user = _user(request)
    recordar = bool(recordar_credenciales)
    simulacion = bool(solo_simulacion)
    _guardar_credenciales_prizma(user, {"usuario": prizma_usuario.strip() if recordar else "", "recordar": recordar})

    document: TestDocument = job["document"]
    issues = validate_document(document)
    errores = [i for i in issues if i.severity == Severity.ERROR]
    if errores:
        return HTMLResponse(_render_review(job_id, job, "Corrige los errores pendientes antes de cargar el test a PRIZMA."), status_code=400)
    datos_academicos = job.get("cascada_datos") or {}
    linea = linea_academica.strip() or str(datos_academicos.get("linea_academica", "")).strip()
    if not linea and datos_academicos.get("programa") and datos_academicos.get("pensum"):
        linea = " ".join(str(datos_academicos.get(k, "")).strip() for k in ("programa", "pensum", "codigo_asignatura", "asignatura") if datos_academicos.get(k))
    from auto_prizma.services.matrix_analysis import _parsear_datos_academicos
    datos_parseados = _parsear_datos_academicos(linea)
    if not datos_parseados:
        return HTMLResponse(_render_review(job_id, job, "Pega la línea académica con código de programa, código de pensum, código de asignatura y nombre de asignatura."), status_code=400)
    if not cascada_nivel.strip():
        return HTMLResponse(_render_review(job_id, job, "Selecciona el nivel de pensum para continuar."), status_code=400)

    headless = not bool(ver_navegador)
    cascada = {
        "facultad": cascada_facultad.strip(),
        "programa": datos_parseados["programa"],
        "pensum": datos_parseados["pensum"],
        "nivel": cascada_nivel.strip(),
        "asignatura": f'{datos_parseados["codigo_asignatura"]} {datos_parseados["asignatura"]}'.strip(),
        "semana": "",
        "corte": "",
        "codigo_asignatura": datos_parseados["codigo_asignatura"],
        "linea_academica": linea,
    }

    ruta_reporte_test = None
    if not simulacion:
        from auto_prizma.services.history import _ruta_reporte_test
        ruta_reporte_test = _ruta_reporte_test(cascada, job_id)

    threading.Thread(
        target=ejecutar_test_job,
        kwargs={
            "job_id": job_id,
            "usuario_prizma": prizma_usuario.strip(),
            "clave_prizma": prizma_clave.strip(),
            "user": user,
            "simulacion": simulacion,
            "headless": headless,
            "cascada_override": cascada,
            "ruta_reporte": ruta_reporte_test,
            "registrar_historial": bool(ruta_reporte_test),
        },
        daemon=True,
    ).start()

    return RedirectResponse(f"/tests/{job_id}/estado-prizma", status_code=303)


@router.get("/tests/{job_id}/estado-prizma", response_class=HTMLResponse)
def status_prizma(request: Request, job_id: str):
    job = _job_for(request, job_id)
    if not job:
        return HTMLResponse(_layout("Test", '<section class="panel"><div class="issue error">⚠️ Este análisis ya no existe en el servidor. Normalmente pasa si el servidor se reinició con la página abierta (los análisis se guardan solo en memoria, no en disco). Sube el documento de nuevo para generar un análisis nuevo.</div></section>'), status_code=404)

    with _AUTOMATION_LOCK:
        auto_state = _AUTOMATION_JOBS.get(job_id)

    if not auto_state:
        return RedirectResponse(f"/tests/{job_id}/revision", status_code=303)

    es_sim = auto_state.get("simulacion", True)
    texto_completado = "✓ Simulación exitosa (Validado sin guardar)" if es_sim else "✓ Guardado completado en PRIZMA"

    rows_tests = []
    for item in auto_state.get("detalle_tests", []):
        st = item.get("estado", "pendiente")
        badge_mod = "ok" if st == "exitoso" else "error" if st == "error" else "proceso" if st == "en_proceso" else "omitido" if st == "omitido" else "pendiente"
        badge_txt = (
            "✓ Guardado"
            if (st == "exitoso" and not es_sim)
            else "✓ Validado"
            if st == "exitoso"
            else "❌ Error"
            if st == "error"
            else "⏳ En proceso..."
            if st == "en_proceso"
            else "⏭ Omitido"
            if st == "omitido"
            else "⚪ En espera"
        )
        rows_tests.append(
            f'<tr id="row-test-{item["numero"]}" style="border-bottom:1px solid var(--borde);">'
            f'<td style="padding:10px 8px;font-weight:700;">{item["numero"]}</td>'
            f'<td style="padding:10px 8px;"><strong>{html.escape(item["titulo"])}</strong></td>'
            f'<td style="padding:10px 8px;"><span class="chip-morado">{item["preguntas"]} preg.</span></td>'
            f'<td style="padding:10px 8px;"><span class="badge-dinamico badge-dinamico--{badge_mod}" id="badge-test-{item["numero"]}">{badge_txt}</span></td>'
            f'<td class="muted" style="padding:10px 8px;font-size:12px;" id="msg-test-{item["numero"]}">{html.escape(item["mensaje"])}</td>'
            f'</tr>'
        )
    filas_html = "".join(rows_tests)

    body = f'''<h1>{'Monitoreo de Simulación en PRIZMA' if es_sim else 'Monitoreo de Creación en PRIZMA'}</h1>
    <p>Visualización y auditoría en tiempo real de cada test en <strong>{html.escape(PRIZMA_HOST)}</strong>.</p>
    <div class="pasos">
        <span class="paso">1 Entrada ✓</span>
        <span class="paso">2 Revisión ✓</span>
        <span class="paso">3 PRIZMA Activo 🚀</span>
        <span class="paso" id="paso-final">{'4 Simulación (Sin guardar)' if es_sim else '4 Creación en Plataforma'}</span>
    </div>

    <!-- BANNER DE ERROR SUPERIOR DESTACADO -->
    <div id="banner-error-superior" class="status-banner status-banner--error" style="display:{'flex' if auto_state.get('estado') == 'error' else 'none'};">
        <div class="status-icon">✕</div>
        <div style="flex:1;">
            <h3>La ejecución se detuvo por un error</h3>
            <p id="texto-error-superior">{html.escape(auto_state.get('error') or auto_state.get('mensaje') or '')}</p>
            <div style="display:flex;gap:12px;flex-wrap:wrap;">
                <a class="boton secundario" href="/tests/{job_id}/revision" style="padding:9px 16px;font-size:13px;">← Volver a Revisión para corregir parámetros</a>
            </div>
        </div>
    </div>

    <!-- BANNER DE ÉXITO SUPERIOR -->
    <div id="banner-exito-superior" class="status-banner status-banner--ok" style="display:{'flex' if auto_state.get('estado') == 'completado' else 'none'};">
        <div class="status-icon">✓</div>
        <div style="flex:1;">
            <h3>{'Simulación validada exitosamente' if es_sim else '¡Tests creados y guardados con éxito en PRIZMA!'}</h3>
            <p id="texto-exito-superior" style="margin:0;">{html.escape(auto_state.get('mensaje', ''))}</p>
        </div>
    </div>

    <!-- BANNER DE DETENCIÓN SUPERIOR -->
    <div id="banner-detenido-superior" class="status-banner status-banner--warn" style="display:{'flex' if auto_state.get('estado') == 'detenido' else 'none'};">
        <div class="status-icon">⏹</div>
        <div style="flex:1;">
            <h3>Automatización detenida por el usuario</h3>
            <p id="texto-detenido-superior">{html.escape(auto_state.get('mensaje', ''))}</p>
            <div style="display:flex;gap:12px;flex-wrap:wrap;">
                <a class="boton secundario" href="/tests/{job_id}/revision" style="padding:9px 16px;font-size:13px;">← Volver a Revisión</a>
            </div>
        </div>
    </div>

    <!-- PANEL INTERACTIVO DE SELECCIÓN DE ASIGNATURA -->
    <div id="panel-seleccion-asignatura" class="status-banner status-banner--warn" style="display:{'flex' if auto_state.get('esperando_asignatura') else 'none'};flex-direction:column;">
        <div style="display:flex;gap:14px;align-items:flex-start;width:100%;">
            <div class="status-icon">⚠️</div>
            <div style="flex:1;">
            <h3 id="titulo-seleccion-campo">Confirma una opción de PRIZMA</h3>
                <p id="txt-asignatura-buscada" style="margin:0;">La asignatura ingresada no coincide exactamente con las opciones registradas en PRIZMA. Selecciona la opción correcta para que el robot continúe:</p>
            </div>
        </div>
        <div style="display:flex;gap:12px;flex-wrap:wrap;align-items:center;margin-top:14px;width:100%;">
            <input type="hidden" id="campo-seleccion-pendiente" value="Asignatura por pensum">
            <select id="sel-asignatura-opciones" style="flex:1;min-width:280px;">
                <option value="">-- Seleccionar opción de PRIZMA --</option>
            </select>
            <button id="btn-confirmar-asignatura" type="button" class="boton">
                Confirmar Asignatura y Continuar ➔
            </button>
        </div>
        <div id="msg-confirmacion-asignatura" style="margin-top:10px;font-size:13px;font-weight:600;display:none;"></div>
    </div>

    <!-- TARJETAS KPI DE PROGRESO -->
    <div style="display:grid;grid-template-columns:repeat(auto-fit, minmax(180px, 1fr));gap:14px;margin-bottom:20px;">
        <div class="kpi-card">
            <div class="kpi-label">Total Tests</div>
            <div id="kpi-total" class="kpi-valor">{auto_state.get('total', 0)}</div>
        </div>
        <div class="kpi-card kpi-card--ok">
            <div class="kpi-label">{'✓ Validados' if es_sim else '✅ Guardados'}</div>
            <div id="kpi-exitosos" class="kpi-valor">{auto_state.get('exitosos', 0)}</div>
        </div>
        <div class="kpi-card">
            <div class="kpi-label">⏭ Omitidos (ya cargados)</div>
            <div id="kpi-omitidos" class="kpi-valor">{auto_state.get('omitidos', 0)}</div>
        </div>
        <div class="kpi-card kpi-card--warn">
            <div class="kpi-label">⏳ Faltantes / En Cola</div>
            <div id="kpi-pendientes" class="kpi-valor">{auto_state.get('pendientes', 0)}</div>
        </div>
        <div class="kpi-card kpi-card--error">
            <div class="kpi-label">❌ Con Errores</div>
            <div id="kpi-fallidos" class="kpi-valor">{auto_state.get('fallidos', 0)}</div>
        </div>
    </div>

    <!-- BARRA DE PROGRESO VISUAL -->
    <div class="panel">
        <div style="display:flex;justify-content:space-between;margin-bottom:8px;font-size:13px;font-weight:700;">
            <span id="progreso-texto-avance">Avance general ({auto_state.get('procesados', 0)} de {auto_state.get('total', 0)} tests)</span>
            <span id="progreso-porcentaje-texto">{auto_state.get('progreso_porcentaje', 0)}%</span>
        </div>
        <div class="progress-track">
            <div id="progreso-barra-fill" class="progress-fill" style="width:{auto_state.get('progreso_porcentaje', 0)}%;"></div>
        </div>
    </div>

    <!-- TABLA DE DETALLE POR TEST -->
    <div class="panel" style="overflow-x:auto;">
        <h3 style="margin:0 0 12px;font-size:15px;">Detalle de Tests en Proceso:</h3>
        <table style="width:100%;border-collapse:collapse;font-size:13px;text-align:left;">
            <thead>
                <tr style="border-bottom:2px solid var(--borde);">
                    <th style="padding:10px 8px;width:50px;">#</th>
                    <th style="padding:10px 8px;">Título del Test</th>
                    <th style="padding:10px 8px;width:110px;">Preguntas</th>
                    <th style="padding:10px 8px;width:170px;">Estado</th>
                    <th style="padding:10px 8px;">Observación</th>
                </tr>
            </thead>
            <tbody id="tabla-tests-body">
                {filas_html}
            </tbody>
        </table>
    </div>

    <section class="panel">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;flex-wrap:wrap;gap:10px;">
            <span class="badge {'ok' if auto_state['estado'] == 'completado' else 'error' if auto_state['estado'] == 'error' else 'warn'}" id="estado-badge" style="font-size:14px;padding:8px 16px;">
                {texto_completado if auto_state['estado'] == 'completado' else '❌ Error en la ejecución' if auto_state['estado'] == 'error' else '⏳ En ejecución...'}
            </span>
            <span class="muted" id="estado-resumen">{auto_state.get('procesados', 0)} de {auto_state.get('total', 0)} test(s) procesados</span>
        </div>
        <h3 id="estado-mensaje" style="margin:0 0 16px;">{html.escape(auto_state.get('mensaje', ''))}</h3>

        <div class="acciones" style="margin-top:24px;display:flex;gap:10px;align-items:center;flex-wrap:wrap;">
            <button id="btn-detener-auto" type="button" class="boton secundario peligro" onclick="detenerAutomatizacion()" style="display:{'inline-flex' if auto_state.get('estado') == 'en_ejecucion' else 'none'};align-items:center;gap:6px;cursor:pointer;">⏹ Detener automatización</button>
            <a class="boton secundario" href="/tests/{job_id}/revision">← Volver a Revisión</a>
            <a class="boton secundario" href="/tests">＋ Nuevo análisis</a>
            <a class="boton" href="/" style="background:var(--verde);">✓ Ir a Inicio</a>
        </div>
    </section>

    <script>
    const jobId = "{job_id}";
    const badge = document.getElementById("estado-badge");
    const msg = document.getElementById("estado-mensaje");
    const resumen = document.getElementById("estado-resumen");

    let terminado = {"true" if auto_state['estado'] in ('completado', 'error', 'detenido') else "false"};

    function detenerAutomatizacion() {{
        if (!confirm("¿Confirmas que deseas detener la subida de los tests pendientes? Los tests que ya hayan sido guardados se conservarán.")) return;
        const btn = document.getElementById("btn-detener-auto");
        if (btn) {{
            btn.disabled = true;
            btn.textContent = "⏳ Deteniendo...";
        }}
        fetch(`/tests/${{jobId}}/cancelar-prizma`, {{ method: "POST" }})
            .then(r => r.json())
            .then(data => {{
                if (data.ok) {{
                    msg.textContent = "Deteniendo automatización a solicitud del usuario...";
                }}
            }})
            .catch(() => {{}});
    }}

    function actualizarDetalleTests(detalle, esSimulacion) {{
        if (!detalle || !Array.isArray(detalle)) return;
        detalle.forEach(item => {{
            const b = document.getElementById("badge-test-" + item.numero);
            const m = document.getElementById("msg-test-" + item.numero);
            if (m && item.mensaje) m.textContent = item.mensaje;
            if (b) {{
                if (item.estado === "exitoso") {{
                    b.className = "badge-dinamico badge-dinamico--ok";
                    b.textContent = esSimulacion ? "✓ Validado" : "✓ Guardado";
                }} else if (item.estado === "omitido") {{
                    b.className = "badge-dinamico badge-dinamico--omitido";
                    b.textContent = "⏭ Omitido";
                }} else if (item.estado === "error") {{
                    b.className = "badge-dinamico badge-dinamico--error";
                    b.textContent = "❌ Error";
                }} else if (item.estado === "cancelado") {{
                    b.className = "badge-dinamico badge-dinamico--detenido";
                    b.textContent = "⏹ Detenido";
                }} else if (item.estado === "en_proceso") {{
                    b.className = "badge-dinamico badge-dinamico--proceso";
                    b.textContent = "⏳ En proceso...";
                }} else {{
                    b.className = "badge-dinamico badge-dinamico--pendiente";
                    b.textContent = "⚪ En espera";
                }}
            }}
        }});
    }}

    function pollEstado() {{
        if (terminado) return;
        fetch(`/tests/${{jobId}}/estado-prizma/json`)
            .then(r => r.json())
            .then(data => {{
                if (data.mensaje) msg.textContent = data.mensaje;
                if (data.total !== undefined) {{
                    const elTotal = document.getElementById("kpi-total");
                    const elExitosos = document.getElementById("kpi-exitosos");
                    const elOmitidos = document.getElementById("kpi-omitidos");
                    const elPendientes = document.getElementById("kpi-pendientes");
                    const elFallidos = document.getElementById("kpi-fallidos");
                    if (elTotal) elTotal.textContent = data.total;
                    if (elExitosos) elExitosos.textContent = data.exitosos || 0;
                    if (elOmitidos) elOmitidos.textContent = data.omitidos || 0;
                    if (elPendientes) elPendientes.textContent = data.pendientes !== undefined ? data.pendientes : (data.total - (data.procesados || 0));
                    if (elFallidos) elFallidos.textContent = data.fallidos || 0;

                    const proc = data.procesados || 0;
                    const tot = data.total || 0;
                    const pct = data.progreso_porcentaje !== undefined ? data.progreso_porcentaje : (tot > 0 ? Math.round((proc / tot) * 100) : 0);
                    const elPct = document.getElementById("progreso-porcentaje-texto");
                    const elBar = document.getElementById("progreso-barra-fill");
                    const elTxt = document.getElementById("progreso-texto-avance");
                    if (elPct) elPct.textContent = pct + "%";
                    if (elBar) elBar.style.width = pct + "%";
                    if (elTxt) elTxt.textContent = `Avance general (${{proc}} de ${{tot}} tests)`;
                    if (resumen) resumen.textContent = `${{proc}} de ${{tot}} test(s) procesados`;
                }}
                if (data.detalle_tests) {{
                    actualizarDetalleTests(data.detalle_tests, data.simulacion);
                }}

                // Manejo de selección interactiva de asignatura
                const pnlAsig = document.getElementById("panel-seleccion-asignatura");
                if (pnlAsig) {{
                    if (data.esperando_asignatura && data.opciones_asignatura && data.opciones_asignatura.length > 0) {{
                        pnlAsig.style.display = "flex";
                        const txtBusq = document.getElementById("txt-asignatura-buscada");
                        const tituloCampo = document.getElementById("titulo-seleccion-campo");
                        const selectorCampo = data.campo_seleccion || "Asignatura por pensum";
                        const campoPendiente = document.getElementById("campo-seleccion-pendiente");
                        if (campoPendiente) campoPendiente.value = selectorCampo;
                            if (tituloCampo) tituloCampo.textContent = `Confirma ${{selectorCampo}}`;
                        if (txtBusq && data.asignatura_buscada) {{
                            txtBusq.textContent = `PRIZMA mostró ${{data.opciones_asignatura.length}} opciones para "${{data.asignatura_buscada}}". Elige la correcta para continuar:`;
                        }}
                        const selAsig = document.getElementById("sel-asignatura-opciones");
                        if (selAsig && selAsig.options.length <= 1) {{
                                selAsig.innerHTML = `<option value="">-- Seleccionar opción de PRIZMA (${{data.opciones_asignatura.length}} opciones) --</option>` +
                                data.opciones_asignatura.map(op => `<option value="${{op.replace(/"/g, '&quot;')}}">${{op}}</option>`).join("");
                        }}
                    }} else {{
                        pnlAsig.style.display = "none";
                    }}
                }}

                const btnDet = document.getElementById("btn-detener-auto");
                if (data.estado === "detenido") {{
                    badge.className = "badge warn";
                    badge.textContent = "⏹ Detenido por usuario";
                    const bDet = document.getElementById("banner-detenido-superior");
                    const txtDet = document.getElementById("texto-detenido-superior");
                    if (bDet) bDet.style.display = "flex";
                    if (txtDet && data.mensaje) txtDet.textContent = data.mensaje;
                    if (btnDet) btnDet.style.display = "none";
                    terminado = true;
                }} else if (data.estado === "completado") {{
                    badge.className = "badge ok";
                    badge.textContent = data.simulacion ? "✓ Simulación exitosa (Validado sin guardar)" : "✓ Guardado completado en PRIZMA";
                    const bOk = document.getElementById("banner-exito-superior");
                    const txtOk = document.getElementById("texto-exito-superior");
                    if (bOk) bOk.style.display = "flex";
                    if (txtOk && data.mensaje) txtOk.textContent = data.mensaje;
                    if (btnDet) btnDet.style.display = "none";
                    terminado = true;
                }} else if (data.estado === "error") {{
                    badge.className = "badge error";
                    badge.textContent = "❌ Error en la ejecución";
                    const bErr = document.getElementById("banner-error-superior");
                    const txtErr = document.getElementById("texto-error-superior");
                    if (bErr) bErr.style.display = "flex";
                    if (txtErr) txtErr.textContent = data.error || data.mensaje || "Error durante la automatización.";
                    if (btnDet) btnDet.style.display = "none";
                    if (bErr) bErr.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
                    terminado = true;
                }}
            }})
            .catch(() => {{}});
    }}

    const btnConfAsig = document.getElementById("btn-confirmar-asignatura");
    if (btnConfAsig) {{
        btnConfAsig.addEventListener("click", () => {{
            const selAsig = document.getElementById("sel-asignatura-opciones");
            const msgConf = document.getElementById("msg-confirmacion-asignatura");
            if (!selAsig || !selAsig.value) {{
                    alert("Selecciona una opción de la lista antes de continuar.");
                return;
            }}
            const formData = new FormData();
            formData.append("asignatura", selAsig.value);
            const campoPendiente = document.getElementById("campo-seleccion-pendiente");
            formData.append("selector", campoPendiente ? campoPendiente.value : "Asignatura por pensum");
            btnConfAsig.disabled = true;
            btnConfAsig.textContent = "⏳ Enviando selección...";
            fetch(`/tests/${{jobId}}/seleccionar-asignatura`, {{
                method: "POST",
                body: formData,
            }})
            .then(r => r.json())
            .then(res => {{
                if (res.ok) {{
                    if (msgConf) {{
                        msgConf.style.display = "block";
                        msgConf.style.color = "var(--verde)";
                        msgConf.textContent = `✓ Selección enviada: "${{res.opcion || res.asignatura}}". El robot continuará procesando el test...`;
                    }}
                    btnConfAsig.textContent = "✓ Confirmado";
                    setTimeout(() => {{
                        const pnl = document.getElementById("panel-seleccion-asignatura");
                        if (pnl) pnl.style.display = "none";
                    }}, 2500);
                }} else {{
                    alert(res.error || "Error al enviar la selección.");
                    btnConfAsig.disabled = false;
                    btnConfAsig.textContent = "Confirmar Asignatura y Continuar ➔";
                }}
            }})
            .catch(err => {{
                alert("Error de conexión al enviar selección: " + err);
                btnConfAsig.disabled = false;
                btnConfAsig.textContent = "Confirmar Asignatura y Continuar ➔";
            }});
        }});
    }}

    if (!terminado) {{
        setInterval(pollEstado, 1500);
    }}
    </script>'''
    return HTMLResponse(_layout("Monitoreo PRIZMA", body))


@router.get("/tests/{job_id}/estado-prizma/json")
def status_prizma_json(request: Request, job_id: str):
    job = _job_for(request, job_id)
    if not job:
        return JSONResponse({"error": "Este análisis ya no existe en el servidor. Normalmente pasa si el servidor se reinició con la página abierta (los análisis se guardan solo en memoria, no en disco). Sube el documento de nuevo para generar un análisis nuevo."}, status_code=404)
    with _AUTOMATION_LOCK:
        auto_state = _AUTOMATION_JOBS.get(job_id)
    if not auto_state:
        return JSONResponse({"error": "Automatización no iniciada"}, status_code=404)
    return JSONResponse(auto_state)


@router.post("/tests/{job_id}/cancelar-prizma")
def cancelar_prizma(request: Request, job_id: str):
    job = _job_for(request, job_id)
    if not job:
        return JSONResponse({"error": "Este análisis ya no existe en el servidor. Normalmente pasa si el servidor se reinició con la página abierta (los análisis se guardan solo en memoria, no en disco). Sube el documento de nuevo para generar un análisis nuevo."}, status_code=404)
    with _AUTOMATION_LOCK:
        auto_state = _AUTOMATION_JOBS.get(job_id)
    if not auto_state:
        return JSONResponse({"error": "Automatización no iniciada"}, status_code=404)
    if auto_state.get("estado") == "en_ejecucion":
        auto_state["cancelado"] = True
        auto_state["mensaje"] = "Deteniendo automatización a solicitud del usuario..."
        return JSONResponse({"ok": True, "mensaje": "Solicitud de detención registrada"})
    return JSONResponse({"ok": False, "mensaje": "La automatización no está en ejecución"})


@router.post("/tests/{job_id}/seleccionar-asignatura")
def seleccionar_asignatura(
    request: Request,
    job_id: str,
    asignatura: str = Form(...),
    selector: str = Form(default="Asignatura por pensum"),
):
    job = _job_for(request, job_id)
    if not job:
        return JSONResponse({"error": "Este análisis ya no existe en el servidor. Normalmente pasa si el servidor se reinició con la página abierta (los análisis se guardan solo en memoria, no en disco). Sube el documento de nuevo para generar un análisis nuevo."}, status_code=404)
    with _AUTOMATION_LOCK:
        auto_state = _AUTOMATION_JOBS.get(job_id)
        sync_obj = _AUTOMATION_SYNC.get(job_id)
    if not auto_state or not sync_obj or not auto_state.get("esperando_asignatura"):
        return JSONResponse({"error": "No hay una selección de asignatura pendiente"}, status_code=400)

    asignatura_limpia = asignatura.strip()
    if not asignatura_limpia:
        return JSONResponse({"error": "Debes seleccionar una asignatura"}, status_code=400)

    sync_obj["seleccion"]["asignatura"] = asignatura_limpia
    sync_obj["seleccion"]["campo"] = selector.strip()
    sync_obj["event"].set()
    return JSONResponse({"ok": True, "asignatura": asignatura_limpia, "opcion": asignatura_limpia})


async def _extraer_bytes_docx_request(archivo_docx: UploadFile | None) -> tuple[bytes, str, str | None]:
    """Retorna (contenido_bytes, nombre_fuente, error_str)."""
    if not archivo_docx or not archivo_docx.filename:
        return b"", "", "Selecciona un archivo Word (.docx)."
    if not archivo_docx.filename.lower().endswith(".docx"):
        return b"", "", "El archivo debe tener formato Microsoft Word (.docx)."
    content = await archivo_docx.read()
    if not content:
        return b"", "", "El documento seleccionado está vacío o dañado."
    return content, archivo_docx.filename, None


def _obtener_estado_test_activo(user: str = "") -> dict | None:
    """Solo devuelve un job mientras esta realmente en curso. En cuanto
    termina (exito o error) deja de aparecer aqui - el resultado se
    consulta en Historial/Reportes, no hace falta "marcarlo como visto"."""
    with _AUTOMATION_LOCK:
        for jid, astate in reversed(list(_AUTOMATION_JOBS.items())):
            if user and astate.get("owner") and astate.get("owner") != user:
                continue
            if astate.get("estado") in ["en_ejecucion", "esperando_asignatura"]:
                res = dict(astate)
                res["job_id"] = jid
                return res
    return None


@router.get("/tests/estado-activo/json")
def estado_test_activo_json(request: Request):
    user = _user(request)
    info = _obtener_estado_test_activo(user)
    if not info:
        return JSONResponse({"activo": False})
    return JSONResponse({
        "activo": True,
        "job_id": info.get("job_id"),
        "estado": info.get("estado"),
        "mensaje": info.get("mensaje"),
        "progreso_porcentaje": info.get("progreso_porcentaje", 0),
        "total": info.get("total", 0),
        "procesados": info.get("procesados", 0),
        "exitosos": info.get("exitosos", 0),
        "fallidos": info.get("fallidos", 0),
        "asignatura": info.get("asignatura", ""),
        "titulo": info.get("titulo_doc", ""),
    })
