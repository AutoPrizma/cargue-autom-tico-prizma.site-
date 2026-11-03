"""Ejecucion del cargue de tests en PRIZMA (en segundo plano) y mensajes de error legibles.
"""

from __future__ import annotations

import re
import threading
from datetime import datetime, timezone

from auto_prizma.automation.prizma import engine as motor_prizma
from auto_prizma.core.config import PRIZMA_BASE_URL

from .automation import PrizmaTestAutomator
from .state import (
    _AUTOMATION_JOBS,
    _AUTOMATION_LOCK,
    _AUTOMATION_SYNC,
    _JOBS,
    _JOBS_LOCK,
)


def simplificar_mensaje_error(raw_error: str | Exception | None) -> str:
    """Traduce excepciones o trazas técnicas de Playwright en explicaciones limpias y ejecutivas."""
    if not raw_error:
        return "Ocurrió un error inesperado durante la ejecución en PRIZMA."
    msg = str(raw_error).strip()

    if "se encuentra deshabilitado" in msg or "continúa deshabilitado" in msg:
        return "El botón 'Crear' en PRIZMA se encuentra deshabilitado. Verifica que todos los campos requeridos estén completos."
    if "element is not enabled" in msg.lower():
        return "No se pudo presionar el botón 'Crear' en PRIZMA porque se encuentra deshabilitado. Verifica que todos los campos requeridos estén completos."
    if "No se encontró el botón 'Crear'" in msg:
        return "No se localizó el botón 'Crear' al lado de 'Cancelar' en el formulario activo de PRIZMA."
    if "No se encontró el selector 'Facultad'" in msg:
        return "No se encontró el selector 'Facultad' en el formulario de PRIZMA tras acceder a Actividades -> Tests -> Crear."
    if "Campo obligatorio o inválido" in msg or "Campo requerido o inválido" in msg:
        return msg.split("\n")[0].strip()
    if "Error de PRIZMA al guardar" in msg:
        return msg.split("\n")[0].strip()
    if "inicio-sesion" in msg.lower() or "credenciales" in msg.lower():
        return "Error al iniciar sesión en PRIZMA. Verifica tu usuario, contraseña y conexión a la plataforma."
    if "Importar" in msg and ("timeout" in msg.lower() or "waiting for locator" in msg.lower()):
        return "No se localizó el botón 'Importar' dentro del tiempo de espera en el formulario de PRIZMA."

    if "Call log:" in msg:
        msg = msg.split("Call log:")[0].strip()

    lineas = [l.strip() for l in msg.splitlines() if l.strip()]
    if lineas:
        primera = lineas[0]
        primera = re.sub(r"^(Error durante la automatización:\s*)+", "", primera)
        primera = re.sub(r"^(Locator\.[a-zA-Z_]+:\s*)+", "", primera)
        if "Timeout" in primera and "exceeded" in primera:
            return "Tiempo de espera agotado al interactuar con la plataforma PRIZMA. Revisa la conexión o el estado de la página."
        return primera[:250].strip()

    return "Error durante la interacción con la plataforma PRIZMA."


def ejecutar_test_job(
    job_id: str,
    usuario_prizma: str,
    clave_prizma: str,
    user: str = "",
    simulacion: bool = False,
    headless: bool = True,
    cascada_override: dict | None = None,
    on_test_callback=None,
    on_log_callback=None,
    cancel_checker=None,
    ruta_reporte: str | None = None,
    registrar_historial: bool = False,
) -> dict:
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
    if not job:
        return {"ok": False, "error": "Análisis de test no encontrado en el servidor. Normalmente pasa si el servidor se reinició con la página abierta (los análisis se guardan solo en memoria). Sube el documento de nuevo para generar uno nuevo."}

    document: TestDocument = job["document"]
    cascada = dict(cascada_override or job.get("cascada_datos") or {})

    total_tests = len(document.tests)
    with _AUTOMATION_LOCK:
        detalle_tests = [
            {
                "numero": idx,
                "titulo": t.title,
                "preguntas": sum(len(sec.questions) for sec in t.sections),
                "estado": "pendiente",
                "mensaje": "En cola de espera...",
            }
            for idx, t in enumerate(document.tests, start=1)
        ]
        auto_state = {
            "job_id": job_id,
            "owner": user or job.get("owner", ""),
            "simulacion": simulacion,
            "cancelado": False,
            "estado": "en_ejecucion",
            "mensaje": (
                "Iniciando motor de automatización Playwright en modo simulación (sin guardar)..."
                if simulacion
                else "Iniciando motor de automatización Playwright en modo creación real..."
            ),
            "total": total_tests,
            "procesados": 0,
            "exitosos": 0,
            "omitidos": 0,
            "pendientes": total_tests,
            "fallidos": 0,
            "progreso_porcentaje": 0,
            "detalle_tests": detalle_tests,
            "logs": [],
            "captura": None,
            "error": "",
            "esperando_asignatura": False,
            "opciones_asignatura": [],
            "asignatura_buscada": "",
            "campo_seleccion": "Asignatura por pensum",
            "iniciado_en": datetime.now(timezone.utc).isoformat(),
            "finalizado_en": None,
            "asignatura": cascada.get("asignatura", ""),
            "titulo_doc": getattr(document, "source_name", None) or (document.tests[0].title if document.tests else "Test Evaluativo"),
        }
        _AUTOMATION_JOBS[job_id] = auto_state
        sync_obj = {
            "event": threading.Event(),
            "seleccion": {"asignatura": None, "campo": None},
        }
        _AUTOMATION_SYNC[job_id] = sync_obj

    import time as time_mod

    def on_log(nivel, msg, snap=None):
        with _AUTOMATION_LOCK:
            auto_state["mensaje"] = msg
            auto_state["logs"].append({"tiempo": time_mod.strftime("%H:%M:%S"), "nivel": nivel, "mensaje": msg})
            if snap:
                auto_state["captura"] = snap
        if on_log_callback:
            try:
                on_log_callback(nivel, msg, snap)
            except Exception:
                pass

    def pedir_seleccion_asignatura(opciones: list[str], buscada: str, campo: str = "Asignatura por pensum") -> str:
        with _AUTOMATION_LOCK:
            auto_state["esperando_asignatura"] = True
            auto_state["opciones_asignatura"] = opciones
            auto_state["asignatura_buscada"] = buscada
            auto_state["campo_seleccion"] = campo
            msg_espera = (
                f"Hay varias opciones o no se encontró una coincidencia única para '{buscada}' en '{campo}'. "
                "Selecciona la opción correcta para continuar."
            )
            auto_state["mensaje"] = msg_espera
            auto_state["logs"].append({
                "tiempo": time_mod.strftime("%H:%M:%S"),
                "nivel": "warn",
                "mensaje": msg_espera,
            })
        sync_obj["event"].clear()
        notificado = sync_obj["event"].wait(timeout=300)
        with _AUTOMATION_LOCK:
            auto_state["esperando_asignatura"] = False
            auto_state["opciones_asignatura"] = []
        seleccion = sync_obj["seleccion"].get("asignatura")
        if not notificado or not seleccion:
            raise ValueError(f"Tiempo de espera agotado (5 min) para seleccionar una opción de '{campo}' en PRIZMA.")

        asignatura_confirmada = str(seleccion or "").strip()
        selector_elegido = str(sync_obj["seleccion"].get("campo") or campo)
        clave_cascada = {
            "Facultad": "facultad", "Programa": "programa", "Pensum": "pensum",
            "Nivel de pensum": "nivel", "Asignatura por pensum": "asignatura",
            "Semana": "semana", "Corte": "corte",
        }.get(selector_elegido, "asignatura")
        with _AUTOMATION_LOCK:
            cascada[clave_cascada] = asignatura_confirmada
            if clave_cascada == "asignatura":
                auto_state["asignatura"] = asignatura_confirmada
        with _JOBS_LOCK:
            job["cascada_datos"] = dict(cascada)
        sync_obj["seleccion"]["asignatura"] = None
        sync_obj["seleccion"]["campo"] = None
        return asignatura_confirmada

    def _fila_test_reporte(indice, item, resultado, error_msg=""):
        if not ruta_reporte:
            return
        t = document.tests[indice - 1] if 0 < indice <= len(document.tests) else None
        actividad = {
            "fila_excel": f"Test {indice}",
            "programa": cascada.get("programa") or "",
            "curso": cascada.get("asignatura") or "",
            "semana": (getattr(t, "week", "") or cascada.get("nivel") or "") if t else "",
            "unidad": (getattr(t, "cut", "") or "") if t else "",
            "nombre": item.get("titulo") or f"Test {indice}",
            "categoria_prizma": "Test Evaluativo",
            "tipo_archivo": "Test",
        }
        try:
            motor_prizma.guardar_resultado(ruta_reporte, actividad, resultado, error_msg)
        except Exception:
            pass

    def on_test_progreso(indice: int, estado_test: str, msg_test: str, err: str = ""):
        with _AUTOMATION_LOCK:
            if 1 <= indice <= len(auto_state["detalle_tests"]):
                item = auto_state["detalle_tests"][indice - 1]
                item["estado"] = estado_test
                item["mensaje"] = msg_test
            if estado_test == "exitoso":
                auto_state["exitosos"] += 1
                auto_state["procesados"] += 1
                auto_state["pendientes"] = max(0, auto_state["total"] - auto_state["procesados"])
                _fila_test_reporte(indice, item, "Cargado")
            elif estado_test == "omitido":
                # Ya quedó guardado en PRIZMA en un intento anterior: no se
                # vuelve a crear (evita duplicados en un reintento).
                auto_state["omitidos"] += 1
                auto_state["procesados"] += 1
                auto_state["pendientes"] = max(0, auto_state["total"] - auto_state["procesados"])
                _fila_test_reporte(indice, item, "Omitido", msg_test)
            elif estado_test == "error":
                auto_state["fallidos"] += 1
                auto_state["procesados"] += 1
                auto_state["pendientes"] = max(0, auto_state["total"] - auto_state["procesados"])
                _fila_test_reporte(indice, item, "Error", err or msg_test)
            elif estado_test == "cancelado":
                auto_state["pendientes"] = max(0, auto_state["total"] - auto_state["procesados"])
                _fila_test_reporte(indice, item, "Cancelado")

            total_t = max(1, auto_state["total"])
            auto_state["progreso_porcentaje"] = int((auto_state["procesados"] / total_t) * 100)
        if on_test_callback:
            try:
                on_test_callback(indice, estado_test, msg_test, err)
            except Exception:
                pass

    def _is_cancelled():
        if auto_state.get("cancelado"):
            return True
        if cancel_checker and cancel_checker():
            return True
        return False

    def _registrar_historial_si_aplica():
        if not registrar_historial or not ruta_reporte:
            return
        estado_final = "finalizado" if auto_state["estado"] == "completado" else auto_state["estado"]
        try:
            from auto_prizma.services.history import _registrar_historial_test
            _registrar_historial_test(job_id, ruta_reporte, cascada, estado_final, auto_state.get("owner", ""))
        except Exception:
            pass

    try:
        automator = PrizmaTestAutomator(
            base_url=PRIZMA_BASE_URL,
            headless=headless,
            log_callback=on_log,
        )
        res = automator.ejecutar_cargue(
            usuario_prizma=usuario_prizma,
            clave_prizma=clave_prizma,
            tests=document.tests,
            cascada=cascada,
            solo_simulacion=simulacion,
            test_callback=on_test_progreso,
            cancel_checker=_is_cancelled,
            solicitar_asignatura_callback=pedir_seleccion_asignatura,
        )
        with _AUTOMATION_LOCK:
            auto_state["finalizado_en"] = datetime.now(timezone.utc).isoformat()
            if res.get("detenido") or auto_state.get("cancelado"):
                auto_state["estado"] = "detenido"
                auto_state["mensaje"] = f"⏹ Automatización detenida por el usuario. Se completaron {auto_state.get('exitosos', 0)} de {auto_state.get('total', 0)} tests."
                auto_state["pendientes"] = max(0, auto_state["total"] - auto_state["procesados"])
            elif res.get("ok"):
                auto_state["estado"] = "completado"
                auto_state["progreso_porcentaje"] = 100
                auto_state["pendientes"] = 0
                if simulacion:
                    auto_state["mensaje"] = "🛡 Simulación exitosa: todos los tests fueron validados sin guardar en PRIZMA."
                else:
                    auto_state["mensaje"] = "¡Todos los tests fueron creados y guardados exitosamente en PRIZMA!"
                auto_state["omitidos"] = res.get("omitidos", auto_state.get("omitidos", 0))
                if auto_state.get("omitidos"):
                    auto_state["mensaje"] += f" · {auto_state['omitidos']} ya estaban cargados y se omitieron (sin duplicar)."
                auto_state["procesados"] = res.get("procesados", len(document.tests))
            else:
                auto_state["estado"] = "error"
                raw_err = res.get("error", "Error desconocido en la automatización.")
                auto_state["error"] = simplificar_mensaje_error(raw_err)
                auto_state["mensaje"] = f"Fallo en la ejecución: {auto_state['error']}"
        _registrar_historial_si_aplica()
        return res
    except Exception as e:
        with _AUTOMATION_LOCK:
            auto_state["finalizado_en"] = datetime.now(timezone.utc).isoformat()
            if auto_state.get("cancelado"):
                auto_state["estado"] = "detenido"
                auto_state["mensaje"] = f"⏹ Automatización detenida por el usuario. Se completaron {auto_state.get('exitosos', 0)} de {auto_state.get('total', 0)} tests."
            else:
                auto_state["estado"] = "error"
                auto_state["error"] = simplificar_mensaje_error(e)
                auto_state["mensaje"] = f"Excepción en ejecución: {auto_state['error']}"
        _registrar_historial_si_aplica()
        return {"ok": False, "error": str(e)}
