"""Pruebas del campo Html al guardar un H5P en PRIZMA.

PRIZMA no permite guardar un H5P si el campo "Html" de la actividad tiene
contenido ("Solo puedes subir un H5P o completar el campo Html, no ambos").

Politica TEMPORAL (config.PRIZMA_VACIAR_HTML_CON_H5P = True): el motor vacia
el Html antes de guardar y deja el contenido previo en el reporte. Con la
politica desactivada cancela sin guardar y reporta ERROR_HTML_Y_H5P.
"""

import pytest

from auto_prizma.automation.prizma import engine

TEXTO_HTML = "Presupuesto: El Poder de Planear"


# ============================================================
# FORMULARIO DE PRIZMA SIMULADO
# ============================================================

class _Aviso:
    def __init__(self, pagina):
        self.pagina = pagina

    def count(self):
        return 1 if self.pagina.aviso_visible else 0

    def nth(self, indice):
        return self

    def is_visible(self):
        return self.pagina.aviso_visible


class _Nada:
    def count(self):
        return 0


class _Editor:
    """Editor del campo Html: textarea o editor tipo contenteditable."""

    def __init__(self, pagina):
        self.pagina = pagina

    def count(self):
        return 1

    @property
    def first(self):
        return self

    def evaluate(self, script):
        if "outerHTML" in script:
            return "<div><p>Html</p><div class='editor'>" + self.pagina.html + "</div></div>"
        return "textarea" if self.pagina.tipo_editor == "textarea" else "div"

    def input_value(self, timeout=None):
        return self.pagina.html

    def inner_text(self, timeout=None):
        return self.pagina.html

    def fill(self, valor):
        if self.pagina.editor_borrable:
            self.pagina.html = valor

    def click(self, timeout=None):
        self.pagina.editor_enfocado = True


class _Teclado:
    def __init__(self, pagina):
        self.pagina = pagina
        self.seleccion = False

    def press(self, tecla):
        if tecla == "Control+A" and self.pagina.editor_enfocado:
            self.seleccion = True
        elif tecla == "Backspace" and self.seleccion and self.pagina.editor_borrable:
            self.pagina.html = ""


class _Boton:
    def __init__(self, pagina):
        self.pagina = pagina

    def click(self, timeout=None):
        self.pagina.clics_guardar += 1
        self.pagina.html_al_guardar.append(self.pagina.html)
        if self.pagina.html:
            # Validacion de PRIZMA: con Html + H5P el formulario no se envia.
            self.pagina.aviso_activado = True


class _Respuesta:
    status = 200
    url = "https://api.prizma.site/academic/activity/20"

    class request:
        method = "PATCH"


class _Espera:
    """expect_response: llega el PATCH solo si el formulario era valido."""

    def __init__(self, pagina):
        self.pagina = pagina
        self.value = None

    def __enter__(self):
        return self

    def __exit__(self, tipo, valor, traza):
        if tipo is not None:
            return False
        if self.pagina.html:
            raise engine.PlaywrightTimeoutError(
                'Timeout 45000ms exceeded while waiting for event "response"'
            )
        self.value = _Respuesta()
        return False


class _PaginaPrizma:
    def __init__(
        self,
        html="",
        aviso_antes=False,
        tipo_editor="textarea",
        editor_borrable=True,
        editor_existe=True,
    ):
        self.html = html
        self.aviso_activado = aviso_antes
        self.tipo_editor = tipo_editor
        self.editor_borrable = editor_borrable
        self.editor_existe = editor_existe
        self.editor_enfocado = False
        self.clics_guardar = 0
        self.html_al_guardar = []
        self.keyboard = _Teclado(self)

    @property
    def aviso_visible(self):
        return self.aviso_activado and bool(self.html)

    def get_by_text(self, texto, exact=False):
        if engine.TEXTO_CONFLICTO_HTML_H5P.lower() in texto.lower():
            return _Aviso(self)
        return _Nada()

    def locator(self, selector):
        if selector in (engine._XPATH_EDITOR_HTML, engine._XPATH_SECCION_HTML):
            return _Editor(self) if self.editor_existe else _Nada()
        return _Nada()

    def expect_response(self, predicado, timeout=None):
        return _Espera(self)

    def wait_for_timeout(self, milisegundos):
        pass


@pytest.fixture
def motor_simulado(monkeypatch, tmp_path):
    """Stubs de navegacion; registra cancelaciones y reaperturas."""
    registro = {"cancelaciones": 0, "reaperturas": 0, "temp": str(tmp_path)}

    class _Campo:
        def set_input_files(self, ruta):
            pass

    def cancelar(pagina):
        registro["cancelaciones"] += 1
        return True

    def reabrir(*args, **kwargs):
        registro["reaperturas"] += 1
        return False

    monkeypatch.setattr(engine, "PRIZMA_VACIAR_HTML_CON_H5P", True)
    monkeypatch.setattr(
        engine,
        "resolver_recurso",
        lambda *a: ({"ruta": "C:/tmp/recurso.h5p", "nombre_original": "recurso.h5p"}, None),
    )
    monkeypatch.setattr(engine, "asegurar_listado", lambda pagina: True)
    monkeypatch.setattr(engine, "entrar_categoria", lambda *a: True)
    monkeypatch.setattr(engine, "buscar_actividad_correcta", lambda *a: ("fila", None))
    monkeypatch.setattr(engine, "abrir_edicion", lambda *a: True)
    monkeypatch.setattr(engine, "detectar_campo_recurso", lambda pagina: _Campo())
    monkeypatch.setattr(engine, "limpiar_descripcion", lambda pagina: (True, None))
    monkeypatch.setattr(engine, "_esperar_archivo_visible", lambda *a, **k: True)
    monkeypatch.setattr(engine, "encontrar_boton_guardar", lambda pagina: _Boton(pagina))
    monkeypatch.setattr(engine, "esperar_patch", lambda *a, **k: None)
    monkeypatch.setattr(engine, "cancelar_edicion_segura", cancelar)
    monkeypatch.setattr(engine, "verificar_guardado_por_reapertura", reabrir)
    monkeypatch.setattr(engine, "_guardar_captura_diagnostico", lambda *a: "")
    return registro


def _procesar(pagina, registro, tipo_archivo="H5P"):
    actividad = {
        "fila_excel": 20,
        "nombre": TEXTO_HTML,
        "categoria_prizma": "OVA",
        "tipo_archivo": tipo_archivo,
    }
    return engine.procesar_actividad(
        pagina, actividad, [], registro["temp"], [], {"activa": False}, [actividad],
    )


# ============================================================
# POLITICA TEMPORAL ACTIVA: SE VACIA EL HTML
# ============================================================

@pytest.mark.parametrize("tipo_editor", ["textarea", "contenteditable"])
def test_html_with_content_is_emptied_before_first_save(motor_simulado, tipo_editor):
    pagina = _PaginaPrizma(html=TEXTO_HTML, tipo_editor=tipo_editor)

    resultado = _procesar(pagina, motor_simulado)

    assert resultado["ok"] is True
    assert resultado["confirmacion"] == "PATCH"
    assert resultado["html_vaciado"] == TEXTO_HTML
    assert pagina.html_al_guardar == [""]  # un solo clic, ya con el Html vacio
    assert motor_simulado["cancelaciones"] == 0


def test_conflict_shown_only_on_save_empties_html_and_retries_once(motor_simulado, monkeypatch):
    # El editor no se encuentra antes de guardar (no se vacia proactivamente),
    # pero si existe cuando PRIZMA muestra el aviso.
    pagina = _PaginaPrizma(html=TEXTO_HTML)
    localizar_original = engine._localizar_editor_html
    llamadas = {"n": 0}

    def localizar_tras_aviso(pag):
        llamadas["n"] += 1
        return None if llamadas["n"] == 1 else localizar_original(pag)

    monkeypatch.setattr(engine, "_localizar_editor_html", localizar_tras_aviso)

    resultado = _procesar(pagina, motor_simulado)

    assert resultado["ok"] is True
    assert resultado["html_vaciado"] == TEXTO_HTML
    assert pagina.html_al_guardar == [TEXTO_HTML, ""]  # primer intento bloqueado, reintento OK
    assert motor_simulado["reaperturas"] == 0


def test_html_that_cannot_be_emptied_cancels_without_saving(motor_simulado, tmp_path):
    pagina = _PaginaPrizma(html=TEXTO_HTML, aviso_antes=True, editor_borrable=False)

    resultado = _procesar(pagina, motor_simulado)

    assert resultado["ok"] is False
    assert resultado["error"].startswith("ERROR_LIMPIANDO_HTML:")
    assert "campo_html_fila_20.html" in resultado["error"]
    assert (tmp_path / "campo_html_fila_20.html").exists()
    assert pagina.clics_guardar == 0
    assert motor_simulado["cancelaciones"] == 1


def test_conflict_without_locatable_editor_cancels_without_saving(motor_simulado):
    pagina = _PaginaPrizma(html=TEXTO_HTML, aviso_antes=True, editor_existe=False)

    resultado = _procesar(pagina, motor_simulado)

    assert resultado["error"].startswith("ERROR_LIMPIANDO_HTML:")
    assert pagina.clics_guardar == 0
    assert motor_simulado["cancelaciones"] == 1


def test_empty_html_saves_normally_without_touching_it(motor_simulado):
    pagina = _PaginaPrizma(html="")

    resultado = _procesar(pagina, motor_simulado)

    assert resultado["ok"] is True
    assert resultado["html_vaciado"] is None
    assert pagina.clics_guardar == 1


def test_pdf_activity_never_touches_html(motor_simulado):
    # La politica es solo para H5P: un PDF no vacia el Html.
    pagina = _PaginaPrizma(html="")
    pagina.html = ""
    resultado = _procesar(pagina, motor_simulado, tipo_archivo="PDF")

    assert resultado["ok"] is True
    assert resultado["html_vaciado"] is None


def test_report_observation_records_previous_html_content():
    observacion = engine._observacion_guardado(
        {"confirmacion": "PATCH", "html_vaciado": "Presupuesto:\n El Poder de Planear"}
    )

    assert observacion == (
        "Carga guardada - PATCH confirmado - se vacio el campo Html "
        '(contenido previo: "Presupuesto: El Poder de Planear")'
    )
    assert engine._observacion_guardado({"confirmacion": "PATCH"}) == (
        "Carga guardada - PATCH confirmado"
    )


# ============================================================
# POLITICA DESACTIVADA: NUNCA SE BORRA EL HTML
# ============================================================

def test_policy_off_conflict_before_save_cancels_with_clear_error(motor_simulado, monkeypatch):
    monkeypatch.setattr(engine, "PRIZMA_VACIAR_HTML_CON_H5P", False)
    pagina = _PaginaPrizma(html=TEXTO_HTML, aviso_antes=True)

    resultado = _procesar(pagina, motor_simulado)

    assert resultado["error"] == engine.ERROR_CONFLICTO_HTML_H5P
    assert pagina.html == TEXTO_HTML  # no se toco
    assert pagina.clics_guardar == 0
    assert motor_simulado["cancelaciones"] == 1


def test_policy_off_conflict_on_save_cancels_without_reopening(motor_simulado, monkeypatch):
    monkeypatch.setattr(engine, "PRIZMA_VACIAR_HTML_CON_H5P", False)
    pagina = _PaginaPrizma(html=TEXTO_HTML)

    resultado = _procesar(pagina, motor_simulado)

    assert resultado["error"] == engine.ERROR_CONFLICTO_HTML_H5P
    assert pagina.html == TEXTO_HTML
    assert pagina.clics_guardar == 1
    assert motor_simulado["reaperturas"] == 0


# ============================================================
# OTRAS GARANTIAS
# ============================================================

def test_conflict_detection_never_raises():
    class _PaginaRota:
        def get_by_text(self, *args, **kwargs):
            raise RuntimeError("Target closed")

    assert engine._conflicto_html_h5p_visible(_PaginaRota()) is False


def test_html_errors_are_not_structural():
    # No deben reiniciar la sesion ni reintentar: requieren accion humana.
    assert engine._es_error_estructural_prizma(engine.ERROR_CONFLICTO_HTML_H5P) is False
    assert engine._es_error_estructural_prizma(engine.ERROR_LIMPIANDO_HTML) is False


def test_html_editor_xpath_is_bounded_between_html_and_recurso_titles():
    # Garantia de seguridad: nunca apunta a la Descripcion ni a campos posteriores.
    assert "normalize-space(text())='Html']/following::" in engine._XPATH_EDITOR_HTML
    assert "[following::*[starts-with(normalize-space(text()), 'Recurso')]][1]" in engine._XPATH_EDITOR_HTML
