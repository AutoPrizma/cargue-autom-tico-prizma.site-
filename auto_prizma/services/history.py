"""Historial de cargues y reportes CSV.

Registra cada cargue (y cada Test Evaluativo) en data/historial.json, arma los
nombres y rutas de los reportes y entrega a cada usuario solo sus registros.
"""

import csv
import os
import re
import threading
from datetime import datetime, timedelta

from auto_prizma.core.clock import _ahora_colombia, _ahora_colombia_iso
from auto_prizma.core.config import HISTORIAL_PATH, LOCAL_DATA_RETENTION_DAYS, RESULTADOS_DIR
from auto_prizma.core.storage import read_json, write_json_atomic
from auto_prizma.services.auth import _normalizar_usuario, _usuario_actual


HISTORIAL_LOCK = threading.Lock()
DIAS_CONSERVAR_HISTORIAL = LOCAL_DATA_RETENTION_DAYS


# ============================================================
# NOMBRES Y RUTAS DE REPORTES
# ============================================================

def _sanitizar_parte_nombre(valor, limite=70):
    texto = str(valor or "").strip()
    texto = re.sub(r'[\\/:*?"<>|]+', "-", texto)
    texto = re.sub(r"\s+", " ", texto).strip(" .-")
    if not texto:
        texto = "Sin nombre"
    return texto[:limite].rstrip()


def _nombre_reporte(cursos, trabajo_id):
    fecha = _ahora_colombia().strftime("%Y-%m-%d_%H-%M-%S")

    if cursos:
        curso = _sanitizar_parte_nombre(cursos[0]["curso"], 58)
        programa = _sanitizar_parte_nombre(cursos[0]["programa"], 58)
        extra = ""
        if len(cursos) > 1:
            extra = f"_y_{len(cursos) - 1}_curso_mas"
        return f"{fecha} - {curso} - {programa}{extra} - {trabajo_id[:6]}.csv"

    return f"{fecha} - resultado_prizma - {trabajo_id[:6]}.csv"


def _ruta_reporte_test(cascada, test_job_id):
    """Ruta del CSV de reporte para un Test Evaluativo ejecutado SOLO
    (sin OVI/OVA/Retos), fuera de la cola de cargues normal."""
    fecha = _ahora_colombia().strftime("%Y-%m-%d_%H-%M-%S")
    asignatura = _sanitizar_parte_nombre((cascada or {}).get("asignatura") or "Test Evaluativo", 58)
    nombre = f"{fecha} - {asignatura} - Test - {test_job_id[:6]}.csv"
    return os.path.join(RESULTADOS_DIR, nombre)


# ============================================================
# HISTORIAL
# ============================================================

def _cargar_historial():
    # Un historial ilegible se trata como vacio (cualquier error).
    return read_json(HISTORIAL_PATH, [], list, errors=(Exception,))


def _guardar_historial(registros):
    write_json_atomic(HISTORIAL_PATH, registros)


def _purgar_registros_viejos(registros, ahora=None):
    """Elimina registros vencidos y sus CSV, sin salir de la carpeta local."""
    ahora = ahora or _ahora_colombia()
    limite = ahora - timedelta(days=DIAS_CONSERVAR_HISTORIAL)
    conservar = []
    vencidos = []
    for registro in registros:
        try:
            fecha = datetime.fromisoformat(str(registro.get("fecha_iso") or ""))
            if fecha.tzinfo is None:
                fecha = fecha.replace(tzinfo=ahora.tzinfo)
        except (TypeError, ValueError):
            # Fechas ilegibles se conservan por seguridad.
            conservar.append(registro)
            continue
        (vencidos if fecha < limite else conservar).append(registro)

    nombres_activos = {
        os.path.basename(str(r.get("archivo_reporte") or ""))
        for r in conservar
    }
    nombres_borrar = {
        os.path.basename(str(r.get("archivo_reporte") or ""))
        for r in vencidos
    } - nombres_activos
    return conservar, nombres_borrar


def _eliminar_reportes_viejos(nombres):
    for nombre in nombres:
        if not nombre:
            continue
        ruta = os.path.join(RESULTADOS_DIR, nombre)
        try:
            os.remove(ruta)
        except FileNotFoundError:
            pass
        except OSError:
            pass


def limpiar_historial_viejo():
    """Purge registros y reportes locales con más de 15 días."""
    with HISTORIAL_LOCK:
        registros = _cargar_historial()
        conservados, reportes_viejos = _purgar_registros_viejos(registros)
        if len(conservados) != len(registros):
            _guardar_historial(conservados)
        _eliminar_reportes_viejos(reportes_viejos)


def _agregar_registro_historial(registro_id, ruta_reporte, cursos, estado_final, usuario_app, tipo=None):
    """Escribe una fila en data/historial.json si no existe ya ese id.
    Usado tanto por cargues de recursos (OVI/OVA/Retos) como por
    tests evaluativos (combinados o exclusivos)."""
    if not ruta_reporte or not os.path.isfile(ruta_reporte):
        return False

    with HISTORIAL_LOCK:
        registros = _cargar_historial()
        registros_limpios, reportes_viejos = _purgar_registros_viejos(registros)

        if any(r.get("id") == registro_id for r in registros_limpios):
            if len(registros_limpios) != len(registros):
                _guardar_historial(registros_limpios)
            _eliminar_reportes_viejos(reportes_viejos)
            return False

        registro = {
            "id": registro_id,
            "fecha_iso": _ahora_colombia_iso(),
            "archivo_reporte": os.path.basename(ruta_reporte),
            "cursos": cursos or [],
            "estado_final": estado_final,
            "usuario_app": usuario_app,
        }
        if tipo:
            registro["tipo"] = tipo
        registros_limpios.append(registro)
        _guardar_historial(registros_limpios)
        _eliminar_reportes_viejos(reportes_viejos)
        return True


def _registrar_historial_test(test_job_id, ruta_reporte, cascada, estado_final, usuario_app):
    """Registra en data/historial.json el resultado de un Test Evaluativo
    ejecutado SOLO (flujo exclusivo, sin recursos OVI/OVA/Retos)."""
    cascada = cascada or {}
    cursos = [{
        "curso": f"Test Evaluativo: {cascada.get('asignatura') or 'Sin asignatura'}",
        "programa": cascada.get("programa") or "Programa sin nombre",
    }]
    return _agregar_registro_historial(test_job_id, ruta_reporte, cursos, estado_final, usuario_app, tipo="test")


def _registrar_reporte_final(trabajo):
    escrito = _agregar_registro_historial(
        trabajo.get("id"),
        trabajo.get("ruta_reporte"),
        trabajo.get("cursos", []),
        trabajo.get("etapa", "finalizado"),
        trabajo.get("usuario_app"),
    )
    if escrito or trabajo.get("historial_registrado"):
        trabajo["historial_registrado"] = True


# ============================================================
# CONSULTA POR USUARIO
# ============================================================

def _historial_del_usuario(usuario=None):
    """Solo los registros de esa persona.

    Los registros viejos (anteriores al login) no tienen dueno y no se
    muestran a nadie, para no filtrar reportes de otros.
    """
    usuario = usuario or _usuario_actual()
    limpiar_historial_viejo()

    return [
        registro for registro in _cargar_historial()
        if _normalizar_usuario(
            registro.get("usuario_app")
        ) == _normalizar_usuario(usuario)
    ]


def _leer_reporte_csv(ruta):
    """Devuelve (cabeceras, filas) del CSV del reporte."""
    with open(ruta, "r", encoding="utf-8-sig", newline="") as archivo:
        lector = csv.reader(archivo)
        filas = [fila for fila in lector if any(str(c).strip() for c in fila)]

    if not filas:
        return [], []

    return filas[0], filas[1:]


def find_user_record(registro_id, usuario=None):
    """Registro del historial con ese id, solo si pertenece al usuario (o None)."""
    return next(
        (
            r for r in _historial_del_usuario(usuario)
            if r.get("id") == registro_id
        ),
        None,
    )


def saved_report_path(registro):
    """Ubica el CSV de un registro del historial.

    Solo se usa el nombre del archivo (basename) dentro de RESULTADOS_DIR, para
    que un registro nunca pueda apuntar fuera de la carpeta de reportes.

    Returns:
        (nombre, ruta) si el archivo existe, o (nombre, None) si ya no esta.
    """
    nombre = os.path.basename(str(registro.get("archivo_reporte") or ""))
    ruta = os.path.join(RESULTADOS_DIR, nombre)

    if not nombre or not os.path.isfile(ruta):
        return nombre, None

    return nombre, ruta
