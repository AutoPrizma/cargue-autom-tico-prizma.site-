"""Usuarios de la interfaz, contrasenas, bloqueo por intentos fallidos y cookies de sesion.
"""

import os
import json
import re
import threading
import hmac
import base64
import hashlib
import ipaddress
import secrets
import contextvars
from datetime import (
    datetime,
    timedelta,
)

from auto_prizma.core.storage import read_json, write_json_atomic
from auto_prizma.core.config import (
    BLOQUEO_SEGUNDOS,
    MAX_INTENTOS,
    PBKDF2_ITERACIONES,
    SECRETO_PATH,
    SESION_COOKIE,
    SESION_HORAS,
    USUARIOS_PATH,
    cookie_secure_forced,
    session_secret_from_env,
)


# ============================================================
# SESIONES Y USUARIOS
# ============================================================
#
# - Cada persona entra con usuario y contrasena.
# - La contrasena se guarda como PBKDF2-SHA256 con sal propia.
# - La sesion viaja en una cookie firmada con HMAC; el servidor no
#   guarda estado de sesion, asi que reiniciar uvicorn no desloguea.
#

# SESION_COOKIE, SESION_HORAS, PBKDF2_ITERACIONES, MAX_INTENTOS y
# BLOQUEO_SEGUNDOS viven en auto_prizma.core.config.

USUARIOS_LOCK = threading.Lock()
INTENTOS_LOCK = threading.Lock()
INTENTOS_FALLIDOS = {}

# Se propaga a los endpoints sincronos (Starlette copia el contexto
# al threadpool) y se fija a mano en el hilo de cargue.
USUARIO_ACTUAL = contextvars.ContextVar("usuario_actual", default=None)
ACCESO_LOCAL_DIRECTO = contextvars.ContextVar("acceso_local_directo", default=False)


def _secreto_sesion():
    """Clave para firmar cookies. Prioriza la variable de entorno."""
    desde_entorno = session_secret_from_env()

    if desde_entorno:
        return desde_entorno.encode("utf-8")

    if os.path.isfile(SECRETO_PATH):
        try:
            with open(SECRETO_PATH, "r", encoding="utf-8") as archivo:
                guardado = archivo.read().strip()
            if guardado:
                return guardado.encode("utf-8")
        except OSError:
            pass

    generado = secrets.token_urlsafe(48)

    try:
        with open(SECRETO_PATH, "w", encoding="utf-8") as archivo:
            archivo.write(generado)
    except OSError:
        pass

    return generado.encode("utf-8")


SECRETO_SESION = _secreto_sesion()


def _cookie_segura():
    """Marca la cookie como Secure cuando la app corre bajo https."""
    if cookie_secure_forced():
        return True

    return False


def _normalizar_usuario(usuario):
    return str(usuario or "").strip().lower()


def _cargar_usuarios():
    # Solo errores de lectura/JSON cuentan como "sin usuarios": otros errores
    # se propagan para no sobrescribir un usuarios.json danado al guardar.
    return read_json(USUARIOS_PATH, {}, dict, errors=(OSError, json.JSONDecodeError))


def _guardar_usuarios(usuarios):
    write_json_atomic(USUARIOS_PATH, usuarios)


def _hash_contrasena(contrasena, sal=None):
    sal = sal or secrets.token_hex(16)

    derivada = hashlib.pbkdf2_hmac(
        "sha256",
        str(contrasena or "").encode("utf-8"),
        bytes.fromhex(sal),
        PBKDF2_ITERACIONES,
    )

    return sal, derivada.hex()


def _verificar_contrasena(contrasena, sal, esperado):
    try:
        _, calculado = _hash_contrasena(contrasena, sal)
    except (ValueError, TypeError):
        return False

    return hmac.compare_digest(calculado, str(esperado or ""))


def _crear_usuario(usuario, contrasena, nombre=""):
    """Alta o cambio de contrasena. Lo usa scripts/manage_users.py."""
    usuario = _normalizar_usuario(usuario)

    if not usuario:
        raise ValueError("El usuario no puede estar vacio.")

    if len(str(contrasena or "")) < 8:
        raise ValueError("La contrasena debe tener al menos 8 caracteres.")

    sal, derivada = _hash_contrasena(contrasena)

    with USUARIOS_LOCK:
        usuarios = _cargar_usuarios()
        existente = usuarios.get(usuario) or {}

        usuarios[usuario] = {
            "nombre": str(nombre or existente.get("nombre") or usuario),
            "sal": sal,
            "hash": derivada,
            "activo": True,
            "creado": existente.get("creado") or datetime.now().isoformat(),
            "actualizado": datetime.now().isoformat(),
        }

        _guardar_usuarios(usuarios)

    return usuario


def _autenticar(usuario, contrasena):
    usuario = _normalizar_usuario(usuario)
    registro = _cargar_usuarios().get(usuario)

    if not registro or not registro.get("activo", True):
        # Se calcula igual para no revelar por tiempo si el usuario existe.
        _hash_contrasena(contrasena, secrets.token_hex(16))
        return None

    if not _verificar_contrasena(
        contrasena,
        registro.get("sal"),
        registro.get("hash"),
    ):
        return None

    return usuario


def _bloqueado(clave):
    with INTENTOS_LOCK:
        datos = INTENTOS_FALLIDOS.get(clave)

        if not datos:
            return 0

        intentos, hasta = datos

        if intentos < MAX_INTENTOS:
            return 0

        restante = hasta - datetime.now()

        if restante.total_seconds() <= 0:
            INTENTOS_FALLIDOS.pop(clave, None)
            return 0

        return int(restante.total_seconds()) + 1


def _registrar_fallo(clave):
    with INTENTOS_LOCK:
        intentos, _ = INTENTOS_FALLIDOS.get(clave, (0, datetime.now()))
        intentos += 1
        INTENTOS_FALLIDOS[clave] = (
            intentos,
            datetime.now() + timedelta(seconds=BLOQUEO_SEGUNDOS),
        )


def _limpiar_fallos(clave):
    with INTENTOS_LOCK:
        INTENTOS_FALLIDOS.pop(clave, None)


def _firmar_sesion(usuario):
    expira = int(
        (datetime.now() + timedelta(hours=SESION_HORAS)).timestamp()
    )

    cuerpo = (
        base64.urlsafe_b64encode(
            _normalizar_usuario(usuario).encode("utf-8")
        ).decode("ascii").rstrip("=")
        + "."
        + str(expira)
    )

    firma = hmac.new(
        SECRETO_SESION,
        cuerpo.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    return cuerpo + "." + firma


def _leer_sesion(valor):
    partes = str(valor or "").split(".")

    if len(partes) != 3:
        return None

    cuerpo = partes[0] + "." + partes[1]

    firma = hmac.new(
        SECRETO_SESION,
        cuerpo.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(firma, partes[2]):
        return None

    try:
        if int(partes[1]) < int(datetime.now().timestamp()):
            return None
    except ValueError:
        return None

    try:
        relleno = "=" * (-len(partes[0]) % 4)
        usuario = base64.urlsafe_b64decode(
            partes[0] + relleno
        ).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None

    usuario = _normalizar_usuario(usuario)
    registro = _cargar_usuarios().get(usuario)

    if not registro or not registro.get("activo", True):
        return None

    return usuario


def _usuario_de_request(request):
    return _leer_sesion(request.cookies.get(SESION_COOKIE))


def is_loopback_request(request):
    """True si la petición viene del mismo equipo (127.0.0.1, ::1 o localhost)."""
    host = str(request.client.host if getattr(request, "client", None) else "").split("%", 1)[0]
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host.lower() == "localhost"


def local_identity_for(request):
    """Identidad local sin credenciales; remoto = None.

    Si existe una sola cuenta activa de una instalación previa, la reutiliza
    para mantener visible su historial.
    """
    if not is_loopback_request(request):
        return None
    usuarios = _cargar_usuarios()
    activos = sorted(
        usuario for usuario, datos in usuarios.items()
        if isinstance(datos, dict) and datos.get("activo", True)
    )
    return activos[0] if len(activos) == 1 else "local"


def _usuario_actual():
    return USUARIO_ACTUAL.get()


def acceso_local_directo():
    """Indica si la petición actual entró por loopback sin iniciar sesión."""
    return ACCESO_LOCAL_DIRECTO.get()


def _nombre_visible(usuario):
    if _normalizar_usuario(usuario) == "local":
        return "Equipo local"
    registro = _cargar_usuarios().get(_normalizar_usuario(usuario)) or {}
    return str(registro.get("nombre") or usuario or "")


def _es_de(trabajo, usuario):
    """True si ese trabajo pertenece al usuario indicado."""
    if not trabajo:
        return False
    return _normalizar_usuario(
        trabajo.get("usuario_app")
    ) == _normalizar_usuario(usuario)
