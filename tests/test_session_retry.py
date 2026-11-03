"""Pruebas del reintento al abrir la sesion de PRIZMA al inicio de un cargue.

Antes, un solo "Page.goto: Timeout 60000ms exceeded" (PRIZMA lento un
momento) cancelaba el cargue completo al 0 %. Ahora se reintenta solo ese
tipo de fallo momentaneo; un login rechazado nunca se repite.
"""

import functools

import pytest

from auto_prizma.automation.prizma import engine

TIMEOUT_GOTO = (
    'Page.goto: Timeout 60000ms exceeded.\nCall log:\n'
    '  - navigating to "https://admin.prizma.site/inicio-sesion", waiting until "domcontentloaded"'
)


class _AbrirSesionFalsa:
    """Falla con los errores indicados y luego devuelve una pagina."""

    def __init__(self, errores):
        self.errores = list(errores)
        self.motivos = []

    def __call__(self, motivo):
        self.motivos.append(motivo)
        if self.errores:
            raise RuntimeError(self.errores.pop(0))
        return "pagina"


def test_retries_transient_timeout_and_returns_page():
    abrir = _AbrirSesionFalsa([TIMEOUT_GOTO, TIMEOUT_GOTO])
    esperas = []
    estado = {}

    pagina = engine._abrir_sesion_inicial(abrir, estado, esperas=(5, 15), dormir=esperas.append)

    assert pagina == "pagina"
    assert abrir.motivos == [
        "inicio del cargue",
        "reintento 2 de 3 al iniciar",
        "reintento 3 de 3 al iniciar",
    ]
    assert len(esperas) == 5 + 15
    assert "intento 2 de 3" in estado["mensaje"]


def test_raises_last_error_when_all_attempts_fail():
    abrir = _AbrirSesionFalsa([TIMEOUT_GOTO] * 3)

    with pytest.raises(RuntimeError, match="Page.goto: Timeout 60000ms"):
        engine._abrir_sesion_inicial(abrir, {}, esperas=(1, 1), dormir=lambda s: None)

    assert len(abrir.motivos) == 3


@pytest.mark.parametrize(
    "error",
    ["ERROR_LOGIN_PRIZMA", "ValueError cualquiera que no es estructural"],
)
def test_does_not_retry_rejected_login_or_non_structural_errors(error):
    abrir = _AbrirSesionFalsa([error])

    with pytest.raises(RuntimeError, match=error):
        engine._abrir_sesion_inicial(abrir, {}, esperas=(1, 1), dormir=lambda s: None)

    assert abrir.motivos == ["inicio del cargue"]


def test_cancellation_during_wait_returns_none():
    abrir = _AbrirSesionFalsa([TIMEOUT_GOTO])
    estado = {}

    def dormir(_segundos):
        estado["cancelar_solicitado"] = True

    assert engine._abrir_sesion_inicial(abrir, estado, esperas=(5,), dormir=dormir) is None
    assert len(abrir.motivos) == 1


# ============================================================
# INTEGRACION CON ejecutar_cargue (Playwright simulado)
# ============================================================

class _PaginaFalsa:
    def on(self, evento, funcion):
        pass


class _NavegadorFalso:
    def new_page(self, **kwargs):
        return _PaginaFalsa()

    def close(self):
        pass


class _PlaywrightFalso:
    def __init__(self):
        self.chromium = self

    def launch(self, **kwargs):
        return _NavegadorFalso()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def _preparar_motor(monkeypatch, errores_login):
    llamadas_login = []

    def iniciar_sesion_falsa(pagina, usuario, contrasena, abrir_actividades=True):
        llamadas_login.append(usuario)
        if errores_login:
            raise RuntimeError(errores_login.pop(0))

    actividad = {
        "fila_excel": 5, "programa": "P", "curso": "C", "semana": "1", "unidad": "U1",
        "nombre": "Actividad 1", "categoria_prizma": "OVI", "tipo_archivo": "PDF",
    }
    monkeypatch.setattr(engine, "sync_playwright", lambda: _PlaywrightFalso())
    monkeypatch.setattr(engine, "iniciar_sesion_prizma", iniciar_sesion_falsa)
    monkeypatch.setattr(engine, "leer_actividades_excel", lambda *a, **k: [actividad])
    monkeypatch.setattr(engine, "crear_indice_recursos", lambda ruta: [{"nombre": "a.pdf"}])
    monkeypatch.setattr(engine, "asegurar_listado", lambda pagina: True)
    monkeypatch.setattr(
        engine,
        "procesar_actividad",
        lambda *a, **k: {"ok": True, "error": "", "recurso": "a.pdf", "confirmacion": "PATCH"},
    )
    monkeypatch.setattr(
        engine,
        "_abrir_sesion_inicial",
        functools.partial(engine._abrir_sesion_inicial, esperas=(0, 0)),
    )
    return llamadas_login


def _ejecutar(tmp_path):
    estado = {}
    engine.ejecutar_cargue(
        "matriz.xlsx", "recursos.zip", str(tmp_path), str(tmp_path / "reporte.csv"),
        True, True, True, "usuario", "clave", estado,
    )
    return estado


def test_ejecutar_cargue_survives_two_login_page_timeouts(monkeypatch, tmp_path):
    llamadas = _preparar_motor(monkeypatch, [TIMEOUT_GOTO, TIMEOUT_GOTO])

    estado = _ejecutar(tmp_path)

    assert len(llamadas) == 3
    assert estado["etapa"] == "finalizado"
    assert estado["exitosas"] == 1


def test_ejecutar_cargue_reports_friendly_message_after_three_timeouts(monkeypatch, tmp_path):
    llamadas = _preparar_motor(monkeypatch, [TIMEOUT_GOTO] * 3)

    estado = _ejecutar(tmp_path)

    assert len(llamadas) == 3
    assert estado["etapa"] == "error"
    assert estado["terminado"] is True
    assert estado["mensaje"].startswith(
        "PRIZMA no respondió al abrir la página de inicio de sesión después de 3 intentos."
    )
    assert "Page.goto: Timeout 60000ms exceeded." in estado["mensaje"]
