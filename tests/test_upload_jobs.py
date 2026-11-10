"""Pruebas del servicio de trabajos de cargue (auto_prizma/services/upload_jobs.py)."""

import threading

import pytest

from auto_prizma.services import upload_jobs

CLAVE = "clave-secreta-de-prizma"


def _contiene(valor, buscado):
    """True si `buscado` aparece en cualquier valor anidado de dicts/listas."""
    if isinstance(valor, dict):
        return any(_contiene(v, buscado) for v in valor.values())
    if isinstance(valor, (list, tuple, set)):
        return any(_contiene(v, buscado) for v in valor)
    return isinstance(valor, str) and buscado in valor


@pytest.fixture
def trabajo_en_memoria(monkeypatch):
    """Registra un trabajo de prueba en TRABAJOS y lo limpia al terminar."""
    trabajo_id = "prueba-credenciales"
    upload_jobs.TRABAJOS[trabajo_id] = {
        "id": trabajo_id,
        "etapa": "analizado",
        "mensaje": "",
        "usuario_app": "adminlocal",
        "procesar_ovi": True,
        "procesar_ova": False,
        "procesar_retos": False,
        "ruta_excel": "matriz.xlsx",
        "ruta_zip": "recursos.zip",
        "carpeta_temp": "temp",
        "ruta_reporte": "reporte.csv",
    }
    yield trabajo_id
    upload_jobs.TRABAJOS.pop(trabajo_id, None)
    try:
        upload_jobs.COLA_CARGUES.remove(trabajo_id)
    except ValueError:
        pass


def test_enqueue_keeps_password_only_in_temporary_field(monkeypatch, trabajo_en_memoria):
    # Sin cupo: el trabajo queda en cola y no arranca ningun hilo.
    monkeypatch.setattr(upload_jobs, "CARGUES_ACTIVOS", upload_jobs.MAX_CARGUES_SIMULTANEOS)

    upload_jobs._encolar_trabajo(trabajo_en_memoria, "usuario", CLAVE)

    trabajo = upload_jobs.TRABAJOS[trabajo_en_memoria]
    assert trabajo["etapa"] == "en_cola"
    assert "credenciales_prizma" not in trabajo
    sin_temporales = {
        k: v for k, v in trabajo.items()
        if k not in ("usuario_prizma_temporal", "contrasena_prizma_temporal")
    }
    assert not _contiene(sin_temporales, CLAVE)


def test_password_is_gone_after_the_upload_thread_finishes(monkeypatch, trabajo_en_memoria):
    monkeypatch.setattr(upload_jobs, "CARGUES_ACTIVOS", upload_jobs.MAX_CARGUES_SIMULTANEOS)
    upload_jobs._encolar_trabajo(trabajo_en_memoria, "usuario", CLAVE)
    upload_jobs.COLA_CARGUES.remove(trabajo_en_memoria)

    recibidas = []
    monkeypatch.setattr(
        upload_jobs,
        "ejecutar_cargue_con_historial",
        lambda *args: recibidas.append(args[8]),
    )
    monkeypatch.setattr(upload_jobs, "_registrar_reporte_final", lambda trabajo: None)
    monkeypatch.setattr(upload_jobs, "CARGUES_ACTIVOS", 1)

    upload_jobs._ejecutar_cargue_en_hilo(trabajo_en_memoria)

    assert recibidas == [CLAVE]  # el motor si recibio la contrasena
    assert not _contiene(upload_jobs.TRABAJOS[trabajo_en_memoria], CLAVE)


# ============================================================
# SERVICIOS QUE USAN LAS RUTAS
# ============================================================

@pytest.fixture
def trabajos_aislados(monkeypatch):
    """TRABAJOS y cola vacios solo para la prueba."""
    monkeypatch.setattr(upload_jobs, "TRABAJOS", {})
    monkeypatch.setattr(upload_jobs, "COLA_CARGUES", upload_jobs.deque())
    return upload_jobs.TRABAJOS


def _trabajo(trabajo_id, usuario="ana", **campos):
    base = {
        "id": trabajo_id, "usuario_app": usuario, "etapa": "analizado", "mensaje": "",
        "total": 3, "procesadas": 1, "exitosas": 1, "errores": 0, "terminado": False,
        "ruta_reporte": "no_existe.csv",
    }
    base.update(campos)
    return base


def test_cancel_job_in_queue_cancels_immediately_and_drops_credentials(trabajos_aislados):
    trabajos_aislados["t1"] = _trabajo(
        "t1", etapa="en_cola", usuario_prizma_temporal="u", contrasena_prizma_temporal=CLAVE,
    )
    upload_jobs.COLA_CARGUES.append("t1")

    assert upload_jobs.cancel_job("t1", "ANA") == "cancelado"

    trabajo = trabajos_aislados["t1"]
    assert trabajo["etapa"] == "cancelado" and trabajo["terminado"] is True
    assert "t1" not in upload_jobs.COLA_CARGUES
    assert not _contiene(trabajo, CLAVE)


def test_cancel_job_running_only_requests_stop(trabajos_aislados):
    trabajos_aislados["t2"] = _trabajo("t2", etapa="procesando")

    assert upload_jobs.cancel_job("t2", "ana") == "solicitado"
    assert trabajos_aislados["t2"]["cancelar_solicitado"] is True
    assert trabajos_aislados["t2"]["etapa"] == "procesando"


def test_cancel_job_rejects_other_users_and_ignores_finished(trabajos_aislados):
    trabajos_aislados["t3"] = _trabajo("t3", etapa="procesando")
    trabajos_aislados["t4"] = _trabajo("t4", etapa="finalizado", terminado=True)

    assert upload_jobs.cancel_job("t3", "beto") == "no_encontrado"
    assert upload_jobs.cancel_job("no-existe", "ana") == "no_encontrado"
    assert upload_jobs.cancel_job("t4", "ana") == "terminado"
    assert "cancelar_solicitado" not in trabajos_aislados["t3"]


def test_public_job_status_only_for_owner_and_without_credentials(trabajos_aislados):
    trabajos_aislados["t5"] = _trabajo("t5", contrasena_prizma_temporal=CLAVE)

    estado = upload_jobs.public_job_status("t5", "ana")

    assert upload_jobs.public_job_status("t5", "beto") is None
    assert set(estado) == {
        "etapa", "mensaje", "total", "procesadas", "exitosas", "errores", "terminado",
        "detalle_actividades", "reporte_disponible", "posicion_cola", "cancelar_solicitado",
    }
    assert estado["reporte_disponible"] is False
    assert not _contiene(estado, CLAVE)


def test_active_jobs_filters_finished_and_sorts_oldest_first(trabajos_aislados):
    trabajos_aislados["nuevo"] = _trabajo("nuevo", etapa="procesando", iniciado_en="2026-10-06T10:05:00")
    trabajos_aislados["viejo"] = _trabajo("viejo", etapa="en_cola", encolado_en="2026-10-06T10:00:00")
    trabajos_aislados["listo"] = _trabajo("listo", etapa="finalizado", terminado=True)
    trabajos_aislados["analizado"] = _trabajo("analizado")

    assert [t["id"] for t in upload_jobs.active_jobs()] == ["viejo", "nuevo"]


@pytest.mark.parametrize("acceso_ok", [True, False])
def test_validate_access_and_enqueue(monkeypatch, trabajos_aislados, acceso_ok):
    trabajos_aislados["t6"] = _trabajo("t6")
    monkeypatch.setattr(upload_jobs, "CARGUES_ACTIVOS", upload_jobs.MAX_CARGUES_SIMULTANEOS)
    monkeypatch.setattr(
        upload_jobs,
        "validar_credenciales_prizma",
        lambda usuario, clave: {"ok": acceso_ok, "mensaje": "Credenciales rechazadas."},
    )

    encolado, mensaje = upload_jobs.validate_access_and_enqueue("t6", "usuario", CLAVE)

    trabajo = trabajos_aislados["t6"]
    if acceso_ok:
        assert (encolado, mensaje) == (True, "")
        assert trabajo["etapa"] == "en_cola"
        assert list(upload_jobs.COLA_CARGUES) == ["t6"]
    else:
        assert (encolado, mensaje) == (False, "Credenciales rechazadas.")
        assert trabajo["etapa"] == "analizado"
        assert not _contiene(trabajo, CLAVE)


def test_validate_access_reserves_job_before_external_validation(
    monkeypatch, trabajos_aislados
):
    trabajos_aislados["t7"] = _trabajo("t7")
    monkeypatch.setattr(upload_jobs, "CARGUES_ACTIVOS", upload_jobs.MAX_CARGUES_SIMULTANEOS)
    inicio_validacion = threading.Event()
    terminar_validacion = threading.Event()
    resultados = []

    def validar(_usuario, _clave):
        inicio_validacion.set()
        assert terminar_validacion.wait(timeout=2)
        return {"ok": True}

    monkeypatch.setattr(upload_jobs, "validar_credenciales_prizma", validar)
    hilo = threading.Thread(
        target=lambda: resultados.append(
            upload_jobs.validate_access_and_enqueue("t7", "usuario", CLAVE)
        )
    )
    hilo.start()
    assert inicio_validacion.wait(timeout=2)

    segundo = upload_jobs.validate_access_and_enqueue("t7", "usuario", CLAVE)
    assert segundo == (False, "Este trabajo ya fue iniciado.")
    assert trabajos_aislados["t7"]["etapa"] == "validando_login"
    assert list(upload_jobs.COLA_CARGUES) == []

    terminar_validacion.set()
    hilo.join(timeout=2)
    assert not hilo.is_alive()
    assert resultados == [(True, "")]
    assert list(upload_jobs.COLA_CARGUES) == ["t7"]


def test_cancel_during_access_validation_does_not_enqueue(
    monkeypatch, trabajos_aislados
):
    trabajos_aislados["t8"] = _trabajo("t8")
    inicio_validacion = threading.Event()
    terminar_validacion = threading.Event()
    resultados = []

    def validar(_usuario, _clave):
        inicio_validacion.set()
        assert terminar_validacion.wait(timeout=2)
        return {"ok": True}

    monkeypatch.setattr(upload_jobs, "validar_credenciales_prizma", validar)
    hilo = threading.Thread(
        target=lambda: resultados.append(
            upload_jobs.validate_access_and_enqueue("t8", "usuario", CLAVE)
        )
    )
    hilo.start()
    assert inicio_validacion.wait(timeout=2)

    assert upload_jobs.cancel_job("t8", "ana") == "solicitado"
    terminar_validacion.set()
    hilo.join(timeout=2)

    trabajo = trabajos_aislados["t8"]
    assert not hilo.is_alive()
    assert resultados == [(False, "Cargue cancelado durante la validación de acceso.")]
    assert trabajo["etapa"] == "cancelado"
    assert trabajo["terminado"] is True
    assert list(upload_jobs.COLA_CARGUES) == []
