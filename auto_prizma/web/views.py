"""HTML de la pagina principal: formulario de Inicio y revision antes del cargue (generar_html).

El marco comun (menu lateral, barra superior, tema, estado del servicio) lo
pone web/layout.py; aqui solo va el contenido de Inicio y su CSS/JS propio.
"""

import html

from auto_prizma.services.upload_jobs import _codificar_clave_actividad
from auto_prizma.web.icons import icon
from auto_prizma.web.layout import render_page, status_pills


def _archivo_listo(input_id, nombre_icono):
    """Fila con el archivo elegido (nombre, tamano y boton para quitarlo)."""
    return (
        '<div class="archivo-listo" id="listo-' + input_id + '" hidden>'
        '<span class="icono-tile chico">' + icon(nombre_icono) + "</span>"
        '<div class="archivo-listo-texto"><strong data-nombre></strong><small data-detalle></small></div>'
        + icon("check-circulo", "icono icono-listo")
        + '<button type="button" class="boton-icono" data-quitar="' + input_id + '" aria-label="Quitar archivo">'
        + icon("cerrar") + "</button></div>"
    )


def _tarjeta_tipo(nombre, titulo, descripcion, clase, nombre_icono, marcado, extra=""):
    return (
        '<label class="tarjeta-tipo ' + clase + '">'
        '<input type="checkbox" name="' + nombre + '" value="1"' + (" checked" if marcado else "") + extra + ">"
        '<span class="check-personalizado" aria-hidden="true">' + icon("check") + "</span>"
        '<span class="tipo-icono" aria-hidden="true">' + icon(nombre_icono) + "</span>"
        "<strong>" + titulo + "</strong><small>" + descripcion + "</small></label>"
    )


def _opcion(nombre, valor, titulo, descripcion, nombre_icono, marcado):
    return (
        '<label class="opcion-modo">'
        '<input type="radio" name="' + nombre + '" value="' + valor + '"' + (" checked" if marcado else "") + ">"
        '<span class="radio" aria-hidden="true"></span>'
        + icon(nombre_icono, "icono icono-opcion")
        + '<span class="opcion-texto"><strong>' + titulo + "</strong><small>" + descripcion + "</small></span></label>"
    )


def _pantalla_inicio(error, e):
    bloque_error = ""
    if error:
        bloque_error = (
            '<div class="aviso error alerta-error" role="alert">' + icon("alerta-circulo")
            + "<div><strong>No se pudo continuar</strong><p>" + e(error) + "</p></div></div>"
        )

    return f"""
    <header class="encabezado workspace-page-heading encabezado-cargue">
        <div class="encabezado-titulo">
            <span class="icono-tile grande morado">{icon("subir")}</span>
            <div><h1>Cargue de recursos</h1>
                <p>Selecciona la matriz y el ZIP, revisa las actividades y prepara el cargue en PRIZMA. El syllabus es opcional.</p>
            </div>
        </div>
    </header>
    <div class="pasos-cargue" aria-label="Etapas del cargue">
        <span>1 Archivos</span><span>2 Revisión</span><span>3 Cargue en PRIZMA</span>
    </div>
    <div class="estado-prizma-inicio">{status_pills()}</div>

    {bloque_error}

    <form id="cargue-principal" action="/analizar" method="post" enctype="multipart/form-data" class="panel panel-principal">
        <div class="grid-archivos">
            <section class="tarjeta-archivo">
                <div class="archivo-cabecera">
                    <span class="icono-tile verde">{icon("hoja")}</span>
                    <div>
                        <h2>Archivo de la matriz</h2>
                        <p>Selecciona la matriz guardada en tu equipo.</p>
                    </div>
                </div>
                <label class="dropzone zona-drop" for="archivo-matriz" data-input="archivo-matriz">
                    {icon("subir", "icono icono-drop")}
                    <strong>Selecciona o arrastra tu matriz</strong>
                    <small>Archivo .xlsx o .csv</small>
                    <span class="boton">Seleccionar archivo</span>
                    <input id="archivo-matriz" type="file" name="matriz_archivo" accept=".xlsx,.csv">
                </label>
                {_archivo_listo("archivo-matriz", "hoja")}
            </section>

            <section class="tarjeta-archivo">
                <div class="archivo-cabecera">
                    <span class="icono-tile">{icon("zip")}</span>
                    <div>
                        <h2>ZIP de recursos</h2>
                        <p>Archivos H5P o HTML y PDF. También puedes arrastrar el archivo aquí.</p>
                    </div>
                </div>
                <label class="dropzone zona-drop" for="archivo-zip" data-input="archivo-zip">
                    {icon("subir", "icono icono-drop")}
                    <strong>Selecciona o arrastra tu archivo ZIP</strong>
                    <small>Un solo archivo .zip</small>
                    <span class="boton">Seleccionar archivo</span>
                    <input id="archivo-zip" type="file" name="recursos" accept=".zip" required>
                </label>
                {_archivo_listo("archivo-zip", "zip")}
            </section>

            <section class="tarjeta-archivo">
                <div class="archivo-cabecera">
                    <span class="icono-tile ambar">{icon("libro")}</span>
                    <div>
                        <h2>Syllabus y preparación</h2>
                        <p>Opcional: syllabus PDF y datos para preparar la ficha del curso en PRIZMA.</p>
                    </div>
                </div>
                <label class="dropzone zona-drop" for="archivo-syllabus" data-input="archivo-syllabus">
                    {icon("subir", "icono icono-drop")}
                    <strong>Selecciona o arrastra el syllabus</strong>
                    <small>Archivo PDF (opcional)</small>
                    <span class="boton">Seleccionar archivo</span>
                    <input id="archivo-syllabus" type="file" name="syllabus_archivo" accept=".pdf">
                </label>
                {_archivo_listo("archivo-syllabus", "libro")}
                <div class="campos-preparacion">
                    <label>Línea académica
                        <input type="text" name="linea_academica" autocomplete="off"
                            placeholder="V1130 11301 30S01 COMPETENCIAS MATEMÁTICAS I">
                    </label>
                    <label>Nivel de pensum
                        <input type="text" name="nivel_pensum" autocomplete="off"
                            placeholder="Nivel 1">
                    </label>
                    <small class="nota-campos">Si los dejas vacíos, la preparación se omite. Los videos de intro y cierre se toman del ZIP.</small>
                </div>
            </section>
        </div>

        <div class="separador"></div>

        <section class="seccion-tipos">
            <div class="titulo-seccion">
                <h2>Tipos de actividades</h2>
                <p>Selecciona qué actividades deseas procesar.</p>
            </div>
            <div class="grid-tipos">
                {_tarjeta_tipo("ovi", "OVI", "Objetos Virtuales de Información", "tipo-verde", "ovi", True)}
                {_tarjeta_tipo("ova", "OVA", "Objetos Virtuales de Aprendizaje", "tipo-azul", "ova", True)}
                {_tarjeta_tipo("retos", "Retos Evaluativos", "Retos evaluativos en PDF", "tipo-morado", "reto", True)}
                {_tarjeta_tipo("test_evaluativo", "Test Evaluativo", "Exámenes desde Word", "tipo-naranja", "test", False, ' id="chk-test"')}
            </div>

            <div class="formato-recurso">
                <p class="formato-titulo">
                    <strong>Formato de los recursos interactivos</strong>
                    · OVA y OVI de tipo H5P o infografía (los PDF no cambian)
                </p>
                <div class="opciones-modo compacto" role="radiogroup" aria-label="Formato de los recursos interactivos">
                    {_opcion("formato_recurso", "H5P", "H5P", "Sube el archivo .h5p al campo Recurso", "paquete", True)}
                    {_opcion("formato_recurso", "HTML", "HTML", "Pega el código del archivo .html en el campo Html", "codigo", False)}
                </div>
            </div>
        </section>

        <section id="bloque-test" hidden>
            <div class="separador"></div>
            <div class="titulo-seccion con-icono">
                <span class="icono-tile naranja chico">{icon("test")}</span>
                <div>
                    <h2>Documento de Test y datos académicos</h2>
                    <p>Sube el Word; en el siguiente paso pegarás una sola línea con los datos del curso.</p>
                </div>
            </div>

            <div class="tarjeta-archivo" id="bloque-test-archivo">
                <label class="dropzone zona-drop" for="archivo-test-docx" data-input="archivo-test-docx">
                    {icon("subir", "icono icono-drop")}
                    <strong>Selecciona o arrastra el documento de evaluación</strong>
                    <small>Archivo Word (.docx) con las preguntas</small>
                    <span class="boton naranja">Seleccionar archivo</span>
                    <input id="archivo-test-docx" type="file" name="test_archivo_docx" accept=".docx" disabled>
                </label>
                {_archivo_listo("archivo-test-docx", "word")}
            </div>

        </section>

        <div class="pie-formulario">
            <button type="button" class="enlace-accion" data-abrir-dialogo="dialogo-guia">
                {icon("externo")} Ver guía
            </button>
            <button class="boton grande" type="submit">
                {icon("play", "icono icono-play")} Analizar recursos {icon("flecha-derecha")}
            </button>
            <span aria-hidden="true"></span>
        </div>
        <p class="nota-seguridad">{icon("escudo")} Tus archivos se usan únicamente durante el proceso de cargue.</p>
    </form>
    """


def _dialogo_guia():
    pasos = [
        "Selecciona el archivo XLSX o CSV de la matriz.",
        "Sube el ZIP con los recursos correspondientes.",
        "Selecciona los tipos de actividades y el formato (H5P o HTML).",
        "Analiza, revisa y luego inicia el cargue.",
    ]
    consejos = [
        "El ZIP debe contener los H5P (o los HTML) y PDF correspondientes, con el mismo nombre de cada actividad.",
        "Revisa el análisis antes de iniciar el cargue.",
    ]
    return (
        '<dialog id="dialogo-guia" class="dialogo" aria-labelledby="titulo-guia">'
        '<div class="dialogo-cabecera"><h2 id="titulo-guia">¿Cómo funciona?</h2>'
        '<button type="button" class="boton-icono" data-cerrar-dialogo aria-label="Cerrar">' + icon("cerrar") + "</button></div>"
        '<div class="dialogo-cuerpo"><ol class="pasos-guia">'
        + "".join("<li><b>" + str(n) + "</b><span>" + texto + "</span></li>" for n, texto in enumerate(pasos, 1))
        + '</ol><h3 class="titulo-consejos">Consejos</h3><ul class="consejos">'
        + "".join("<li>" + icon("check") + "<span>" + texto + "</span></li>" for texto in consejos)
        + "</ul></div></dialog>"
    )


_CARGADOR = """
<div id="prizma-loader" class="prizma-loader" role="status" aria-live="polite" aria-hidden="true">
    <div class="loader-contenido">
        <img class="loader-logo" src="/auto-prizma-logo.png" alt="">
        <strong id="prizma-loader-texto">Procesando...</strong>
        <span>Espera mientras Auto Prizma prepara la información.</span>
    </div>
</div>
"""


def _preparation_block(preparacion):
    """Panel de revisión con lo que se preparará en la ficha del curso.

    Muestra syllabus, videos de intro/cierre detectados en el ZIP, si se
    dejará vacía la descripción y los datos académicos. Si hay videos sin
    línea académica, avisa que la preparación se omitirá.
    """
    if not isinstance(preparacion, dict):
        return ""

    def e(valor):
        return html.escape(str(valor or ""))

    tiene_syllabus = bool(preparacion.get("syllabus"))
    video_intro = str(preparacion.get("video_intro") or "")
    video_cierre = str(preparacion.get("video_cierre") or "")
    linea = str(preparacion.get("linea_academica") or "").strip()
    nivel = str(preparacion.get("nivel") or "").strip()
    curso = preparacion.get("curso") or {}

    if not (tiene_syllabus or video_intro or video_cierre or linea):
        return ""

    def fila(estado, texto):
        marca = {
            "ok": ('badge-verde', "Se cargará"),
            "aviso": ('badge-ambar', "Aviso"),
            "omitido": ('badge-gris', "Omitido"),
        }.get(estado, ('badge-gris', "—"))
        return (
            "<tr><td><span class=\"" + marca[0] + "\">" + marca[1] + "</span></td>"
            + "<td>" + e(texto) + "</td></tr>"
        )

    filas = ""

    if linea and nivel:
        nombre_curso = str(curso.get("asignatura") or "").strip()
        filas += fila(
            "ok",
            "Datos académicos: " + (nombre_curso or linea)
            + " · Nivel " + nivel,
        )
    else:
        filas += fila(
            "omitido",
            "Sin línea académica y nivel: la ficha de la asignatura no se preparará.",
        )

    preparacion_activa = bool(linea and nivel)

    if tiene_syllabus and preparacion_activa:
        filas += fila("ok", "Syllabus: el PDF adjunto se subirá al campo Syllabus.")
    elif tiene_syllabus:
        filas += fila("aviso", "Syllabus adjunto, pero falta la línea académica: no se subirá.")
    else:
        filas += fila("omitido", "Syllabus: no se adjuntó ninguno.")

    if preparacion_activa:
        if video_intro:
            filas += fila("ok", "Video de introductorio: " + video_intro + " (desde el ZIP).")
        else:
            filas += fila("omitido", "Video de introductorio: el ZIP no incluye uno.")
        if video_cierre:
            filas += fila("ok", "Video de cierre: " + video_cierre + " (desde el ZIP).")
        else:
            filas += fila("omitido", "Video de cierre: el ZIP no incluye uno.")
        filas += fila("ok", "Descripción: se dejará el campo vacío.")
    else:
        if video_intro or video_cierre:
            filas += fila(
                "aviso",
                "El ZIP trae videos de intro/cierre, pero sin línea académica no se cargan.",
            )

    aviso_extra = ""
    if not preparacion_activa and (video_intro or video_cierre):
        aviso_extra = (
            '<div class="aviso ambar">' + icon("alerta-circulo")
            + "<div><strong>Preparación omitida</strong><p>Para cargar los videos de "
            "intro/cierre y el syllabus, vuelve a Inicio y completa la línea académica "
            "y el nivel de pensum en la tarjeta «Syllabus y preparación».</p></div></div>"
        )

    return (
        '<section class="panel preparacion-panel"><div class="titulo-bloque">'
        "<h2>Preparación de la asignatura</h2>"
        "<p>Antes de subir recursos, PRIZMA recibirá estos cambios en la ficha del curso.</p>"
        '</div><div class="tabla-scroll"><table class="tabla"><thead><tr>'
        "<th>Estado</th><th>Acción</th></tr></thead><tbody>"
        + filas + "</tbody></table></div>" + aviso_extra + "</section>"
    )


def generar_html(
    resultado=None,
    error=None,
    trabajo_id=None,
    seleccion_actual=None,
    aviso=None,
):

    def e(valor):
        return html.escape(
            str(valor or "")
        )

    # ========================================================
    # PANTALLA INICIAL
    # ========================================================

    if resultado is None:
        return render_page(
            "Cargue PRIZMA",
            _pantalla_inicio(error, e),
            active="prizma",
            page_css=_CSS_INICIO,
            page_js=_js_inicio(),
            after_main=_dialogo_guia() + _CARGADOR,
        )

    # ========================================================
    # PANTALLA DE REVISIÓN
    # ========================================================

    total_actividades = 0
    total_ovi = 0
    total_ova = 0
    total_retos = 0
    total_h5p = 0
    total_pdf = 0
    total_html = 0
    filas_html = ""
    tipos_recurso_conteo = {}
    tipos_recurso_seleccionados = {}

    seleccion_actual_claves = None
    if seleccion_actual is not None:
        seleccion_actual_claves = set()
        for item in seleccion_actual or []:
            if not isinstance(item, (list, tuple)) or len(item) != 2:
                continue
            try:
                seleccion_actual_claves.add((str(item[0] or ""), int(item[1])))
            except (TypeError, ValueError):
                continue

    nombre_matriz = str(resultado.get("nombre_matriz") or "").strip()
    modo_html = str(resultado.get("formato_recurso") or "H5P").upper() == "HTML"

    for hoja in resultado["hojas"]:

        total_actividades += len(
            hoja["actividades"]
        )
        total_ovi += hoja.get("ovi", 0)
        total_ova += hoja.get("ova", 0)
        total_retos += hoja.get("retos", 0)
        total_h5p += hoja.get("h5p", 0)
        total_pdf += hoja.get("pdf", 0)
        total_html += hoja.get("html", 0)

        for actividad in hoja["actividades"]:

            tipo_recurso = str(
                actividad.get("tipo_recurso")
                or actividad.get("tipo")
                or "Sin tipo"
            ).strip()
            tipos_recurso_conteo[tipo_recurso] = (
                tipos_recurso_conteo.get(tipo_recurso, 0) + 1
            )

            clave_tuple = (
                str(hoja.get("hoja") or ""),
                int(actividad.get("fila") or 0),
            )
            seleccionada = (
                seleccion_actual_claves is None
                or clave_tuple in seleccion_actual_claves
            )
            if seleccionada:
                tipos_recurso_seleccionados[tipo_recurso] = (
                    tipos_recurso_seleccionados.get(tipo_recurso, 0) + 1
                )

            clave_actividad = _codificar_clave_actividad(*clave_tuple)

            categoria = actividad["categoria"]
            clase_categoria = {
                "OVI": "badge-verde",
                "OVA": "badge-azul",
                "CHALLENGE": "badge-morado",
            }.get(categoria, "badge-gris")

            etiqueta_categoria = (
                "RETO"
                if categoria == "CHALLENGE"
                else categoria
            )

            clase_tipo = (
                "badge-pdf"
                if actividad["tipo"] == "PDF"
                else "badge-html"
                if actividad["tipo"] == "HTML"
                else "badge-h5p"
            )

            archivo_drive = "Se resolverá desde el ZIP"
            estado_zip = "Se comprobará al cargar"

            filas_html += f"""
            <tr>
                <td class="celda-seleccion">
                    <input
                        type="checkbox"
                        class="actividad-seleccion"
                        name="actividades_seleccionadas"
                        value="{e(clave_actividad)}"
                        data-tipo-recurso="{e(tipo_recurso)}"
                        form="form-iniciar-cargue"
                        {"checked" if seleccionada else ""}
                        aria-label="Seleccionar {e(actividad["nombre"])}"
                    >
                </td>
                <td>{e(actividad["semana"])}</td>
                <td>{e(actividad["unidad"])}</td>
                <td class="celda-actividad">{e(actividad["nombre"])}</td>
                <td><span class="badge {clase_categoria}">{e(etiqueta_categoria)}</span></td>
                <td><span class="badge badge-recurso">{e(tipo_recurso)}</span></td>
                <td><span class="badge {clase_tipo}">{e(actividad["tipo"])}</span></td>
                <td class="celda-actividad" title="{e(archivo_drive)}">
                    <strong>{e(archivo_drive)}</strong>
                </td>
                <td><span class="badge badge-gris">{e(estado_zip)}</span></td>
            </tr>
            """

    total_seleccionadas = sum(tipos_recurso_seleccionados.values())
    filtros_tipo_html = ""
    for tipo_recurso, cantidad in tipos_recurso_conteo.items():
        seleccionadas_tipo = tipos_recurso_seleccionados.get(tipo_recurso, 0)
        marcado = seleccionadas_tipo == cantidad and cantidad > 0
        filtros_tipo_html += f"""
        <label class="filtro-recurso-item">
            <input
                type="checkbox"
                class="filtro-tipo-recurso"
                data-tipo-recurso="{e(tipo_recurso)}"
                {"checked" if marcado else ""}
            >
            <span class="filtro-recurso-check">{icon("check")}</span>
            <span class="filtro-recurso-texto">
                <strong>{e(tipo_recurso)}</strong>
                <small>{cantidad} actividad{"es" if cantidad != 1 else ""}</small>
            </span>
        </label>
        """

    bloque_advertencias_revision = ""

    bloque_error_revision = ""
    if error:
        bloque_error_revision = (
            '<div class="aviso error alerta-error" role="alert">' + icon("alerta-circulo")
            + "<div><strong>No se pudo iniciar el cargue</strong><p>" + e(error) + "</p></div></div>"
        )

    bloque_aviso_revision = ""
    if aviso:
        bloque_aviso_revision = (
            '<div class="aviso info" role="status">' + icon("info")
            + "<div><strong>Reintento de cargues anteriores</strong><p>"
            + e(aviso)
            + "</p></div></div>"
        )

    resumen_origen = (
        e(nombre_matriz or "Matriz local") + " · "
        + str(int((resultado.get("zip") or {}).get("total") or 0))
        + " recurso(s) " + ("HTML" if modo_html else "H5P") + "/PDF detectado(s) en el ZIP"
    )
    encabezado_recurso = "Resolución de recurso"
    encabezado_estado = "Estado"

    bloque_test_html = ""
    test_info = resultado.get("test_info")
    if test_info:
        test_job_id = test_info.get("test_job_id", "")
        cant_tests = test_info.get("cantidad_tests", 1)
        cant_preg = test_info.get("cantidad_preguntas", 0)
        nom_doc = test_info.get("nombre_documento", "documento.docx")
        bloque_test_html = f"""
        <section class="panel test-preparado">
            <span class="icono-tile naranja">{icon("test")}</span>
            <div class="test-preparado-texto">
                <h3>Test Evaluativo preparado</h3>
                <p>Documento: <strong>{e(nom_doc)}</strong> · {cant_tests} examen(es) con {cant_preg} preguntas detectadas.</p>
            </div>
            <a href="/tests/{test_job_id}/revision" class="boton naranja">Revisar y configurar test {icon("flecha-derecha")}</a>
        </section>
        """

    bloque_preparacion = _preparation_block(resultado.get("preparacion"))

    bloque_revision_h5p = ""
    revision_h5p = resultado.get("revision_h5p") or {}
    if revision_h5p:
        if not revision_h5p.get("ok"):
            bloque_revision_h5p = (
                '<section class="panel aviso ambar"><div><strong>No se pudo previsualizar '
                'el título H5P</strong><p>' + e(revision_h5p.get("error"))
                + " El análisis y el cargue pueden continuar.</p></div></section>"
            )
        else:
            filas_h5p = ""
            estados_h5p = {"ok": ("badge-verde", "Coincide"), "alerta": ("badge-ambar", "Revisar"),
                           "faltante": ("badge-rojo", "Falta"), "fuera-de-alcance": ("badge-gris", "No aplica")}
            for item in revision_h5p.get("resultados") or []:
                estado_clase, estado_texto = estados_h5p.get(str(item.get("estado") or ""), ("badge-gris", "Revisar"))
                titulos_contenido = " · ".join(str(t) for t in item.get("titulos_contenido") or [])
                filas_h5p += (
                    "<tr><td>" + e(item.get("fila")) + "</td>"
                    + "<td><strong>" + e(item.get("nombre")) + "</strong></td>"
                    + "<td>" + e(item.get("archivo")) + "</td>"
                    + "<td>" + (e(item.get("titulo_h5p")) or "<span class=\"muted\">Sin título interno</span>") + "</td>"
                    + "<td>" + (e(titulos_contenido) or "—") + "</td>"
                    + '<td><span class="badge ' + estado_clase + '">' + estado_texto + "</span><small class=\"detalle-h5p\">"
                    + e(item.get("detalle")) + "</small></td></tr>"
                )
            if filas_h5p:
                bloque_revision_h5p = (
                    '<section class="panel revision-h5p"><div class="titulo-bloque">'
                    '<h2>Previsualización y títulos H5P</h2>'
                    '<p>Compara el título de la matriz, el archivo del ZIP, el título del paquete y los títulos visibles dentro del contenido.</p>'
                    '</div><div class="tabla-scroll"><table class="tabla"><thead><tr>'
                    '<th>Fila</th><th>Matriz</th><th>Archivo del ZIP</th><th>Título del paquete</th>'
                    '<th>Títulos internos visibles</th><th>Resultado</th></tr></thead><tbody>'
                    + filas_h5p + "</tbody></table></div></section>"
                )
            else:
                bloque_revision_h5p = (
                    '<section class="panel aviso info"><div><strong>No hay paquetes H5P para comparar</strong>'
                    '<p>Esta matriz y el ZIP no contienen actividades H5P seleccionadas.</p></div></section>'
                )

    contenido = f"""
    <div class="revision">
    <section id="cargue-principal" class="panel encabezado-exito">
        <span class="icono-tile verde grande">{icon("check-circulo")}</span>
        <div>
            <h1>Análisis completado</h1>
            <p>{resumen_origen}</p>
        </div>
    </section>

    <section class="resumen-grid">
        <div class="resumen-card"><span>Actividades</span><strong>{total_actividades}</strong></div>
        <div class="resumen-card verde"><span>OVI</span><strong>{total_ovi}</strong></div>
        <div class="resumen-card azul"><span>OVA</span><strong>{total_ova}</strong></div>
        <div class="resumen-card morado"><span>Retos</span><strong>{total_retos}</strong></div>
        <div class="resumen-card violeta"><span>{"HTML" if modo_html else "H5P"}</span><strong>{total_html if modo_html else total_h5p}</strong></div>
        <div class="resumen-card rojo"><span>PDF</span><strong>{total_pdf}</strong></div>
    </section>

    {bloque_test_html}
    {bloque_preparacion}
    {bloque_revision_h5p}
    {bloque_advertencias_revision}
    {bloque_error_revision}
    {bloque_aviso_revision}

    <section class="panel selector-recursos-panel">
        <div class="selector-recursos-cabecera">
            <div class="titulo-bloque">
                <h2>Selecciona qué se cargará</h2>
                <p>Marca tipos completos para seleccionar rápido y ajusta actividades individuales en la tabla.</p>
            </div>
            <div class="selector-recursos-contador">
                <strong id="contador-seleccionadas">{total_seleccionadas} de {total_actividades}</strong>
                <span>actividades seleccionadas</span>
            </div>
        </div>

        <div class="filtros-recursos">
            {filtros_tipo_html}
        </div>

        <div class="selector-recursos-acciones">
            <button type="button" class="boton secundario chico" id="seleccionar-todas-actividades">Seleccionar todo</button>
            <button type="button" class="boton neutro chico" id="limpiar-seleccion-actividades">Limpiar selección</button>
        </div>
    </section>

    <section class="revision-grid">
        <div class="panel tabla-actividades">
            <div class="titulo-bloque">
                <h2>Actividades detectadas</h2>
                <p>Revisa que las actividades y categorías sean correctas.</p>
            </div>

            <div class="tabla-scroll tabla-revision">
                <table class="tabla">
                    <thead>
                        <tr>
                            <th>✓</th>
                            <th>Semana</th>
                            <th>Unidad</th>
                            <th>Actividad</th>
                            <th>Categoría</th>
                            <th>Tipo de recurso</th>
                            <th>Formato</th>
                            <th>{e(encabezado_recurso)}</th>
                            <th>{e(encabezado_estado)}</th>
                        </tr>
                    </thead>
                    <tbody>
                        {filas_html}
                    </tbody>
                </table>
            </div>
        </div>

        <div class="panel credenciales-panel">
            <div class="titulo-bloque">
                <h2>Acceso a PRIZMA</h2>
                <p>Ingresa tus credenciales para autorizar este cargue.</p>
            </div>

            <form id="form-iniciar-cargue" action="/iniciar/{trabajo_id}" method="post" autocomplete="off">
                <label class="campo-label" for="usuario_prizma">Usuario PRIZMA</label>
                <div class="campo-moderno">
                    {icon("usuario")}
                    <input
                        id="usuario_prizma"
                        type="text"
                        name="usuario_prizma"
                        placeholder="Ingresa tu usuario"
                        autocomplete="off"
                        required
                    >
                </div>

                <label class="campo-label" for="contrasena_prizma">Contraseña PRIZMA</label>
                <div class="campo-moderno">
                    {icon("clave")}
                    <input
                        id="contrasena_prizma"
                        type="password"
                        name="contrasena_prizma"
                        placeholder="Ingresa tu contraseña"
                        autocomplete="new-password"
                        required
                    >
                </div>

                <div class="caja-seguridad">
                    {icon("escudo")}
                    <div>
                        <strong>Credenciales de uso temporal</strong>
                        <span>La aplicación no las escribe en archivos, reportes ni base de datos.</span>
                    </div>
                </div>

                <button class="boton grande boton-iniciar" type="submit">
                    {icon("play", "icono icono-play")} Iniciar cargue en PRIZMA
                </button>
            </form>
        </div>
    </section>

    <a class="boton neutro volver-inicio" href="/prizma">{icon("flecha-izquierda")} Cambiar matriz o ZIP</a>
    </div>
    """

    return render_page(
        "Revisión del análisis",
        contenido,
        active="prizma",
        page_css=_CSS_INICIO,
        page_js=_js_inicio(),
        after_main=_CARGADOR,
    )


# ============================================================
# CSS PROPIO DE INICIO
# ============================================================

_CSS_INICIO = r"""
/* ---------- Pantalla inicial ---------- */
.estado-prizma-inicio { margin: 0 0 16px; }
.encabezado-cargue { margin-bottom: 16px; }
.encabezado-cargue .encabezado-titulo > div { min-width: 0; }
.encabezado-cargue p { max-width: 980px; line-height: 1.5; }
.pasos-cargue { display: flex; flex-wrap: wrap; gap: 8px; margin: 0 0 16px; }
.pasos-cargue span { padding: 8px 13px; border-radius: 999px; background: var(--morado-suave); color: var(--morado); font-size: 13px; font-weight: 800; }
.alerta-error { margin-bottom: 20px; }

.panel-principal { padding: 26px; display: grid; gap: 24px; }

.opciones-modo { display: grid; grid-template-columns: 1fr 1fr; gap: 18px; }
.opcion-modo {
  position: relative; display: flex; align-items: center; gap: 18px; min-width: 0;
  padding: 22px 26px; border: 1.5px solid var(--borde); border-radius: 16px;
  background: var(--panel); cursor: pointer; transition: border-color .15s ease, background .15s ease;
}
.opcion-modo:hover { border-color: var(--acento-borde); }
.opcion-modo input { position: absolute; opacity: 0; pointer-events: none; }
.opcion-modo .radio {
  width: 24px; height: 24px; flex: none; border-radius: 50%;
  border: 2px solid var(--borde-2); background: var(--panel); display: grid; place-items: center;
}
.opcion-modo:has(input:checked) { border-color: var(--acento); background: var(--acento-suave); }
.opcion-modo:has(input:checked) .radio { border-color: var(--acento); }
.opcion-modo:has(input:checked) .radio::after { content: ""; width: 12px; height: 12px; border-radius: 50%; background: var(--acento); }
.opcion-modo:has(input:focus-visible) { outline: 3px solid var(--foco); outline-offset: 2px; }
.opcion-modo .icono-opcion { width: 30px; height: 30px; color: var(--acento-texto); }
.opcion-texto { min-width: 0; }
.opcion-texto strong { display: block; font-size: 18px; font-weight: 800; color: var(--texto); }
.opcion-texto small { display: block; margin-top: 4px; font-size: 14px; color: var(--muted); }
.opciones-modo.compacto .opcion-modo { padding: 15px 20px; gap: 14px; }
.opciones-modo.compacto .opcion-texto strong { font-size: 15px; }
.opciones-modo.compacto .opcion-texto small { font-size: 13px; }
.opciones-modo.compacto .icono-opcion { width: 24px; height: 24px; }

.grid-archivos { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 340px), 1fr)); gap: 24px; align-items: start; }
.tarjeta-archivo {
  display: grid; gap: 20px; min-width: 0; align-content: start; overflow-wrap: anywhere;
  padding: 26px; border: 1px solid var(--borde); border-radius: 16px; background: var(--panel);
}
.archivo-cabecera { display: flex; align-items: center; gap: 20px; min-width: 0; }
.archivo-cabecera > div { flex: 1; min-width: 0; }
.archivo-cabecera h2 { margin: 0; font-size: 19px; font-weight: 800; }
.archivo-cabecera p { margin: 6px 0 0; color: var(--muted); font-size: 15px; line-height: 1.5; }
.archivo-cabecera .icono-tile { width: 76px; height: 76px; border-radius: 18px; }
.archivo-cabecera .icono-tile .icono { width: 36px; height: 36px; }
.campo-enlace { min-height: 60px; }
.campo-enlace .icono { width: 22px; height: 22px; }

.dropzone {
  display: grid; justify-items: center; gap: 6px; text-align: center;
  padding: 24px 18px; border: 2px dashed var(--acento-borde); border-radius: 14px;
  background: var(--panel-2); cursor: pointer; transition: border-color .15s ease, background .15s ease;
}
.dropzone:hover, .dropzone.arrastrando { border-color: var(--acento); background: var(--acento-suave); }
.dropzone input { display: none; }
.dropzone .icono-drop { width: 34px; height: 34px; color: var(--acento-texto); }
.dropzone strong { font-size: 16px; color: var(--texto); }
.dropzone small { font-size: 14px; color: var(--muted); }
.dropzone .boton { width: min(100%, 280px); margin-top: 10px; padding: 12px 20px; white-space: normal; text-align: center; }
.boton.naranja { background: var(--boton); }

.archivo-listo {
  display: flex; align-items: center; gap: 14px; min-width: 0;
  padding: 12px 14px; border: 1px solid var(--borde); border-radius: 14px; background: var(--panel);
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

.campos-preparacion { display: grid; gap: 12px; }
.campos-preparacion label { display: grid; gap: 6px; font-size: 14px; font-weight: 700; color: var(--texto); }
.campos-preparacion input[type="text"] {
  padding: 11px 13px; border: 1px solid var(--borde); border-radius: 12px;
  background: var(--panel-2); color: var(--texto); font-size: 14.5px; font-family: inherit;
}
.campos-preparacion input[type="text"]:focus { outline: 2px solid var(--acento); outline-offset: 1px; }
.campos-preparacion .nota-campos { font-size: 12.5px; font-weight: 400; color: var(--muted); line-height: 1.5; }

.separador { height: 1px; background: var(--borde); }
.seccion-tipos { display: grid; gap: 18px; }
.titulo-seccion h2 { margin: 0; font-size: 19px; font-weight: 800; }
.titulo-seccion p { margin: 5px 0 0; color: var(--muted); font-size: 14px; }
.titulo-seccion.con-icono { display: flex; align-items: center; gap: 14px; }

.grid-tipos { display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; }
.tarjeta-tipo {
  position: relative; display: flex; flex-direction: column; min-height: 128px;
  padding: 18px; border: 1.5px solid var(--borde); border-radius: 16px; background: var(--panel);
  cursor: pointer; transition: border-color .15s ease, background .15s ease;
}
.tarjeta-tipo:hover { border-color: var(--acento-borde); }
.tarjeta-tipo input { position: absolute; opacity: 0; pointer-events: none; }
.tarjeta-tipo:has(input:focus-visible) { outline: 3px solid var(--foco); outline-offset: 2px; }
.check-personalizado {
  position: absolute; top: 14px; right: 14px; width: 24px; height: 24px;
  border-radius: 7px; display: grid; place-items: center; background: var(--borde-2); color: var(--boton-texto);
}
.check-personalizado .icono { width: 15px; height: 15px; stroke-width: 2.8; }
.tipo-icono { width: 44px; height: 44px; border-radius: 12px; display: grid; place-items: center; margin-bottom: 14px; }
.tipo-icono .icono { width: 24px; height: 24px; }
.tarjeta-tipo strong { font-size: 16px; color: var(--texto); }
.tarjeta-tipo small { margin-top: 5px; color: var(--muted); font-size: 13px; line-height: 1.4; }
.tipo-verde .tipo-icono, .tipo-azul .tipo-icono, .tipo-morado .tipo-icono, .tipo-naranja .tipo-icono { background: var(--acento-suave); color: var(--acento-texto); }
.tarjeta-tipo:has(input:checked) { border-color: var(--acento); background: var(--acento-suave); }
.tarjeta-tipo:has(input:checked) .check-personalizado { background: var(--boton); }

.formato-recurso { display: grid; gap: 12px; }
.formato-titulo { margin: 0; font-size: 14px; color: var(--muted); }
.formato-titulo strong { color: var(--texto); }

#bloque-test { display: grid; gap: 18px; }
#bloque-test[hidden] { display: none; }
#bloque-test .opcion-modo:has(input:checked) { border-color: var(--acento); background: var(--acento-suave); }
#bloque-test .opcion-modo:has(input:checked) .radio { border-color: var(--acento); }
#bloque-test .opcion-modo:has(input:checked) .radio::after { background: var(--acento); }
#bloque-test .opcion-modo .icono-opcion { color: var(--acento-texto); }
#bloque-test .dropzone { border-color: var(--acento-borde); }
#bloque-test .dropzone .icono-drop { color: var(--acento-texto); }
#bloque-test .tarjeta-archivo { padding: 18px; }
.caja-datos {
  display: grid; gap: 16px; padding: 18px;
  border: 1px solid var(--borde); border-radius: 14px; background: var(--panel-2);
}
.caja-datos label { display: block; margin: 0 0 6px; font-size: 14px; font-weight: 700; color: var(--texto-2); }
.caja-datos input, .caja-datos select {
  width: 100%; padding: 12px 14px; border: 1px solid var(--borde-2); border-radius: 12px;
  background: var(--panel); color: var(--texto); font-size: 14px;
}
.caja-datos select { max-width: 280px; cursor: pointer; }
.caja-datos input:focus, .caja-datos select:focus { outline: none; border-color: var(--acento); box-shadow: 0 0 0 4px var(--foco); }
.caja-datos small { display: block; margin-top: 6px; color: var(--muted); font-size: 12.5px; }

.pie-formulario {
  display: grid; grid-template-columns: 1fr auto 1fr; align-items: center; gap: 16px;
  padding: 18px 22px; border: 1px solid var(--borde); border-radius: 16px;
}
.pie-formulario .boton.grande { min-width: min(380px, 100%); }
.nota-seguridad {
  display: flex; align-items: center; justify-content: center; gap: 6px;
  margin: -8px 0 0; color: var(--muted); font-size: 13px;
}
.nota-seguridad .icono { width: 16px; height: 16px; }

/* Guia (dialogo) */
.pasos-guia { list-style: none; margin: 0; padding: 0; display: grid; gap: 14px; }
.pasos-guia li { display: grid; grid-template-columns: 30px 1fr; gap: 12px; align-items: start; color: var(--texto-2); line-height: 1.5; }
.pasos-guia b {
  width: 28px; height: 28px; border-radius: 50%; display: grid; place-items: center;
  background: var(--acento-suave); color: var(--acento-texto); font-size: 13px;
}
.titulo-consejos { margin: 22px 0 10px; font-size: 16px; color: var(--acento-texto); }
.consejos { list-style: none; margin: 0; padding: 0; display: grid; gap: 10px; }
.consejos li { display: flex; gap: 10px; color: var(--texto-2); line-height: 1.5; }
.consejos .icono { width: 18px; height: 18px; margin-top: 2px; color: var(--verde); stroke-width: 2.4; }

/* ---------- Revision del analisis ---------- */
.revision { display: grid; gap: 20px; }
.encabezado-exito { display: flex; align-items: center; gap: 18px; padding: 22px 26px; }
.encabezado-exito h1 { margin: 0; font-size: 26px; font-weight: 800; }
.encabezado-exito p { margin: 6px 0 0; color: var(--muted); }
.resumen-grid { display: grid; grid-template-columns: repeat(6, minmax(110px, 1fr)); gap: 14px; }
.resumen-card {
  padding: 16px; text-align: center; border-radius: 16px;
  background: var(--panel); border: 1px solid var(--borde); box-shadow: var(--sombra);
}
.resumen-card span { display: block; font-size: 13px; color: var(--muted); }
.resumen-card strong { display: block; margin-top: 4px; font-size: 28px; font-weight: 800; color: var(--texto); }
.resumen-card.verde strong { color: var(--verde); }
.resumen-card.azul strong { color: var(--azul); }
.resumen-card.morado strong, .resumen-card.violeta strong { color: var(--morado); }
.resumen-card.rojo strong { color: var(--rojo); }

.test-preparado { display: flex; align-items: center; gap: 16px; flex-wrap: wrap; padding: 20px 22px; border-color: var(--ambar-borde); }
.test-preparado-texto { flex: 1; min-width: 220px; }
.test-preparado h3 { margin: 0 0 4px; font-size: 18px; color: var(--naranja); }
.test-preparado p { margin: 0; color: var(--texto-2); font-size: 14px; }
.revision-h5p { padding: 20px; }
.revision-h5p .tabla-scroll { max-height: 420px; overflow: auto; margin-top: 14px; }
.revision-h5p td { vertical-align: top; min-width: 110px; }
.revision-h5p td:last-child { min-width: 240px; }
.detalle-h5p { display: block; margin-top: 5px; color: var(--muted); white-space: normal; }

.advertencias { overflow: hidden; border-color: var(--ambar-borde); }
.advertencias-cabecera {
  display: flex; gap: 12px; align-items: flex-start; padding: 16px 20px;
  background: var(--ambar-suave); color: var(--ambar); border-bottom: 1px solid var(--ambar-borde);
}
.advertencias-cabecera .icono { width: 22px; height: 22px; margin-top: 1px; }
.advertencias-cabecera strong { font-size: 15px; color: var(--ambar); }
.advertencias-cabecera p { margin: 6px 0 8px; color: var(--muted); font-size: 13px; }
.advertencias-resumen { color: var(--muted); font-size: 12.5px; }
.advertencias-scroll { max-height: 340px; overflow: auto; }
.advertencias .tabla th { position: sticky; top: 0; }

.selector-recursos-panel { padding: 24px; }
.selector-recursos-cabecera { display: flex; justify-content: space-between; gap: 20px; align-items: flex-start; }
.titulo-bloque h2 { margin: 0; font-size: 18px; font-weight: 800; }
.titulo-bloque p { margin: 5px 0 0; color: var(--muted); font-size: 13.5px; }
.selector-recursos-contador { text-align: right; min-width: 170px; }
.selector-recursos-contador strong { display: block; font-size: 20px; color: var(--acento-texto); }
.selector-recursos-contador span { display: block; margin-top: 3px; font-size: 12px; color: var(--muted); }
.filtros-recursos { display: grid; grid-template-columns: repeat(auto-fit, minmax(190px, 1fr)); gap: 10px; margin-top: 18px; }
.filtro-recurso-item {
  position: relative; display: flex; gap: 10px; align-items: center; padding: 12px;
  border: 1px solid var(--borde); border-radius: 12px; background: var(--panel); cursor: pointer;
}
.filtro-recurso-item:hover { border-color: var(--acento-borde); }
.filtro-recurso-item input { position: absolute; opacity: 0; pointer-events: none; }
.filtro-recurso-item:has(input:focus-visible) { outline: 3px solid var(--foco); outline-offset: 2px; }
.filtro-recurso-check {
  width: 22px; height: 22px; flex: none; border-radius: 6px; display: grid; place-items: center;
  background: var(--borde-2); color: var(--boton-texto);
}
.filtro-recurso-check .icono { width: 14px; height: 14px; stroke-width: 2.8; }
.filtro-recurso-item:has(input:checked) { border-color: var(--acento); background: var(--acento-suave); }
.filtro-recurso-item:has(input:checked) .filtro-recurso-check { background: var(--acento); }
.filtro-recurso-texto strong, .filtro-recurso-texto small { display: block; }
.filtro-recurso-texto strong { font-size: 13px; color: var(--texto); }
.filtro-recurso-texto small { margin-top: 2px; font-size: 11.5px; color: var(--muted); }
.selector-recursos-acciones { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 14px; }

.revision-grid { display: grid; grid-template-columns: minmax(0, 1.55fr) minmax(310px, .75fr); gap: 20px; align-items: start; }
.tabla-actividades, .credenciales-panel { padding: 24px; }
.titulo-bloque { margin-bottom: 16px; }
.tabla-revision { max-height: 570px; overflow: auto; border: 1px solid var(--borde); border-radius: 12px; }
.tabla-revision .tabla { font-size: 13px; }
.tabla-revision .tabla th { position: sticky; top: 0; z-index: 1; color: var(--texto-2); font-size: 12px; padding: 12px 13px; }
.tabla-revision .tabla td { padding: 11px 13px; }
.celda-seleccion { width: 48px; text-align: center; }
.actividad-seleccion { width: 18px; height: 18px; accent-color: var(--acento); cursor: pointer; }
.celda-actividad { min-width: 240px; }
.tamano-drive { display: block; margin-top: 4px; color: var(--muted); font-size: 11px; }

.campo-label { display: block; margin: 18px 0 8px; font-size: 13px; font-weight: 700; color: var(--texto-2); }
.campo-moderno {
  display: flex; align-items: center; gap: 10px; padding: 0 14px;
  border: 1px solid var(--borde-2); border-radius: 12px; background: var(--panel); color: var(--muted);
}
.campo-moderno:focus-within { border-color: var(--acento); box-shadow: 0 0 0 4px var(--foco); }
.campo-moderno input { width: 100%; padding: 13px 0; border: 0; outline: 0; background: transparent; color: var(--texto); font-size: 14px; }
.caja-seguridad {
  display: flex; gap: 10px; margin-top: 20px; padding: 14px;
  border: 1px solid var(--acento-borde); border-radius: 12px; background: var(--acento-suave); color: var(--acento-texto);
}
.caja-seguridad strong { display: block; font-size: 13px; color: var(--acento-texto); }
.caja-seguridad span { display: block; margin-top: 4px; font-size: 12.5px; color: var(--muted); line-height: 1.45; }
.boton-iniciar { width: 100%; margin-top: 22px; padding: 15px 20px; font-size: 15px; }
.volver-inicio { justify-self: start; }

@media (max-width: 1200px) {
  .panel-principal .grid-archivos { grid-template-columns: repeat(auto-fit, minmax(min(100%, 300px), 1fr)); }
  .grid-tipos { grid-template-columns: repeat(2, 1fr); }
  .resumen-grid { grid-template-columns: repeat(3, 1fr); }
  .revision-grid { grid-template-columns: 1fr; }
}
@media (max-width: 760px) {
  .encabezado-cargue { align-items: flex-start; gap: 12px; }
  .encabezado-cargue .encabezado-titulo { align-items: flex-start; gap: 12px; }
  .encabezado-cargue h1 { font-size: 26px; }
  .encabezado-cargue p { font-size: 14px; }
  .pasos-cargue { gap: 6px; }
  .pasos-cargue span { padding: 7px 10px; font-size: 12px; }
  .panel-principal { padding: 18px; gap: 18px; }
  .panel-principal .grid-archivos, .opciones-modo { grid-template-columns: minmax(0, 1fr); gap: 14px; }
  .tarjeta-archivo { padding: 18px; gap: 16px; }
  .archivo-cabecera { gap: 12px; }
  .archivo-cabecera .icono-tile { width: 54px; height: 54px; border-radius: 14px; }
  .archivo-cabecera .icono-tile .icono { width: 27px; height: 27px; }
  .archivo-cabecera h2 { font-size: 17px; }
  .archivo-cabecera p { font-size: 14px; }
  .dropzone { padding: 20px 14px; }
  .grid-tipos { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .pie-formulario { grid-template-columns: minmax(0, 1fr); justify-items: stretch; padding: 16px; }
  .pie-formulario .boton.grande { min-width: 0; width: 100%; }
  .resumen-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .opcion-modo { padding: 16px; }
  .selector-recursos-cabecera { flex-direction: column; }
  .selector-recursos-contador { text-align: left; min-width: 0; }
  .tabla-actividades, .credenciales-panel, .selector-recursos-panel { padding: 16px; }
}
@media (max-width: 420px) {
  .panel-principal { padding: 12px; }
  .tarjeta-archivo { padding: 14px; }
  .archivo-listo { gap: 8px; padding: 10px; }
  .archivo-listo-texto strong { font-size: 13px; }
  .grid-tipos, .resumen-grid { grid-template-columns: minmax(0, 1fr); }
}
"""


# ============================================================
# JS PROPIO DE INICIO
# ============================================================

def _js_inicio():
    return _JS_INICIO


_JS_INICIO = r"""
(function () {
  var matriz = document.getElementById('archivo-matriz');
  var zip = document.getElementById('archivo-zip');
  var loader = document.getElementById('prizma-loader');
  var loaderTexto = document.getElementById('prizma-loader-texto');

  function mostrarLoader(texto) {
    if (!loader) return;
    if (loaderTexto && texto) loaderTexto.textContent = texto;
    loader.classList.add('activo');
    loader.setAttribute('aria-hidden', 'false');
  }

  var formularioAnalisis = document.querySelector('form[action="/analizar"]');
  if (formularioAnalisis) {
    formularioAnalisis.addEventListener('submit', function () {
      mostrarLoader('Analizando matriz y recursos...');
    });
  }

  window.addEventListener('pageshow', function () {
    if (!loader) return;
    loader.classList.remove('activo');
    loader.setAttribute('aria-hidden', 'true');
  });

  // ---------- Revision: seleccion de actividades ----------
  var formularioInicio = document.querySelector('form[action^="/iniciar/"]');
  var actividadesSeleccion = Array.prototype.slice.call(document.querySelectorAll('.actividad-seleccion'));
  var filtrosTipoRecurso = Array.prototype.slice.call(document.querySelectorAll('.filtro-tipo-recurso'));
  var contadorSeleccionadas = document.getElementById('contador-seleccionadas');
  var botonSeleccionarTodas = document.getElementById('seleccionar-todas-actividades');
  var botonLimpiarSeleccion = document.getElementById('limpiar-seleccion-actividades');

  function actualizarEstadoSeleccion() {
    var totalMarcadas = actividadesSeleccion.filter(function (item) { return item.checked; }).length;
    if (contadorSeleccionadas) {
      contadorSeleccionadas.textContent = totalMarcadas + ' de ' + actividadesSeleccion.length;
    }
    filtrosTipoRecurso.forEach(function (filtro) {
      var tipo = filtro.dataset.tipoRecurso || '';
      var delTipo = actividadesSeleccion.filter(function (actividad) {
        return (actividad.dataset.tipoRecurso || '') === tipo;
      });
      var marcadas = delTipo.filter(function (actividad) { return actividad.checked; }).length;
      filtro.checked = delTipo.length > 0 && marcadas === delTipo.length;
      filtro.indeterminate = marcadas > 0 && marcadas < delTipo.length;
    });
  }

  filtrosTipoRecurso.forEach(function (filtro) {
    filtro.addEventListener('change', function () {
      var tipo = filtro.dataset.tipoRecurso || '';
      actividadesSeleccion.forEach(function (actividad) {
        if ((actividad.dataset.tipoRecurso || '') === tipo) actividad.checked = filtro.checked;
      });
      actualizarEstadoSeleccion();
    });
  });
  actividadesSeleccion.forEach(function (actividad) {
    actividad.addEventListener('change', actualizarEstadoSeleccion);
  });
  if (botonSeleccionarTodas) {
    botonSeleccionarTodas.addEventListener('click', function () {
      actividadesSeleccion.forEach(function (actividad) { actividad.checked = true; });
      actualizarEstadoSeleccion();
    });
  }
  if (botonLimpiarSeleccion) {
    botonLimpiarSeleccion.addEventListener('click', function () {
      actividadesSeleccion.forEach(function (actividad) { actividad.checked = false; });
      actualizarEstadoSeleccion();
    });
  }
  actualizarEstadoSeleccion();

  if (formularioInicio) {
    formularioInicio.addEventListener('submit', function (evento) {
      var totalMarcadas = actividadesSeleccion.filter(function (item) { return item.checked; }).length;
      if (actividadesSeleccion.length && totalMarcadas === 0) {
        evento.preventDefault();
        alert('Selecciona al menos una actividad para cargar en PRIZMA.');
        return;
      }
      mostrarLoader('Procesando cargue...');
    });
  }

  // ---------- Archivos elegidos ----------
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
    fila.querySelector('[data-detalle]').textContent = tamanoLegible(archivo.size) + ' · Listo para analizar';
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

  // ---------- Test Evaluativo ----------
  var chkTest = document.getElementById('chk-test');
  var bloqueTest = document.getElementById('bloque-test');
  var testDocx = document.getElementById('archivo-test-docx');
  var testDatos = document.getElementById('test-datos-academicos');

  function ajustarRequeridosGenerales() {
    var chkOvi = document.querySelector('input[name="ovi"]');
    var chkOva = document.querySelector('input[name="ova"]');
    var chkRetos = document.querySelector('input[name="retos"]');
    var tieneRecursos = (chkOvi && chkOvi.checked) || (chkOva && chkOva.checked) || (chkRetos && chkRetos.checked);
    if (zip) zip.required = !!tieneRecursos;
    if (matriz) matriz.required = !!tieneRecursos;
  }

  function aplicarModoTest() {
    var activo = !!chkTest && chkTest.checked;
    if (testDocx) {
      testDocx.disabled = !activo;
      testDocx.required = activo;
    }
  }

  function toggleTest() {
    var activo = !!chkTest && chkTest.checked;
    if (bloqueTest) bloqueTest.hidden = !activo;
    if (testDatos) {
      testDatos.disabled = !activo;
      testDatos.required = activo;
    }
    aplicarModoTest();
    ajustarRequeridosGenerales();
  }

  if (chkTest) chkTest.addEventListener('change', toggleTest);
  document.querySelectorAll('input[name="ovi"], input[name="ova"], input[name="retos"]').forEach(function (casilla) {
    casilla.addEventListener('change', ajustarRequeridosGenerales);
  });

  if (chkTest) toggleTest();
})();
"""
