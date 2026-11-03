"""Traduccion de codigos ERROR_* a mensajes en lenguaje humano.

El motor escribe codigos estables (ERROR_...) en el reporte y en el historial:
así se pueden seguir diagnosticando y no se rompen si cambia un texto. Esta
capa es solo de presentacion: convierte el codigo en una frase que el usuario
entienda sin conocer el codigo.
"""

import re

# Codigo -> frase para el usuario. Si el codigo no esta aqui, se muestra tal
# cual (nunca inventamos una explicacion para un codigo desconocido).
MENSAJES_ERROR = {
    # --- Acceso / sesion PRIZMA ---
    "ERROR_LOGIN_PRIZMA": (
        "PRIZMA no aceptó el usuario o la contraseña. Revisa las credenciales."
    ),
    "ERROR_CONECTANDO_PRIZMA": (
        "No fue posible conectar con PRIZMA para iniciar sesión. Revisa la "
        "conexión o que PRIZMA esté disponible."
    ),
    # --- Curso / actividad ---
    "ERROR_CURSO_SIN_PLANTILLA": (
        "El curso no tiene la plantilla precargada en PRIZMA: la actividad no "
        "existe todavía y hay que crearla antes de cargar."
    ),
    "ERROR_ACTIVIDAD_NO_ENCONTRADA": (
        "Ninguna actividad del curso coincide con el nombre de la matriz. "
        "Revisa el nombre o la categoría en PRIZMA."
    ),
    "ERROR_ACTIVIDAD_DUPLICADA": (
        "El curso tiene varias actividades con el mismo nombre y no se sabe "
        "cuál usar."
    ),
    "ERROR_NO_SE_PUDO_VOLVER_AL_LISTADO": (
        "PRIZMA no volvió a mostrar el listado de actividades después de "
        "guardar. La actividad quedó sin confirmar."
    ),
    "ERROR_ENTRANDO_CATEGORIA": (
        "No se pudo abrir la categoría del curso en PRIZMA."
    ),
    # --- Edicion / guardado ---
    "ERROR_ABRIENDO_EDICION": (
        "No se pudo abrir la edición de la actividad en PRIZMA."
    ),
    "ERROR_BOTON_GUARDAR": (
        "El botón Guardar de PRIZMA no respondió. La actividad quedó sin "
        "guardar."
    ),
    "ERROR_POST_GUARDADO_LISTADO": (
        "PRIZMA no confirmó el guardado en el listado. La actividad quedó sin "
        "confirmar."
    ),
    "ERROR_PATCH_HTTP_": (
        "PRIZMA rechazó la petición de guardado con un error HTTP. La "
        "actividad quedó sin guardar."
    ),
    "ERROR_LIMPIANDO_DESCRIPCION": (
        "El editor de descripción de PRIZMA no se pudo limpiar para escribir "
        "el contenido nuevo."
    ),
    "ERROR_DESCRIPCION_MULTIPLE": (
        "La actividad tiene varios campos de descripción y no se usó ninguno."
    ),
    "ERROR_DESCRIPCION_CONTENIDO_ADICIONAL": (
        "No se encontró el campo de contenido adicional de la descripción."
    ),
    "ERROR_CAMPO_RECURSO_NO_ENCONTRADO": (
        "No se encontró el campo donde va el recurso dentro de la actividad."
    ),
    "ERROR_CAMPO_CONTENIDO_RETO_NO_ENCONTRADO": (
        "No se encontró el campo de contenido del reto dentro de la actividad."
    ),
    "ERROR_SELECCIONANDO_CORTE": (
        "No se pudo elegir el corte del recurso en PRIZMA."
    ),
    "ERROR_SELECCIONANDO_NIVEL_DIFICULTAD": (
        "No se pudo elegir el nivel de dificultad en PRIZMA."
    ),
    "ERROR_UNIDAD_PREGRADO_NO_SOPORTADA": (
        "La unidad de pregrado de la matriz no está soportada por PRIZMA."
    ),
    "ERROR_UNIDAD_POSGRADO_NO_SOPORTADA": (
        "La unidad de posgrado de la matriz no está soportada por PRIZMA."
    ),
    "ERROR_UNIDAD_RETO_NO_RECONOCIDA": (
        "La unidad del reto no es un valor que PRIZMA reconozca."
    ),
    "ERROR_TIPO_RECURSO_NO_SOPORTADO": (
        "El tipo de recurso de la fila no está soportado."
    ),
    # --- Recurso / archivo ---
    "ERROR_RECURSO_NO_ENCONTRADO": (
        "La fila no tiene recurso: la columna Recurso del Excel está vacía o "
        "no coincide con ningún archivo."
    ),
    "ERROR_RECURSO_NO_VISIBLE": (
        "El recurso no quedó visible después de guardarlo en PRIZMA."
    ),
    "ERROR_RECURSO_DUPLICADO": (
        "El recurso aparece más de una vez en el ZIP."
    ),
    "ERROR_RECURSO_AMBIGUO": (
        "Hay varios archivos que pueden ser el recurso y no se sabe cuál usar."
    ),
    "ERROR_RECURSO_NO_COINCIDE_CON_ACTIVIDAD": (
        "El nombre del recurso no coincide con la actividad de la matriz."
    ),
    "ERROR_RECURSO_ZIP_TAMANO_CAMBIO": (
        "El tamaño del recurso cambió entre la revisión y el cargue."
    ),
    "ERROR_EXTRAYENDO_RECURSO": (
        "No se pudo extraer el recurso del ZIP."
    ),
    "ERROR_SET_INPUT_FILES": (
        "El navegador no aceptó el archivo del recurso al subirlo."
    ),
    # --- Archivos HTML ---
    "ERROR_HTML_VACIO": (
        "El archivo HTML del recurso está vacío."
    ),
    "ERROR_HTML_NO_ES_UTF8": (
        "El archivo HTML no está en codificación UTF-8 y no se pudo leer."
    ),
    "ERROR_LEYENDO_HTML": (
        "No se pudo leer el archivo HTML del recurso."
    ),
    # --- Navegador / conexión ---
    "ERROR_RECUPERANDO_PAGINA": (
        "El navegador o PRIZMA dejaron de responder y no se pudo recuperar la "
        "página."
    ),
    "ERROR_RECUPERANDO_FILA": (
        "No se pudo recuperar la fila de la actividad en PRIZMA tras un fallo "
        "del navegador."
    ),
    "ERROR_RECUPERANDO_TRAS_PAGE_CRASH": (
        "La página del navegador se cayó y no se pudo recuperar."
    ),
    # --- Genéricos ---
    "ERROR_DESCONOCIDO": (
        "Falló por una razón no identificada. Revisa el reporte o el log."
    ),
    "ERROR_CANCELADO": (
        "El proceso fue cancelado por el usuario."
    ),
    "ERROR_ARCHIVO_RECURSO_NO_VALIDO": (
        "El archivo elegido como recurso no se pudo leer desde el disco; "
        "vuelve a elegirlo."
    ),
    "ERROR_PROCESANDO_ACTIVIDAD": (
        "Ocurrió un error inesperado al procesar la actividad en PRIZMA."
    ),
    "ERROR_NO_ESTA_EN_PRIZMA": (
        "La verificación en PRIZMA no encontró la actividad: no está en el "
        "curso."
    ),
}


def extraer_codigo_error(texto):
    """Devuelve el primer codigo ERROR_* que encuentre en ``texto``.

    El motor a veces escribe "codigo: detalle" o "codigo | detalle". Si no hay
    codigo conocido, devuelve "".
    """
    fragmento = str(texto or "")
    if fragmento in MENSAJES_ERROR:
        return fragmento

    for parte in fragmento.replace("|", "\n").splitlines():
        token = re.split(r"[\s:,;]+", parte.strip(), maxsplit=1)[0].strip()
        if not token:
            continue
        if token in MENSAJES_ERROR:
            return token
        if token.startswith("ERROR_"):
            # Prefijo conocido con sufijo variable (ej. ERROR_PATCH_HTTP_500).
            for codigo in MENSAJES_ERROR:
                if codigo.endswith("_") and token.startswith(codigo):
                    return codigo
    return ""


def mensaje_error(codigo_o_texto):
    """Devuelve la frase humana para un codigo (o texto con codigo).

    Si el motor anexo un detalle ("codigo: lo que paso"), la frase se
    completa con ese detalle: el usuario ve que archivo pide el Excel o
    donde esta la actividad repetida, no solo el codigo. Si no hay
    traduccion, devuelve el texto original sin tocar.
    """
    texto = str(codigo_o_texto or "")
    codigo = extraer_codigo_error(texto)
    if not codigo:
        return texto
    base = MENSAJES_ERROR[codigo]
    detalle = ""
    posicion = texto.find(codigo)
    if posicion >= 0:
        detalle = texto[posicion + len(codigo):].lstrip(" \t:|-").strip()
    if not detalle:
        return base
    return f"{base} Detalle: {detalle}"


def es_codigo_error(texto):
    """True si el texto es (o contiene) un codigo ERROR_* conocido."""
    return bool(extraer_codigo_error(texto))
