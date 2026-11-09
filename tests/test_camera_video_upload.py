"""Detección de videos a cámara y controles de revisión del cargue."""

import io
import zipfile

from openpyxl import Workbook

from auto_prizma.services.matrix_analysis import detectar_videos_a_camara
from auto_prizma.automation.prizma.engine import (
    _codigo_en_texto,
    _coincide_nombre_tema,
    _consultas_busqueda_tema,
    _extraer_codigo_inicial,
    _valor_codigo_detectado,
)


def _matriz():
    libro = Workbook()
    hoja = libro.active
    hoja.title = "Presupuesto"
    hoja["A4"] = "Semana correspondiente"
    filas = [
        (None, None, "1.1", "Características, Operaciones básicas.", None, None, None),
        ("Semana 1", "Unidad 1", None, "Fundamentos de las listas doblemente enlazadas", "OVI", "Video a cámara", "CLASE1-ESTRUCTURA DE DATOS II_1080p_caption.webm"),
        ("Semana 1", "Unidad 1", None, "Lectura de presupuesto", "OVI", "PDF descargable"),
        (None, None, "1.2", "Estructuras de datos avanzadas", None, None, None),
        ("Semana 7", "Unidad 3", None, "Estrategias de modelado y diseño algorítmico multinivel", "OVI", "Video a cámara", "CLASE2-ESTRUCTURA DE DATOS II_1080p_caption.webm"),
        ("Semana 7", "Unidad 3", None, "Video de cierre", "OVI", "Video cierre"),
    ]
    for fila_num, valores in enumerate(filas, start=5):
        for col, valor in enumerate(valores, start=1):
            hoja.cell(fila_num, col, valor)
    salida = io.BytesIO()
    libro.save(salida)
    return salida.getvalue()


def _zip():
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w") as archivo:
        archivo.writestr("Fundamentos de las listas doblemente enlazadas.webm", b"camera-1")
        archivo.writestr("Estrategias de modelado y diseno algoritmico multinivel.webm", b"camera-2")
        archivo.writestr("video unrelated.webm", b"unrelated")
        archivo.writestr("video_intro.webm", b"intro")
        archivo.writestr("video_cierre.webm", b"closing")
    return salida.getvalue()


def test_detecta_solo_filas_de_video_a_camara_y_ignora_punto_final():
    videos = detectar_videos_a_camara(_matriz(), _zip())

    assert [video["nombre"] for video in videos] == [
        "Características, Operaciones básicas.",
        "Estructuras de datos avanzadas",
    ]
    assert [video["nombre_recurso"] for video in videos] == [
        "Fundamentos de las listas doblemente enlazadas",
        "Estrategias de modelado y diseño algorítmico multinivel",
    ]
    assert [video["miembro_zip"] for video in videos] == [
        "Fundamentos de las listas doblemente enlazadas.webm",
        "Estrategias de modelado y diseno algoritmico multinivel.webm",
    ]
    assert [video["semana"] for video in videos] == ["Semana 1", "Semana 7"]


def test_video_sin_nombre_coincidente_no_se_asocia_por_orden():
    contenido_zip = io.BytesIO()
    with zipfile.ZipFile(contenido_zip, "w") as archivo:
        archivo.writestr("video_intro.webm", b"intro")

    videos = detectar_videos_a_camara(_matriz(), contenido_zip.getvalue())

    assert videos
    assert all(not video["miembro_zip"] for video in videos)


def test_revision_pide_codigos_academicos_si_hay_videos_a_camara():
    from auto_prizma.web.views import generar_html

    pagina = generar_html(
        resultado={
            "hojas": [],
            "zip": {"total": 0},
            "nombre_matriz": "matriz.xlsx",
            "videos_camara": [{
                "nombre": "Características, Operaciones básicas.",
                "nombre_recurso": "Fundamentos de las listas doblemente enlazadas",
                "semana": "Semana 1",
                "miembro_zip": "Fundamentos de las listas doblemente enlazadas.webm",
            }, {
                "nombre": "Estructuras de datos avanzadas",
                "nombre_recurso": "Estrategias de modelado y diseño algorítmico multinivel",
                "semana": "Semana 7",
                "miembro_zip": "Estrategias de modelado y diseno algoritmico multinivel.webm",
            }],
        },
        trabajo_id="job-1",
    )

    assert 'name="codigo_programa_video_camara"' in pagina
    assert 'name="codigo_pensum_video_camara"' in pagina
    assert "videos de intro y cierre no se modifican" in pagina
    assert "Características, Operaciones básicas." in pagina
    assert "Fundamentos de las listas doblemente enlazadas" in pagina
    assert 'data-tipo-recurso="Video a cámara"' in pagina
    assert 'name="videos_camara_seleccionados"' in pagina
    assert 'data-cantidad="2"' in pagina
    assert "2 de 2" in pagina
    assert 'value="1"' in pagina
    assert "<strong>WebM</strong>" in pagina


def test_formulario_inicial_incluye_checkbox_webm_deshabilitado_por_defecto():
    from auto_prizma.web.views import generar_html

    pagina = generar_html()
    assert 'type="checkbox" name="webm" value="1"' in pagina
    assert "Videos a cámara" in pagina
    assert 'name="webm" value="1" checked' not in pagina


def test_pantalla_progreso_incluye_panel_separado_para_videos_a_camara():
    from auto_prizma.api.routes.uploads import _pagina_progreso

    pagina = _pagina_progreso()

    assert 'id="videos-camara-progreso"' in pagina
    assert 'id="lista-videos-camara"' in pagina
    assert "renderizarVideosCamara(datos.videos_camara)" in pagina


def test_selector_horizontal_y_envio_incluyen_videos_a_camara():
    from auto_prizma.web.views import _JS_INICIO

    assert "filtro-videos-camara" in _JS_INICIO
    assert "filtroCamara.checked" in _JS_INICIO
    from auto_prizma.web.views import generar_html
    pagina = generar_html(
        resultado={
            "hojas": [], "zip": {"total": 0}, "nombre_matriz": "matriz.xlsx",
            "videos_camara": [{"nombre": "Tema 1"}, {"nombre": "Tema 2"}],
        },
        trabajo_id="job-1",
    )
    assert 'name="videos_camara_seleccionados"' in pagina
    assert 'data-cantidad="2"' in pagina
    assert 'name="webm"' in _JS_INICIO


def test_codigo_academico_se_compara_como_codigo_completo():
    assert _codigo_en_texto("V1329 - Contaduría pública", "V1329")
    assert _codigo_en_texto("13291 - Pensum", "13291")
    assert _codigo_en_texto(
        "22042 - Pensum tecnología de software (pr2021)", "22042"
    )
    assert _codigo_en_texto(
        "22042 - Pensum tecnología de software", "22042 - Pensum esperado"
    )
    assert not _codigo_en_texto("V13290 - Programa", "V1329")
    assert not _codigo_en_texto("22043 - Pensum tecnología de software", "22042")
    assert _codigo_en_texto("V2204 - Programa con código 9999", "V2204")
    assert _codigo_en_texto("22042 - Pensum (pr2021)", "22042 - otra descripción")
    assert not _codigo_en_texto("Programa V2204", "V2204")
    assert _extraer_codigo_inicial(" V2204 - Programa con código 9999") == "V2204"
    assert _extraer_codigo_inicial("22042 - Pensum (pr2021)") == "22042"
    assert _extraer_codigo_inicial("") == ""


def test_codigo_se_recupera_de_otro_control_si_no_se_detecta_la_etiqueta():
    validacion = {
        "programa": "",
        "pensum": "",
        "seleccionados": [
            "V2204 - Programa ingeniería",
            "22042 - Pensum tecnología (pr2021)",
        ],
    }
    programa = _valor_codigo_detectado(validacion, "programa", "V2204")
    pensum = _valor_codigo_detectado(validacion, "pensum", "22042")

    assert _extraer_codigo_inicial(programa) == "V2204"
    assert _extraer_codigo_inicial(pensum) == "22042"
    assert _valor_codigo_detectado(validacion, "pensum", "99999") == ""


def test_edicion_inspecciona_etiqueta_de_programa_y_pensum_en_ancestros():
    import inspect
    from auto_prizma.automation.prizma import engine

    fuente = inspect.getsource(engine.subir_video_a_tema)
    assert "i < 8" in fuente
    assert "[role=\"combobox\"]" in fuente
    assert "[aria-haspopup=\"listbox\"]" in fuente
    assert "seleccionados" in fuente
    assert "label[for=\"${CSS.escape(campo.id)}\"]" in fuente


def test_campo_de_archivo_se_busca_por_la_etiqueta_recursos():
    from auto_prizma.automation.prizma.engine import find_field_file_input

    class PaginaFalsa:
        def evaluate(self, _script, etiquetas):
            assert etiquetas == ["recursos"]
            return 2

    assert find_field_file_input(PaginaFalsa(), ("recursos",)) == 2


def test_busqueda_tema_conserva_tildes_y_solo_quita_punto_final():
    consultas = _consultas_busqueda_tema("Estrategias de diseño algorítmico.")

    assert consultas == ["Estrategias de diseño algorítmico"]
    assert _consultas_busqueda_tema("Características, Operaciones básicas") == [
        "Características, Operaciones básicas"
    ]


def test_compara_tema_en_filas_html_y_filas_div_sin_celdas():
    objetivo = "Características, Operaciones básicas"

    assert _coincide_nombre_tema(
        ["Características, Operaciones básicas"], "", objetivo
    )
    assert _coincide_nombre_tema(
        [], "Activo\nCaracterísticas, Operaciones básicas\nSEMANA 1", objetivo
    )
    assert _coincide_nombre_tema(
        ["Características, Operaciones básicas."], "", objetivo
    )
    assert not _coincide_nombre_tema(["Otro tema"], "", objetivo)
    # Otros temas contienen el título buscado, pero no son el mismo tema.
    assert not _coincide_nombre_tema(
        ["Características, Operaciones básicas en Multilistas"], "", objetivo
    )
    assert not _coincide_nombre_tema(
        [], "Características, Operaciones básicas en bicolas\nSEMANA 5", objetivo
    )
    assert not _coincide_nombre_tema(
        ["Caracteristicas, Operaciones basicas"], "", objetivo
    )
