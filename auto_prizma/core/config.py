"""Configuracion central de Auto Prizma Pro.

Reúne carpetas de trabajo y datos, variables de entorno, parámetros de sesión,
cola de cargues, URLs de PRIZMA y configuración del navegador.

Los modulos importan desde aqui los valores con el mismo nombre que usaban
antes, para no cambiar su comportamiento.
"""

import os
from urllib.parse import urlparse
from zoneinfo import ZoneInfo


# ============================================================
# VARIABLES DE ENTORNO
# ============================================================
#
# Variables soportadas (ver .env.example):
#   AUTO_PRIZMA_DATA_DIR        carpeta de datos persistentes (por defecto ./data)
#   AUTO_PRIZMA_SECRET          clave HMAC para firmar las cookies de sesion
#   AUTO_PRIZMA_COOKIE_SECURE   "1" fuerza la cookie Secure
#   AUTO_PRIZMA_MAX_SIMULTANEOS limite de cargues simultaneos (1 o 2)
#   AUTO_PRIZMA_URL_PRIZMA      URL de PRIZMA (vacio = produccion)
#   N8N_WEBHOOK_*               URLs privadas de los webhooks n8n
#   N8N_SHARED_SECRET           Header secreto opcional para n8n
#
# La variable de cookie Secure se lee en cada llamada.


def env_str(nombre):
    """Devuelve el valor de una variable de entorno sin espacios ("" si no existe)."""
    return str(os.environ.get(nombre) or "").strip()


def session_secret_from_env():
    """Clave de firma de cookies definida por entorno ("" si no existe)."""
    return env_str("AUTO_PRIZMA_SECRET")


def cookie_secure_forced():
    """True cuando AUTO_PRIZMA_COOKIE_SECURE vale exactamente "1"."""
    return env_str("AUTO_PRIZMA_COOKIE_SECURE") == "1"


# ============================================================
# CARPETAS
# ============================================================

# Raiz del proyecto (carpeta que contiene main.py): este archivo vive en
# auto_prizma/core/config.py, por eso se suben tres niveles.
BASE_DIR = os.path.dirname(
    os.path.dirname(
        os.path.dirname(
            os.path.abspath(__file__)
        )
    )
)

LOGO_PATH = os.path.join(
    BASE_DIR,
    "static",
    "auto_prizma_logo.png",
)

# Hoja de estilos y script comunes de todas las paginas (marco, tema claro/
# oscuro, menus, tablas). Se sirven en /app.css y /app.js.
STATIC_DIR = os.path.join(BASE_DIR, "static")
APP_CSS_PATH = os.path.join(STATIC_DIR, "app.css")
APP_JS_PATH = os.path.join(STATIC_DIR, "app.js")

UPLOADS_DIR = os.path.join(
    BASE_DIR,
    "uploads",
)

TEMP_DIR = os.path.join(
    BASE_DIR,
    "temp",
)

DATA_DIR = os.environ.get(
    "AUTO_PRIZMA_DATA_DIR",
    os.path.join(BASE_DIR, "data"),
)

# Historiales, estado de cursos y reportes locales se conservan 15 días.
LOCAL_DATA_RETENTION_DAYS = 15

RESULTADOS_DIR = os.path.join(
    DATA_DIR,
    "reportes",
)

HISTORIAL_PATH = os.path.join(
    DATA_DIR,
    "historial.json",
)

# Estado acumulado por curso: que actividades de cada curso ya quedaron
# subidas a PRIZMA y cual es la causa de las que faltan.
ESTADO_CURSOS_PATH = os.path.join(
    DATA_DIR,
    "estado_cursos.json",
)

USUARIOS_PATH = os.path.join(
    DATA_DIR,
    "usuarios.json",
)

SECRETO_PATH = os.path.join(
    DATA_DIR,
    "secreto_sesion.txt",
)


for carpeta in [
    UPLOADS_DIR,
    TEMP_DIR,
    DATA_DIR,
    RESULTADOS_DIR,
]:

    os.makedirs(
        carpeta,
        exist_ok=True,
    )


# ============================================================
# SESIONES Y USUARIOS
# ============================================================

SESION_COOKIE = "ap_sesion"
SESION_HORAS = 12
PBKDF2_ITERACIONES = 240000

# Bloqueo de login: tras MAX_INTENTOS fallos (por usuario + IP) se espera
# BLOQUEO_SEGUNDOS antes de volver a intentar.
MAX_INTENTOS = 5
BLOQUEO_SEGUNDOS = 120


# ============================================================
# CARGUES
# ============================================================

ZONA_HORARIA_COLOMBIA = ZoneInfo("America/Bogota")


def _resolver_max_cargues_simultaneos(valor):
    """Seguridad operativa: nunca mas de 2 Chromium de cargue a la vez.

    AUTO_PRIZMA_MAX_SIMULTANEOS puede bajarlo a 1; 0, invalidos o >2 vuelven a 2.
    """
    try:
        limite = int(valor)
    except (TypeError, ValueError):
        return 2

    if limite == 1:
        return 1

    return 2


MAX_CARGUES_SIMULTANEOS = _resolver_max_cargues_simultaneos(
    os.environ.get("AUTO_PRIZMA_MAX_SIMULTANEOS")
)


# ============================================================
# PRIZMA Y NAVEGADOR
# ============================================================

# URL de PRIZMA. Por defecto produccion. Para probar sin tocar produccion se
# define AUTO_PRIZMA_URL_PRIZMA con el ambiente de pruebas (por ejemplo
# https://admin.prizma.solutions) y se reinicia la app. Se lee al importar.
# Railway no la define, asi que alli siempre se usa produccion.
PRIZMA_URL_PRODUCCION = "https://admin.prizma.site"


def _resolver_url_prizma(valor):
    """URL base de PRIZMA a partir del valor de AUTO_PRIZMA_URL_PRIZMA.

    Args:
        valor: texto de la variable de entorno ("" o None = produccion).

    Returns:
        URL sin "/" final; si falta el esquema se asume https://.
    """
    url = str(valor or "").strip().rstrip("/")
    if not url:
        return PRIZMA_URL_PRODUCCION
    if not url.lower().startswith(("http://", "https://")):
        url = "https://" + url
    return url


PRIZMA_BASE_URL = _resolver_url_prizma(env_str("AUTO_PRIZMA_URL_PRIZMA"))
URL_PRIZMA = PRIZMA_BASE_URL + "/inicio-sesion"
PRIZMA_HOST = urlparse(PRIZMA_BASE_URL).netloc or PRIZMA_BASE_URL
PRIZMA_ES_PRODUCCION = PRIZMA_BASE_URL == PRIZMA_URL_PRODUCCION

# Argumentos de Chromium usados por todas las automatizaciones headless.
# Se copian (list(...)) en cada uso para que nadie modifique el original.
CHROMIUM_ARGS = ["--no-sandbox", "--disable-dev-shm-usage"]

VIEWPORT_NAVEGADOR = {"width": 1440, "height": 900}

# Estado real del servicio que muestran la barra lateral y los indicadores de
# Inicio (services/health.py): cada comprobacion se guarda en memoria este
# tiempo para no repetirla en cada pagina.
# Bajo a 5 min: 30 min hacia que el indicador de Chromium siga en rojo mucho
# despues de instalarlo, y confunde al usuario.
HEALTH_CHROMIUM_TTL_SECONDS = 5 * 60
HEALTH_PRIZMA_TTL_SECONDS = 3 * 60
HEALTH_PRIZMA_TIMEOUT_SECONDS = 6

# Reintentos al abrir la sesion de PRIZMA al INICIO de un cargue: segundos de
# espera antes de cada reintento (2 esperas = 3 intentos en total). Solo se
# reintentan fallos momentaneos (timeouts, navegador caido), nunca un login
# rechazado.
PRIZMA_ESPERAS_REINTENTO_SESION = (5, 15)

# Politica TEMPORAL del campo "Html" (decision del usuario, 2026-10-06):
# PRIZMA no permite guardar un H5P si el campo Html de la actividad tiene
# contenido. Mientras se carguen recursos H5P, True = el motor vacia el Html
# antes de guardar y deja el contenido previo en el reporte. Cuando se deje de
# usar H5P y se implemente HTML, poner False: el motor cancelara sin guardar y
# reportara ERROR_HTML_Y_H5P para revisar a mano.
PRIZMA_VACIAR_HTML_CON_H5P = True


# ============================================================
# FORMATO DE LOS RECURSOS INTERACTIVOS (H5P / HTML)
# ============================================================
#
# Se elige en cada cargue. Afecta a las actividades que llevan recurso
# interactivo (OVA y OVI de tipo H5P o infografia); los PDF no cambian.
#   "H5P":  se sube el archivo .h5p al campo "Recurso" de la actividad.
#   "HTML": se pega el codigo completo del archivo .html en el campo "Html".
FORMATOS_RECURSO_INTERACTIVO = ("H5P", "HTML")
FORMATO_RECURSO_POR_DEFECTO = "H5P"

# Extensiones que se aceptan como archivo HTML dentro del ZIP.
EXTENSIONES_HTML = (".html", ".htm")

# Politica del modo HTML (decisiones del usuario, 2026-10-06 y 2026-10-07):
# PRIZMA no permite un archivo en "Recurso" y Html a la vez. True = si la
# actividad ya tiene CUALQUIER archivo en "Recurso" (H5P o no; a veces PRIZMA
# solo lo muestra como "Archivo"), el motor lo elimina antes de guardar el HTML
# y lo deja en el reporte. False = no toca la actividad, cancela sin guardar y
# reporta ERROR_RECURSO_Y_HTML.
PRIZMA_VACIAR_RECURSO_CON_HTML = True


# ============================================================
# AUTOMATIZACIONES N8N
# ============================================================

N8N_TIMEOUT_SECONDS = 58
N8N_WEBHOOK_DEFAULTS = {
    "aut-tests": "https://auton8n4.americana.edu.co/webhook/generar-tests-json",
    "descargar-recursos": "https://auton8n4.americana.edu.co/webhook/prueba-descargar-recursos-portal",
    "matriz-csv": "https://auton8n4.americana.edu.co/webhook/matriz-csv-portal",
    "plantillas-tematicas": "https://auton8n4.americana.edu.co/webhook/plantillas-tematicas-portal",
}
# Webhooks GET para consultar el avance de flujos largos (responden de inmediato
# con un jobId y siguen trabajando en n8n).
N8N_STATUS_WEBHOOK_DEFAULTS = {
    "descargar-recursos": "https://auton8n4.americana.edu.co/webhook/prueba-descargar-recursos-estado",
}
N8N_STATUS_TIMEOUT_SECONDS = 15
