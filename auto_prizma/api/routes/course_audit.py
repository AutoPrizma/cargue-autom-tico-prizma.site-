"""Auditoria profunda de un curso publicado en PRIZMA (solo lectura, sin matriz).

A diferencia de la verificacion de /cursos (que cruza el curso contra el
estado guardado de un cargue), esta auditoria entra al curso tal cual esta,
enumera las actividades del propio listado y abre cada una para validar su
recurso: PDF con hojas y contenido, H5P con paquete valido y titulo de
portada igual al nombre que muestra el curso. No toca nada de PRIZMA.
"""

import csv
import os
import threading
import traceback
from datetime import datetime

from fastapi import Form, Request
from fastapi.responses import HTMLResponse, JSONResponse

from auto_prizma.automation.prizma import engine as motor_prizma
from auto_prizma.api.routes.uploads import _pagina_progreso
from auto_prizma.core.application import app
from auto_prizma.core.config import RESULTADOS_DIR
from auto_prizma.services.auth import USUARIO_ACTUAL, _usuario_actual
from auto_prizma.services.error_messages import mensaje_error
from auto_prizma.services.upload_jobs import (
    TRABAJOS,
    crear_trabajo_manual,
    public_job_status,
)
from auto_prizma.evaluative_tests.state import (
    _cargar_credenciales_prizma,
    _guardar_credenciales_prizma,
)
from auto_prizma.web.course_audit_views import render_prizma_audit_page


# Una auditoria de curso a la vez: abre navegador contra PRIZMA.
_BLOQUE_AUDITORIA = threading.Lock()

_ETIQUETA_ESTADO = {
    "ok": "Completo",
    "revisar": "Revisar",
    "sin_recurso": "Sin recurso",
    "no_se_pudo": "No se pudo revisar",
}


def _lanzar_hilo(target, args):
    """Corre la auditoria en su propio hilo (los tests lo ejecutan en el momento)."""
    threading.Thread(target=target, args=args, daemon=True).start()


def _pagina_error(mensaje):
    return HTMLResponse(
        render_prizma_audit_page(error=mensaje),
        status_code=400,
    )


def _propietario_request(request):
    """Usa la identidad fijada por el middleware en la petición actual."""
    return str(
        getattr(getattr(request, "state", None), "usuario", None)
        or _usuario_actual()
        or ""
    )


def _ruta_reporte_auditoria(trabajo_id):
    marca = datetime.now().strftime("%Y%m%d-%H%M%S")
    return os.path.join(
        RESULTADOS_DIR,
        "Auditoria curso - " + marca + "-" + str(trabajo_id)[:6] + ".csv",
    )


def _escribir_reporte_auditoria(ruta, resultados):
    """CSV de la auditoria (columnas propias: no es un cargue)."""
    with open(ruta, "w", newline="", encoding="utf-8-sig") as fh:
        escritor = csv.writer(fh)
        escritor.writerow([
            "Pestaña", "Actividad", "Tipo", "Estado",
            "Título interno", "Coincide con el curso", "Detalle",
        ])
        for entrada in resultados:
            coincide = entrada.get("coincide")
            if coincide is True:
                coincide_texto = "Sí"
            elif coincide is False:
                coincide_texto = "No"
            else:
                coincide_texto = ""
            escritor.writerow([
                str(entrada.get("categoria") or ""),
                str(entrada.get("nombre") or ""),
                str(entrada.get("tipo") or ""),
                _ETIQUETA_ESTADO.get(
                    str(entrada.get("estado") or ""), "No se pudo revisar"
                ),
                str(entrada.get("titulo_interno") or ""),
                coincide_texto,
                str(entrada.get("detalle") or ""),
            ])


def _ejecutar_auditoria_curso(trabajo_id, usuario_prizma, contrasena_prizma, curso_prizma):
    """Hilo: audita el curso publicado y deja el resultado en el trabajo."""
    trabajo = TRABAJOS.get(trabajo_id)
    testigo = None
    try:
        if trabajo is None:
            return

        testigo = USUARIO_ACTUAL.set(str(trabajo.get("usuario_app") or ""))

        resultado = motor_prizma.auditar_curso_prizma(
            usuario_prizma,
            contrasena_prizma,
            curso_prizma,
            trabajo,
        ) or {}

        error = str(resultado.get("error") or "")
        if not resultado.get("ok"):
            if error == "ERROR_CANCELADO":
                mensaje = "Auditoría cancelada por el usuario."
                etapa = "cancelado"
            elif error.startswith("ERROR_SELECCION_CURSO_PRIZMA:"):
                detalle = error.split(":", 1)[-1].strip()
                mensaje = "No se pudo abrir la vista previa del curso seleccionado. " + detalle
                etapa = "error"
            else:
                mensaje = "No se pudo auditar el curso: " + mensaje_error(error)
                etapa = "error"
            motor_prizma.actualizar_estado(
                trabajo,
                etapa=etapa,
                mensaje=mensaje,
                terminado=True,
            )
            return

        resultados = resultado.get("resultados") or []
        _escribir_reporte_auditoria(trabajo["ruta_reporte"], resultados)

        filas = []
        for numero, entrada in enumerate(resultados, start=1):
            es_ok = str(entrada.get("estado")) == "ok"
            filas.append({
                "numero": numero,
                "nombre": str(entrada.get("nombre") or entrada.get("categoria") or ""),
                "estado": "ok" if es_ok else "error",
                "error": "" if es_ok else str(entrada.get("detalle") or ""),
            })
        trabajo["detalle_actividades"] = filas

        total = len(resultados)
        exitosas = sum(
            1 for entrada in resultados
            if str(entrada.get("estado")) == "ok"
        )
        problemas = total - exitosas
        if total == 0:
            mensaje = (
                "Auditoría terminada: el curso no muestra actividades en sus "
                "pestañas (OVI, OVA y Retos)."
            )
        elif problemas:
            mensaje = (
                "Auditoría terminada: " + str(exitosas) + " de " + str(total)
                + " actividades están completas; revisa el reporte para ver "
                "qué ajustar."
            )
        else:
            mensaje = (
                "Auditoría terminada: las " + str(total)
                + " actividades del curso están completas."
            )
        motor_prizma.actualizar_estado(
            trabajo,
            etapa="completado",
            mensaje=mensaje,
            total=total,
            procesadas=total,
            exitosas=exitosas,
            errores=problemas,
            terminado=True,
        )
    except Exception as exc:
        traceback.print_exc()
        try:
            motor_prizma.actualizar_estado(
                trabajo,
                etapa="error",
                mensaje="No se pudo completar la auditoría: " + str(exc)[:200],
                terminado=True,
            )
        except Exception:
            pass
    finally:
        if testigo is not None:
            USUARIO_ACTUAL.reset(testigo)
        _BLOQUE_AUDITORIA.release()


@app.get("/auditor-curso", response_class=HTMLResponse)
def pagina_auditoria_curso(request: Request):
    credenciales = _cargar_credenciales_prizma(_propietario_request(request))
    return HTMLResponse(render_prizma_audit_page(
        usuario_prizma=credenciales.get("usuario", ""),
        recordar_usuario=credenciales.get("recordar", True),
    ))


@app.post("/auditor-curso", response_class=HTMLResponse)
def iniciar_auditoria_curso(
    request: Request,
    usuario_prizma: str = Form(""),
    contrasena_prizma: str = Form(""),
    linea_academica: str = Form(""),
    nivel_pensum: str = Form(""),
    facultad: str = Form(""),
    recordar_credenciales: str | None = Form(default=None),
    modo_navegador: str = Form("segundo_plano"),
):
    usuario_prizma = str(usuario_prizma or "").strip()
    contrasena_prizma = str(contrasena_prizma or "")

    if not usuario_prizma or not contrasena_prizma:
        return _pagina_error(
            "Escribe el usuario y la contraseña de PRIZMA para poder auditar."
        )

    recordar = bool(recordar_credenciales)
    _guardar_credenciales_prizma(
        _propietario_request(request),
        {"usuario": usuario_prizma if recordar else "", "recordar": recordar},
    )

    linea_academica = str(linea_academica or "").strip()
    nivel_pensum = str(nivel_pensum or "").strip()
    facultad = str(facultad or "").strip()
    modo_navegador = str(modo_navegador or "segundo_plano").strip()
    if modo_navegador not in {"segundo_plano", "visual"}:
        return _pagina_error("Selecciona un modo de navegador válido.")
    from auto_prizma.services.matrix_analysis import _parsear_datos_academicos

    datos_academicos = _parsear_datos_academicos(linea_academica)
    if not datos_academicos:
        return _pagina_error(
            "Pega la línea académica con código de programa, código de pensum, "
            "código de asignatura y nombre de asignatura."
        )
    if not nivel_pensum:
        return _pagina_error("Selecciona o escribe el nivel de pensum para continuar.")

    curso_prizma = {
        "facultad": facultad,
        "programa": datos_academicos["programa"],
        "pensum": datos_academicos["pensum"],
        "nivel": nivel_pensum,
        "codigo_asignatura": datos_academicos["codigo_asignatura"],
        "asignatura": (
            str(datos_academicos["codigo_asignatura"])
            + " " + str(datos_academicos["asignatura"])
        ).strip(),
        "linea_academica": linea_academica,
        "modo_navegador": modo_navegador,
    }

    if not _BLOQUE_AUDITORIA.acquire(blocking=False):
        return _pagina_error(
            "Ya hay una auditoría de curso en curso. Espera a que termine "
            "antes de empezar otra."
        )

    try:
        trabajo_id = crear_trabajo_manual(
            "auditor-curso",
            "Auditoría: " + curso_prizma["asignatura"],
            _propietario_request(request),
        )
        trabajo = TRABAJOS[trabajo_id]
        trabajo["ruta_reporte"] = _ruta_reporte_auditoria(trabajo_id)

        pagina = _pagina_progreso(
            titulo="Auditoría de curso en progreso",
            lista_titulo="Actividades del curso",
            active="curso-auditor",
            estado_url="/auditor-curso/__TRABAJO_ID__/estado",
        ).replace("__TRABAJO_ID__", str(trabajo["id"]))
        trabajo["pagina_progreso"] = pagina

        _lanzar_hilo(
            _ejecutar_auditoria_curso,
            (trabajo_id, usuario_prizma, contrasena_prizma, curso_prizma),
        )

        return HTMLResponse(pagina)
    except Exception:
        _BLOQUE_AUDITORIA.release()
        traceback.print_exc()
        return _pagina_error(
            "Ocurrió un error inesperado al montar la auditoría; revisa el log."
        )


@app.get("/auditor-curso/{trabajo_id}/estado")
def estado_auditoria_curso(trabajo_id: str, request: Request):
    """Estado público del trabajo de auditoría, aislado por propietario."""
    estado = public_job_status(trabajo_id, _propietario_request(request))
    if estado is None:
        return JSONResponse({"error": "No se encontró la auditoría de este usuario."}, status_code=404)
    return estado
