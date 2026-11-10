"""Estado de los cargues y cola de ejecucion con limite de cargues simultaneos.

El historial y los reportes viven en auto_prizma.services.history.
"""

from auto_prizma.automation.prizma import engine as motor_prizma_modulo
from auto_prizma.automation.prizma.engine import (
    ejecutar_cargue,
    validar_credenciales_prizma,
)
import json
import os
import threading
import uuid
from collections import deque

from auto_prizma.core.clock import _ahora_colombia_iso
from auto_prizma.core.config import (
    FORMATO_RECURSO_POR_DEFECTO,
    MAX_CARGUES_SIMULTANEOS,
    RESULTADOS_DIR,
    TEMP_DIR,
    UPLOADS_DIR,
)
from auto_prizma.services.auth import USUARIO_ACTUAL, _es_de
from auto_prizma.services.history import _nombre_reporte, _registrar_reporte_final
from auto_prizma.services.matrix_analysis import _parsear_datos_academicos


# ============================================================
# TRABAJOS
# ============================================================

TRABAJOS = {}
TRABAJOS_LOCK = threading.RLock()
COLA_CARGUES = deque()
COLA_CONDICION = threading.Condition(TRABAJOS_LOCK)

# Cuantos cargues pueden correr al mismo tiempo: MAX_CARGUES_SIMULTANEOS
# (maximo 2, ver auto_prizma.core.config).

CARGUES_ACTIVOS = 0


def _codificar_clave_actividad(hoja, fila):
    return json.dumps(
        [str(hoja or ""), int(fila or 0)],
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _parsear_clave_actividad(valor):
    try:
        datos = json.loads(str(valor or ""))
    except (TypeError, ValueError, json.JSONDecodeError):
        return None

    if not isinstance(datos, list) or len(datos) != 2:
        return None

    hoja = str(datos[0] or "")
    try:
        fila = int(datos[1])
    except (TypeError, ValueError):
        return None

    if not hoja or fila <= 0:
        return None

    return hoja, fila


def _validar_seleccion_actividades(valores, resultado):
    permitidas = set()
    for hoja in (resultado or {}).get("hojas", []) or []:
        nombre_hoja = str(hoja.get("hoja") or "")
        for actividad in hoja.get("actividades", []) or []:
            try:
                fila = int(actividad.get("fila") or 0)
            except (TypeError, ValueError):
                continue
            if nombre_hoja and fila > 0:
                permitidas.add((nombre_hoja, fila))

    seleccion = []
    vistas = set()
    for valor in valores or []:
        clave = _parsear_clave_actividad(valor)
        if clave is None or clave not in permitidas or clave in vistas:
            continue
        vistas.add(clave)
        seleccion.append([clave[0], clave[1]])

    return seleccion


def _cursos_desde_hojas(hojas):
    cursos = []
    vistos = set()

    for hoja in hojas or []:
        curso = str(hoja.get("curso") or "").strip() or "Curso sin nombre"
        programa = str(hoja.get("programa") or "").strip() or "Programa sin nombre"
        clave = (curso.casefold(), programa.casefold())
        if clave in vistos:
            continue
        vistos.add(clave)
        cursos.append({"curso": curso, "programa": programa})

    return cursos


def ejecutar_cargue_con_historial(
    ruta_excel,
    ruta_zip,
    carpeta_temp,
    ruta_reporte,
    procesar_ovi,
    procesar_ova,
    procesar_retos,
    usuario_prizma,
    contrasena_prizma,
    trabajo,
):
    # El hilo del worker no hereda el contexto de la peticion.
    testigo_usuario = USUARIO_ACTUAL.set(trabajo.get("usuario_app"))

    try:
        ejecutar_cargue(
            ruta_excel,
            ruta_zip,
            carpeta_temp,
            ruta_reporte,
            procesar_ovi,
            procesar_ova,
            procesar_retos,
            usuario_prizma,
            contrasena_prizma,
            trabajo,
            trabajo.get("seleccion_actividades"),
            formato_recurso=trabajo.get("formato_recurso") or FORMATO_RECURSO_POR_DEFECTO,
            preparacion=trabajo.get("preparacion"),
            ruta_syllabus=trabajo.get("ruta_syllabus") or "",
        )
    finally:
        USUARIO_ACTUAL.reset(testigo_usuario)
        # El registro en historial se hace en _ejecutar_cargue_en_hilo,
        # despues de que tambien corra (si aplica) el Test Evaluativo,
        # para que el resultado del test quede reflejado.


# ============================================================
# COLA GLOBAL DE CARGUES - HASTA 2 PROCESOS A LA VEZ
# ============================================================

def _posicion_en_cola(trabajo_id):
    with TRABAJOS_LOCK:
        pendientes = [
            tid for tid in COLA_CARGUES
            if tid in TRABAJOS
            and TRABAJOS[tid].get("etapa") == "en_cola"
            and not TRABAJOS[tid].get("terminado")
        ]
        try:
            return pendientes.index(trabajo_id) + 1
        except ValueError:
            return None


def _encolar_trabajo(trabajo_id, usuario_prizma, contrasena_prizma):
    with COLA_CONDICION:
        trabajo = TRABAJOS[trabajo_id]
        # Las credenciales solo viven en estos dos campos temporales: el hilo
        # del cargue (o la cancelacion) los elimina. Nunca se guardan en otro
        # campo del trabajo, que permanece en memoria mientras el servidor vive.
        trabajo["usuario_prizma_temporal"] = usuario_prizma
        trabajo["contrasena_prizma_temporal"] = contrasena_prizma
        trabajo["etapa"] = "en_cola"
        trabajo["mensaje"] = "Cargue agregado a la cola de procesamiento."
        trabajo["encolado_en"] = _ahora_colombia_iso()
        trabajo["cancelar_solicitado"] = False
        trabajo["terminado"] = False
        if trabajo_id not in COLA_CARGUES:
            COLA_CARGUES.append(trabajo_id)

        # Despacha solo si hay uno de los dos cupos globales disponible.
        # Si ambos estan ocupados, el trabajo conserva su posicion FIFO.
        _despachar_cargues_pendientes()


def _hay_capacidad():
    """Debe llamarse con COLA_CONDICION tomado."""
    return CARGUES_ACTIVOS < MAX_CARGUES_SIMULTANEOS


def _despachar_cargues_pendientes():
    """Lanza un hilo propio por cada cargue que quepa.

    Debe llamarse con COLA_CONDICION tomado.
    """
    global CARGUES_ACTIVOS

    while COLA_CARGUES and _hay_capacidad():
        trabajo_id = COLA_CARGUES.popleft()
        trabajo = TRABAJOS.get(trabajo_id)

        if not trabajo:
            continue

        if trabajo.get("terminado") or trabajo.get("cancelar_solicitado"):
            continue

        CARGUES_ACTIVOS += 1

        threading.Thread(
            target=_ejecutar_cargue_en_hilo,
            args=(trabajo_id,),
            name="auto-prizma-cargue-" + str(trabajo_id)[:8],
            daemon=True,
        ).start()

    COLA_CONDICION.notify_all()


def _ejecutar_test_en_cargue(trabajo, test_job_id, usuario, contrasena):
    from auto_prizma.evaluative_tests.state import _JOBS, _JOBS_LOCK
    from auto_prizma.evaluative_tests.execution import ejecutar_test_job
    with _JOBS_LOCK:
        job_test = _JOBS.get(test_job_id)
    if not job_test:
        return

    doc = job_test.get("document")
    if not doc or not getattr(doc, "tests", None):
        return

    tests_list = doc.tests
    num_tests = len(tests_list)
    if num_tests == 0:
        return

    cascada_test = job_test.get("cascada_datos") or {}
    ruta_reporte = trabajo.get("ruta_reporte")

    detalle = trabajo.setdefault("detalle_actividades", [])
    offset = len(detalle)
    for idx, t in enumerate(tests_list, start=1):
        num_preg = sum(len(sec.questions) for sec in t.sections)
        detalle.append({
            "numero": offset + idx,
            "nombre": f"Test Evaluativo: {t.title or f'Test {idx}'} ({num_preg} preguntas)",
            "estado": "pendiente",
            "error": "",
        })

    trabajo["total"] = len(detalle)
    trabajo["terminado"] = False
    trabajo["etapa"] = "cargando_test"
    trabajo["mensaje"] = f"Iniciando cargue del Test Evaluativo en PRIZMA ({num_tests} examen{'es' if num_tests > 1 else ''})..."

    def _fila_test_reporte(indice, item, resultado):
        t = tests_list[indice - 1] if 0 < indice <= len(tests_list) else None
        actividad = {
            "fila_excel": f"Test {indice}",
            "programa": cascada_test.get("programa") or "",
            "curso": cascada_test.get("asignatura") or "",
            "semana": (getattr(t, "week", "") or cascada_test.get("nivel") or "") if t else "",
            "unidad": (getattr(t, "cut", "") or "") if t else "",
            "nombre": item["nombre"],
            "categoria_prizma": "Test Evaluativo",
            "tipo_archivo": "Test",
        }
        try:
            motor_prizma_modulo.guardar_resultado(
                ruta_reporte,
                actividad,
                resultado,
                item.get("error") or "",
            )
        except Exception:
            pass

    def on_test(indice, estado_test, msg_test, err=""):
        item_idx = offset + indice - 1
        if 0 <= item_idx < len(trabajo["detalle_actividades"]):
            item = trabajo["detalle_actividades"][item_idx]
            if estado_test == "en_proceso":
                item["estado"] = "procesando"
                trabajo["mensaje"] = f"Cargando {item['nombre']}..."
            elif estado_test == "exitoso":
                item["estado"] = "ok"
                trabajo["procesadas"] = (trabajo.get("procesadas") or 0) + 1
                trabajo["exitosas"] = (trabajo.get("exitosas") or 0) + 1
                trabajo["mensaje"] = f"{item['nombre']} guardado con éxito."
                if ruta_reporte:
                    _fila_test_reporte(indice, item, "Cargado")
            elif estado_test == "omitido":
                # Ya existía en PRIZMA de un intento anterior: el objetivo ya
                # está cumplido (el test está en PRIZMA), solo no se duplica.
                item["estado"] = "ok"
                trabajo["procesadas"] = (trabajo.get("procesadas") or 0) + 1
                trabajo["exitosas"] = (trabajo.get("exitosas") or 0) + 1
                trabajo["mensaje"] = f"{item['nombre']} ya estaba cargado en PRIZMA (omitido para no duplicar)."
                if ruta_reporte:
                    _fila_test_reporte(indice, item, "Omitido")
            elif estado_test == "error":
                item["estado"] = "error"
                item["error"] = err or msg_test
                trabajo["procesadas"] = (trabajo.get("procesadas") or 0) + 1
                trabajo["errores"] = (trabajo.get("errores") or 0) + 1
                trabajo["mensaje"] = f"Error en {item['nombre']}: {item['error']}"
                if ruta_reporte:
                    _fila_test_reporte(indice, item, "Error")
            elif estado_test == "cancelado":
                item["estado"] = "error"
                item["error"] = "Detenido por usuario"
                if ruta_reporte:
                    _fila_test_reporte(indice, item, "Cancelado")

    def on_log(nivel, msg, snap=None):
        if nivel in ["error", "warn"]:
            trabajo["mensaje"] = f"Test: {msg}"

    res = ejecutar_test_job(
        job_id=test_job_id,
        usuario_prizma=usuario,
        clave_prizma=contrasena,
        user=trabajo.get("usuario_app", ""),
        simulacion=False,
        headless=True,
        on_test_callback=on_test,
        on_log_callback=on_log,
        cancel_checker=lambda: bool(trabajo.get("cancelar_solicitado")),
    )

    trabajo["terminado"] = True
    ex = trabajo.get("exitosas", 0)
    er = trabajo.get("errores", 0)
    if not res.get("ok"):
        trabajo["etapa"] = "error"
        trabajo["mensaje"] = f"Error en el cargue del Test Evaluativo: {res.get('error', 'Error desconocido.')}"
    else:
        trabajo["etapa"] = "finalizado"
        trabajo["mensaje"] = f"Cargue completo finalizado. Exitosas: {ex}. Errores: {er}."


def _ejecutar_cargue_en_hilo(trabajo_id):
    """Corre UN cargue completo. Cada cargue tiene su propio hilo y su
    propio navegador, asi que varios usuarios pueden cargar a la vez."""
    global CARGUES_ACTIVOS

    usuario = ""
    contrasena = ""

    with COLA_CONDICION:
        trabajo = TRABAJOS.get(trabajo_id)

        if not trabajo:
            CARGUES_ACTIVOS -= 1
            COLA_CONDICION.notify_all()
            return

        usuario = trabajo.pop("usuario_prizma_temporal", "")
        contrasena = trabajo.pop("contrasena_prizma_temporal", "")
        trabajo["etapa"] = "iniciando"
        trabajo["mensaje"] = "Iniciando navegador y autenticación PRIZMA..."
        trabajo["iniciado_en"] = _ahora_colombia_iso()
        trabajo["terminado"] = False

    try:
        tiene_recursos = (
            bool(trabajo.get("procesar_ovi")) or
            bool(trabajo.get("procesar_ova")) or
            bool(trabajo.get("procesar_retos"))
        )
        test_job_id = trabajo.get("test_job_id")

        if tiene_recursos:
            ejecutar_cargue_con_historial(
                trabajo["ruta_excel"],
                trabajo["ruta_zip"],
                trabajo["carpeta_temp"],
                trabajo["ruta_reporte"],
                trabajo["procesar_ovi"],
                trabajo["procesar_ova"],
                trabajo["procesar_retos"],
                usuario,
                contrasena,
                trabajo,
            )

        if test_job_id and not trabajo.get("cancelar_solicitado"):
            msg_act = str(trabajo.get("mensaje", ""))
            # Si hubo error fatal de login en los recursos, no intentamos el test
            if tiene_recursos and ("ERROR_LOGIN_PRIZMA" in msg_act or "No fue posible iniciar sesión en PRIZMA" in msg_act):
                pass
            else:
                _ejecutar_test_en_cargue(trabajo, test_job_id, usuario, contrasena)

    except Exception as exc:
        trabajo["etapa"] = "error"
        trabajo["mensaje"] = str(exc)
        trabajo["terminado"] = True
    finally:
        usuario = ""
        contrasena = ""
        trabajo.pop("usuario_prizma_temporal", None)
        trabajo.pop("contrasena_prizma_temporal", None)
        trabajo["finalizado_en"] = _ahora_colombia_iso()
        _registrar_reporte_final(trabajo)

        with COLA_CONDICION:
            CARGUES_ACTIVOS -= 1
            _despachar_cargues_pendientes()


# ============================================================
# CICLO DE VIDA DE UN TRABAJO (lo usan las rutas web)
# ============================================================

# Etapas en las que un trabajo cuenta como "cargue en curso".
ETAPAS_ACTIVAS = {
    "en_cola",
    "iniciando",
    "login",
    "preparando",
    "procesando",
    "validando_login",
    "cargando_test",
}


def create_analyzed_job(
    contenido_excel,
    contenido_zip,
    hojas,
    zip_info,
    nombre_matriz,
    procesar_ovi,
    procesar_ova,
    procesar_retos,
    usuario_app,
    test_job_id=None,
    test_info=None,
    formato_recurso=FORMATO_RECURSO_POR_DEFECTO,
    contenido_syllabus=None,
    nombre_syllabus="",
    linea_academica="",
    nivel_pensum="",
):
    """Registra un trabajo de cargue a partir de un analisis valido.

    Guarda la matriz y el ZIP en uploads/<id>/, crea temp/<id>/, ejecuta la
    deja el trabajo en TRABAJOS con etapa "analizado". Los recursos se
    resuelven exclusivamente contra el ZIP seleccionado por el usuario.

    Args:
        contenido_excel: bytes de la matriz ya normalizada a XLSX.
        contenido_zip: bytes del ZIP de recursos.
        hojas: hojas validas devueltas por analizar_excel.
        zip_info: resumen devuelto por analizar_zip.
        nombre_matriz: nombre visible de la matriz.
        procesar_ovi, procesar_ova, procesar_retos: categorias elegidas.
        usuario_app: usuario de la aplicacion dueno del trabajo.
        test_job_id: id del Test Evaluativo combinado, si lo hay.
        test_info: resumen del Test Evaluativo para la pagina, si lo hay.
        formato_recurso: "H5P" o "HTML".
        contenido_syllabus: bytes del PDF del syllabus, si lo hay.
        nombre_syllabus: nombre visible del syllabus.
        linea_academica: "programa pensum asignatura nombre" de la ficha a
            preparar (opcional; vacio = sin preparacion).
        nivel_pensum: nivel de pensum de la misma ficha.

    Returns:
        (trabajo_id, resultado): resultado es lo que muestra la pagina de analisis.

    Raises:
        ValueError: si los archivos no se pueden guardar.
    """
    trabajo_id = uuid.uuid4().hex
    carpeta_trabajo = os.path.join(UPLOADS_DIR, trabajo_id)
    os.makedirs(carpeta_trabajo, exist_ok=True)

    ruta_excel = os.path.join(carpeta_trabajo, "matriz.xlsx")
    ruta_zip = os.path.join(carpeta_trabajo, "recursos.zip")

    with open(ruta_excel, "wb") as archivo:
        archivo.write(contenido_excel)

    with open(ruta_zip, "wb") as archivo:
        archivo.write(contenido_zip)

    # Syllabus opcional (PDF aparte del ZIP) para la preparación de la
    # asignatura; los videos de intro/cierre se toman del ZIP adjunto.
    ruta_syllabus = ""
    preparacion = {
        "syllabus": False,
        "video_intro": "",
        "video_cierre": "",
        "linea_academica": str(linea_academica or "").strip(),
        "nivel": str(nivel_pensum or "").strip(),
        "curso": None,
    }

    if contenido_syllabus:
        ruta_syllabus = os.path.join(carpeta_trabajo, "syllabus.pdf")
        with open(ruta_syllabus, "wb") as archivo:
            archivo.write(contenido_syllabus)
        preparacion["syllabus"] = True

    if preparacion["linea_academica"] and preparacion["nivel"]:
        datos_academicos = _parsear_datos_academicos(
            preparacion["linea_academica"]
        )
        if datos_academicos:
            datos_academicos["nivel"] = preparacion["nivel"]
            preparacion["curso"] = datos_academicos

    videos = motor_prizma_modulo.detect_assignment_videos(contenido_zip)
    preparacion["video_intro"] = videos.get("intro", "")
    preparacion["video_cierre"] = videos.get("closing", "")

    carpeta_temp = os.path.join(TEMP_DIR, trabajo_id)
    os.makedirs(carpeta_temp, exist_ok=True)

    modo_html = str(formato_recurso or "").strip().upper() == "HTML"
    cursos_trabajo = _cursos_desde_hojas(hojas)
    ruta_reporte = os.path.join(
        RESULTADOS_DIR,
        _nombre_reporte(cursos_trabajo, trabajo_id),
    )

    TRABAJOS[trabajo_id] = {
        "id": trabajo_id,
        "ruta_excel": ruta_excel,
        "ruta_zip": ruta_zip,
        "carpeta_temp": carpeta_temp,
        "ruta_reporte": ruta_reporte,
        "procesar_ovi": procesar_ovi,
        "procesar_ova": procesar_ova,
        "procesar_retos": procesar_retos,
        "formato_recurso": "HTML" if modo_html else "H5P",
        "etapa": "analizado",
        "mensaje": "Archivos analizados correctamente.",
        "total": 0,
        "procesadas": 0,
        "exitosas": 0,
        "errores": 0,
        "terminado": False,
        "detalle_actividades": [],
        "nombre_matriz": nombre_matriz,
        "usuario_app": usuario_app,
        "cursos": cursos_trabajo,
        "historial_registrado": False,
        "creado_en": _ahora_colombia_iso(),
        "cancelar_solicitado": False,
        "preparacion": preparacion,
        "ruta_syllabus": ruta_syllabus,
    }

    resultado = {
        "hojas": hojas,
        "zip": zip_info,
        "nombre_matriz": nombre_matriz,
        "formato_recurso": "HTML" if modo_html else "H5P",
        "preparacion": preparacion,
    }

    if test_info is not None:
        resultado["test_info"] = test_info
        TRABAJOS[trabajo_id]["test_job_id"] = test_job_id

    TRABAJOS[trabajo_id]["resultado_analisis"] = resultado

    return trabajo_id, resultado


def validate_access_and_enqueue(
    trabajo_id,
    usuario_prizma,
    contrasena_prizma,
    seleccion_actividades=None,
):
    """Reserva el trabajo, valida credenciales y lo encola si sigue vigente.

    Returns:
        (True, "") si el trabajo quedo en cola, o (False, mensaje) si ya habia
        sido iniciado, se cancelo o PRIZMA rechazo/no respondio. La reserva de
        etapa se hace bajo el lock; la validacion externa ocurre sin lock.
    """
    with COLA_CONDICION:
        trabajo = TRABAJOS.get(trabajo_id)
        if not trabajo or trabajo.get("etapa") not in {"analizado", "error"}:
            return False, "Este trabajo ya fue iniciado."
        trabajo["etapa"] = "validando_login"
        trabajo["mensaje"] = "Validando usuario y contraseña en PRIZMA..."
        if seleccion_actividades is not None:
            trabajo["seleccion_actividades"] = seleccion_actividades

    try:
        validacion = validar_credenciales_prizma(usuario_prizma, contrasena_prizma)
    except Exception:
        validacion = {
            "ok": False,
            "mensaje": "No fue posible validar el acceso a PRIZMA. Puedes intentarlo de nuevo.",
        }

    with COLA_CONDICION:
        trabajo = TRABAJOS.get(trabajo_id)
        if not trabajo:
            return False, "Trabajo no encontrado."
        if trabajo.get("cancelar_solicitado"):
            trabajo.pop("cancelar_solicitado", None)
            trabajo["etapa"] = "cancelado"
            trabajo["mensaje"] = "Cargue cancelado durante la validación de acceso."
            trabajo["terminado"] = True
            COLA_CONDICION.notify_all()
            return False, trabajo["mensaje"]
        if trabajo.get("etapa") != "validando_login":
            return False, "Este trabajo ya no está disponible para iniciar."
        if not validacion.get("ok"):
            trabajo["etapa"] = "analizado"
            trabajo["mensaje"] = validacion.get(
                "mensaje", "No fue posible validar el acceso a PRIZMA."
            )
            return False, trabajo["mensaje"]

        _encolar_trabajo(trabajo_id, usuario_prizma, contrasena_prizma)
    return True, ""


def active_jobs():
    """Cargues en curso de todos los usuarios, del mas antiguo al mas reciente."""
    activos = [
        trabajo for trabajo in TRABAJOS.values()
        if not trabajo.get("terminado")
        and trabajo.get("etapa") in ETAPAS_ACTIVAS
    ]
    activos.sort(key=lambda item: item.get("encolado_en") or item.get("iniciado_en") or item.get("creado_en", ""))
    return activos


def crear_trabajo_manual(tipo, titulo, usuario_app, ruta_reporte="", cursos=None):
    """Trabajo corto (reintento individual o verificacion) en TRABAJOS.

    Entra con etapa "preparando" y sin cola: lo ejecuta su propio hilo. Como
    trae todas las claves que leen /estado, /reporte y la tarjeta de
    "Cargue actual", usa la misma pagina de progreso, el mismo cancelado y el
    mismo reporte que un cargue normal.
    """
    trabajo_id = uuid.uuid4().hex
    ahora = _ahora_colombia_iso()

    with TRABAJOS_LOCK:
        TRABAJOS[trabajo_id] = {
            "id": trabajo_id,
            "trabajo_id": trabajo_id,
            "tipo": tipo,
            "titulo": str(titulo or ""),
            "usuario_app": str(usuario_app or ""),
            "cursos": list(cursos or []),
            "creado_en": ahora,
            "iniciado_en": ahora,
            "etapa": "preparando",
            "mensaje": str(titulo or "Preparando..."),
            "total": 0,
            "procesadas": 0,
            "exitosas": 0,
            "errores": 0,
            "terminado": False,
            "ruta_reporte": ruta_reporte or "",
            "detalle_actividades": [],
            "cancelar_solicitado": False,
        }

    return trabajo_id


def cancel_job(trabajo_id, usuario):
    """Pide cancelar un trabajo del usuario.

    Returns:
        "no_encontrado": no existe o pertenece a otra persona.
        "terminado": ya habia terminado; no se hace nada.
        "cancelado": estaba en cola y se cancelo sin llegar a iniciar.
        "solicitado": esta en ejecucion; se detendra de forma segura al
            terminar la actividad actual.
    """
    with COLA_CONDICION:
        trabajo = TRABAJOS.get(trabajo_id)
        if not trabajo or not _es_de(trabajo, usuario):
            return "no_encontrado"

        if trabajo.get("terminado"):
            return "terminado"

        trabajo["cancelar_solicitado"] = True

        if trabajo.get("etapa") == "en_cola":
            try:
                COLA_CARGUES.remove(trabajo_id)
            except ValueError:
                pass
            trabajo.pop("usuario_prizma_temporal", None)
            trabajo.pop("contrasena_prizma_temporal", None)
            trabajo["etapa"] = "cancelado"
            trabajo["mensaje"] = "Proceso cancelado antes de iniciar."
            trabajo["terminado"] = True
            trabajo["finalizado_en"] = _ahora_colombia_iso()
            resultado = "cancelado"
        else:
            trabajo["mensaje"] = (
                "Cancelación solicitada. El proceso se detendrá de forma segura "
                "al terminar la actividad actual."
            )
            resultado = "solicitado"

        COLA_CONDICION.notify_all()

    return resultado


def public_job_status(trabajo_id, usuario):
    """Estado de un trabajo para la pagina de progreso (JSON de /estado).

    Returns:
        El diccionario publico (sin credenciales ni rutas internas salvo la
        disponibilidad del reporte), o None si el trabajo no existe o
        pertenece a otra persona.
    """
    trabajo = TRABAJOS.get(trabajo_id)

    if not trabajo or not _es_de(trabajo, usuario):
        return None

    return {
        "etapa": trabajo["etapa"],
        "mensaje": trabajo["mensaje"],
        "total": trabajo["total"],
        "procesadas": trabajo["procesadas"],
        "exitosas": trabajo["exitosas"],
        "errores": trabajo["errores"],
        "terminado": trabajo["terminado"],
        "detalle_actividades": trabajo.get("detalle_actividades", []),
        "reporte_disponible": os.path.isfile(trabajo["ruta_reporte"]),
        "posicion_cola": _posicion_en_cola(trabajo_id),
        "cancelar_solicitado": bool(trabajo.get("cancelar_solicitado")),
    }


print(
    "Cargues simultaneos:",
    MAX_CARGUES_SIMULTANEOS,
)
