"""Pruebas de la preparación de la asignatura previa al cargue.

Cubren la detección de videos de intro/cierre en el ZIP, la extracción de
miembros, el antepone de las acciones de preparación en el detalle del
progreso y el bloque de revisión que ve el usuario.
"""

import io
import os
import shutil
import tempfile
import zipfile

from auto_prizma.automation.prizma import engine as motor


def _carpeta_temporal():
    """Carpeta temporal propia (el tmp_path de pytest no siempre es escribible)."""
    return tempfile.mkdtemp(prefix="auto_prizma_prep_")


def _zip_bytes(miembros):
    salida = io.BytesIO()
    with zipfile.ZipFile(salida, "w") as archivo:
        for nombre, contenido in miembros.items():
            archivo.writestr(nombre, contenido)
    return salida.getvalue()


# ============================================================
# DETECCIÓN DE VIDEOS EN EL ZIP
# ============================================================

def test_detect_assignment_videos_finds_intro_and_closing():
    contenido = _zip_bytes({
        "Infografia_de_costos.h5p": b"h5p",
        "Video Introductorio.webm": b"intro",
        "video_cierre.mp4": b"cierre",
    })

    videos = motor.detect_assignment_videos(contenido)

    assert videos == {"intro": "Video Introductorio.webm", "closing": "video_cierre.mp4"}


def test_detect_assignment_videos_ignores_non_video_files():
    contenido = _zip_bytes({
        "introductorio.pdf": b"pdf",
        "cierre.docx": b"docx",
        "Lectura guía.pdf": b"%PDF",
    })

    assert motor.detect_assignment_videos(contenido) == {"intro": "", "closing": ""}


def test_detect_assignment_videos_accepts_path_and_handles_bad_zip():
    carpeta = _carpeta_temporal()
    try:
        ruta = os.path.join(carpeta, "recursos.zip")
        with open(ruta, "wb") as archivo:
            archivo.write(_zip_bytes({"intro_final.mov": b"v"}))

        assert motor.detect_assignment_videos(ruta) == {
            "intro": "intro_final.mov",
            "closing": "",
        }

        # Un ZIP ilegible no lanza: la preparación simplemente queda vacía.
        assert motor.detect_assignment_videos(b"esto no es un zip") == {"intro": "", "closing": ""}
    finally:
        shutil.rmtree(carpeta, ignore_errors=True)


def test_detect_assignment_videos_picks_first_match_per_slot():
    contenido = _zip_bytes({
        "intro_a.webm": b"a",
        "intro_b.webm": b"b",
        "cierre.mp4": b"c",
        "closing_extra.mp4": b"d",
    })

    videos = motor.detect_assignment_videos(contenido)

    assert videos["intro"] == "intro_a.webm"
    assert videos["closing"] == "cierre.mp4"


# ============================================================
# EXTRACCIÓN DE MIEMBROS DEL ZIP
# ============================================================

def test_extract_zip_member_extracts_file():
    carpeta = _carpeta_temporal()
    try:
        ruta_zip = os.path.join(carpeta, "recursos.zip")
        with open(ruta_zip, "wb") as archivo:
            archivo.write(_zip_bytes({"Video Introductorio.webm": b"intro"}))
        destino = os.path.join(carpeta, "temp", "intro.webm")

        extraido, motivo = motor.extract_zip_member(ruta_zip, "Video Introductorio.webm", destino)

        assert motivo is None
        assert extraido == destino
        with open(destino, "rb") as archivo:
            assert archivo.read() == b"intro"
    finally:
        shutil.rmtree(carpeta, ignore_errors=True)


def test_extract_zip_member_reports_missing_member():
    carpeta = _carpeta_temporal()
    try:
        ruta_zip = os.path.join(carpeta, "recursos.zip")
        with open(ruta_zip, "wb") as archivo:
            archivo.write(_zip_bytes({"otro.pdf": b"x"}))

        extraido, motivo = motor.extract_zip_member(
            ruta_zip, "no_existe.webm", os.path.join(carpeta, "v.webm")
        )

        assert extraido is None
        assert motivo
    finally:
        shutil.rmtree(carpeta, ignore_errors=True)


# ============================================================
# DETALLE DEL PROGRESO (acciones de preparación)
# ============================================================

def test_preparation_details_are_prepended_with_number_zero():
    estado = {
        "detalle_actividades": [
            {"numero": 1, "nombre": "Actividad 1", "estado": "pendiente", "error": ""},
            {"numero": 2, "nombre": "Actividad 2", "estado": "pendiente", "error": ""},
        ]
    }
    acciones = [
        {"nombre": "Syllabus", "estado": "ok", "detalle": "Cargado."},
        {"nombre": "Video de cierre", "estado": "error", "detalle": "Fallo."},
    ]

    motor.set_preparation_details(estado, acciones)

    detalle = estado["detalle_actividades"]
    assert [fila["numero"] for fila in detalle] == [0, 0, 1, 2]
    assert detalle[0]["nombre"] == "Preparación: Syllabus"
    assert detalle[1]["estado"] == "error"
    assert detalle[1]["error"] == "Fallo."


def test_update_detail_activity_matches_by_number_not_position():
    estado = {
        "detalle_actividades": [
            {"numero": 0, "nombre": "Preparación: Syllabus", "estado": "pendiente", "error": ""},
            {"numero": 1, "nombre": "Actividad 1", "estado": "pendiente", "error": ""},
        ]
    }

    motor.actualizar_detalle_actividad(estado, 1, "ok")

    assert estado["detalle_actividades"][0]["estado"] == "pendiente"
    assert estado["detalle_actividades"][1]["estado"] == "ok"


def test_preparation_details_keep_list_unchanged_when_empty():
    estado = {"detalle_actividades": [{"numero": 1, "nombre": "A", "estado": "pendiente", "error": ""}]}

    motor.set_preparation_details(estado, [])

    assert len(estado["detalle_actividades"]) == 1


# ============================================================
# ALMACENAMIENTO DEL TRABAJO (upload_jobs)
# ============================================================

def _limpiar_trabajo(upload_jobs, trabajo_id):
    trabajo = upload_jobs.TRABAJOS.pop(trabajo_id, None) or {}
    for carpeta in (
        os.path.dirname(trabajo.get("ruta_excel") or ""),
        trabajo.get("carpeta_temp"),
    ):
        if carpeta and os.path.basename(carpeta) == trabajo_id:
            shutil.rmtree(carpeta, ignore_errors=True)


def test_create_analyzed_job_stores_syllabus_and_prep_data():
    from auto_prizma.services import upload_jobs

    contenido_zip = _zip_bytes({
        "Infografia_de_costos.h5p": b"h5p",
        "Video Introductorio.webm": b"intro",
    })

    trabajo_id, resultado = upload_jobs.create_analyzed_job(
        b"xlsx", contenido_zip,
        [{"curso": "C", "programa": "P", "actividades": [{}]}],
        {"total": 1}, "Curso A", True, True, True, "adminlocal",
        contenido_syllabus=b"%PDF syllabus",
        nombre_syllabus="syllabus.pdf",
        linea_academica="V1130 11301 30S01 COMPETENCIAS",
        nivel_pensum="Nivel 1",
    )

    try:
        trabajo = upload_jobs.TRABAJOS[trabajo_id]

        assert trabajo["ruta_syllabus"].endswith("syllabus.pdf")
        assert os.path.isfile(trabajo["ruta_syllabus"])

        preparacion = trabajo["preparacion"]
        assert preparacion["syllabus"] is True
        assert preparacion["video_intro"] == "Video Introductorio.webm"
        assert preparacion["nivel"] == "Nivel 1"
        assert preparacion["curso"]["codigo_asignatura"] == "30S01"
        assert resultado["preparacion"] == preparacion
    finally:
        _limpiar_trabajo(upload_jobs, trabajo_id)


def test_create_analyzed_job_parses_line_only_with_level():
    from auto_prizma.services import upload_jobs

    trabajo_id, _ = upload_jobs.create_analyzed_job(
        b"xlsx", _zip_bytes({"a.h5p": b"h5p"}),
        [{"curso": "C", "programa": "P", "actividades": [{}]}],
        {"total": 1}, "Curso A", True, True, True, "adminlocal",
        linea_academica="V1130 11301 30S01 COMPETENCIAS",
    )

    try:
        # Sin nivel de pensum no hay curso para preparar.
        assert upload_jobs.TRABAJOS[trabajo_id]["preparacion"]["curso"] is None
    finally:
        _limpiar_trabajo(upload_jobs, trabajo_id)


# ============================================================
# BLOQUE DE REVISIÓN (web)
# ============================================================

def test_preparation_block_shows_actions_when_line_present():
    from auto_prizma.web.views import _preparation_block

    bloque = _preparation_block({
        "syllabus": True,
        "video_intro": "Video Introductorio.webm",
        "video_cierre": "",
        "linea_academica": "V1130 11301 30S01 COMPETENCIAS",
        "nivel": "Nivel 1",
        "curso": {"asignatura": "COMPETENCIAS"},
    })

    assert "Preparación de la asignatura" in bloque
    assert "Video Introductorio.webm" in bloque
    assert "Syllabus" in bloque
    # La descripción se deja vacía, no solo se borra el placeholder.
    assert "dejará el campo vacío" in bloque
    assert "Preparación omitida" not in bloque


def test_preparation_block_warns_when_videos_without_line():
    from auto_prizma.web.views import _preparation_block

    bloque = _preparation_block({
        "syllabus": False,
        "video_intro": "intro.webm",
        "video_cierre": "cierre.mp4",
        "linea_academica": "",
        "nivel": "",
        "curso": None,
    })

    assert "Preparación omitida" in bloque
    assert "sin línea académica no se cargan" in bloque


def test_preparation_block_hidden_without_anything_to_prepare():
    from auto_prizma.web.views import _preparation_block

    vacio = {
        "syllabus": False,
        "video_intro": "",
        "video_cierre": "",
        "linea_academica": "",
        "nivel": "",
        "curso": None,
    }

    assert _preparation_block(vacio) == ""
    assert _preparation_block(None) == ""


# ============================================================
# DESCRIPCIÓN DEL CURSO (dejar el campo vacío)
# ============================================================

class _EditorFalso:
    """contenteditable falso; Backspace limpia salvo que resista."""

    def __init__(self, texto, resiste=False):
        self.texto = texto
        self.resiste = resiste
        self.vaciado_por_js = False

    def is_visible(self):
        return True

    def inner_text(self):
        return self.texto

    def click(self):
        pass

    def press(self, tecla):
        if tecla == "Backspace" and not self.resiste:
            self.texto = ""

    def wait_for(self, **kwargs):
        pass


class _ListaEditoresFalsa:
    def __init__(self, editores):
        self._editores = editores

    def count(self):
        return len(self._editores)

    def nth(self, indice):
        return self._editores[indice]


class _PaginaFalsa:
    def __init__(self, editores, ignora_js=False):
        self._editores = editores
        self._ignora_js = ignora_js

    def locator(self, selector):
        return _ListaEditoresFalsa(self._editores)

    def wait_for_timeout(self, ms):
        pass

    def evaluate(self, script, indice):
        # Respaldo JS: vacía el editor indicado (o no, si la página ignora).
        if not self._ignora_js:
            self._editores[indice].texto = ""
            self._editores[indice].vaciado_por_js = True


def test_empty_description_field_reports_omitted_when_already_empty():
    from auto_prizma.automation.prizma import engine as motor

    pagina = _PaginaFalsa([_EditorFalso("")])

    estado, detalle = motor.empty_description_field(pagina)

    assert estado == "omitido"
    assert "ya estaba vacía" in detalle


def test_empty_description_field_clears_any_text():
    from auto_prizma.automation.prizma import engine as motor

    editor = _EditorFalso("Prueba")
    pagina = _PaginaFalsa([editor])

    estado, detalle = motor.empty_description_field(pagina)

    # No importa el texto: el campo queda vacío (antes solo se borraba
    # el placeholder «No disponible»).
    assert estado == "ok"
    assert "Prueba" in detalle
    assert editor.texto == ""


def test_empty_description_field_uses_js_fallback_when_backspace_fails():
    from auto_prizma.automation.prizma import engine as motor

    editor = _EditorFalso("NO_DISPONIBLE", resiste=True)
    pagina = _PaginaFalsa([editor])

    estado, detalle = motor.empty_description_field(pagina)

    assert estado == "ok"
    assert editor.texto == ""
    assert editor.vaciado_por_js is True


def test_empty_description_field_fails_when_text_remains():
    from auto_prizma.automation.prizma import engine as motor

    editor = _EditorFalso("Texto que no se va", resiste=True)
    pagina = _PaginaFalsa([editor], ignora_js=True)

    estado, detalle = motor.empty_description_field(pagina)

    assert estado == "error"
    assert "No se pudo vaciar" in detalle


def test_empty_description_field_fails_without_editors():
    from auto_prizma.automation.prizma import engine as motor

    estado, detalle = motor.empty_description_field(_PaginaFalsa([]))

    assert estado == "error"
    assert "no se encontró el campo de descripción" in detalle
