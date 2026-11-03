"""Auditoria profunda de un curso de Moodle publicado (solo lectura).

El curso se abre tal cual esta, en el navegador visible de este equipo (el
mismo perfil y login manual del cargue), y se recorre semana por semana.
Cada recurso se abre en una pestana aparte y se valida que renderice de
verdad y que el titulo que se ve al abrirlo sea el nombre que el curso
muestra. No toca nada del curso: no sube, edita ni borra.

Los reportes viven en data/reportes/moodle/<persona>/ con el prefijo
moodle-auditoria- y comparten la purga de 15 dias del resto de reportes
Moodle.
"""

import csv
import hashlib
import io
import json
import os
import threading
import uuid
from datetime import datetime, timezone

from auto_prizma.core.config import DATA_DIR
from auto_prizma.core.storage import write_json_atomic, write_text_atomic
from auto_prizma.automation.content_checks import inspeccionar_pdf_bytes
from auto_prizma.domain.moodle_audit import (
    audit_row,
    interpret_activity_probe,
    summarize_audit_rows,
)
from auto_prizma.services.moodle_resources import (
    _read_matrix,
    local_profile_path,
    validate_course_url,
)

MOODLE_AUDIT_JOBS = {}
MOODLE_AUDIT_LOCK = threading.RLock()

RUNNING_AUDIT_STATUSES = {"logging_in", "auditing"}


def start_moodle_audit(owner, course_url, matrix_filename="", matrix_bytes=None):
    """Lanza una auditoría; la matriz opcional es solo referencia, nunca syllabus."""
    course_url = validate_course_url(course_url)
    matrix_rows = None
    if matrix_bytes is not None:
        if len(matrix_bytes) > 20 * 1024 * 1024:
            raise ValueError("La matriz supera el límite de 20 MB.")
        matrix_filename = os.path.basename(str(matrix_filename or ""))
        if os.path.splitext(matrix_filename)[1].lower() not in {".csv", ".xlsx"}:
            raise ValueError("La matriz debe ser un archivo CSV o XLSX.")
        matrix_rows, _ = _read_matrix(matrix_filename, matrix_bytes)
        if not matrix_rows:
            raise ValueError("La matriz no contiene filas de recursos para comparar.")
    owner = str(owner or "")
    with MOODLE_AUDIT_LOCK:
        for job in MOODLE_AUDIT_JOBS.values():
            if job.get("owner") == owner and not job.get("finished"):
                raise ValueError(
                    "Ya hay una auditoría de curso en curso; espera a que termine "
                    "o cancela la que está corriendo."
                )
        job_id = uuid.uuid4().hex
        job = {
            "id": job_id,
            "owner": owner,
            "course_url": course_url,
            "matrix_rows": matrix_rows,
            "status": "logging_in",
            "message": "Abriendo el navegador de Moodle en este equipo…",
            "progress": {"index": 0, "total": 0, "week": "", "title": "", "phase": "Preparando"},
            "results": [],
            "report": None,
            "report_paths": {},
            "finished": False,
            "cancel_requested": False,
            "started_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        }
        MOODLE_AUDIT_JOBS[job_id] = job
    _iniciar_hilo(job)
    return job


def _iniciar_hilo(job):
    """Corre la auditoria en su propio hilo (los tests la corren en el momento)."""
    hilo = threading.Thread(
        target=_run_moodle_audit,
        args=(job,),
        daemon=True,
        name="moodle-audit-" + job["id"][:8],
    )
    job["thread"] = hilo
    hilo.start()


def get_moodle_audit_job(job_id, owner):
    job = MOODLE_AUDIT_JOBS.get(str(job_id or ""))
    if not job or job.get("owner") != str(owner or ""):
        return None
    return job


def latest_moodle_audit(owner):
    """Trabajo mas reciente de la persona (para volver a ver su reporte)."""
    owner = str(owner or "")
    trabajos = [job for job in MOODLE_AUDIT_JOBS.values() if job.get("owner") == owner]
    trabajos.sort(key=lambda job: job.get("started_at") or "", reverse=True)
    return trabajos[0] if trabajos else None


def active_moodle_audit(owner):
    """Trabajo en curso de la persona, si lo hay."""
    owner = str(owner or "")
    with MOODLE_AUDIT_LOCK:
        for job in MOODLE_AUDIT_JOBS.values():
            if job.get("owner") == owner and not job.get("finished"):
                return job
    return None


def cancel_moodle_audit(job):
    with MOODLE_AUDIT_LOCK:
        if job.get("finished"):
            raise ValueError("La auditoría ya terminó.")
        if job.get("cancel_requested"):
            return
        job["cancel_requested"] = True
        job["message"] = (
            "Cancelando: se detendrá al terminar el recurso actual (máximo aproximado 30 s)."
        )


def public_moodle_audit_status(job):
    """Estado listo para la pagina: sin hilos ni rutas internas."""
    with MOODLE_AUDIT_LOCK:
        filas = [dict(item) for item in job.get("results") or []]
        return {
            "id": job["id"],
            "status": job.get("status"),
            "message": job.get("message", ""),
            "started_at": job.get("started_at"),
            "finished": bool(job.get("finished")),
            "cancel_requested": bool(job.get("cancel_requested")),
            "course_url": job.get("course_url", ""),
            "progress": dict(job.get("progress") or {}),
            "results": filas,
            "summary": summarize_audit_rows(filas),
        }


def audit_report_from_results(results, stopped_reason=""):
    filas = [dict(item) for item in results]
    return {
        "createdAt": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "stoppedReason": stopped_reason,
        "summary": summarize_audit_rows(filas),
        "rows": filas,
    }


def _comparar_matriz(results, matrix_rows, complete=True):
    """Anota coincidencias por semana/nombre y agrega filas esperadas ausentes."""
    if matrix_rows is None:
        return

    def key(value):
        from auto_prizma.auditor.procesar import clave
        return clave(str(value or ""))

    pendientes = list(enumerate(matrix_rows))
    for actual in results:
        semana_actual = key(actual.get("semana"))
        titulo_actual = key(actual.get("actividad"))
        coincidencia = next((
            (indice, fila) for indice, fila in pendientes
            if key(fila.get("title")) == titulo_actual
            and (not key(fila.get("week")) or key(fila.get("week")) == semana_actual)
        ), None)
        if coincidencia:
            indice, fila = coincidencia
            pendientes = [(i, item) for i, item in pendientes if i != indice]
            actual.update({
                "matriz_estado": "coincide",
                "matriz_recurso": fila.get("title", ""),
                "matriz_fila": fila.get("sourceRow", ""),
            })
        elif actual.get("estado") != "no procesado":
            actual.update({
                "matriz_estado": "no está en matriz",
                "matriz_recurso": "",
                "matriz_fila": "",
            })

    if complete:
        for _, fila in pendientes:
            results.append({
                "semana": fila.get("week", ""),
                "actividad": fila.get("title", ""),
                "tipo": fila.get("resourceType", ""),
                "estado": "falta",
                "renderiza": "",
                "titulo_interno": "",
                "coincide": None,
                "detalle": "La fila de la matriz no tiene un recurso publicado con ese nombre en Moodle.",
                "matriz_estado": "no publicado",
                "matriz_recurso": fila.get("title", ""),
                "matriz_fila": fila.get("sourceRow", ""),
            })


def write_moodle_audit_report(job, report):
    owner_hash = hashlib.sha256(str(job["owner"]).encode("utf-8")).hexdigest()[:24]
    report_dir = os.path.join(DATA_DIR, "reportes", "moodle", owner_hash)
    os.makedirs(report_dir, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    base = os.path.join(report_dir, "moodle-auditoria-" + stamp + "-" + job["id"][:8])
    json_path, csv_path = base + ".json", base + ".csv"
    write_json_atomic(json_path, report)
    headers = (
        "semana", "actividad", "tipo", "estado", "renderiza",
        "titulo_interno", "coincide", "matriz_estado", "matriz_recurso",
        "matriz_fila", "detalle",
    )
    with io.StringIO(newline="") as buffer:
        writer = csv.writer(buffer)
        writer.writerow(headers)
        for row in report.get("rows", []):
            writer.writerow([row.get(header, "") for header in headers])
        write_text_atomic(csv_path, buffer.getvalue())
    return {"jsonPath": json_path, "csvPath": csv_path}


def _mensaje_amistoso(error):
    texto = str(error)
    baja = texto.lower()
    if "login" in baja or "sesión" in baja or "sesion" in baja:
        return (
            "No se pudo abrir el curso en Moodle. Vuelve a iniciar la auditoría y "
            "espera a que cargue la sesión en la ventana de Chromium."
        )
    if "timeout" in baja:
        return "Moodle tardó demasiado en responder. Intenta la auditoría de nuevo."
    return (texto.splitlines() or [""])[0][:200] or "Error desconocido."


def _run_moodle_audit(job):
    client = None
    results = job["results"]
    try:
        profile = local_profile_path(job["owner"])
        with MOODLE_AUDIT_LOCK:
            job["message"] = (
                "Iniciando sesión en Moodle en la ventana visible de Chromium..."
            )
            job["progress"].update({"phase": "Esperando inicio de sesión"})

        from auto_prizma.automation.moodle.client import MoodleClient

        client = MoodleClient.launch(
            job["course_url"], profile,
            cancel_check=lambda: bool(job.get("cancel_requested")),
            enable_edit_mode=False,
        )

        with MOODLE_AUDIT_LOCK:
            job["message"] = "Leyendo las semanas del curso..."
            job["progress"].update({"phase": "Leyendo semanas del curso"})
        semanas = client.list_weeks()
        if not semanas:
            raise RuntimeError("No encontré semanas en el curso de Moodle; revisa el enlace.")

        # Descubrimiento primero: el total fija la barra de avance antes de
        # abrir actividad por actividad (que es lo lento).
        pendientes = []
        for semana in semanas:
            if job.get("cancel_requested"):
                break
            with MOODLE_AUDIT_LOCK:
                job["progress"].update({"week": semana["nombre"], "phase": "Leyendo recursos"})
            client.open_week_url(semana["url"], semana["nombre"])
            pendientes.extend(
                (semana["nombre"], actividad)
                for actividad in client.list_week_activities()
            )

        total = len(pendientes)
        with MOODLE_AUDIT_LOCK:
            job["progress"].update({"total": total, "week": "", "phase": "Auditando recursos"})
            job["message"] = (
                "El curso tiene " + str(total) + " recursos; abriendo uno a uno..."
                if total else "El curso no muestra recursos en sus semanas."
            )

        for indice, (nombre_semana, actividad) in enumerate(pendientes, start=1):
            if job.get("cancel_requested"):
                with MOODLE_AUDIT_LOCK:
                    results.append({
                        "semana": nombre_semana,
                        "actividad": actividad["titulo"],
                        "tipo": actividad.get("tipo", ""),
                        "estado": "no procesado",
                        "renderiza": "",
                        "titulo_interno": "",
                        "coincide": None,
                        "detalle": "El usuario canceló la auditoría.",
                    })
                continue

            with MOODLE_AUDIT_LOCK:
                job["status"] = "auditing"
                job["message"] = "Revisando " + nombre_semana + ": " + actividad["titulo"]
                job["progress"].update({
                    "index": indice,
                    "total": total,
                    "week": nombre_semana,
                    "title": actividad["titulo"],
                    "phase": "Abriendo el recurso",
                })

            sonda = client.audit_activity(actividad["url"])
            if (sonda or {}).get("cancelled"):
                with MOODLE_AUDIT_LOCK:
                    for semana_pendiente, actividad_pendiente in pendientes[indice - 1:]:
                        results.append({
                            "semana": semana_pendiente,
                            "actividad": actividad_pendiente["titulo"],
                            "tipo": actividad_pendiente.get("tipo", ""),
                            "estado": "no procesado",
                            "renderiza": "",
                            "titulo_interno": "",
                            "coincide": None,
                            "detalle": "El usuario canceló la auditoría.",
                        })
                break
            veredicto = interpret_activity_probe(sonda, actividad["titulo"])

            pdf_validacion = None
            descarga = (sonda or {}).get("download") or {}
            bytes_descargados = descarga.get("bytes")
            if (
                str(descarga.get("filename") or "").lower().endswith(".pdf")
                and isinstance(bytes_descargados, bytes)
            ):
                pdf_validacion = inspeccionar_pdf_bytes(bytes_descargados)
            pdf = (sonda or {}).get("pdf") or {}
            origen = str(pdf.get("origen") or "")
            if pdf_validacion is None and veredicto["tipo"] == "pdf" and origen and not pdf.get("embebido"):
                # Solo enlace de descarga: se baja el archivo con la sesion
                # abierta y se valida como en PRIZMA (hojas y contenido).
                try:
                    pdf_validacion = inspeccionar_pdf_bytes(client.fetch_bytes(origen))
                except Exception:
                    pdf_validacion = None

            fila = audit_row(nombre_semana, actividad, veredicto, pdf_validacion)
            with MOODLE_AUDIT_LOCK:
                results.append(fila)

        cancelled = bool(job.get("cancel_requested"))
        _comparar_matriz(results, job.get("matrix_rows"), complete=not cancelled)
        report = audit_report_from_results(
            results, "Cancelado por el usuario." if cancelled else ""
        )
        paths = write_moodle_audit_report(job, report)
        with MOODLE_AUDIT_LOCK:
            job.update({
                "status": "cancelled" if cancelled else "completed",
                "message": (
                    "Auditoría cancelada por el usuario." if cancelled
                    else "Auditoría del curso terminada."
                ),
                "report": report,
                "report_paths": paths,
                "finished": True,
                "progress": {
                    "index": len(results),
                    "total": max(total, len(results)),
                    "week": "",
                    "title": "",
                    "phase": "Cancelado" if cancelled else "Completado",
                },
            })
    except Exception as exc:
        cancelled = bool(job.get("cancel_requested"))
        message = "Auditoría cancelada por el usuario." if cancelled else _mensaje_amistoso(exc)
        _comparar_matriz(results, job.get("matrix_rows"), complete=False)
        report = audit_report_from_results(
            results, "Cancelado por el usuario." if cancelled else message
        ) if results else None
        paths = write_moodle_audit_report(job, report) if report else {}
        with MOODLE_AUDIT_LOCK:
            job.update({
                "status": "cancelled" if cancelled else "error",
                "message": message,
                "report": report,
                "report_paths": paths,
                "finished": True,
            })
    finally:
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
