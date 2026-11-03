"""Historial de cargues, reportes guardados y descarga de reportes.
"""

from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    FileResponse,
)
from auto_prizma.automation.prizma.engine import normalizar_texto
import os
import html
from datetime import datetime

from auto_prizma.core.application import app
from auto_prizma.core.config import ZONA_HORARIA_COLOMBIA
from auto_prizma.services.auth import (
    _es_de,
    _usuario_actual,
)
from auto_prizma.services.course_state import _clave_actividad, _clave_curso
from auto_prizma.services.history import (
    _historial_del_usuario,
    _leer_reporte_csv,
    find_user_record,
    saved_report_path,
)
from auto_prizma.services.upload_jobs import TRABAJOS
from auto_prizma.web.icons import icon
from auto_prizma.web.layout import render_page


# ============================================================
# FECHAS
# ============================================================

_MESES = ("ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic")


def _fecha_local(fecha_iso):
    """La fecha del historial en hora de Colombia, o None si no se puede leer."""
    try:
        fecha = datetime.fromisoformat(str(fecha_iso or ""))
    except ValueError:
        return None
    if fecha.tzinfo is None:
        fecha = fecha.replace(tzinfo=ZONA_HORARIA_COLOMBIA)
    return fecha.astimezone(ZONA_HORARIA_COLOMBIA)


_FECHA_DESCONOCIDA = datetime(1970, 1, 1, tzinfo=ZONA_HORARIA_COLOMBIA)


def _mas_recientes_primero(registros):
    """Registros del historial ordenados por fecha, del mas reciente al mas antiguo."""
    return sorted(
        registros,
        key=lambda registro: _fecha_local(registro.get("fecha_iso")) or _FECHA_DESCONOCIDA,
        reverse=True,
    )


def _fecha_corta(fecha):
    """23 sep 2026"""
    return f"{fecha.day} {_MESES[fecha.month - 1]} {fecha.year}" if fecha else "—"


def _formatear_fecha_hora(fecha_iso):
    fecha = _fecha_local(fecha_iso)
    if fecha is None:
        return "—", "—"

    fecha_texto = fecha.strftime("%d/%m/%Y")
    hora = fecha.strftime("%I:%M").lstrip("0") or "0:00"
    sufijo = "a. m." if fecha.hour < 12 else "p. m."
    return fecha_texto, f"{hora} {sufijo}"


# ============================================================
# PIEZAS COMUNES DE LAS TABLAS
# ============================================================

def _e(valor):
    return html.escape(str(valor or ""), quote=True)


def _cursos(registro):
    return registro.get("cursos") or [{"curso": "Curso sin nombre", "programa": "Programa sin nombre"}]


def _texto(item, clave, por_defecto):
    return str(item.get(clave) or por_defecto)


def _encabezado(nombre_icono, titulo, subtitulo, derecha):
    return (
        '<header class="encabezado"><div class="encabezado-titulo">'
        '<span class="icono-tile grande">' + icon(nombre_icono) + "</span>"
        "<div><h1>" + html.escape(titulo) + "</h1><p>" + html.escape(subtitulo) + "</p></div></div>"
        + derecha + "</header>"
    )


def _selector(id_tabla, nombre_icono, tipo, etiqueta, opciones, campo=""):
    return (
        '<label class="campo">' + icon(nombre_icono)
        + '<select data-control-tabla="' + id_tabla + '" data-tipo="' + tipo + '"'
        + (' data-campo="' + campo + '"' if campo else "")
        + ' aria-label="' + _e(etiqueta) + '">' + opciones + "</select>"
        + icon("chevron", "icono icono-chevron") + "</label>"
    )


def _opciones(texto_todos, valores):
    return '<option value="">' + html.escape(texto_todos) + "</option>" + "".join(
        '<option value="' + _e(valor) + '">' + html.escape(valor) + "</option>"
        for valor in sorted(valores, key=str.casefold)
    )


_OPCIONES_FECHA = (
    '<option value="">Todas las fechas</option>'
    '<option value="hoy">Hoy</option>'
    '<option value="7">Últimos 7 días</option>'
    '<option value="30">Últimos 30 días</option>'
    '<option value="90">Últimos 90 días</option>'
)


def _encabezado_orden(texto, tipo="texto", inicial=""):
    return (
        '<th data-orden="' + tipo + '"' + (' data-orden-inicial="' + inicial + '"' if inicial else "")
        + '><button type="button" class="orden">' + html.escape(texto) + icon("ordenar") + "</button></th>"
    )


def _pie_tabla(total, unidad, por_pagina=10, tamanos=True):
    if total:
        resumen = f"Mostrando 1 – {min(por_pagina, total)} de {total} {unidad}"
    else:
        resumen = "Sin " + unidad + " todavía"
    selector = ""
    if tamanos:
        selector = (
            '<label><span class="sr-only">Filas por página</span><select data-tabla-tamano>'
            + "".join(
                f'<option value="{n}"{" selected" if n == por_pagina else ""}>{n} por página</option>'
                for n in (10, 25, 50)
            )
            + "</select></label>"
        )
    return (
        '<div class="tabla-pie"><span data-tabla-resumen>' + resumen + "</span>"
        '<div class="tabla-pie-derecha">' + selector
        + '<nav class="paginas" data-tabla-paginas aria-label="Páginas"></nav></div></div>'
    )


def _menu_acciones(etiqueta, items):
    return (
        '<div class="menu-acciones" data-menu>'
        '<button type="button" class="boton-icono" data-menu-boton aria-haspopup="menu" '
        'aria-expanded="false" aria-label="' + _e(etiqueta) + '">' + icon("mas") + "</button>"
        '<div class="menu-desplegable flotante" role="menu" data-menu-lista hidden>' + items + "</div></div>"
    )


# ============================================================
# HISTORIAL Y REPORTES
# ============================================================

def _nombre_visible_reporte(cursos):
    """Nombre del reporte para la tabla: "Curso - Programa"."""
    principal = cursos[0]
    nombre = _texto(principal, "curso", "Curso sin nombre") + " - " + _texto(principal, "programa", "Programa sin nombre")
    if len(cursos) > 1:
        nombre += f" (y {len(cursos) - 1} curso(s) más)"
    return nombre


def _pagina_reportes(registros):
    filas = []
    programas = set()
    cursos_vistos = set()
    ultima = None

    for registro in registros:
        fecha = _fecha_local(registro.get("fecha_iso"))
        cursos = _cursos(registro)
        principal = cursos[0]
        curso = _texto(principal, "curso", "Curso sin nombre")
        programa = _texto(principal, "programa", "Programa sin nombre")
        programas_registro = [_texto(item, "programa", "Programa sin nombre") for item in cursos]
        cursos_registro = [_texto(item, "curso", "Curso sin nombre") for item in cursos]
        programas.update(programas_registro)
        cursos_vistos.update(cursos_registro)
        if fecha and (ultima is None or fecha > ultima):
            ultima = fecha

        nombre = _nombre_visible_reporte(cursos)
        archivo = str(registro.get("archivo_reporte") or "reporte.csv")
        registro_id = _e(registro.get("id"))
        url = "/reporte-guardado/" + registro_id
        fecha_iso = fecha.isoformat() if fecha else ""
        curso_celda = html.escape(curso) + (
            f' <span class="chip">+{len(cursos) - 1}</span>' if len(cursos) > 1 else ""
        )
        busqueda = " ".join([nombre, archivo] + cursos_registro + programas_registro).lower()

        menu = _menu_acciones(
            "Más acciones para " + nombre,
            '<a role="menuitem" href="' + url + '">' + icon("ver") + "Ver reporte</a>"
            '<a role="menuitem" href="' + url + '?descargar=1">' + icon("descargar") + "Descargar CSV</a>"
            '<button type="button" role="menuitem" data-copiar="' + url + '" data-copiar-url '
            'data-copiado="Enlace copiado">' + icon("copiar") + "Copiar enlace</button>",
        )

        filas.append(
            '<tr data-fila data-busqueda="' + _e(busqueda) + '" data-programa="' + _e("|".join(programas_registro))
            + '" data-curso="' + _e("|".join(cursos_registro)) + '" data-fecha="' + fecha_iso + '">'
            '<td data-valor="' + _e(nombre.lower()) + '"><div class="celda-nombre" title="' + _e(archivo) + '">'
            '<span class="icono-tile chico">' + icon("documento") + "</span><div><strong>" + html.escape(nombre)
            + "</strong><small>" + (fecha.strftime("%Y-%m-%d · %H:%M:%S") if fecha else "—") + "</small></div></div></td>"
            '<td data-valor="' + _e(curso.lower()) + '">' + curso_celda + "</td>"
            '<td data-valor="' + _e(programa.lower()) + '"><span class="badge-programa">' + html.escape(programa) + "</span></td>"
            '<td class="celda-fecha" data-valor="' + fecha_iso + '"><strong>' + _fecha_corta(fecha) + "</strong><small>"
            + (fecha.strftime("%H:%M") if fecha else "") + "</small></td>"
            '<td class="celda-acciones">'
            '<a class="boton secundario chico" href="' + url + '">' + icon("ver") + "Ver</a>"
            '<a class="boton secundario chico" href="' + url + '?descargar=1">' + icon("descargar") + "CSV</a>"
            + menu + "</td></tr>"
        )

    total = len(registros)
    if not filas:
        filas.append('<tr class="fila-vacia"><td colspan="5">Todavía no hay reportes guardados.</td></tr>')

    plural = "" if total == 1 else "s"
    contenido = (
        _encabezado(
            "documento",
            "Reportes generados",
            "Todos los reportes se guardan automáticamente con el nombre del curso y el programa correspondiente.",
            '<span class="chip grande">' + icon("documento") + f"{total} reporte{plural}</span>",
        )
        + '<div class="panel herramientas">'
        '<label class="campo">' + icon("buscar") + '<span class="sr-only">Buscar</span>'
        '<input type="search" placeholder="Buscar reporte, curso o programa..." '
        'data-control-tabla="tabla-reportes" data-tipo="buscar"></label>'
        + _selector("tabla-reportes", "filtro", "filtro", "Programa", _opciones("Todos los programas", programas), "programa")
        + _selector("tabla-reportes", "birrete", "filtro", "Curso", _opciones("Todos los cursos", cursos_vistos), "curso")
        + _selector("tabla-reportes", "calendario", "fecha", "Fecha", _OPCIONES_FECHA)
        + "</div>"
        '<section class="mosaicos" aria-label="Resumen">'
        '<div class="mosaico"><span class="icono-tile">' + icon("documento") + f'</span><div><strong class="num">{total}</strong><span>Reportes generados</span></div></div>'
        '<div class="mosaico"><span class="icono-tile verde">' + icon("birrete") + f'</span><div><strong class="num">{len(programas)}</strong><span>Programas</span></div></div>'
        '<div class="mosaico"><span class="icono-tile azul">' + icon("libro") + f'</span><div><strong class="num">{len(cursos_vistos)}</strong><span>Cursos</span></div></div>'
        '<div class="mosaico"><span class="icono-tile morado">' + icon("calendario") + "</span><div><strong>"
        + _fecha_corta(ultima) + "</strong><span>Último reporte</span></div></div>"
        "</section>"
        '<section class="panel tabla-panel" id="tabla-reportes" data-tabla data-unidad="reportes" data-por-pagina="10">'
        '<div class="tabla-scroll"><table class="tabla"><thead><tr>'
        + _encabezado_orden("Nombre del reporte")
        + _encabezado_orden("Curso")
        + _encabezado_orden("Programa")
        + _encabezado_orden("Fecha de generación", "fecha", "desc")
        + "<th>Acción</th></tr></thead><tbody>" + "".join(filas) + "</tbody></table></div>"
        + _pie_tabla(total, "reportes")
        + "</section>"
    )
    return render_page("Reportes", contenido, active="reportes", page_css=_CSS_REGISTROS)


def _pagina_historial(registros):
    filas = []
    programas = set()

    for registro in registros:
        fecha = _fecha_local(registro.get("fecha_iso"))
        fecha_texto, hora = _formatear_fecha_hora(registro.get("fecha_iso"))
        registro_id = _e(registro.get("id"))
        fecha_iso = fecha.isoformat() if fecha else ""

        for item in _cursos(registro):
            curso = _texto(item, "curso", "Curso sin nombre")
            programa = _texto(item, "programa", "Programa sin nombre")
            programas.add(programa)
            filas.append(
                '<tr data-fila data-busqueda="' + _e(f"{curso} {programa}".lower()) + '" data-programa="'
                + _e(programa) + '" data-fecha="' + fecha_iso + '">'
                '<td class="celda-fecha" data-valor="' + fecha_iso + '"><div class="celda-nombre">'
                '<span class="icono-tile chico">' + icon("historial") + "</span><div><strong>"
                + html.escape(fecha_texto) + "</strong><small>" + html.escape(hora) + "</small></div></div></td>"
                '<td data-valor="' + _e(curso.lower()) + '" class="celda-fuerte">' + html.escape(curso) + "</td>"
                '<td data-valor="' + _e(programa.lower()) + '"><span class="badge-programa">' + html.escape(programa) + "</span></td>"
                '<td class="celda-acciones"><a class="boton secundario chico" href="/reporte-guardado/' + registro_id + '">'
                + icon("ver") + "Ver reporte</a></td></tr>"
            )

    total = len(filas)
    if not filas:
        filas.append('<tr class="fila-vacia"><td colspan="4">Todavía no hay cargues registrados.</td></tr>')

    plural = "" if total == 1 else "s"
    contenido = (
        _encabezado(
            "historial",
            "Historial de cargues",
            "Consulta los cursos procesados anteriormente y accede a su reporte correspondiente.",
            '<span class="chip grande">' + icon("historial") + f"{total} registro{plural}</span>",
        )
        + '<div class="panel herramientas dos">'
        '<label class="campo">' + icon("buscar") + '<span class="sr-only">Buscar</span>'
        '<input type="search" placeholder="Buscar curso o programa..." '
        'data-control-tabla="tabla-historial" data-tipo="buscar"></label>'
        + _selector("tabla-historial", "filtro", "filtro", "Programa", _opciones("Todos los programas", programas), "programa")
        + _selector("tabla-historial", "calendario", "fecha", "Fecha", _OPCIONES_FECHA)
        + "</div>"
        '<section class="panel tabla-panel" id="tabla-historial" data-tabla data-unidad="registros" data-por-pagina="10">'
        '<div class="tabla-scroll"><table class="tabla"><thead><tr>'
        + _encabezado_orden("Fecha y hora", "fecha", "desc")
        + _encabezado_orden("Curso")
        + _encabezado_orden("Programa")
        + "<th>Reporte</th></tr></thead><tbody>" + "".join(filas) + "</tbody></table></div>"
        + _pie_tabla(total, "registros")
        + "</section>"
    )
    return render_page("Historial", contenido, active="historial", page_css=_CSS_REGISTROS)


@app.get("/historial", response_class=HTMLResponse)
def historial_cargues():
    return HTMLResponse(_pagina_historial(_mas_recientes_primero(_historial_del_usuario())))


@app.get("/reportes", response_class=HTMLResponse)
def reportes_generados():
    return HTMLResponse(_pagina_reportes(_mas_recientes_primero(_historial_del_usuario())))


# ============================================================
# DETALLE DE UN REPORTE
# ============================================================

def _categoria_resultado(valor):
    """ok / omitido / cancelado / error segun el texto de la columna Resultado."""
    texto = normalizar_texto(valor)

    if "cargad" in texto or "exito" in texto or texto == "ok":
        return "ok"

    if "omitid" in texto or "ya exist" in texto or "duplicad" in texto:
        return "omitido"

    if "cancel" in texto:
        return "cancelado"

    return "error"


_ICONO_RESULTADO = {"ok": "check-circulo", "error": "alerta-circulo", "omitido": "info", "cancelado": "info"}

_MOSAICOS_RESULTADO = (
    # (categoria, icono, titulo, descripcion, siempre visible)
    ("error", "alerta", "Errores encontrados", "Registros con problemas en la carga", True),
    ("ok", "check", "Registros OK", "Cargados correctamente", True),
    ("omitido", "info", "Omitidos", "Ya existían o estaban duplicados", False),
    ("cancelado", "info", "Cancelados", "No se procesaron por la cancelación", False),
)


# Columnas cortas que no se parten y columnas de texto largo con ancho minimo.
_COLUMNAS_ESTRECHAS = {"fila excel", "categoria", "tipo", "resultado"}
_COLUMNAS_ANCHAS = {"actividad", "recurso", "curso"}


def _clase_columna(nombre):
    clave = normalizar_texto(nombre)
    if clave in _COLUMNAS_ESTRECHAS:
        return "col-estrecha"
    if clave in _COLUMNAS_ANCHAS:
        return "col-ancha"
    if clave == "observacion":
        return "col-observacion"
    return ""


def _indice_columna(cabeceras, nombre):
    for posicion, cabecera in enumerate(cabeceras):
        if normalizar_texto(cabecera) == normalizar_texto(nombre):
            return posicion
    return None


def _pagina_reporte_html(titulo, subtitulo, ruta_csv, url_descarga, registro_id=""):
    """Muestra el reporte como tabla dentro de la app."""
    try:
        cabeceras, filas = _leer_reporte_csv(ruta_csv)
    except OSError:
        cabeceras, filas = [], []

    indice_resultado = _indice_columna(cabeceras, "Resultado")
    indice_observacion = _indice_columna(cabeceras, "Observación")
    indice_fila = _indice_columna(cabeceras, "Fila Excel")
    indice_hoja = _indice_columna(cabeceras, "Hoja")
    indice_programa = _indice_columna(cabeceras, "Programa")
    indice_curso = _indice_columna(cabeceras, "Curso")

    clases = [_clase_columna(nombre) for nombre in cabeceras]
    conteo = {"ok": 0, "error": 0, "omitido": 0, "cancelado": 0}
    filas_html = []

    for fila in filas:
        celdas = []
        for posicion, valor in enumerate(fila):
            texto = str(valor or "")
            clase = clases[posicion] if posicion < len(clases) else ""
            if posicion == indice_resultado:
                categoria = _categoria_resultado(texto)
                conteo[categoria] += 1
                celdas.append(
                    '<td class="' + clase + '"><span class="resultado ' + categoria + '">'
                    + icon(_ICONO_RESULTADO[categoria]) + html.escape(texto.strip() or "—") + "</span></td>"
                )
            elif posicion == indice_fila:
                celdas.append('<td class="celda-fuerte num ' + clase + '">' + html.escape(texto) + "</td>")
            else:
                celdas.append('<td class="' + clase + '">' + html.escape(texto) + "</td>")

        if indice_observacion is not None:
            observacion = fila[indice_observacion] if indice_observacion < len(fila) else ""
            reintento = ""
            if (
                indice_resultado is not None
                and indice_fila is not None
                and indice_hoja is not None
                and indice_programa is not None
                and indice_curso is not None
                and _categoria_resultado(
                    fila[indice_resultado] if indice_resultado < len(fila) else ""
                ) == "error"
            ):
                valor = lambda indice: fila[indice] if indice < len(fila) else ""
                id_curso = _clave_curso(valor(indice_curso), valor(indice_programa), _usuario_actual())
                clave = _clave_actividad(valor(indice_hoja), valor(indice_fila))
                indice_actividad = _indice_columna(cabeceras, "Actividad")
                nombre_actividad = valor(indice_actividad) if indice_actividad is not None else ""
                reintento = (
                    '<button type="button" role="menuitem" data-reintentar-reporte '
                    'data-curso="' + _e(id_curso) + '" data-clave="' + _e(clave)
                    + '" data-nombre="' + _e(nombre_actividad)
                    + '">' + icon("subir") + "Reintentar recurso</button>"
                )
            celdas.append(
                '<td class="celda-acciones">' + _menu_acciones(
                    "Más acciones para la fila",
                    reintento + '<button type="button" role="menuitem" data-copiar="' + _e(observacion) + '" '
                    'data-copiado="Observación copiada">' + icon("copiar") + "Copiar observación</button>",
                ) + "</td>"
            )

        filas_html.append(
            '<tr data-fila data-busqueda="' + _e(" ".join(str(v) for v in fila).lower()) + '">' + "".join(celdas) + "</tr>"
        )

    columnas = len(cabeceras) + (1 if indice_observacion is not None else 0)

    if indice_resultado is not None:
        mosaicos = "".join(
            '<div class="mosaico estado ' + categoria + '"><span class="icono-tile ' + {
                "error": "rojo", "ok": "verde", "omitido": "ambar", "cancelado": ""
            }[categoria] + '">' + icon(nombre_icono) + '</span><div><strong class="num">' + str(conteo[categoria])
            + "</strong><b>" + titulo_mosaico + "</b><small>" + descripcion + "</small></div></div>"
            for categoria, nombre_icono, titulo_mosaico, descripcion, siempre in _MOSAICOS_RESULTADO
            if siempre or conteo[categoria]
        )
    else:
        mosaicos = (
            '<div class="mosaico estado"><span class="icono-tile">' + icon("documento")
            + '</span><div><strong class="num">' + str(len(filas)) + "</strong><b>Registros</b>"
            "<small>Filas del reporte</small></div></div>"
        )

    if filas_html:
        cuerpo_tabla = "".join(filas_html)
    else:
        cuerpo_tabla = '<tr class="fila-vacia"><td colspan="' + str(max(columnas, 1)) + '">El reporte no tiene filas todavía.</td></tr>'

    encabezados = "".join(
        '<th class="' + clase + '">' + html.escape(nombre) + "</th>"
        for nombre, clase in zip(cabeceras, clases)
    )
    if indice_observacion is not None:
        encabezados += '<th><span class="sr-only">Acciones</span></th>'

    contenido = (
        '<header class="encabezado"><div class="encabezado-titulo">'
        '<span class="icono-tile grande">' + icon("birrete") + "</span>"
        "<div><h1>" + html.escape(titulo) + "</h1><p>" + html.escape(subtitulo) + "</p></div></div>"
        '<div class="encabezado-acciones">'
        '<a class="boton neutro" href="/reportes">' + icon("flecha-izquierda") + "Volver</a>"
        '<a class="boton" href="' + _e(url_descarga) + '">' + icon("descargar") + "Descargar CSV</a>"
        "</div></header>"
        '<section class="mosaicos mosaicos-resultado" aria-label="Resumen del resultado">' + mosaicos + "</section>"
        '<section class="panel tabla-panel" id="tabla-detalle" data-tabla data-unidad="registros" data-por-pagina="10">'
        '<div class="tabla-cabecera"><div class="encabezado-titulo">'
        '<span class="icono-tile chico">' + icon("reportes") + "</span>"
        "<div><h2>Detalle de registros del curso</h2>"
        "<p>Revisa el resultado de la carga por fila del archivo Excel.</p></div></div>"
        '<label class="campo campo-borde">' + icon("buscar") + '<span class="sr-only">Buscar en la tabla</span>'
        '<input type="search" placeholder="Buscar en la tabla..." data-control-tabla="tabla-detalle" data-tipo="buscar"></label>'
        "</div>"
        '<div class="tabla-scroll"><table class="tabla mayusculas tabla-detalle"><thead><tr>' + encabezados
        + "</tr></thead><tbody>" + cuerpo_tabla + "</tbody></table></div>"
        + _pie_tabla(len(filas), "registros")
        + "</section>"
        + (
            '<form id="form-reintento-reporte" class="panel form-reintento-reporte" '
            'hidden method="post" action="/cursos/reintentar" enctype="multipart/form-data">'
            '<h2>Reintentar: <span id="reintento-reporte-nombre"></span></h2>'
            '<p>Sin archivo se vuelve a intentar con el ZIP original del cargue; también puedes adjuntar otro recurso.</p>'
            '<input type="hidden" name="id_curso" id="reintento-reporte-curso">'
            '<input type="hidden" name="clave" id="reintento-reporte-clave">'
            '<input type="hidden" name="registro_id" value="' + _e(registro_id) + '">'
            '<div class="form-reintento-campos"><label>Archivo opcional<input type="file" name="recurso"></label>'
            '<label>Usuario PRIZMA<input type="text" name="usuario_prizma" autocomplete="username" required></label>'
            '<label>Contraseña PRIZMA<input type="password" name="contrasena_prizma" autocomplete="current-password" required></label></div>'
            '<button class="boton" type="submit">Reintentar actividad</button></form>'
        )
    )
    js_reintento = r'''document.querySelectorAll("[data-reintentar-reporte]").forEach(function(b){b.addEventListener("click",function(){
      document.getElementById("reintento-reporte-curso").value=b.dataset.curso||"";
      document.getElementById("reintento-reporte-clave").value=b.dataset.clave||"";
      document.getElementById("reintento-reporte-nombre").textContent=b.dataset.nombre||"";
      var f=document.getElementById("form-reintento-reporte");f.hidden=false;f.scrollIntoView({behavior:"smooth",block:"center"});
    });});'''
    return render_page(
        titulo, contenido, active="reportes",
        page_css=_CSS_REGISTROS + ".form-reintento-reporte{padding:20px;margin-top:16px}.form-reintento-reporte[hidden]{display:none}.form-reintento-campos{display:grid;grid-template-columns:repeat(auto-fit,minmax(220px,1fr));gap:12px}.form-reintento-reporte label{display:grid;gap:6px}",
        page_js=js_reintento,
    )


_CSS_REGISTROS = r"""
.mosaicos-resultado { grid-template-columns: repeat(auto-fit, minmax(260px, 340px)); }
.tabla-detalle th, .tabla-detalle td { padding: 14px 12px; }
.tabla-detalle td { vertical-align: top; }
.tabla-detalle .col-estrecha { white-space: nowrap; }
.tabla-detalle .col-ancha { min-width: 130px; }
.tabla-detalle .col-observacion { min-width: 200px; overflow-wrap: anywhere; }
.tabla .resultado { margin-top: -3px; }
.celda-nombre .icono-tile.chico { width: 40px; height: 40px; }
"""


@app.get("/reporte-guardado/{registro_id}")
def descargar_reporte_guardado(registro_id: str, descargar: int = 0):
    registro = find_user_record(registro_id)

    if not registro:
        return JSONResponse({"error": "Reporte no encontrado"}, status_code=404)

    nombre, ruta = saved_report_path(registro)

    if ruta is None:
        return JSONResponse({"error": "El archivo del reporte ya no está disponible"}, status_code=404)

    if descargar:
        return FileResponse(ruta, media_type="text/csv", filename=nombre)

    cursos = registro.get("cursos") or []
    if cursos:
        titulo = str(cursos[0].get("curso") or "Reporte del cargue")
        subtitulo = " · ".join(
            filter(None, [
                str(cursos[0].get("programa") or ""),
                _formatear_fecha_hora(registro.get("fecha_iso"))[0],
            ])
        )
    else:
        titulo = "Reporte del cargue"
        subtitulo = _formatear_fecha_hora(registro.get("fecha_iso"))[0]

    return HTMLResponse(_pagina_reporte_html(
        titulo,
        subtitulo,
        ruta,
        "/reporte-guardado/" + registro_id + "?descargar=1",
        registro_id=registro_id,
    ))


# ============================================================
# DESCARGAR REPORTE
# ============================================================

@app.get(
    "/reporte/{trabajo_id}",
)
def descargar_reporte(
    trabajo_id: str,
    descargar: int = 0,
):

    trabajo = TRABAJOS.get(
        trabajo_id
    )

    if not trabajo or not _es_de(trabajo, _usuario_actual()):

        return JSONResponse(
            {
                "error":
                    "Trabajo no encontrado"
            },
            status_code=404,
        )

    ruta = trabajo[
        "ruta_reporte"
    ]

    if not os.path.isfile(
        ruta
    ):

        return JSONResponse(
            {
                "error":
                    "Reporte todavía no disponible"
            },
            status_code=404,
        )

    if descargar:
        return FileResponse(
            ruta,
            media_type="text/csv",
            filename=os.path.basename(ruta),
        )

    cursos = trabajo.get("cursos") or []
    titulo = (
        str(cursos[0].get("curso") or "Reporte del cargue")
        if cursos else "Reporte del cargue"
    )
    subtitulo = (
        str(trabajo.get("mensaje") or "")
        or "Resultado del cargue en PRIZMA"
    )

    return HTMLResponse(_pagina_reporte_html(
        titulo,
        subtitulo,
        ruta,
        "/reporte/" + trabajo_id + "?descargar=1",
        registro_id=trabajo_id,
    ))
