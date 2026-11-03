"""Pruebas de la logica pura de la auditoria de cursos de Moodle.

El dominio decide, a partir de lo que el navegador observo, que la semana
se leyo bien, que el recurso del listado no es una etiqueta de bloque y que
la pagina abierta renderiza de verdad (H5P montado, PDF embebido o archivo
descargable validado por separado).
"""

from auto_prizma.domain.moodle_audit import (
    RENDER_NO,
    RENDER_NO_COMPROBABLE,
    RENDER_SI,
    audit_row,
    interpret_activity_probe,
    parse_activity_cards,
    parse_week_links,
    summarize_audit_rows,
)


def _curso_url(seccion):
    return "https://prizma.americana.edu.co/course/view.php?id=42&section=" + str(seccion)


def test_parse_week_links_ordena_por_seccion_y_sin_repetir():
    enlaces = [
        {"text": "Semana 2", "href": _curso_url(2)},
        {"text": "General", "href": _curso_url(0)},
        {"text": "Semana 1", "href": _curso_url(1)},
        {"text": "Semana 2", "href": _curso_url(2) + "#y"},
        {"text": "Foro", "href": "https://prizma.americana.edu.co/mod/forum/view.php?id=9"},
        {"text": "", "href": _curso_url(3)},
    ]

    semanas = parse_week_links(enlaces)

    assert [semana["nombre"] for semana in semanas] == ["General", "Semana 1", "Semana 2"]
    assert semanas[0]["seccion"] == "0"


def test_parse_week_links_vacio_no_explota():
    assert parse_week_links([]) == []
    assert parse_week_links(None) == []


def test_parse_activity_cards_quita_etiquetas_de_bloque():
    tarjetas = [
        {"id": "module-10", "modtype": "label", "titulo": "Recurso educativo digital", "href": ""},
        {"id": "module-11", "modtype": "h5pactivity", "titulo": "Video avatar de bienvenida", "href": _curso_url(1)},
        {"id": "module-12", "modtype": "url", "titulo": "", "href": ""},
        {"id": "", "modtype": "page", "titulo": "Página sin id", "href": _curso_url(1)},
    ]

    recursos = parse_activity_cards(tarjetas, "Semana 1")

    assert [recurso["titulo"] for recurso in recursos] == ["Video avatar de bienvenida"]
    assert recursos[0]["semana"] == "Semana 1"
    assert recursos[0]["tipo"] == "h5pactivity"


def test_parse_activity_prefiere_nombre_visible_ante_etiqueta_tipo_h5p_o_file():
    tarjetas = [
        {"id": "module-20", "modtype": "h5pactivity", "titulos_candidatos": ["H5P", "Clasificación de interesados"], "href": _curso_url(1)},
        {"id": "module-21", "modtype": "resource", "titulos_candidatos": ["File", "Fundamentos para identificar actores clave"], "href": _curso_url(1)},
    ]

    recursos = parse_activity_cards(tarjetas, "Semana 1")

    assert [item["titulo"] for item in recursos] == [
        "Clasificación de interesados", "Fundamentos para identificar actores clave",
    ]


def test_interpretar_h5p_montado_con_texto_renderiza():
    veredicto = interpret_activity_probe({
        "encabezados": ["Video avatar de bienvenida"],
        "texto_cuerpo": "Video avatar de bienvenida Contenido del curso",
        "h5p": {"presente": True, "alto": 640, "texto": "Bienvenidos a este video", "titulo": "Video avatar de bienvenida"},
        "pdf": {"presente": False},
    }, "Video avatar de bienvenida")

    assert veredicto["cargado"] is True
    assert veredicto["renderiza"] == RENDER_SI
    assert veredicto["tipo"] == "h5p"
    assert veredicto["coincide"] is True


def test_interpretar_h5p_prioriza_titulo_que_coincide_con_actividad():
    veredicto = interpret_activity_probe({
        "encabezados": ["Video avatar de bienvenida"],
        "texto_cuerpo": "Contenido",
        "h5p": {
            "presente": True, "alto": 640, "texto": "Bienvenidos",
            "titulo": "Introducción", "titulos": ["Introducción", "Video avatar de bienvenida"],
        },
        "pdf": {"presente": False},
    }, "Video avatar de bienvenida")

    assert veredicto["titulo_interno"] == "Video avatar de bienvenida"
    assert veredicto["coincide"] is True


def test_h5p_en_iframe_inaccesible_no_compara_titulo_exterior_de_moodle():
    veredicto = interpret_activity_probe({
        "encabezados": ["Gestión de Interesados, Comunicaciones y Cultura Organizacional 20262"],
        "texto_cuerpo": "Contenido H5P",
        "h5p": {"presente": True, "alto": 640, "texto": "", "titulo": ""},
        "pdf": {"presente": False},
    }, "Secuencia para incorporar criterios éticos en decisiones sobre interesados")

    fila = audit_row("Semana 1", {"titulo": "Secuencia para incorporar criterios éticos en decisiones sobre interesados"}, veredicto)
    assert fila["coincide"] is None
    assert fila["estado"] == "ok"


def test_timeout_de_apertura_queda_como_revision_y_no_como_recurso_faltante():
    veredicto = interpret_activity_probe({
        "error": "Moodle no terminó de abrir el recurso dentro del tiempo de espera.", "timeout": True,
    }, "Actividad")

    fila = audit_row("Semana 1", {"titulo": "Actividad"}, veredicto)
    assert fila["estado"] == "revisar"
    assert fila["tipo"] == "desconocido"
    assert fila["renderiza"] == RENDER_NO_COMPROBABLE
    assert "tiempo de espera" in fila["detalle"]


def test_timeout_usa_tipo_del_modulo_para_no_reportar_desconocido():
    fila = audit_row(
        "Semana 1", {"titulo": "Lectura", "tipo": "resource"},
        {"cargado": True, "renderiza": RENDER_NO_COMPROBABLE, "tipo": "desconocido",
         "coincide": None, "detalle": "Timeout"},
    )

    assert fila["tipo"] == "archivo"
    assert fila["estado"] == "revisar"


def test_descarga_directa_de_pdf_se_reconoce_como_archivo_y_no_timeout():
    veredicto = interpret_activity_probe({
        "download": {"filename": "guia.pdf", "bytes": b"%PDF-1.4"},
    }, "Guía")

    assert veredicto["tipo"] == "pdf"
    assert veredicto["cargado"] is True
    assert veredicto["renderiza"] == RENDER_NO_COMPROBABLE
    assert "descarga" in veredicto["detalle"]


def test_interpretar_h5p_sin_interior_no_se_puede_comprobar():
    veredicto = interpret_activity_probe({
        "encabezados": [],
        "texto_cuerpo": "Recurso H5P",
        "h5p": {"presente": True, "alto": 0, "texto": "", "titulo": ""},
        "pdf": {"presente": False},
    }, "Recurso H5P")

    assert veredicto["cargado"] is False
    assert veredicto["renderiza"] == RENDER_NO_COMPROBABLE


def test_interpretar_pdf_embebido_renderiza():
    veredicto = interpret_activity_probe({
        "encabezados": ["Lectura guía"],
        "texto_cuerpo": "Lectura guía archivo.pdf",
        "h5p": {"presente": False},
        "pdf": {"presente": True, "embebido": True, "origen": "https://x/file.pdf"},
    }, "Lectura guía")

    assert veredicto["tipo"] == "pdf"
    assert veredicto["renderiza"] == RENDER_SI
    assert veredicto["cargado"] is True


def test_interpretar_pdf_solo_descarga_lo_dice():
    veredicto = interpret_activity_probe({
        "encabezados": ["Lectura guía"],
        "texto_cuerpo": "Lectura guía descargar",
        "h5p": {"presente": False},
        "pdf": {"presente": True, "embebido": False, "origen": "https://x/file.pdf"},
    }, "Lectura guía")

    assert veredicto["renderiza"] == RENDER_NO_COMPROBABLE
    assert "descarga" in veredicto["detalle"]


def test_interpretar_pagina_en_blanco():
    veredicto = interpret_activity_probe({
        "encabezados": [],
        "texto_cuerpo": "   ",
        "h5p": {"presente": False},
        "pdf": {"presente": False},
    }, "Recurso perdido")

    assert veredicto["cargado"] is False
    assert veredicto["renderiza"] == RENDER_NO
    assert "blanco" in veredicto["detalle"]


def test_interpretar_error_de_apertura():
    veredicto = interpret_activity_probe({"error": "No se pudo abrir la actividad: 404"}, "X")

    assert veredicto["cargado"] is False
    assert "404" in veredicto["detalle"]


def test_interpretar_titulo_interno_distinto_al_curso():
    veredicto = interpret_activity_probe({
        "encabezados": ["Título viejo del recurso"],
        "texto_cuerpo": "Título viejo del recurso contenido",
        "h5p": {"presente": False},
        "pdf": {"presente": False},
    }, "Lectura guía")

    assert veredicto["coincide"] is False
    assert "REVISAR" in veredicto["detalle"]


def test_audit_row_cierra_el_veredicto_con_pdf_descargado():
    veredicto = interpret_activity_probe({
        "encabezados": ["Lectura guía"],
        "texto_cuerpo": "Lectura guía descargar",
        "h5p": {"presente": False},
        "pdf": {"presente": True, "embebido": False, "origen": "https://x/file.pdf"},
    }, "Lectura guía")

    fila = audit_row("Semana 1", {"titulo": "Lectura guía"}, veredicto, {
        "ok": True, "paginas": 3, "con_contenido": True,
        "detalle": "PDF con 3 hojas y contenido visible.",
    })

    assert fila["estado"] == "ok"
    assert fila["renderiza"] == RENDER_SI
    assert fila["coincide"] is True


def test_audit_row_pdf_en_blanco_es_revision():
    veredicto = interpret_activity_probe({
        "encabezados": [],
        "texto_cuerpo": "Lectura guía descargar",
        "h5p": {"presente": False},
        "pdf": {"presente": True, "embebido": False, "origen": "https://x/file.pdf"},
    }, "Lectura guía")

    fila = audit_row("Semana 1", {"titulo": "Lectura guía"}, veredicto, {
        "ok": True, "paginas": 1, "con_contenido": False,
        "detalle": "PDF con 1 hoja pero sin texto ni imagenes: parece en blanco.",
    })

    assert fila["estado"] == "revisar"
    assert fila["renderiza"] == RENDER_NO
    assert "en blanco" in fila["detalle"]


def test_audit_row_recurso_inexistente():
    fila = audit_row(
        "Semana 2", {"titulo": "Recurso perdido"},
        {"cargado": False, "renderiza": RENDER_NO, "coincide": None, "detalle": "La página abrió en blanco."},
    )

    assert fila["estado"] == "falta"


def test_summarize_audit_rows_cuenta_por_estado():
    filas = [
        {"estado": "ok"},
        {"estado": "ok"},
        {"estado": "revisar"},
        {"estado": "falta"},
    ]

    resumen = summarize_audit_rows(filas)

    assert resumen == {"ok": 2, "revisar": 1, "falta": 1, "total": 4}
