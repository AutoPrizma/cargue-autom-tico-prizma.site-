"""Logica pura de la auditoria profunda de cursos de Moodle publicados.

El recorrido abre el curso tal cual esta (semanas y recursos), sin matriz.
Aqui se decide, a partir de lo que el navegador observo en cada actividad,
si el recurso existe, renderiza de verdad (iframe H5P con contenido, visor
PDF embebido o archivo descargable valido) y si el titulo que se ve al
abrirlo es el nombre que el curso muestra en su listado.
"""

from urllib.parse import parse_qs, urlparse

from auto_prizma.auditor.procesar import clave


# Veredictos de render: "si" = el navegador mostro contenido real;
# "no" = la pagina cargo vacia; "no_comprobable" = no hubo forma de mirarlo.
RENDER_SI = "si"
RENDER_NO = "no"
RENDER_NO_COMPROBABLE = "no_comprobable"


def _seccion_de(url):
    try:
        return parse_qs(urlparse(str(url or "")).query).get("section", [""])[0]
    except ValueError:
        return ""


def parse_week_links(enlaces):
    """Enlaces de secciones del curso, deduplicados y en orden de semana.

    ``enlaces`` es [{text, href}] tal cual lo extrajo el navegador del
    índice lateral. Se queda con los que apuntan a ?section=N y se ordena
    por ese número (la general va primero: es la sección 0).

    Returns:
        [{"nombre", "url", "seccion"}]
    """
    semanas = {}
    for enlace in enlaces or []:
        url = str(enlace.get("href") or "")
        nombre = str(enlace.get("text") or "").strip()
        seccion = _seccion_de(url)
        if not url or not nombre or not seccion.isdigit():
            continue
        semanas.setdefault(seccion, {"nombre": nombre, "url": url, "seccion": seccion})
    return sorted(semanas.values(), key=lambda semana: int(semana["seccion"]))


def parse_activity_cards(tarjetas, semana=""):
    """Recursos de una semana, sin las etiquetas de texto del curso.

    ``tarjetas`` es [{id, modtype, titulo, href}] leido de los módulos
    ``module-*``/``data-cmid``. Las etiquetas (modtype_label) son rótulos de
    bloque, no recursos: se descartan.

    Returns:
        [{"id", "titulo", "url", "tipo", "semana"}]
    """
    recursos = []
    etiquetas_genericas = {
        "h5p", "file", "archivo", "url", "page", "pagina", "book", "libro",
        "folder", "carpeta", "resource", "recurso", "interactive content",
        "contenido interactivo",
    }
    for tarjeta in tarjetas or []:
        recurso_id = str(tarjeta.get("id") or "").strip()
        candidatos = tarjeta.get("titulos_candidatos") or [tarjeta.get("titulo")]
        candidatos = [str(item or "").strip() for item in candidatos if str(item or "").strip()]
        titulo = next(
            (item for item in candidatos if clave(item) not in etiquetas_genericas),
            candidatos[0] if candidatos else "",
        )
        url = str(tarjeta.get("href") or "").strip()
        modtype = str(tarjeta.get("modtype") or "").strip()
        if not recurso_id or modtype == "label" or not titulo:
            continue
        recursos.append({
            "id": recurso_id,
            "titulo": titulo,
            "url": url,
            "tipo": modtype or "desconocido",
            "semana": semana,
        })
    return recursos


def interpret_activity_probe(sonda, titulo_actividad):
    """Veredicto de una actividad abierta en el navegador.

    ``sonda`` es lo que la pestaña reporto de la pagina del recurso:
    encabezados, cuerpo, si había un H5P montado (y su texto/titulo por
    dentro) y si había un PDF embebido o solo un enlace de descarga.

    Returns:
        {"cargado", "renderiza", "tipo", "titulo_interno", "coincide",
        "detalle"} con ``coincide`` en True, False o None (sin titulo que
        comparar).
    """
    sonda = sonda or {}
    veredicto = {
        "cargado": False,
        "renderiza": RENDER_NO,
        "tipo": "desconocido",
        "titulo_interno": "",
        "coincide": None,
        "detalle": "",
    }

    if sonda.get("error"):
        veredicto["detalle"] = str(sonda["error"])
        if sonda.get("timeout"):
            veredicto["cargado"] = True
            veredicto["renderiza"] = RENDER_NO_COMPROBABLE
        return veredicto

    descarga = sonda.get("download") or {}
    if descarga:
        nombre_archivo = str(descarga.get("filename") or "").strip()
        extension = nombre_archivo.rsplit(".", 1)[-1].lower() if "." in nombre_archivo else ""
        veredicto["cargado"] = True
        veredicto["renderiza"] = RENDER_NO_COMPROBABLE
        veredicto["tipo"] = "pdf" if extension == "pdf" else "h5p" if extension == "h5p" else "archivo"
        veredicto["detalle"] = str(
            descarga.get("error")
            or ("Moodle inició la descarga de " + (nombre_archivo or "un archivo") + "; se valida el contenido descargado.")
        )
        return veredicto

    cuerpo = str(sonda.get("texto_cuerpo") or "").strip()
    encabezados = [str(item or "").strip() for item in sonda.get("encabezados") or []]
    h5p = sonda.get("h5p") or {}
    pdf = sonda.get("pdf") or {}

    if h5p.get("presente"):
        veredicto["tipo"] = "h5p"
        texto_h5p = str(h5p.get("texto") or "").strip()
        alto_h5p = int(h5p.get("alto") or 0)
        titulos_h5p = [
            str(item or "").strip()
            for item in h5p.get("titulos") or []
            if str(item or "").strip()
        ]
        titulo_h5p = str(h5p.get("titulo") or "").strip()
        titulo_h5p = next(
            (item for item in titulos_h5p if clave(item) == clave(titulo_actividad)),
            titulo_h5p,
        )
        # No usar el encabezado exterior de Moodle como si fuera el título
        # interno del H5P: puede ser el título del curso o de la página.
        veredicto["titulo_interno"] = titulo_h5p
        if texto_h5p or alto_h5p > 80:
            veredicto["cargado"] = True
            veredicto["renderiza"] = RENDER_SI
            veredicto["detalle"] = "El contenido H5P se montó y mostró texto por dentro."
        else:
            veredicto["renderiza"] = RENDER_NO_COMPROBABLE
            veredicto["detalle"] = (
                "El H5P está en la página, pero su interior no respondió a tiempo "
                "(revisa que la portada abra con normalidad)."
            )
    elif pdf.get("presente"):
        veredicto["tipo"] = "pdf"
        veredicto["cargado"] = True
        origen = str(pdf.get("origen") or "")
        if pdf.get("embebido"):
            veredicto["renderiza"] = RENDER_SI
            veredicto["detalle"] = "PDF embebido en la página del recurso."
        elif origen:
            veredicto["renderiza"] = RENDER_NO_COMPROBABLE
            veredicto["detalle"] = (
                "Muestra el archivo PDF para descargar; se valida el archivo aparte."
            )
        else:
            veredicto["renderiza"] = RENDER_NO
            veredicto["detalle"] = "Aparece un PDF referenciado, pero sin visor ni archivo."
    elif cuerpo:
        veredicto["tipo"] = "pagina"
        veredicto["cargado"] = True
        veredicto["renderiza"] = RENDER_SI
        veredicto["detalle"] = "La página del recurso cargó con contenido."
    else:
        veredicto["renderiza"] = RENDER_NO
        veredicto["detalle"] = "La página del recurso abrió en blanco."
        return veredicto

    encabezado = encabezados[0] if encabezados else ""
    if not veredicto["titulo_interno"] and veredicto["tipo"] != "h5p":
        veredicto["titulo_interno"] = encabezado
    interno = str(veredicto["titulo_interno"] or "")
    if interno:
        veredicto["coincide"] = clave(interno) == clave(titulo_actividad)
        if not veredicto["coincide"]:
            veredicto["detalle"] += (
                " REVISAR: el título que se ve (\"" + interno
                + "\") no coincide con el nombre del curso (\""
                + str(titulo_actividad) + "\")."
            )
    return veredicto


def audit_row(semana, actividad, veredicto, pdf_validacion=None):
    """Fila final de reporte de una actividad auditada.

    ``pdf_validacion`` (opcional) es la salida de
    ``content_checks.inspeccionar_pdf_bytes`` cuando se pudo descargar el
    PDF por separado: con ella se cierra el veredicto de render.
    """
    renderiza = veredicto.get("renderiza")
    detalle = str(veredicto.get("detalle") or "")
    cargado = bool(veredicto.get("cargado"))

    if pdf_validacion is not None:
        if not pdf_validacion.get("ok"):
            cargado = False
            renderiza = RENDER_NO
            detalle = str(pdf_validacion.get("detalle") or "El archivo PDF no es válido.")
        elif not pdf_validacion.get("con_contenido"):
            renderiza = RENDER_NO
            detalle = str(pdf_validacion.get("detalle") or "El PDF parece en blanco.")
        elif renderiza != RENDER_SI:
            renderiza = RENDER_SI
            detalle = str(pdf_validacion.get("detalle") or "Archivo PDF descargado y validado.")

    if cargado and renderiza == RENDER_SI and veredicto.get("coincide") is not False:
        estado = "ok"
    elif cargado or renderiza == RENDER_NO_COMPROBABLE:
        # Presente pero con algo que mirar a mano, o imposible de comprobar.
        estado = "revisar"
    else:
        estado = "falta"

    tipo = str(veredicto.get("tipo") or "")
    if tipo == "desconocido":
        tipo = {
            "h5pactivity": "h5p",
            "resource": "archivo",
            "url": "enlace",
            "page": "página",
            "book": "libro",
            "folder": "carpeta",
        }.get(str(actividad.get("tipo") or "").lower(), tipo)

    return {
        "semana": semana,
        "actividad": str(actividad.get("titulo") or ""),
        "tipo": tipo,
        "estado": estado,
        "renderiza": renderiza,
        "titulo_interno": str(veredicto.get("titulo_interno") or ""),
        "coincide": veredicto.get("coincide"),
        "detalle": detalle,
    }


def summarize_audit_rows(filas):
    """Contadores para el encabezado del reporte de auditoria."""
    return {
        "ok": sum(1 for fila in filas if fila["estado"] == "ok"),
        "revisar": sum(1 for fila in filas if fila["estado"] == "revisar"),
        "falta": sum(1 for fila in filas if fila["estado"] == "falta"),
        "total": len(filas),
    }
