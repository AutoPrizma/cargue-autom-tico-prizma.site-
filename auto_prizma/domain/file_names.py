"""Nombres de archivo de recursos (H5P/PDF): nombre base y clave exacta.

Reúne normalizaciones de nombres de archivo utilizadas por el análisis y el
emparejamiento de recursos incluidos en el ZIP.

Nota: el motor usa ademas clave_nombre_archivo_exacto (engine.py), que ignora
mayusculas; tiene otra semantica a proposito y no se unifica aqui.
"""

import unicodedata


def file_base_name(value):
    """Ultimo componente de una ruta, separe con / o con \\, sin espacios al borde.

    Args:
        value: nombre o ruta del archivo (acepta None).

    Returns:
        El nombre del archivo sin carpetas.
    """
    texto = str(value or "").replace("\\", "/")
    return texto.rsplit("/", 1)[-1].strip()


def exact_name_key(value):
    """Clave para comparar nombres EXACTOS de archivo.

    Solo unifica la forma Unicode de los acentos (NFC); distingue mayusculas,
    espacios y guiones.

    Args:
        value: nombre o ruta del archivo.

    Returns:
        Nombre base normalizado a NFC.
    """
    return unicodedata.normalize("NFC", file_base_name(value))
