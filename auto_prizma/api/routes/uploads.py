"""Iniciar, seguir, cancelar y consultar el estado de los cargues.
"""

from fastapi import (
    Form,
    BackgroundTasks,
)
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
)
import html
from datetime import datetime

from auto_prizma.core.application import app
from auto_prizma.core.config import ZONA_HORARIA_COLOMBIA
from auto_prizma.services.auth import (
    _es_de,
    _nombre_visible,
    _usuario_actual,
)
from auto_prizma.services.upload_jobs import (
    TRABAJOS,
    _posicion_en_cola,
    _validar_seleccion_actividades,
    active_jobs,
    cancel_job,
    public_job_status,
    validate_access_and_enqueue,
)
from auto_prizma.web.views import generar_html
from auto_prizma.web.icons import icon
from auto_prizma.web.layout import render_page


# ============================================================
# INICIAR
# ============================================================

@app.post(
    "/iniciar/{trabajo_id}",
    response_class=HTMLResponse,
)
def iniciar_trabajo(
    trabajo_id: str,
    background_tasks: BackgroundTasks,
    usuario_prizma: str = Form(...),
    contrasena_prizma: str = Form(...),
    actividades_seleccionadas: list[str] = Form(default=[]),
):
    trabajo = TRABAJOS.get(trabajo_id)
    if not trabajo or not _es_de(trabajo, _usuario_actual()):
        return HTMLResponse("<h2>Trabajo no encontrado.</h2><a href='/'>Volver</a>", status_code=404)

    seleccion_validada = _validar_seleccion_actividades(
        actividades_seleccionadas,
        trabajo.get("resultado_analisis") or {},
    )
    if not seleccion_validada:
        return generar_html(
            resultado=trabajo.get("resultado_analisis"),
            trabajo_id=trabajo_id,
            error=(
                "Selecciona al menos una actividad para cargar en PRIZMA. "
                "Puedes elegir por tipo de recurso o actividad individual."
            ),
            seleccion_actual=[],
        )

    trabajo["seleccion_actividades"] = seleccion_validada

    usuario_prizma = usuario_prizma.strip()
    if not usuario_prizma or not contrasena_prizma:
        return generar_html(
            resultado=trabajo.get("resultado_analisis"),
            trabajo_id=trabajo_id,
            error="Debes ingresar el usuario y la contraseña de PRIZMA.",
            seleccion_actual=seleccion_validada,
        )

    if trabajo.get("etapa") not in ["analizado", "error"]:
        return HTMLResponse("<h2>Este trabajo ya fue iniciado.</h2>")

    # Validar el acceso antes de encolar el curso.
    encolado, mensaje_error = validate_access_and_enqueue(
        trabajo_id,
        usuario_prizma,
        contrasena_prizma,
    )

    if not encolado:
        return generar_html(
            resultado=trabajo.get("resultado_analisis"),
            trabajo_id=trabajo_id,
            error=mensaje_error,
            seleccion_actual=seleccion_validada,
        )

    html_progreso = _pagina_progreso()

    pagina_progreso = html_progreso.replace(
        "__TRABAJO_ID__",
        trabajo_id,
    )
    trabajo["pagina_progreso"] = pagina_progreso

    return HTMLResponse(pagina_progreso)


def _pagina_sin_cargue_actual():
    contenido = (
        '<section class="panel vacio">'
        '<span class="icono-tile">' + icon("subir") + "</span>"
        "<h1>No hay cargues activos</h1>"
        "<p>Cuando alguien inicie un proceso desde Inicio, aparecerá aquí para que el equipo "
        "pueda consultar su progreso.</p>"
        '<a class="boton" href="/">' + icon("inicio") + "Iniciar un nuevo cargue</a>"
        "</section>"
    )
    return HTMLResponse(render_page("Cargue actual", contenido, active="cargue"))


def _formatear_inicio_cargue(fecha_iso):
    if not fecha_iso:
        return "Iniciando..."
    try:
        fecha = datetime.fromisoformat(fecha_iso)
        if fecha.tzinfo is None:
            fecha = fecha.replace(tzinfo=ZONA_HORARIA_COLOMBIA)
        else:
            fecha = fecha.astimezone(ZONA_HORARIA_COLOMBIA)
        return fecha.strftime("%d/%m/%Y · %I:%M %p").replace("AM", "a. m.").replace("PM", "p. m.")
    except Exception:
        return "En progreso"


def _render_tarjeta_cargue(trabajo, usuario_actual):
    cursos = trabajo.get("cursos") or []
    if cursos:
        curso = cursos[0].get("curso") or "Curso sin nombre"
        programa = cursos[0].get("programa") or "Programa sin nombre"
        if len(cursos) > 1:
            curso = f"{curso} y {len(cursos) - 1} curso(s) más"
    else:
        curso, programa = "Curso en proceso", "Programa sin nombre"

    total = int(trabajo.get("total") or 0)
    procesadas = int(trabajo.get("procesadas") or 0)
    exitosas = int(trabajo.get("exitosas") or 0)
    errores = int(trabajo.get("errores") or 0)
    porcentaje = max(
        0,
        min(100, round((procesadas / total) * 100) if total > 0 else 0),
    )
    trabajo_id_raw = str(trabajo.get("id") or "")
    trabajo_id = html.escape(trabajo_id_raw)
    en_cola = trabajo.get("etapa") == "en_cola"
    posicion = _posicion_en_cola(trabajo_id_raw) if en_cola else None
    estado_texto = f"En cola · #{posicion}" if posicion else "En progreso"
    inicio_label = "En cola desde" if en_cola else "Iniciado"
    fecha_mostrar = trabajo.get("encolado_en") if en_cola else trabajo.get("iniciado_en")
    propietario = str(trabajo.get("usuario_app") or "")
    propietario_visible = _nombre_visible(propietario) or propietario or "Usuario"
    es_propietario = _es_de(trabajo, usuario_actual)

    if es_propietario:
        acciones = (
            f'<a class="boton" href="/proceso/{trabajo_id}">Entrar al proceso {icon("flecha-derecha")}</a>'
            f'<form action="/cancelar/{trabajo_id}" method="post">'
            '<button type="submit" class="boton peligro chico">Cancelar</button></form>'
        )
    else:
        acciones = '<span class="solo-lectura">Cargue de otro usuario</span>'

    return (
        f'<article class="panel carga-card">'
        f'<div class="curso-bloque"><span class="icono-tile grande">{icon("birrete")}</span><div class="curso-texto">'
        f'<h2>{html.escape(curso)}</h2><p>Programa: {html.escape(programa)}</p>'
        f'<p>Iniciado por: <strong>{html.escape(propietario_visible)}</strong></p>'
        f'<span class="estado-chip"><span></span> {html.escape(estado_texto)}</span></div></div>'
        f'<div class="inicio-bloque"><small>{icon("historial")} {inicio_label}</small>'
        f'<strong>{html.escape(_formatear_inicio_cargue(fecha_mostrar))}</strong></div>'
        f'<div class="avance-bloque"><div class="avance-cab"><span>Progreso general</span>'
        f'<strong>{porcentaje}%</strong></div><div class="barra"><div class="barra-interna" '
        f'style="width:{porcentaje}%"></div></div><div class="metricas">'
        f'<div><i class="verde"></i><small>Procesadas</small><strong>{procesadas}</strong></div>'
        f'<div><i class="verde"></i><small>Exitosas</small><strong>{exitosas}</strong></div>'
        f'<div><i class="rojo"></i><small>Errores</small><strong>{errores}</strong></div></div></div>'
        f'<div class="accion-bloque">{acciones}</div></article>'
    )


def _pagina_cargues_activos(trabajos, usuario_actual=None):
    if usuario_actual is None:
        usuario_actual = _usuario_actual()
    tarjetas = [
        _render_tarjeta_cargue(trabajo, usuario_actual)
        for trabajo in trabajos
    ]
    cuerpo = "".join(tarjetas)
    cantidad = len(trabajos)
    plural = "s" if cantidad != 1 else ""
    contenido = (
        '<header class="encabezado"><div class="encabezado-titulo">'
        '<span class="icono-tile grande">' + icon("subir") + "</span>"
        "<div><h1>Cargue actual</h1>"
        "<p>Cursos que se están procesando ahora. Entra a un proceso para ver el detalle de sus actividades.</p>"
        "</div></div>"
        f'<span class="chip grande">{cantidad} proceso{plural} activo{plural}</span></header>'
        f'<section class="lista-cargues">{cuerpo}</section>'
        '<div class="aviso info nota-equipo">' + icon("info")
        + "<div><strong>Vista global del equipo.</strong>"
        "<p>Cada tarjeta es un cargue activo. Solo quien lo inició puede entrar al proceso o cancelarlo.</p></div></div>"
    )
    return HTMLResponse(render_page(
        "Cargue actual",
        contenido,
        active="cargue",
        page_css=_CSS_CARGUES,
        page_js="setTimeout(function () { window.location.reload(); }, 3000);",
    ))


@app.get("/cargue-actual", response_class=HTMLResponse)
def cargue_actual():
    usuario = _usuario_actual()

    activos = active_jobs()
    if not activos:
        return _pagina_sin_cargue_actual()
    return _pagina_cargues_activos(activos, usuario)


@app.post("/cancelar/{trabajo_id}", response_class=HTMLResponse)
def cancelar_trabajo(trabajo_id: str):
    if cancel_job(trabajo_id, _usuario_actual()) == "no_encontrado":
        return HTMLResponse("<h2>Proceso no encontrado.</h2>", status_code=404)

    # Terminado, cancelado en cola o cancelacion solicitada: volver al listado.
    return HTMLResponse("<script>window.location='/cargue-actual';</script>")


@app.get("/proceso/{trabajo_id}", response_class=HTMLResponse)
def ver_proceso(trabajo_id: str):
    trabajo = TRABAJOS.get(trabajo_id)
    if not trabajo or not _es_de(trabajo, _usuario_actual()):
        return HTMLResponse("<h2>Proceso no encontrado.</h2><p><a href='/cargue-actual'>Volver a Cargue actual</a></p>", status_code=404)
    pagina = trabajo.get("pagina_progreso")
    if pagina:
        return HTMLResponse(pagina)
    return HTMLResponse("<h2>El proceso todavía se está preparando.</h2><p><a href='/cargue-actual'>Volver a Cargue actual</a></p>", status_code=202)


# ============================================================
# ESTADO
# ============================================================

@app.get(
    "/estado/{trabajo_id}",
)
def estado_trabajo(
    trabajo_id: str,
):

    estado = public_job_status(
        trabajo_id,
        _usuario_actual(),
    )

    if estado is None:

        return JSONResponse(
            {
                "error":
                    "Trabajo no encontrado"
            },
            status_code=404,
        )

    return estado


# ============================================================
# HTML Y CSS DE LAS PAGINAS
# ============================================================

_CSS_CARGUES = r"""
.lista-cargues { display: grid; gap: 16px; }
.carga-card {
  display: grid; grid-template-columns: minmax(250px, 1.2fr) 170px minmax(300px, 1.3fr) 200px;
  gap: 24px; align-items: center; padding: 22px 24px;
}
.curso-bloque { display: flex; gap: 16px; align-items: center; min-width: 0; }
.curso-texto { min-width: 0; }
.curso-texto h2 { margin: 0 0 5px; font-size: 17px; font-weight: 800; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.curso-texto p { margin: 0 0 6px; color: var(--muted); font-size: 13px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.curso-texto p strong { color: var(--texto-2); }
.estado-chip {
  display: inline-flex; align-items: center; gap: 6px; padding: 5px 10px; border-radius: 999px;
  background: var(--azul-suave); color: var(--azul); font-size: 12px; font-weight: 800;
}
.estado-chip span { width: 7px; height: 7px; border-radius: 50%; background: currentColor; }
.inicio-bloque small { display: flex; align-items: center; gap: 6px; color: var(--muted); font-size: 12px; margin-bottom: 7px; }
.inicio-bloque small .icono { width: 16px; height: 16px; }
.inicio-bloque strong { font-size: 13px; color: var(--texto-2); }
.avance-cab { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; color: var(--muted); font-size: 12px; }
.avance-cab strong { font-size: 22px; color: var(--acento-texto); }
.barra { height: 10px; border-radius: 999px; background: var(--acento-suave); overflow: hidden; }
.barra-interna { height: 100%; border-radius: 999px; background: var(--boton); }
.metricas { display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; margin-top: 12px; }
.metricas div { display: grid; grid-template-columns: 8px 1fr; column-gap: 6px; align-items: center; }
.metricas i { width: 7px; height: 7px; border-radius: 50%; }
.metricas i.verde { background: var(--verde); }
.metricas i.rojo { background: var(--rojo); }
.metricas small { font-size: 11px; color: var(--muted); }
.metricas strong { grid-column: 2; font-size: 15px; color: var(--texto); }
.accion-bloque { display: grid; gap: 8px; padding-left: 22px; border-left: 1px solid var(--borde); }
.accion-bloque form { margin: 0; }
.accion-bloque .boton { width: 100%; }
.solo-lectura {
  display: block; padding: 11px 12px; text-align: center; border-radius: 10px;
  border: 1px solid var(--borde); background: var(--panel-2); color: var(--muted); font-size: 12px; font-weight: 700;
}
.nota-equipo { margin-top: 18px; }
@media (max-width: 1200px) {
  .carga-card { grid-template-columns: 1fr 1fr; }
  .accion-bloque { border-left: 0; padding-left: 0; }
}
@media (max-width: 700px) {
  .carga-card { grid-template-columns: 1fr; padding: 18px; }
}
"""


def _pagina_progreso(
    titulo="Cargue en progreso",
    lista_titulo="Actividades del cargue",
    active="cargue",
    estado_url="",
):
    """Pagina de progreso de un trabajo (se guarda en el para /proceso/<id>).

    Es generica: la usan los cargues normales y los trabajos cortos de
    /cursos (reintento individual y verificacion), que solo cambian el
    titulo y la etiqueta de la lista.
    """
    contenido = """
    <section id="cargue-progreso" class="panel cabecera-progreso" data-estado-url="__ESTADO_URL__">
        <div class="cabecera-linea">
            <div class="cabecera-titulo">
                <span class="icono-tile">__ICONO_SUBIR__</span>
                <h1>__TITULO__</h1>
            </div>
            <div class="porcentaje"><strong id="porcentaje">0%</strong> completado</div>
        </div>
        <div class="barra-progreso"><div id="progreso" class="progreso"></div></div>
        <div id="estado" class="estado" aria-live="polite">Iniciando...</div>
    </section>

    <section class="numeros">
        <div class="panel numero procesadas">
            <span class="icono-tile">__ICONO_GIRAR__</span>
            <div><span>Procesadas</span><strong id="procesadas">0</strong></div>
        </div>
        <div class="panel numero exitosas">
            <span class="icono-tile verde">__ICONO_OK__</span>
            <div><span>Exitosas</span><strong id="exitosas">0</strong></div>
        </div>
        <div class="panel numero errores">
            <span class="icono-tile rojo">__ICONO_ERROR__</span>
            <div><span>Errores</span><strong id="errores">0</strong></div>
        </div>
    </section>

    <section class="zona">
        <div class="panel lista-panel">
            <h2 class="titulo-panel">__LISTA_TITULO__</h2>
            <div id="lista-actividades" class="lista-actividades">
                <div class="actividad-progreso">Preparando lista de actividades...</div>
            </div>
            <div class="pie">El progreso se actualiza automáticamente.</div>
        </div>

        <div class="panel estado-panel">
            <h2 class="titulo-panel">Estado del proceso</h2>
            <div class="estado-caja">
                <span>Actividad actual</span>
                <strong id="actividad-actual">Preparando cargue...</strong>
            </div>
            <div class="estado-caja">
                <span>Total de actividades</span>
                <strong id="total-actividades">—</strong>
            </div>
            <div class="leyenda">
                <div>⏳ Pendiente</div>
                <div>🔄 Procesando</div>
                <div>✅ Completada</div>
                <div>➖ Omitida</div>
                <div>❌ Con error</div>
            </div>
            <form action="/cancelar/__TRABAJO_ID__" method="post" class="form-cancelar">
                <button type="submit" class="boton peligro">Cancelar proceso</button>
            </form>
            <div id="final"></div>
        </div>
    </section>
    """
    contenido = (
        contenido
        .replace("__ICONO_SUBIR__", icon("subir"))
        .replace("__ICONO_GIRAR__", icon("girar"))
        .replace("__ICONO_OK__", icon("check-circulo"))
        .replace("__ICONO_ERROR__", icon("alerta-circulo"))
        .replace("__TITULO__", titulo)
        .replace("__LISTA_TITULO__", lista_titulo)
        .replace("__ESTADO_URL__", estado_url)
    )
    return render_page(
        titulo,
        contenido,
        active=active,
        page_css=_CSS_PROGRESO,
        page_js=_JS_PROGRESO,
    )


_CSS_PROGRESO = r"""
.cabecera-progreso { padding: 24px 28px; }
.cabecera-linea { display: flex; justify-content: space-between; align-items: center; gap: 20px; flex-wrap: wrap; }
.cabecera-titulo { display: flex; gap: 14px; align-items: center; }
.cabecera-titulo h1 { margin: 0; font-size: 24px; font-weight: 800; }
.porcentaje { font-size: 14px; color: var(--muted); }
.porcentaje strong { font-size: 20px; color: var(--acento-texto); }
.barra-progreso { height: 12px; background: var(--acento-suave); border-radius: 999px; overflow: hidden; margin: 22px 0 14px; }
.progreso { height: 100%; width: 0%; border-radius: 999px; background: var(--boton); transition: width .35s ease; }
.estado { color: var(--acento-texto); font-size: 14px; font-weight: 600; line-height: 1.45; }
.numeros { display: grid; grid-template-columns: repeat(3, 1fr); gap: 18px; margin: 20px 0; }
.numero { padding: 20px; display: flex; align-items: center; gap: 16px; }
.numero > div > span { display: block; color: var(--muted); font-size: 13px; }
.numero > div > strong { display: block; font-size: 28px; font-weight: 800; color: var(--texto); }
.zona { display: grid; grid-template-columns: minmax(0, 1.55fr) minmax(280px, .75fr); gap: 20px; align-items: start; }
.lista-panel, .estado-panel { padding: 24px; }
.titulo-panel { margin: 0 0 16px; font-size: 17px; font-weight: 800; }
.lista-actividades { max-height: 570px; overflow: auto; border: 1px solid var(--borde); border-radius: 12px; }
.actividad-progreso {
  display: grid; grid-template-columns: 27px 1fr; gap: 10px; align-items: start;
  padding: 11px 13px; border-bottom: 1px solid var(--borde); background: var(--panel); color: var(--texto-2);
}
.actividad-progreso:last-child { border-bottom: 0; }
.actividad-icono { width: 23px; height: 23px; display: grid; place-items: center; font-size: 15px; }
.actividad-nombre { font-size: 13px; line-height: 1.4; color: var(--texto); }
.actividad-error { margin-top: 4px; color: var(--rojo); font-size: 11.5px; word-break: break-word; }
.actividad-ok { background: var(--verde-suave); }
.actividad-omitida { background: var(--ambar-suave); }
.actividad-error-fila { background: var(--rojo-suave); }
.actividad-procesando { background: var(--acento-suave); box-shadow: inset 3px 0 0 var(--acento); }
.estado-caja { padding: 16px; margin-bottom: 14px; border: 1px solid var(--borde); border-radius: 12px; background: var(--panel-2); }
.estado-caja span { display: block; color: var(--muted); font-size: 12px; }
.estado-caja strong { display: block; margin-top: 6px; font-size: 14px; line-height: 1.45; color: var(--texto); }
.leyenda { display: grid; gap: 12px; margin-top: 22px; }
.leyenda div { display: flex; align-items: center; gap: 9px; color: var(--texto-2); font-size: 13px; }
.form-cancelar { margin-top: 18px; }
.form-cancelar .boton { width: 100%; }
.final { margin-top: 18px; padding: 18px; border-radius: 12px; background: var(--verde-suave); border: 1px solid var(--verde-borde); }
.final h3 { margin: 0 0 6px; color: var(--verde); }
.final p { margin: 0; color: var(--texto-2); font-size: 13px; }
.final .boton { margin-top: 14px; }
.pie { margin-top: 18px; color: var(--muted); font-size: 12px; text-align: center; }
@media (max-width: 1050px) { .zona { grid-template-columns: 1fr; } }
@media (max-width: 680px) { .numeros { grid-template-columns: 1fr; } }
"""

_JS_PROGRESO = r"""
const trabajoId = "__TRABAJO_ID__";
const raizProgreso = document.getElementById("cargue-progreso");
const estadoUrl = (raizProgreso && raizProgreso.dataset.estadoUrl) || ("/estado/" + trabajoId);

function escaparHtml(texto) {
    return String(texto ?? "")
        .replaceAll("&", "&amp;")
        .replaceAll("<", "&lt;")
        .replaceAll(">", "&gt;")
        .replaceAll('"', "&quot;")
        .replaceAll("'", "&#039;");
}

function renderizarActividades(actividades) {
    const contenedor = document.getElementById("lista-actividades");

    if (!Array.isArray(actividades) || actividades.length === 0) {
        contenedor.innerHTML = '<div class="actividad-progreso">Preparando lista de actividades...</div>';
        return;
    }

    let html = "";
    let actual = "Preparando cargue...";

    for (const actividad of actividades) {
        let icono = "⏳";
        let clase = "";

        if (actividad.estado === "procesando") {
            icono = "🔄";
            clase = "actividad-procesando";
            actual = actividad.numero + ". " + actividad.nombre;
        } else if (actividad.estado === "ok") {
            icono = "✅";
            clase = "actividad-ok";
        } else if (actividad.estado === "omitido") {
            icono = "➖";
            clase = "actividad-omitida";
        } else if (actividad.estado === "error") {
            icono = "❌";
            clase = "actividad-error-fila";
        }

        html += '<div class="actividad-progreso ' + clase + '">' +
            '<div class="actividad-icono">' + icono + '</div>' +
            '<div><div class="actividad-nombre">' +
            actividad.numero + '. ' + escaparHtml(actividad.nombre) + '</div>';

        if ((actividad.estado === "error" || actividad.estado === "omitido") && actividad.error) {
            html += '<div class="actividad-error">' + escaparHtml(actividad.error) + '</div>';
        }

        html += '</div></div>';
    }

    contenedor.innerHTML = html;
    document.getElementById("actividad-actual").innerText = actual;
}

async function revisarEstado() {
    try {
        const respuesta = await fetch(estadoUrl);
        const datos = await respuesta.json();

        if (!respuesta.ok || datos.error) {
            document.getElementById("estado").innerText = datos.error || "No se pudo consultar el estado del proceso.";
            document.getElementById("actividad-actual").innerText = "No se pudo consultar el estado";
            document.getElementById("procesadas").innerText = "0";
            document.getElementById("exitosas").innerText = "0";
            document.getElementById("errores").innerText = "0";
            return;
        }

        document.getElementById("estado").innerText = (datos.mensaje || "Preparando proceso...") + (datos.posicion_cola ? ' · Posición en cola: ' + datos.posicion_cola : '');
        document.getElementById("procesadas").innerText = datos.procesadas ?? 0;
        document.getElementById("exitosas").innerText = datos.exitosas ?? 0;
        document.getElementById("errores").innerText = datos.errores ?? 0;
        document.getElementById("total-actividades").innerText = datos.total || "—";

        renderizarActividades(datos.detalle_actividades);

        let porcentaje = 0;
        if (datos.total > 0) {
            porcentaje = (datos.procesadas / datos.total) * 100;
        }
        porcentaje = Math.min(100, porcentaje);

        document.getElementById("progreso").style.width = porcentaje + "%";
        document.getElementById("porcentaje").innerText = Math.round(porcentaje) + "%";

        if (datos.terminado) {
            document.getElementById("actividad-actual").innerText = "Proceso finalizado";

            let html = '<div class="final"><h3>Proceso terminado</h3><p>' +
                escaparHtml(datos.mensaje) + '</p>';

            if (datos.reporte_disponible) {
                html += '<a class="boton" href="/reporte/' + trabajoId + '">Ver reporte</a>';
            }

            html += '</div>';
            document.getElementById("final").innerHTML = html;
            return;
        }

        setTimeout(revisarEstado, 1500);
    } catch (error) {
        document.getElementById("estado").innerText = "Error consultando estado.";
        setTimeout(revisarEstado, 3000);
    }
}

revisarEstado();
"""
