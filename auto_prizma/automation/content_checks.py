"""Validacion profunda de archivos descargados: PDF y H5P, sin navegador.

La auditoria de curso abre cada actividad publicada y baja su recurso. Aqui
se decide, solo con los bytes del archivo, si el recurso esta realmente
completo: un PDF con hojas y texto/imagenes, o un paquete H5P valido con su
titulo interno (la portada que se ve al abrirlo, no el metadato del
archivo). Sin librerias externas: PDF se inspecciona con zlib y H5P con
zipfile, reusando la lectura de titulos del tablero Auditor.
"""

import json
import re
import zipfile
import zlib

from auto_prizma.auditor.procesar import (
    clave,
    leer_titulo_h5p,
    titulos_principales_h5p,
    titulos_visibles_h5p,
)


# Estados posibles de una actividad auditada.
ESTADO_OK = "ok"
ESTADO_REVISAR = "revisar"
ESTADO_SIN_RECURSO = "sin_recurso"
ESTADO_NO_SE_PUDO = "no_se_pudo"

_CABECERA_PDF = b"%PDF-"
_PAGINA_PDF = re.compile(rb"/Type\s*/Page(?!s)")
_CONTEO_PDF = re.compile(rb"/Count\s+(\d+)")
_STREAM_PDF = re.compile(rb"stream\r?\n(.*?)\r?\nendstream", re.DOTALL)
# Operadores que solo existen cuando la hoja dibuja algo (texto o imagen).
_OPERADORES_CONTENIDO = (b"BT", b"Tj", b"TJ", b" Do", b"BI")
_TOPE_STREAMS = 24
_TOPE_DESPLAZADO = 8 * 1024 * 1024


def inspeccionar_pdf_bytes(datos):
    """Cabecera, hojas y contenido real de un PDF descargado.

    - ``ok``: trae cabecera PDF y al menos una hoja.
    - ``paginas``: hojas contadas por /Type /Page (con /Count como respaldo).
    - ``con_contenido``: alguna hoja tiene texto o imagenes; un PDF en
      blanco (solo cabecera y streams vacios) queda en False.

    Returns:
        {"ok", "paginas", "con_contenido", "detalle"}
    """
    datos = datos or b""
    resultado = {"ok": False, "paginas": 0, "con_contenido": False, "detalle": ""}
    if _CABECERA_PDF not in datos[:1024]:
        resultado["detalle"] = "No es un PDF: no trae la cabecera %PDF."
        return resultado

    paginas = len(_PAGINA_PDF.findall(datos))
    if not paginas:
        conteos = [int(valor) for valor in _CONTEO_PDF.findall(datos)]
        paginas = max(conteos, default=0)

    resultado["paginas"] = paginas
    resultado["ok"] = paginas > 0
    if not resultado["ok"]:
        resultado["detalle"] = "PDF con cabecera correcta pero sin hojas legibles."
        return resultado

    con_contenido = False
    desplazado_total = 0
    for pedazo in _STREAM_PDF.findall(datos)[:_TOPE_STREAMS]:
        contenido = pedazo
        try:
            contenido = zlib.decompress(pedazo)
            desplazado_total += len(contenido)
        except zlib.error:
            pass
        if desplazado_total > _TOPE_DESPLAZADO:
            break
        if any(operador in contenido for operador in _OPERADORES_CONTENIDO):
            con_contenido = True
            break

    resultado["con_contenido"] = con_contenido
    if con_contenido:
        resultado["detalle"] = (
            "PDF con " + str(paginas) + (" hoja" if paginas == 1 else " hojas")
            + " y contenido visible."
        )
    else:
        resultado["detalle"] = (
            "PDF con " + str(paginas) + (" hoja" if paginas == 1 else " hojas")
            + " pero sin texto ni imagenes: parece en blanco."
        )
    return resultado


def inspeccionar_h5p_archivo(ruta):
    """Titulo interno, titulos visibles y bibliotecas de un .h5p descargado.

    Un paquete sano trae h5p.json (titulo del paquete), content/content.json
    (lo que la portada muestra por dentro) y al menos una carpeta en
    libraries/ (sin bibliotecas el contenido no puede renderizar).

    Returns:
        {"ok", "titulo_paquete", "titulos_visibles", "bibliotecas", "detalle"}
    """
    resultado = {
        "ok": False,
        "titulo_paquete": "",
        "titulos_portada": [],
        "titulos_visibles": [],
        "bibliotecas": 0,
        "detalle": "",
    }
    try:
        with zipfile.ZipFile(ruta) as paquete:
            nombres = paquete.namelist()
            contenido_json = None
            if "content/content.json" in nombres:
                with paquete.open("content/content.json") as fh:
                    contenido_json = fh.read()
    except zipfile.BadZipFile:
        resultado["detalle"] = "No es un ZIP/H5P valido."
        return resultado
    except Exception as error:  # noqa: BLE001
        resultado["detalle"] = "No se pudo leer el paquete: " + str(error)[:120]
        return resultado

    if "h5p.json" not in nombres:
        resultado["detalle"] = "El paquete no contiene h5p.json."
        return resultado

    titulo, error = leer_titulo_h5p(ruta)
    if error:
        resultado["detalle"] = "H5P ilegible: " + str(error) + "."
        return resultado

    if contenido_json is None:
        resultado["detalle"] = "El paquete no contiene content/content.json."
        return resultado
    try:
        json.loads(contenido_json)
    except ValueError:
        resultado["detalle"] = "El content.json del paquete está dañado."
        return resultado

    visibles = [
        str(item or "").strip()
        for item in titulos_visibles_h5p(ruta)
        if str(item or "").strip()
    ]
    titulos_portada = [
        str(item or "").strip()
        for item in titulos_principales_h5p(ruta)
        if str(item or "").strip()
    ]
    bibliotecas = sum(
        1 for nombre in nombres
        if nombre.startswith("libraries/") and nombre.count("/") >= 2
    )

    resultado.update({
        "ok": True,
        "titulo_paquete": str(titulo or "").strip(),
        "titulos_portada": titulos_portada,
        "titulos_visibles": visibles[:8],
        "bibliotecas": bibliotecas,
    })
    if bibliotecas:
        resultado["detalle"] = "Paquete H5P válido con sus bibliotecas."
    else:
        resultado["ok"] = False
        resultado["detalle"] = "El paquete H5P no trae bibliotecas: no podrá renderizar."
    return resultado


def titulo_coincide(titulo_interno, titulo_esperado):
    """¿El titulo que se ve al abrir el recurso es el nombre de la actividad?

    Compara como el tablero Auditor: sin mayusculas, acentos ni puntuacion.
    """
    interno = clave(str(titulo_interno or ""))
    esperado = clave(str(titulo_esperado or ""))
    return bool(interno and esperado and interno == esperado)


def evaluar_recurso_auditoria(nombre_actividad, nombre_archivo, inspeccion):
    """Veredicto de una actividad auditada segun su archivo adjunto.

    ``inspeccion`` es la salida de :func:`inspeccionar_pdf_bytes` o
    :func:`inspeccionar_h5p_archivo` (None si el archivo no se pudo leer).

    Returns:
        {"estado", "tipo", "archivo", "titulo_interno", "coincide", "detalle"}
        con estado en ok | revisar | sin_recurso | no_se_pudo y ``coincide``
        en True, False o None (cuando no hay titulo interno que comparar).
    """
    archivo = str(nombre_archivo or "").strip()
    veredicto = {
        "estado": ESTADO_NO_SE_PUDO,
        "tipo": "",
        "archivo": archivo,
        "titulo_interno": "",
        "coincide": None,
        "detalle": "",
    }

    if not archivo:
        veredicto["estado"] = ESTADO_SIN_RECURSO
        veredicto["detalle"] = "La actividad no tiene archivo en el campo Recurso."
        return veredicto

    extension = str(archivo).rsplit(".", 1)[-1].lower() if "." in archivo else ""
    if extension == "h5p":
        veredicto["tipo"] = "H5P"
    elif extension == "pdf":
        veredicto["tipo"] = "PDF"
    else:
        veredicto["estado"] = ESTADO_REVISAR
        veredicto["tipo"] = extension.upper() or "(sin extensión)"
        veredicto["detalle"] = (
            "Archivo adjunto de tipo no auditable (." + veredicto["tipo"].lower()
            + "); se revisa solo que exista."
        )
        return veredicto

    if inspeccion is None:
        veredicto["detalle"] = "No se pudo leer el archivo adjunto para validarlo."
        return veredicto

    if veredicto["tipo"] == "PDF":
        if not inspeccion.get("ok"):
            veredicto["estado"] = ESTADO_REVISAR
            veredicto["detalle"] = str(inspeccion.get("detalle") or "El PDF no es válido.")
            return veredicto
        if not inspeccion.get("con_contenido"):
            veredicto["estado"] = ESTADO_REVISAR
            veredicto["detalle"] = str(inspeccion.get("detalle") or "El PDF parece en blanco.")
            return veredicto
        veredicto["estado"] = ESTADO_OK
        veredicto["detalle"] = str(inspeccion.get("detalle") or "PDF con contenido.")
        titulo_interno = str(inspeccion.get("titulo_pdf") or "").strip()
        if titulo_interno:
            veredicto["titulo_interno"] = titulo_interno
            veredicto["coincide"] = titulo_coincide(titulo_interno, nombre_actividad)
        return veredicto

    # H5P.
    if not inspeccion.get("ok"):
        veredicto["estado"] = ESTADO_REVISAR
        veredicto["detalle"] = str(inspeccion.get("detalle") or "El paquete H5P no es válido.")
        return veredicto

    titulo_paquete = str(inspeccion.get("titulo_paquete") or "")
    titulos_portada = [
        str(item or "") for item in inspeccion.get("titulos_portada") or []
    ]
    visibles = [str(item or "") for item in inspeccion.get("titulos_visibles") or []]
    veredicto["titulo_interno"] = titulos_portada[0] if titulos_portada else ""

    coincide_alguno = any(
        titulo_coincide(titulo, nombre_actividad)
        for titulo in titulos_portada
        if str(titulo or "").strip()
    )
    veredicto["coincide"] = coincide_alguno

    if coincide_alguno:
        veredicto["estado"] = ESTADO_OK
        veredicto["detalle"] = (
        "Paquete H5P válido; el título de portada coincide con el curso (\""
            + veredicto["titulo_interno"] + "\")."
        )
        return veredicto

    veredicto["estado"] = ESTADO_REVISAR
    veredicto["detalle"] = (
        "REVISAR: el H5P abre, pero el título de portada (\"" + (veredicto["titulo_interno"] or "sin título verificable")
        + "\") no coincide con el nombre del curso (\"" + str(nombre_actividad) + "\")."
    )
    if titulo_paquete:
        veredicto["detalle"] += " El metadato del paquete no se usa para esta comparación."
    if visibles:
        veredicto["detalle"] += " Otros títulos visibles: " + " · ".join(visibles[:3]) + "."
    return veredicto
