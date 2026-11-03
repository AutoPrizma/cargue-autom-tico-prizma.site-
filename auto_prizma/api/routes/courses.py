"""Estado por curso: actividades que ya estan en PRIZMA y las que faltan.

Cruza data/estado_cursos.json (acumulado entre cargues) y muestra, por curso,
cuantas actividades quedaron subidas y cual es la causa humana de las que
faltan. Cada falta se puede reintentar de forma individual con el recurso
elegido a mano, y cada curso se puede verificar (solo lectura) contra PRIZMA
para confirmar que las actividades aparezcan ahi.
"""

from datetime import datetime
import csv
import html
import os
import shutil
import threading
import traceback

from fastapi import File, Form, UploadFile
from fastapi.responses import HTMLResponse

from auto_prizma.automation.prizma import engine as motor_prizma
from auto_prizma.api.routes.uploads import _pagina_progreso
from auto_prizma.core.application import app
from auto_prizma.core.config import RESULTADOS_DIR, TEMP_DIR, UPLOADS_DIR, ZONA_HORARIA_COLOMBIA
from auto_prizma.services.auth import USUARIO_ACTUAL, _usuario_actual
from auto_prizma.services.course_state import (
    _clave_actividad,
    _clave_curso,
    actividades_para_verificar,
    actividad_para_reintento,
    marcar_verificacion,
    resumen_cursos,
    total_faltantes,
)
from auto_prizma.services.error_messages import mensaje_error
from auto_prizma.services.history import _nombre_reporte, find_user_record
from auto_prizma.services.upload_jobs import TRABAJOS, crear_trabajo_manual
from auto_prizma.web.icons import icon
from auto_prizma.web.layout import render_page


# Un reintento o verificacion a la vez: ambos abren navegador contra PRIZMA.
_BLOQUE_MANUAL = threading.Lock()


def _lanzar_hilo(target, args):
    """Corre un trabajo manual en su propio hilo (los tests lo ejecutan en el momento)."""
    threading.Thread(target=target, args=args, daemon=True).start()


def _e(valor):
    return html.escape(str(valor or ""))


def _fecha_corta(fecha_iso):
    """'22 oct 2026' a partir de un ISO, o '' si no se puede leer."""
    try:
        fecha = datetime.fromisoformat(str(fecha_iso or ""))
    except ValueError:
        return ""
    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=ZONA_HORARIA_COLOMBIA)
    fecha = fecha.astimezone(ZONA_HORARIA_COLOMBIA)
    return fecha.strftime("%d %b %Y").lstrip("0")


def _ubicacion(item):
    hoja = str(item.get("hoja") or "").strip()
    fila = str(item.get("fila") or "").strip()
    partes = [p for p in (hoja, ("fila " + fila) if fila else "") if p]
    return " · ".join(partes)


def _motivo_html(item):
    """Causa en lenguaje humano; el codigo queda chiquito abajo."""
    motivo = str(item.get("motivo") or "").strip()
    codigo = str(item.get("codigo") or "").strip()

    if not motivo and not codigo:
        return '<span class="motivo-vacio">Sin detalle registrado</span>'

    html_salida = _e(motivo or codigo)
    if motivo and codigo and codigo != motivo:
        html_salida += '<small class="motivo-codigo">' + _e(codigo) + "</small>"
    return html_salida


def _verificacion_html(item):
    """Constancia de la ultima verificacion en PRIZMA, si hay."""
    verificacion = str(item.get("verificacion") or "").strip()
    if not verificacion:
        return ""

    fecha = _fecha_corta(item.get("verificado_en"))
    if verificacion == "existe":
        texto = "aparece en PRIZMA"
        clase = " ok"
    elif verificacion == "no_esta":
        texto = "no aparece en PRIZMA"
        clase = ""
    else:
        texto = "sin confirmar"
        clase = ""

    detalle = str(item.get("verificacion_detalle") or "").strip()
    return (
        '<small class="verificado' + clase + '">· verificado'
        + (" " + fecha if fecha else "")
        + ": " + texto + "</small>"
        + ('<small class="verificacion-detalle">' + _e(detalle) + "</small>" if detalle else "")
    )


def _fila_faltante(item, id_curso):
    clave = _clave_actividad(item.get("hoja"), item.get("fila"))
    boton = (
        '<button type="button" class="boton chico" data-reintento'
        ' data-curso="' + _e(id_curso) + '"'
        ' data-clave="' + _e(clave) + '"'
        ' data-nombre="' + _e(item.get("nombre")) + '">'
        + icon("subir") + "Reintentar</button>"
    )
    return (
        "<tr>"
        '<td class="celda-fuerte">' + _e(item.get("nombre")) + "</td>"
        '<td class="col-estrecha">' + _e(_ubicacion(item)) + "</td>"
        '<td class="col-motivo">' + _motivo_html(item) + _verificacion_html(item) + "</td>"
        '<td class="col-accion">' + boton + "</td>"
        "</tr>"
    )


def _fila_subida(item):
    fecha = _fecha_corta(item.get("ok_en"))
    texto = "Subida" + (" el " + fecha if fecha else "")
    ultimo_error = str(item.get("motivo") or "").strip()
    extra = ""
    if item.get("estado") == "error" and ultimo_error:
        extra = ' <small class="intento-fallido">· último intento falló: ' + _e(ultimo_error) + "</small>"
    return (
        "<li><span>" + _e(item.get("nombre")) + "</span>"
        '<small class="estado-subida">' + _e(texto) + extra + "</small></li>"
    )


def _tarjeta_curso(resumen):
    total = int(resumen.get("total") or 0)
    subidas = int(resumen.get("subidas") or 0)
    faltantes = int(resumen.get("faltantes") or 0)
    pct = int(round(100 * subidas / total)) if total else 100
    actualizado = _fecha_corta(resumen.get("actualizado"))
    id_curso = resumen.get("id") or _clave_curso(resumen.get("curso"), resumen.get("programa"), _usuario_actual())

    if faltantes:
        cuerpo_faltantes = (
            '<div class="tabla-scroll"><table class="tabla">'
            "<thead><tr><th>Actividad</th><th>Ubicación</th><th>Por qué falta</th>"
            '<th class="col-accion">Acción</th></tr></thead>'
            "<tbody>"
            + "".join(_fila_faltante(i, id_curso) for i in resumen.get("detalle_faltantes") or [])
            + "</tbody></table></div>"
        )
        boton = (
            '<a class="boton" href="/">' + icon("play")
            + "Reintentar las " + str(faltantes) + " pendientes</a>"
        )
        clase_estado = "con-faltantes"
        resumen_estado = str(faltantes) + " pendiente" + ("s" if faltantes != 1 else "")
    else:
        cuerpo_faltantes = (
            '<p class="curso-completo">' + icon("check-circulo")
            + " Todas las actividades de este curso ya quedaron en PRIZMA.</p>"
        )
        boton = ""
        clase_estado = "completo"
        resumen_estado = "Curso completo"

    detalle_subidas = resumen.get("detalle_subidas") or []
    subidas_html = ""
    if detalle_subidas:
        subidas_html = (
            "<details class=\"subidas-detalle\"><summary>Ver las " + str(subidas)
            + " ya subidas</summary><ul>"
            + "".join(_fila_subida(i) for i in detalle_subidas)
            + "</ul></details>"
        )

    verificar = (
        '<button type="button" class="boton secundario" data-verificar'
        ' data-curso="' + _e(id_curso) + '"'
        ' data-nombre="' + _e(resumen.get("curso")) + '">'
        + icon("buscar") + "Verificar en PRIZMA</button>"
    )

    return (
        '<section class="panel curso-estado ' + clase_estado + '">'
        '<div class="curso-estado-cabecera">'
        '<span class="icono-tile grande">' + icon("libro") + "</span>"
        '<div class="curso-estado-titulo">'
        "<h2>" + _e(resumen.get("curso")) + "</h2>"
        "<p>" + _e(resumen.get("programa"))
        + (" · actualizado " + actualizado if actualizado else "")
        + "</p></div>"
        '<div class="curso-estado-progreso">'
        "<strong>" + str(subidas) + " de " + str(total) + "</strong>"
        "<span>" + _e(resumen_estado) + "</span>"
        "</div></div>"
        '<div class="barra-progreso"><span style="width:' + str(pct) + '%"></span></div>'
        + cuerpo_faltantes
        + subidas_html
        + '<div class="curso-estado-acciones">' + boton + verificar + "</div>"
        + "</section>"
    )


def _pagina_cursos(resumenes, pendientes):
    cabecera = (
        '<header class="encabezado"><div class="encabezado-titulo">'
        '<span class="icono-tile grande">' + icon("libro") + "</span>"
        "<div><h1>Cursos</h1><p>Qué actividades de cada curso ya están en PRIZMA y cuáles faltan.</p></div>"
        "</div></header>"
    )

    if not resumenes:
        return (
            '<div class="cursos-page">' + cabecera
            + '<section class="panel estado-vacio"><span class="icono-tile cursos-vacio-icon">'
            + icon("info") + '</span><div class="estado-vacio-contenido">'
            + '<span class="cursos-eyebrow">ESTADO DEL HISTORIAL</span>'
            + '<h2>Todavía no hay cargues registrados</h2>'
            + '<p>Cuando realices un cargue, aquí verás el avance de cada curso, las actividades completadas y lo que queda pendiente.</p>'
            + '<a class="boton" href="/">Ir a Inicio</a></div></section></div>'
        )

    banner = ""
    if pendientes:
        banner = (
            '<div class="aviso info" role="status">' + icon("info")
            + "<div><strong>Hay " + str(pendientes) + " actividad(es) pendientes</strong>"
            "<p>En la tabla de cada curso, <b>Reintentar</b> sube el recurso de una "
            "actividad por separado (elige el archivo y listo). En <a href=\"/\">Inicio</a> "
            "también puedes volver a subir la matriz y el ZIP para reintentar todas juntas.</p></div></div>"
        )

    tarjetas = "".join(_tarjeta_curso(r) for r in resumenes)

    return '<div class="cursos-page">' + cabecera + banner + _formularios_manuales() + '<div class="lista-cursos">' + tarjetas + "</div></div>"


def _formularios_manuales():
    """Formularios compartidos de reintento y verificacion (los abre cada boton)."""
    return (
        '<form id="form-reintento" class="panel form-manual" hidden method="post" '
        'action="/cursos/reintentar" enctype="multipart/form-data">'
        "<h3>Reintentar: <span id=\"reintento-nombre\"></span></h3>"
        '<p class="form-pista">Adjunta el recurso de esa actividad: se sube solo a '
        'esa, sin tocar las demás.</p>'
        '<input type="hidden" name="id_curso" id="reintento-curso">'
        '<input type="hidden" name="clave" id="reintento-clave">'
        '<div class="form-fila">'
        "<label>Recurso (archivo de la actividad)"
        '<input type="file" name="recurso" required></label>'
        "<label>Usuario PRIZMA"
        '<input type="text" name="usuario_prizma" autocomplete="username" required></label>'
        "<label>Contraseña PRIZMA"
        '<input type="password" name="contrasena_prizma" autocomplete="current-password" required></label>'
        "</div>"
        '<div class="form-acciones">'
        '<button type="submit" class="boton">' + icon("subir")
        + "Subir el recurso a esta actividad</button>"
        '<button type="button" class="boton neutro" data-cerrar-form="form-reintento">Cancelar</button>'
        "</div></form>"
        '<form id="form-verificacion" class="panel form-manual" hidden method="post" '
        'action="/cursos/verificar">'
        "<h3>Verificar en PRIZMA: <span id=\"verificar-nombre\"></span></h3>"
        '<p class="form-pista">Solo lectura: se recorre PRIZMA para confirmar qué '
        "actividades del curso aparecen ahí. No se cambia nada.</p>"
        '<input type="hidden" name="id_curso" id="verificacion-curso">'
        '<div class="form-fila">'
        "<label>Usuario PRIZMA"
        '<input type="text" name="usuario_prizma" autocomplete="username" required></label>'
        "<label>Contraseña PRIZMA"
        '<input type="password" name="contrasena_prizma" autocomplete="current-password" required></label>'
        "</div>"
        '<div class="form-acciones">'
        '<button type="submit" class="boton">' + icon("buscar")
        + "Revisar si todo está en PRIZMA</button>"
        '<button type="button" class="boton neutro" data-cerrar-form="form-verificacion">Cancelar</button>'
        "</div></form>"
    )


_CSS_CURSOS = r"""
.cursos-page { display: grid; gap: 22px; color: var(--texto); }
.cursos-page .aviso { background: var(--panel); color: var(--texto); border-color: var(--borde); }
.lista-cursos { display: grid; gap: 18px; }
.curso-estado-cabecera { display: flex; gap: 16px; align-items: center; }
.curso-estado-titulo { min-width: 0; flex: 1; }
.curso-estado-titulo h2 { margin: 0 0 4px; font-size: 18px; font-weight: 800; }
.curso-estado-titulo p { margin: 0; color: var(--muted); font-size: 13px; }
.curso-estado-progreso { text-align: right; }
.curso-estado-progreso strong { display: block; font-size: 20px; }
.curso-estado-progreso span { font-size: 12px; color: var(--muted); }
.barra-progreso { height: 8px; border-radius: 6px; background: var(--panel-2); margin: 14px 0 6px; overflow: hidden; }
.barra-progreso span { display: block; height: 100%; background: var(--verde); border-radius: 6px; }
.curso-estado.con-faltantes .barra-progreso span { background: var(--ambar); }
.curso-estado .tabla { margin-top: 12px; }
.curso-estado .col-motivo { overflow-wrap: anywhere; min-width: 220px; }
.motivo-codigo { display: block; color: var(--muted); font-size: 11px; font-family: monospace; margin-top: 4px; }
.motivo-vacio { color: var(--muted); font-style: italic; }
.curso-completo { display: flex; align-items: center; gap: 8px; color: var(--verde); font-weight: 600; margin: 12px 0 0; }
.curso-estado-acciones { margin-top: 16px; display: flex; justify-content: flex-end; }
.subidas-detalle { margin-top: 14px; font-size: 13px; }
.subidas-detalle summary { cursor: pointer; color: var(--muted); }
.subidas-detalle ul { list-style: none; padding: 0; margin: 10px 0 0; display: grid; gap: 6px; }
.subidas-detalle li { display: flex; justify-content: space-between; gap: 12px; padding: 6px 0; border-bottom: 1px solid var(--borde); }
.subidas-detalle li span { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.estado-subida { color: var(--verde); white-space: nowrap; }
.intento-fallido { color: var(--muted); font-weight: 400; }
.estado-vacio { width: min(100%,900px); margin: 2px auto 0; padding: clamp(24px,4vw,40px); display: grid; grid-template-columns: 60px minmax(0,1fr); gap: 20px; align-items: start; border: 1px solid var(--borde); border-radius: 18px; background: var(--panel); }
.estado-vacio .cursos-vacio-icon { width: 60px; height: 60px; border-radius: 16px; display: grid; place-items: center; }
.estado-vacio-contenido { min-width: 0; }
.cursos-eyebrow { display: block; margin: 0 0 8px; color: var(--muted); font-size: 11px; font-weight: 800; letter-spacing: .09em; }
.estado-vacio h2 { margin: 0 0 8px; font-size: clamp(20px,2.5vw,25px); line-height: 1.25; font-weight: 800; }
.estado-vacio p { max-width: 620px; margin: 0 0 20px; color: var(--muted); line-height: 1.6; }
.estado-vacio .boton { justify-self: start; min-height: 44px; padding: 10px 18px; border-radius: 11px; }
.col-accion { width: 140px; }
.verificado { display: block; color: var(--muted); font-size: 12px; margin-top: 4px; }
.verificado.ok { color: var(--verde); }
.verificacion-detalle { display: block; color: var(--muted); font-size: 11px; margin-top: 3px; white-space: normal; }
.curso-estado-acciones { margin-top: 16px; display: flex; justify-content: flex-end; gap: 10px; flex-wrap: wrap; }

/* Formularios de reintento y verificacion (abiertos por boton) */
.form-manual { padding: 22px 24px; display: grid; gap: 14px; margin-bottom: 18px; }
.form-manual[hidden] { display: none; }
.form-manual h3 { margin: 0; font-size: 16px; font-weight: 800; }
.form-manual .form-pista { margin: 0; color: var(--muted); font-size: 13px; }
.form-manual .form-fila { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 14px; }
.form-manual label { display: grid; gap: 6px; font-size: 13px; font-weight: 700; color: var(--texto-2); }
.form-manual input[type="text"],
.form-manual input[type="password"] {
  padding: 11px 13px; border: 1px solid var(--borde-2); border-radius: 12px;
  background: var(--panel); color: var(--texto); font-size: 15px;
}
.form-manual input[type="text"]:focus,
.form-manual input[type="password"]:focus {
  outline: none; border-color: var(--acento); box-shadow: 0 0 0 4px var(--foco);
}
.form-manual input[type="file"] { font-size: 14px; color: var(--muted); }
.form-manual .form-acciones { display: flex; gap: 10px; flex-wrap: wrap; }
@media(max-width:600px) { .estado-vacio { grid-template-columns: 1fr; gap: 14px; } .estado-vacio .cursos-vacio-icon { width: 48px; height: 48px; } .curso-estado-cabecera { align-items: flex-start; flex-wrap: wrap; } .curso-estado-progreso { margin-left: auto; } }
"""

_JS_CURSOS = r"""
document.querySelectorAll("[data-reintento]").forEach(function (boton) {
    boton.addEventListener("click", function () {
        document.getElementById("reintento-curso").value = boton.dataset.curso || "";
        document.getElementById("reintento-clave").value = boton.dataset.clave || "";
        document.getElementById("reintento-nombre").textContent = boton.dataset.nombre || "";
        var form = document.getElementById("form-reintento");
        form.hidden = false;
        form.scrollIntoView({ behavior: "smooth", block: "center" });
    });
});

document.querySelectorAll("[data-verificar]").forEach(function (boton) {
    boton.addEventListener("click", function () {
        document.getElementById("verificacion-curso").value = boton.dataset.curso || "";
        document.getElementById("verificar-nombre").textContent = boton.dataset.nombre || "";
        var form = document.getElementById("form-verificacion");
        form.hidden = false;
        form.scrollIntoView({ behavior: "smooth", block: "center" });
    });
});

document.querySelectorAll("[data-cerrar-form]").forEach(function (boton) {
    boton.addEventListener("click", function () {
        var form = document.getElementById(boton.dataset.cerrarForm);
        if (form) form.hidden = true;
    });
});
"""


@app.get("/cursos", response_class=HTMLResponse)
def cursos_estado():
    resumenes = resumen_cursos(_usuario_actual())
    pendientes = total_faltantes(_usuario_actual())
    return HTMLResponse(
        render_page(
            "Cursos",
            _pagina_cursos(resumenes, pendientes),
            active="cursos",
            page_css=_CSS_CURSOS,
            page_js=_JS_CURSOS,
        )
    )


# ============================================================
# REINTENTO INDIVIDUAL: UNA ACTIVIDAD, UN RECURSO ELEGIDO A MANO
# ============================================================

def _pagina_error(titulo, mensaje, volver="/cursos"):
    cuerpo = (
        '<div class="cursos-page"><section class="panel estado-vacio">'
        + '<span class="icono-tile cursos-vacio-icon">' + icon("alerta") + '</span>'
        + '<div class="estado-vacio-contenido"><h2>' + _e(titulo) + '</h2><p>' + _e(mensaje) + '</p>'
        + '<a class="boton" href="' + volver + '">Volver a Cursos</a></div></section></div>'
    )
    return HTMLResponse(
        render_page(titulo, cuerpo, active="cursos", page_css=_CSS_CURSOS)
    )


def _ruta_reporte_manual(trabajo_id, curso, programa):
    nombre = _nombre_reporte(
        [{"curso": curso or "", "programa": programa or ""}],
        trabajo_id,
    )
    return os.path.join(RESULTADOS_DIR, nombre)


def _pagina_manual(trabajo, titulo, lista_titulo):
    """Pagina de progreso del trabajo manual, con su id ya inyectado."""
    pagina = _pagina_progreso(
        titulo=titulo,
        lista_titulo=lista_titulo,
        active="cursos",
    ).replace("__TRABAJO_ID__", str(trabajo["id"]))
    trabajo["pagina_progreso"] = pagina
    return HTMLResponse(pagina)


def _ejecutar_reintento(
    trabajo_id,
    actividad,
    ruta_archivo,
    carpeta_temp,
    usuario_prizma,
    contrasena_prizma,
    indice_recursos=None,
):
    """Hilo: sube el recurso elegido a mano y deja el resultado en el trabajo."""
    trabajo = TRABAJOS.get(trabajo_id)
    testigo = None
    try:
        if trabajo is None:
            return

        testigo = USUARIO_ACTUAL.set(str(trabajo.get("usuario_app") or ""))

        args = (
            usuario_prizma, contrasena_prizma, actividad,
            ruta_archivo, carpeta_temp, trabajo,
        )
        if indice_recursos is None:
            resultado = motor_prizma.subir_actividad_manual(*args) or {}
        else:
            resultado = motor_prizma.subir_actividad_manual(
                *args, indice_recursos=indice_recursos
            ) or {}

        error = str(resultado.get("error") or "")

        if not resultado.get("ok") and error == "ERROR_CANCELADO":
            motor_prizma.actualizar_estado(
                trabajo,
                etapa="cancelado",
                mensaje="Reintento cancelado por el usuario.",
                terminado=True,
            )
            return

        if resultado.get("ok"):
            motor_prizma.guardar_resultado(
                trabajo["ruta_reporte"],
                actividad,
                "OK",
                motor_prizma._observacion_guardado(resultado),
                resultado.get("recurso", ""),
            )
            mensaje_final = (
                "Listo: el recurso quedó en PRIZMA ("
                + str(actividad.get("nombre") or "") + ")."
            )
            etapa_final = "completado"
            exitosas, errores = 1, 0
        else:
            if not error:
                error = "ERROR_DESCONOCIDO"
            motor_prizma.guardar_resultado(
                trabajo["ruta_reporte"],
                actividad,
                "ERROR",
                error,
                resultado.get("recurso", ""),
            )
            mensaje_final = (
                "No se pudo subir el recurso: " + mensaje_error(error)
            )
            etapa_final = "error"
            exitosas, errores = 0, 1

        trabajo["detalle_actividades"] = [
            {
                "numero": 1,
                "nombre": str(actividad.get("nombre") or ""),
                "estado": "ok" if exitosas else "error",
                "error": "" if exitosas else mensaje_error(error),
            }
        ]
        motor_prizma.actualizar_estado(
            trabajo,
            etapa=etapa_final,
            mensaje=mensaje_final,
            procesadas=1,
            exitosas=exitosas,
            errores=errores,
            terminado=True,
        )
    except Exception as exc:
        traceback.print_exc()
        try:
            motor_prizma.actualizar_estado(
                trabajo,
                etapa="error",
                mensaje="No se pudo completar el reintento: " + str(exc)[:200],
                procesadas=1,
                errores=1,
                terminado=True,
            )
        except Exception:
            pass
    finally:
        if testigo is not None:
            USUARIO_ACTUAL.reset(testigo)
        shutil.rmtree(carpeta_temp, ignore_errors=True)
        _BLOQUE_MANUAL.release()


@app.post("/cursos/reintentar", response_class=HTMLResponse)
def reintentar_actividad(
    # Defaults en "" (no Form(...)): un campo vacio llega como ausente y se
    # prefiere el aviso humano de abajo antes que un 422 en JSON.
    id_curso: str = Form(""),
    clave: str = Form(""),
    usuario_prizma: str = Form(""),
    contrasena_prizma: str = Form(""),
    registro_id: str = Form(""),
    recurso: UploadFile = File(None),
):
    usuario_prizma = str(usuario_prizma or "").strip()
    contrasena_prizma = str(contrasena_prizma or "")

    if not usuario_prizma or not contrasena_prizma:
        return _pagina_error(
            "Falta el acceso a PRIZMA",
            "Escribe el usuario y la contraseña de PRIZMA para poder reintentar.",
        )

    try:
        contenido = recurso.file.read() if recurso is not None else b""
    except Exception:
        contenido = b""
    indice_recursos = None
    if not contenido and registro_id:
        registro = find_user_record(str(registro_id).strip())
        ruta_zip = os.path.join(UPLOADS_DIR, str(registro_id).strip(), "recursos.zip")
        if registro and os.path.isfile(ruta_zip):
            try:
                indice_recursos = motor_prizma.crear_indice_recursos(ruta_zip)
            except Exception:
                indice_recursos = None
        if indice_recursos is None:
            return _pagina_error(
                "No está disponible el ZIP original",
                "Adjunta el archivo del recurso para reintentar esta actividad.",
                volver="/reportes",
            )
    elif not contenido:
        return _pagina_error(
            "Falta el recurso",
            "Elige el archivo del recurso. Para reintentar desde el ZIP original, abre el reporte del cargue.",
        )

    actividad, error = actividad_para_reintento(
        str(id_curso or "").strip(),
        str(clave or ""),
        _usuario_actual(),
    )
    if error:
        return _pagina_error("No se pudo preparar el reintento", error)

    if not _BLOQUE_MANUAL.acquire(blocking=False):
        return _pagina_error(
            "Ya hay un proceso en curso",
            "Espera a que termine el reintento o la verificación que está "
            "corriendo antes de empezar otro.",
        )

    try:
        trabajo_id = crear_trabajo_manual(
            "reintento",
            "Reintento: " + str(actividad.get("nombre") or ""),
            _usuario_actual(),
            cursos=[
                {
                    "curso": str(actividad.get("curso") or ""),
                    "programa": str(actividad.get("programa") or ""),
                }
            ],
        )
        trabajo = TRABAJOS[trabajo_id]
        trabajo["ruta_reporte"] = _ruta_reporte_manual(
            trabajo_id,
            str(actividad.get("curso") or ""),
            str(actividad.get("programa") or ""),
        )

        carpeta_temp = os.path.join(TEMP_DIR, trabajo_id)
        os.makedirs(carpeta_temp, exist_ok=True)
        ruta_archivo = None
        if contenido:
            nombre_archivo = (
                os.path.basename(str(recurso.filename or "")).strip() or "recurso"
            )
            ruta_archivo = os.path.join(carpeta_temp, nombre_archivo)
            with open(ruta_archivo, "wb") as fh:
                fh.write(contenido)

        pagina = _pagina_manual(
            trabajo,
            titulo="Reintento en progreso",
            lista_titulo="Actividad a reintentar",
        )

        _lanzar_hilo(
            _ejecutar_reintento,
            (
                trabajo_id,
                actividad,
                ruta_archivo,
                carpeta_temp,
                usuario_prizma,
                contrasena_prizma,
                indice_recursos,
            ),
        )

        return pagina
    except Exception:
        _BLOQUE_MANUAL.release()
        traceback.print_exc()
        return _pagina_error(
            "No se pudo preparar el reintento",
            "Ocurrió un error inesperado al montar el reintento; revisa el log.",
        )


# ============================================================
# VERIFICACION DEL CURSO EN PRIZMA (SOLO LECTURA)
# ============================================================

def _escribir_reporte_verificacion(ruta, resultados, sin_datos):
    """CSV con lo que encontro la verificacion (columnas propias: no es un cargue)."""
    with open(ruta, "w", newline="", encoding="utf-8-sig") as fh:
        escritor = csv.writer(fh)
        escritor.writerow(["Actividad", "Verificación", "Detalle"])
        for entrada in resultados:
            verificacion = str(entrada.get("verificacion") or "")
            if verificacion == "existe":
                etiqueta = "Aparece en PRIZMA"
            elif verificacion == "no_esta":
                etiqueta = "No aparece en PRIZMA"
            else:
                etiqueta = "No se pudo verificar"
            escritor.writerow(
                [
                    str(entrada.get("nombre") or ""),
                    etiqueta,
                    str(entrada.get("detalle") or ""),
                ]
            )
        for dato in sin_datos:
            escritor.writerow(
                [
                    str(dato.get("nombre") or ""),
                    "Sin datos",
                    str(dato.get("motivo") or ""),
                ]
            )


def _ejecutar_verificacion(
    trabajo_id,
    id_curso,
    actividades,
    sin_datos,
    usuario_prizma,
    contrasena_prizma,
):
    """Hilo: verifica el curso contra PRIZMA y aplica el resultado al estado."""
    trabajo = TRABAJOS.get(trabajo_id)
    sin_datos = sin_datos or []
    testigo = None
    try:
        if trabajo is None:
            return

        testigo = USUARIO_ACTUAL.set(str(trabajo.get("usuario_app") or ""))

        resultado = motor_prizma.verificar_actividades_prizma(
            usuario_prizma,
            contrasena_prizma,
            actividades,
            trabajo,
        ) or {}

        error = str(resultado.get("error") or "")
        if not resultado.get("ok"):
            if error == "ERROR_CANCELADO":
                mensaje = "Verificación cancelada por el usuario."
                etapa = "cancelado"
            else:
                mensaje = "No se pudo verificar: " + mensaje_error(error)
                etapa = "error"
            motor_prizma.actualizar_estado(
                trabajo,
                etapa=etapa,
                mensaje=mensaje,
                terminado=True,
            )
            return

        resultados = resultado.get("resultados") or []
        marcar_verificacion(
            id_curso,
            resultados,
            usuario_app=str(trabajo.get("usuario_app") or ""),
        )

        _escribir_reporte_verificacion(
            trabajo["ruta_reporte"],
            resultados,
            sin_datos,
        )

        filas = []
        for numero, entrada in enumerate(resultados, start=1):
            es_existe = str(entrada.get("verificacion")) == "existe"
            filas.append(
                {
                    "numero": numero,
                    "nombre": str(entrada.get("nombre") or ""),
                    "estado": "ok" if es_existe else "error",
                    "error": "" if es_existe else str(entrada.get("detalle") or ""),
                }
            )

        for dato in sin_datos:
            filas.append(
                {
                    "numero": len(filas) + 1,
                    "nombre": str(dato.get("nombre") or ""),
                    "estado": "error",
                    "error": str(dato.get("motivo") or "Sin datos registrados."),
                }
            )

        total = len(resultados)
        aparecen = sum(
            1 for e in resultados
            if str(e.get("verificacion")) == "existe"
        )
        no_aparecen = sum(
            1 for e in resultados
            if str(e.get("verificacion")) == "no_esta"
        )
        dudas = total - aparecen - no_aparecen

        mensaje = (
            "Verificación terminada: " + str(aparecen) + " de " + str(total)
            + " actividades aparecen en PRIZMA."
        )
        if no_aparecen:
            mensaje += " " + str(no_aparecen) + " no aparecen."
        if dudas:
            mensaje += " " + str(dudas) + " no se pudieron verificar."
        if sin_datos:
            mensaje += " " + str(len(sin_datos)) + " sin datos registrados."

        trabajo["detalle_actividades"] = filas
        motor_prizma.actualizar_estado(
            trabajo,
            etapa="completado",
            mensaje=mensaje,
            procesadas=total,
            exitosas=aparecen,
            errores=no_aparecen + dudas + len(sin_datos),
            terminado=True,
        )
    except Exception as exc:
        traceback.print_exc()
        try:
            motor_prizma.actualizar_estado(
                trabajo,
                etapa="error",
                mensaje="No se pudo verificar el curso: " + str(exc)[:200],
                terminado=True,
            )
        except Exception:
            pass
    finally:
        if testigo is not None:
            USUARIO_ACTUAL.reset(testigo)
        _BLOQUE_MANUAL.release()


@app.post("/cursos/verificar", response_class=HTMLResponse)
def verificar_curso(
    id_curso: str = Form(""),
    usuario_prizma: str = Form(""),
    contrasena_prizma: str = Form(""),
):
    usuario_prizma = str(usuario_prizma or "").strip()
    contrasena_prizma = str(contrasena_prizma or "")

    if not usuario_prizma or not contrasena_prizma:
        return _pagina_error(
            "Falta el acceso a PRIZMA",
            "Escribe el usuario y la contraseña de PRIZMA para poder verificar.",
        )

    id_curso = str(id_curso or "").strip()
    actividades, sin_datos, error = actividades_para_verificar(
        id_curso,
        _usuario_actual(),
    )
    if error:
        return _pagina_error("No se pudo preparar la verificación", error)

    if not actividades:
        return _pagina_error(
            "Sin datos para verificar",
            "Ninguna actividad del curso tiene los datos necesarios. Sube la "
            "matriz otra vez en Inicio para regenerarlos.",
        )

    if not _BLOQUE_MANUAL.acquire(blocking=False):
        return _pagina_error(
            "Ya hay un proceso en curso",
            "Espera a que termine el reintento o la verificación que está "
            "corriendo antes de empezar otro.",
        )

    try:
        curso_nombre = str(actividades[0][1].get("curso") or "")
        programa_nombre = str(actividades[0][1].get("programa") or "")

        trabajo_id = crear_trabajo_manual(
            "verificacion",
            "Verificar: " + curso_nombre,
            _usuario_actual(),
            cursos=[{"curso": curso_nombre, "programa": programa_nombre}],
        )
        trabajo = TRABAJOS[trabajo_id]
        trabajo["ruta_reporte"] = _ruta_reporte_manual(
            trabajo_id,
            curso_nombre,
            programa_nombre,
        )

        pagina = _pagina_manual(
            trabajo,
            titulo="Verificación en progreso",
            lista_titulo="Actividades del curso",
        )

        _lanzar_hilo(
            _ejecutar_verificacion,
            (
                trabajo_id,
                id_curso,
                actividades,
                sin_datos,
                usuario_prizma,
                contrasena_prizma,
            ),
        )

        return pagina
    except Exception:
        _BLOQUE_MANUAL.release()
        traceback.print_exc()
        return _pagina_error(
            "No se pudo preparar la verificación",
            "Ocurrió un error inesperado al montar la verificación; revisa el log.",
        )
