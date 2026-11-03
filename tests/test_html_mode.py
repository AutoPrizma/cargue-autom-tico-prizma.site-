"""Pruebas del modo de carga HTML (pegar el codigo del .html en el campo Html).

Decisiones del usuario (2026-10-06): los .html llegan en el ZIP, se llaman
igual que la actividad, se pega el archivo completo y, si la actividad ya
tiene un archivo en "Recurso", se quita (config.PRIZMA_VACIAR_RECURSO_CON_HTML);
desde el 2026-10-07, cualquier archivo, no solo .h5p.
En modo HTML el campo Html que se acaba de pegar NUNCA se borra.
"""

import zipfile

import pytest

from auto_prizma.automation.prizma import engine, html_field
from auto_prizma.services import upload_jobs

resolver_recurso = engine.resolver_recurso

CODIGO = "<html>\n<head><style>h1{color:#123}</style></head>\n<body><h1>Presupuesto & más</h1></body>\n</html>\n"


# ============================================================
# FORMULARIO DE PRIZMA SIMULADO (campo Html + tarjeta H5P)
# ============================================================

class _Nada:
    def count(self):
        return 0


class _Aviso:
    def __init__(self, pagina):
        self.pagina = pagina

    def count(self):
        return 1 if self.pagina.aviso_visible else 0

    def nth(self, indice):
        return self

    def is_visible(self):
        return self.pagina.aviso_visible


class _EditorHtml:
    def __init__(self, pagina):
        self.pagina = pagina

    def count(self):
        return 1

    @property
    def first(self):
        return self

    def evaluate(self, script):
        if "outerHTML" in script:
            return "<section><p>Html</p><textarea>" + self.pagina.html + "</textarea></section>"
        if "className" in script:
            return '<div class="ql-editor">' if self.pagina.tipo_editor != "textarea" else "<textarea>"
        return "textarea" if self.pagina.tipo_editor == "textarea" else "div"

    def fill(self, valor):
        if self.pagina.maxlength is not None:
            valor = valor[:self.pagina.maxlength]
        # Un textarea del navegador normaliza CRLF a LF.
        self.pagina.html = valor.replace("\r\n", "\n")

    def input_value(self, timeout=None):
        return self.pagina.html

    def inner_text(self, timeout=None):
        return self.pagina.html

    def click(self, timeout=None):
        pass


class _TarjetaArchivo:
    """div.fileItem del campo Recurso (solo existe si hay un archivo cargado)."""

    def __init__(self, pagina):
        self.pagina = pagina

    def count(self):
        return 1 if self.pagina.archivo_visible_ahora else 0

    @property
    def first(self):
        return self

    def nth(self, indice):
        return self

    def is_visible(self):
        return self.pagina.archivo_visible_ahora

    def inner_text(self, timeout=None):
        return self.pagina.archivo


class _BotonTarjeta:
    def __init__(self, pagina, indice):
        self.pagina = pagina
        self.indice = indice

    def click(self, timeout=None):
        if self.indice == 0:
            self.pagina.descarga_pulsada = True  # boton descargar
            return
        self.pagina.clics_quitar += 1  # papelera
        if self.pagina.con_dialogo:
            self.pagina.dialogo_abierto = True


class _BotonesTarjeta:
    def __init__(self, pagina):
        self.pagina = pagina

    def count(self):
        return 2 if self.pagina.archivo_visible_ahora else 0

    def nth(self, indice):
        return _BotonTarjeta(self.pagina, indice)


class _TextoDialogo:
    def __init__(self, pagina):
        self.pagina = pagina

    def count(self):
        return 1 if self.pagina.dialogo_abierto else 0

    @property
    def first(self):
        return self

    def is_visible(self):
        return self.pagina.dialogo_abierto


class _BotonEliminar(_TextoDialogo):
    def nth(self, indice):
        return self

    def click(self, timeout=None):
        self.pagina.dialogo_abierto = False
        if self.pagina.archivo_quitable:
            self.pagina.archivo = ""


class _SeccionRecurso:
    def count(self):
        return 1

    @property
    def first(self):
        return self

    def evaluate(self, script):
        return "<section><p>Recurso (H5P)</p><div>tarjeta</div></section>"


class _BotonGuardar:
    def __init__(self, pagina):
        self.pagina = pagina

    def click(self, timeout=None):
        self.pagina.clics_guardar += 1
        self.pagina.html_al_guardar.append(self.pagina.html)
        self.pagina.intentos_guardar += 1
        if self.pagina.tiene_archivo and self.pagina.html:
            # Validacion de PRIZMA: H5P + Html no se puede guardar.
            self.pagina.aviso_activado = True


class _Respuesta:
    status = 200
    url = "https://api.prizma.site/academic/activity/20"

    class request:
        method = "PATCH"


class _Espera:
    def __init__(self, pagina):
        self.pagina = pagina
        self.value = None

    def __enter__(self):
        return self

    def __exit__(self, tipo, valor, traza):
        if tipo is not None:
            return False
        if self.pagina.tiene_archivo and self.pagina.html:
            raise engine.PlaywrightTimeoutError('Timeout 45000ms exceeded while waiting for event "response"')
        self.value = _Respuesta()
        return False


class _PaginaPrizma:
    def __init__(
        self,
        html_previo="",
        h5p_cargado=False,
        archivo_recurso=None,
        archivo_detectable=True,
        tarjeta_tras_guardar=False,
        archivo_quitable=True,
        con_dialogo=True,
        tipo_editor="textarea",
        maxlength=None,
    ):
        self.html = html_previo
        if archivo_recurso is None:
            archivo_recurso = "Presupuestar Paso a Paso.h5p" if h5p_cargado else ""
        self.archivo = archivo_recurso
        self.archivo_detectable = archivo_detectable
        self.tarjeta_tras_guardar = tarjeta_tras_guardar
        self.archivo_quitable = archivo_quitable
        self.con_dialogo = con_dialogo
        self.dialogo_abierto = False
        self.descarga_pulsada = False
        self.tipo_editor = tipo_editor
        self.maxlength = maxlength
        self.aviso_activado = False
        self.clics_guardar = 0
        self.clics_quitar = 0
        self.intentos_guardar = 0
        self.html_al_guardar = []

    @property
    def tiene_archivo(self):
        return bool(self.archivo)

    @property
    def archivo_visible_ahora(self):
        if not self.archivo:
            return False
        if self.tarjeta_tras_guardar:
            return self.intentos_guardar > 0
        return self.archivo_detectable

    @property
    def aviso_visible(self):
        return self.aviso_activado and self.tiene_archivo and bool(self.html)

    def get_by_text(self, texto, exact=False):
        if engine.TEXTO_CONFLICTO_HTML_H5P.lower() in texto.lower():
            return _Aviso(self)
        if html_field.TEXTO_CONFIRMAR_ELIMINACION.lower() in texto.lower():
            return _TextoDialogo(self)
        return _Nada()

    def get_by_role(self, rol, name=None, exact=False):
        if rol == "button" and name == "Eliminar":
            return _BotonEliminar(self)
        return _Nada()

    def locator(self, selector):
        if selector in (engine._XPATH_EDITOR_HTML, engine._XPATH_SECCION_HTML):
            return _EditorHtml(self)
        if selector in (html_field.XPATH_TARJETA_ARCHIVO_RECURSO, html_field._XPATH_NOMBRE_ARCHIVO_RECURSO):
            return _TarjetaArchivo(self)
        if selector == html_field._XPATH_BOTONES_TARJETA_RECURSO:
            return _BotonesTarjeta(self)
        if selector == html_field.XPATH_SECCION_RECURSO:
            return _SeccionRecurso()
        return _Nada()

    def expect_response(self, predicado, timeout=None):
        return _Espera(self)

    def wait_for_timeout(self, milisegundos):
        pass


@pytest.fixture
def motor_html(monkeypatch, tmp_path):
    registro = {"cancelaciones": 0, "reaperturas": 0, "temp": str(tmp_path)}
    archivo = tmp_path / "Presupuestar Paso a Paso.html"
    # Bytes exactos: write_text traduciria los saltos de linea a CRLF en Windows.
    archivo.write_bytes(CODIGO.encode("utf-8"))
    registro["archivo"] = archivo

    def cancelar(pagina):
        registro["cancelaciones"] += 1
        return True

    def reabrir(*args, **kwargs):
        registro["reaperturas"] += 1
        return False

    def no_usar_campo_de_archivo(pagina):
        raise AssertionError("en modo HTML no se usa el campo de archivo Recurso")

    monkeypatch.setattr(engine, "PRIZMA_VACIAR_RECURSO_CON_HTML", True)
    monkeypatch.setattr(
        engine,
        "resolver_recurso",
        lambda *a: ({"ruta": str(registro["archivo"]), "nombre_original": registro["archivo"].name}, None),
    )
    monkeypatch.setattr(engine, "asegurar_listado", lambda pagina: True)
    monkeypatch.setattr(engine, "entrar_categoria", lambda *a: True)
    monkeypatch.setattr(engine, "buscar_actividad_correcta", lambda *a: ("fila", None))
    monkeypatch.setattr(engine, "abrir_edicion", lambda *a: True)
    monkeypatch.setattr(engine, "detectar_campo_recurso", no_usar_campo_de_archivo)
    monkeypatch.setattr(engine, "limpiar_descripcion", lambda pagina: (True, None))
    monkeypatch.setattr(engine, "encontrar_boton_guardar", lambda pagina: _BotonGuardar(pagina))
    monkeypatch.setattr(engine, "esperar_patch", lambda *a, **k: None)
    monkeypatch.setattr(engine, "cancelar_edicion_segura", cancelar)
    monkeypatch.setattr(engine, "verificar_guardado_por_reapertura", reabrir)
    monkeypatch.setattr(engine, "_guardar_captura_diagnostico", lambda *a: "")
    return registro


def _procesar(pagina, registro):
    actividad = {
        "fila_excel": 19,
        "nombre": "Presupuestar Paso a Paso",
        "categoria_prizma": "OVA",
        "tipo_archivo": "HTML",
    }
    return engine.procesar_actividad(
        pagina, actividad, [], registro["temp"], [], {"activa": False}, [actividad],
    )


# ============================================================
# PEGAR EL HTML EN PRIZMA
# ============================================================

def test_html_is_pasted_verified_and_saved(motor_html):
    pagina = _PaginaPrizma()

    resultado = _procesar(pagina, motor_html)

    assert resultado["ok"] is True
    assert resultado["confirmacion"] == "PATCH"
    assert pagina.html == CODIGO
    assert pagina.html_al_guardar == [CODIGO]
    assert resultado["html_pegado"] == {"caracteres": len(CODIGO), "reemplazo_previo": False}
    assert resultado["recurso_quitado"] == ""
    assert motor_html["cancelaciones"] == 0


def test_html_replaces_previous_html_content(motor_html):
    pagina = _PaginaPrizma(html_previo="Presupuestar Paso a Paso")

    resultado = _procesar(pagina, motor_html)

    assert resultado["ok"] is True
    assert pagina.html == CODIGO
    assert resultado["html_pegado"]["reemplazo_previo"] is True


def test_crlf_file_is_accepted(motor_html):
    motor_html["archivo"].write_bytes(CODIGO.replace("\n", "\r\n").encode("utf-8"))
    pagina = _PaginaPrizma()

    resultado = _procesar(pagina, motor_html)

    assert resultado["ok"] is True
    assert resultado["html_pegado"]["caracteres"] == len(CODIGO)


@pytest.mark.parametrize(
    "nombre",
    [
        "Presupuestar Paso a Paso.h5p",
        "Archivo",  # nombre generico que muestra PRIZMA (ambiente de pruebas, 2026-10-07)
        "Infografia de costos.png",
    ],
)
def test_any_file_in_recurso_is_removed_before_pasting(motor_html, nombre):
    pagina = _PaginaPrizma(archivo_recurso=nombre)

    resultado = _procesar(pagina, motor_html)

    assert resultado["ok"] is True
    assert resultado["recurso_quitado"] == nombre
    assert pagina.tiene_archivo is False
    assert pagina.clics_quitar == 1  # papelera + confirmacion "Eliminar"
    assert pagina.descarga_pulsada is False  # nunca el boton de descarga
    assert pagina.html_al_guardar == [CODIGO]  # un solo guardado, ya sin archivo


def test_file_detected_only_on_save_is_removed_and_html_is_never_cleared(motor_html):
    pagina = _PaginaPrizma(h5p_cargado=True, tarjeta_tras_guardar=True)

    resultado = _procesar(pagina, motor_html)

    assert resultado["ok"] is True
    assert resultado["recurso_quitado"] == "Presupuestar Paso a Paso.h5p"
    # Primer guardado bloqueado por PRIZMA, reintento OK: el Html se conserva.
    assert pagina.html_al_guardar == [CODIGO, CODIGO]
    assert motor_html["reaperturas"] == 0


def test_file_that_cannot_be_removed_cancels_without_saving(motor_html, tmp_path):
    pagina = _PaginaPrizma(h5p_cargado=True, archivo_quitable=False)

    resultado = _procesar(pagina, motor_html)

    assert resultado["ok"] is False
    assert resultado["error"].startswith("ERROR_QUITANDO_RECURSO:")
    assert "campo_recurso_fila_19.html" in resultado["error"]
    assert (tmp_path / "campo_recurso_fila_19.html").exists()
    assert pagina.clics_guardar == 0
    assert motor_html["cancelaciones"] == 1


def test_file_undetectable_before_and_after_save_cancels_keeping_html(motor_html):
    pagina = _PaginaPrizma(h5p_cargado=True, archivo_detectable=False)

    resultado = _procesar(pagina, motor_html)

    assert resultado["error"].startswith("ERROR_QUITANDO_RECURSO:")
    assert "no se ve ningun archivo en Recurso" in resultado["error"]
    assert pagina.html_al_guardar == [CODIGO]  # se intento una vez y nunca se borro el Html
    assert motor_html["cancelaciones"] == 1


def test_policy_off_never_removes_the_recurso_file(motor_html, monkeypatch):
    monkeypatch.setattr(engine, "PRIZMA_VACIAR_RECURSO_CON_HTML", False)
    pagina = _PaginaPrizma(archivo_recurso="Archivo")

    resultado = _procesar(pagina, motor_html)

    assert resultado["error"] == engine.ERROR_RECURSO_Y_HTML
    assert pagina.tiene_archivo is True
    assert pagina.clics_quitar == 0 and pagina.clics_guardar == 0


def test_unsupported_editor_cancels_without_saving(motor_html, tmp_path):
    pagina = _PaginaPrizma(tipo_editor="contenteditable")

    resultado = _procesar(pagina, motor_html)

    assert resultado["error"].startswith('ERROR_ESCRIBIENDO_HTML: editor no soportado <div class="ql-editor">')
    assert (tmp_path / "campo_html_fila_19.html").exists()
    assert pagina.clics_guardar == 0
    assert motor_html["cancelaciones"] == 1


def test_truncated_paste_is_detected_before_saving(motor_html):
    pagina = _PaginaPrizma(maxlength=10)

    resultado = _procesar(pagina, motor_html)

    assert f"el campo Html quedo con 10 caracteres y el archivo tiene {len(CODIGO)}" in resultado["error"]
    assert pagina.clics_guardar == 0


def test_non_utf8_file_cancels_without_touching_prizma(motor_html):
    motor_html["archivo"].write_bytes("<p>Gestión</p>".encode("cp1252"))
    pagina = _PaginaPrizma()

    resultado = _procesar(pagina, motor_html)

    assert resultado["error"] == "ERROR_HTML_NO_ES_UTF8"
    assert pagina.html == "" and pagina.clics_guardar == 0


def test_invalid_html_file_never_removes_the_recurso_file(motor_html):
    # El .html se lee antes de tocar el formulario: si no sirve, el archivo
    # de "Recurso" se queda donde estaba.
    motor_html["archivo"].write_bytes(b"   \n")
    pagina = _PaginaPrizma(archivo_recurso="Archivo")

    resultado = _procesar(pagina, motor_html)

    assert resultado["error"] == "ERROR_HTML_VACIO"
    assert pagina.archivo == "Archivo"
    assert pagina.clics_quitar == 0 and pagina.clics_guardar == 0
    assert motor_html["cancelaciones"] == 1


# ============================================================
# ARCHIVOS, EMPAREJAMIENTO Y FORMATO
# ============================================================

def test_leer_archivo_html(tmp_path):
    con_bom = tmp_path / "a.html"
    con_bom.write_bytes(b"\xef\xbb\xbf<p>Hola</p>")
    vacio = tmp_path / "b.html"
    vacio.write_text("  \n", encoding="utf-8")

    assert html_field.leer_archivo_html(str(con_bom)) == ("<p>Hola</p>", None)
    assert html_field.leer_archivo_html(str(vacio)) == (None, "ERROR_HTML_VACIO")
    assert html_field.leer_archivo_html(str(tmp_path / "no.html")) == (None, "ERROR_LEYENDO_HTML")


def test_zip_index_accepts_html_and_htm(tmp_path):
    ruta = tmp_path / "recursos.zip"
    with zipfile.ZipFile(ruta, "w") as archivo:
        archivo.writestr("html/Infografía de costos.html", "<p>1</p>")
        archivo.writestr("html/Lectura.HTM", "<p>2</p>")
        archivo.writestr("notas.txt", "x")

    indice = engine.crear_indice_recursos(str(ruta))

    assert [(r["nombre"], r["extension"]) for r in indice] == [
        ("Infografía de costos.html", ".html"),
        ("Lectura.HTM", ".html"),
    ]


def test_resolver_finds_html_file_by_activity_name(tmp_path):
    ruta = tmp_path / "recursos.zip"
    with zipfile.ZipFile(ruta, "w") as archivo:
        archivo.writestr("html/Infografia_de_costos.html", "<p>costos</p>")
        archivo.writestr("Infografia_de_costos.h5p", b"h5p")
    actividad = {
        "fila_excel": 5, "hoja": "Curso A", "programa": "P", "curso": "C", "semana": "1",
        "unidad": "Unidad 1", "nombre": "Infografía de costos", "categoria_prizma": "OVI",
        "tipo_recurso": "Infografía", "tipo_archivo": "HTML", "enlace": "",
    }
    carpeta = tmp_path / "extraccion"
    carpeta.mkdir()

    recurso, error = resolver_recurso(actividad, engine.crear_indice_recursos(str(ruta)), str(carpeta), [actividad])

    assert error is None
    assert recurso["nombre_original"] == "Infografia_de_costos.html"
    assert open(recurso["ruta"], encoding="utf-8").read() == "<p>costos</p>"


def test_aplicar_formato_recurso():
    def actividades():
        return [{"tipo_archivo": "H5P"}, {"tipo_archivo": "PDF"}]

    assert [a["tipo_archivo"] for a in engine.aplicar_formato_recurso(actividades(), "HTML")] == ["HTML", "PDF"]
    assert [a["tipo_archivo"] for a in engine.aplicar_formato_recurso(actividades(), "H5P")] == ["H5P", "PDF"]
    assert [a["tipo_archivo"] for a in engine.aplicar_formato_recurso(actividades(), None)] == ["H5P", "PDF"]


def test_report_observation_for_html_mode():
    observacion = engine._observacion_guardado({
        "confirmacion": "PATCH",
        "html_pegado": {"caracteres": 1234, "reemplazo_previo": True},
        "recurso_quitado": "Archivo",
    })

    assert observacion == (
        "Carga guardada - PATCH confirmado - HTML pegado (1234 caracteres, reemplaza el Html previo)"
        ' - se quito el archivo previo de Recurso ("Archivo")'
    )


def test_report_observation_when_the_removed_file_had_no_readable_name():
    observacion = engine._observacion_guardado({
        "confirmacion": "PATCH",
        "html_pegado": {"caracteres": 10, "reemplazo_previo": False},
        "recurso_quitado": html_field.NOMBRE_ARCHIVO_DESCONOCIDO,
    })

    assert observacion.endswith("HTML pegado (10 caracteres) - se quito el archivo previo de Recurso")


def test_upload_thread_passes_resource_format_to_engine(monkeypatch):
    recibido = {}
    monkeypatch.setattr(upload_jobs, "ejecutar_cargue", lambda *a, **k: recibido.update(k))

    upload_jobs.ejecutar_cargue_con_historial(
        "m.xlsx", "r.zip", "temp", "r.csv", True, True, True, "u", "c",
        {"usuario_app": "ana", "formato_recurso": "HTML"},
    )

    assert recibido["formato_recurso"] == "HTML"


def test_engine_converts_h5p_activities_when_format_is_html(monkeypatch, tmp_path):
    class _Navegador:
        def new_page(self, **kwargs):
            class _Pagina:
                def on(self, *a):
                    pass
            return _Pagina()

        def close(self):
            pass

    class _Playwright:
        chromium = None

        def __enter__(self):
            self.chromium = self
            return self

        def __exit__(self, *a):
            return False

        def launch(self, **kwargs):
            return _Navegador()

    tipos = []
    actividad = {
        "fila_excel": 5, "programa": "P", "curso": "C", "semana": "1", "unidad": "U1",
        "nombre": "Actividad", "categoria_prizma": "OVA", "tipo_archivo": "H5P",
    }
    monkeypatch.setattr(engine, "sync_playwright", lambda: _Playwright())
    monkeypatch.setattr(engine, "iniciar_sesion_prizma", lambda *a, **k: None)
    monkeypatch.setattr(engine, "leer_actividades_excel", lambda *a, **k: [dict(actividad)])
    monkeypatch.setattr(engine, "crear_indice_recursos", lambda ruta: [{"nombre": "Actividad.html"}])
    monkeypatch.setattr(engine, "asegurar_listado", lambda pagina: True)
    monkeypatch.setattr(
        engine,
        "procesar_actividad",
        lambda pagina, act, *a, **k: tipos.append(act["tipo_archivo"]) or {"ok": True, "error": "", "recurso": "x"},
    )

    estado = {}
    engine.ejecutar_cargue(
        "m.xlsx", "r.zip", str(tmp_path), str(tmp_path / "r.csv"),
        True, True, True, "u", "c", estado, formato_recurso="HTML",
    )

    assert tipos == ["HTML"]
    assert estado["etapa"] == "finalizado"


def test_missing_confirmation_dialog_stops_without_saving(motor_html):
    pagina = _PaginaPrizma(h5p_cargado=True, con_dialogo=False)

    resultado = _procesar(pagina, motor_html)

    assert resultado["error"].startswith("ERROR_QUITANDO_RECURSO:")
    assert "PRIZMA no mostro la confirmacion para eliminar el archivo" in resultado["error"]
    assert pagina.tiene_archivo is True
    assert pagina.descarga_pulsada is False
    assert pagina.clics_guardar == 0


def test_save_click_exception_is_reported_with_its_cause(motor_html, monkeypatch):
    class _BotonQueFalla:
        def click(self, timeout=None):
            raise RuntimeError("Element is not attached to the DOM\nCall log: ...")

    monkeypatch.setattr(engine, "encontrar_boton_guardar", lambda pagina: _BotonQueFalla())
    pagina = _PaginaPrizma()

    resultado = _procesar(pagina, motor_html)

    assert resultado["error"] == "ERROR_CLIC_GUARDAR: RuntimeError: Element is not attached to the DOM"


def test_prizma_form_errors_are_part_of_save_diagnostics():
    assert "p.form-error" in engine._SELECTORES_ALERTAS_PRIZMA
