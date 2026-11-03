#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
procesar.py — Auditor de cruce matriz de curso <-> carpeta de recursos.

Toma una matriz (CSV) y una carpeta (o ZIP) de recursos, empareja cada
recurso de la matriz con su archivo local, y verifica que el título interno
de cada .h5p coincida con el nombre del recurso. Todo esto SIN modificar los
originales. El resultado es un reporte Markdown en resultados/.

No afirma que nada fue "cargado" a Moodle: esto es solo verificación/auditoría.

Uso:
    python procesar.py <carpeta_o_zip> [--matriz MATRIZ] [--salida DIR]

Ejemplo:
    python procesar.py "~/Downloads/Videos 2" \
        --matriz "~/Downloads/SEMESTRE 1 - Fundamentos de Educación y Pedagogía.csv"
"""
import argparse
import csv
import html
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata
import zipfile
import zlib
from datetime import datetime

try:
    from difflib import SequenceMatcher
except ImportError:  # pragma: no cover
    SequenceMatcher = None


# ---------------------------------------------------------------------------
# Normalización de texto (regla tomada de PRODUCT.md de la app Prizma)
# ---------------------------------------------------------------------------
# Se ignoran acentos, puntuación, mayúsculas y los prefijos de unidad/tema
# ("U1-T1-", "UUnidad 1-TTema 2-", "ID014-Tema_1-") al comparar nombres.


def quitar_acentos(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in descompuesto if not unicodedata.combining(c))


def normalizar(texto: str) -> str:
    """Devuelve una forma comparable: sin acentos, minúsculas, sin puntuación."""
    if texto is None:
        return ""
    t = quitar_acentos(str(texto)).lower()
    t = t.replace("_", " ").replace("-", " ")
    t = re.sub(r"[^\w\s]", " ", t)          # puntuación -> espacio
    t = re.sub(r"\s+", " ", t).strip()
    return t


# Prefijos reconocidos de curso/tema que se ignoran al comparar.
# Cubren: "U1-T3-", "U-T-" (sin números), "UUnidad 1-TTema 2-", "ID015-Tema_1-",
# "ID004-Tema_Tema 4-" y prefijos de formato como "PDF - ..." u "PDF ...".
PREFIJOS = [
    r"^uunidad\s*\d*\s*tt\s*ema\s*\d*\s*",
    r"^unidad\s*\d*\s*tema\s*\d*\s*",
    r"^id\s*\d*\s*(tema\s*)+\d*\s*",
    r"^u\s*\d*\s*t\s*\d*\s*",
    r"^tema\s*\d*\s*",
    r"^pdf\s+",
]


def quitar_prefijo(texto_normalizado: str) -> str:
    """Elimina repetidamente los prefijos de unidad/tema ya normalizados."""
    t = texto_normalizado
    cambio = True
    while cambio:
        cambio = False
        for patron in PREFIJOS:
            nuevo = re.sub(patron, "", t).strip()
            if nuevo != t and nuevo:
                t = nuevo
                cambio = True
    return t


def clave(texto: str) -> str:
    """Clave final de comparación: normaliza y quita prefijos."""
    return quitar_prefijo(normalizar(texto))


def es_inicio_exacto(clave_archivo: str, clave_titulo: str, minimo: int = 18) -> bool:
    """Un nombre truncado solo calza si es el inicio EXACTO del título (>= min chars)."""
    if not clave_archivo or not clave_titulo:
        return False
    if len(clave_archivo) < minimo:
        return False
    return clave_titulo.startswith(clave_archivo)


def quitar_duplicado(base: str) -> str:
    """Quita un sufijo de copia duplicada ' (2)' o '(1)' al final del nombre.

    Cubre los nombres que quedan al descargar/copiar un archivo dos veces
    ("... (1).h5p", "... (2).h5p"). Devuelve el nombre sin ese sufijo.
    """
    return re.sub(r"\s*\(\d+\)\s*$", "", base).strip()


def similitud(a: str, b: str) -> float:
    if SequenceMatcher is None:
        return 1.0 if a == b else 0.0
    return SequenceMatcher(None, a, b).ratio()


# Umbral de similitud para el archivo más parecido de un recurso faltante
# (comparación sin mayúsculas/acentos/puntuación; ver PRODUCT.md). Si el más
# parecido llega a este porcentaje, se empareja directamente como OK.
SIMILITUD_ACEPTAR = 0.51


# ---------------------------------------------------------------------------
# Lectura de la matriz
# ---------------------------------------------------------------------------

# Extensión esperada según la columna "Tipo de recurso" de la matriz.
# Nota: "Video Avatar" y "Video interactivo Avatar" son en realidad paquetes H5P;
# lo mismo ocurre con las "Infografía" (en los cursos reales vienen como .h5p).
EXT_POR_TIPO = {
    "recurso h5p": ".h5p",
    "h5p": ".h5p",
    "video avatar": ".h5p",
    "video interactivo avatar": ".h5p",
    "infografia": ".h5p",
    "pdf": ".pdf",
    "reto evaluativo": ".pdf",
    # Videos e imágenes también se auditan: toda fila con enlace debe tener su archivo.
    "video a camara": "video",
    "video intro": "video",
    "video cierre": "video",
    "video": "video",
    "imagen": "imagen",
}

# Familias de extensiones aceptadas para los tipos que no tienen una sola extensión.
EXTS_POR_FAMILIA = {
    "video": (".webm", ".mp4", ".mov", ".m4v", ".mkv", ".avi"),
    "imagen": (".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg"),
}

# Ningún tipo queda fuera de la auditoría: se auditan todas las filas con enlace.
TIPOS_FUERA_DE_ALCANCE = set()


def ext_coincide(ext, esperada):
    """True si la extensión del archivo corresponde a la esperada (o a su familia)."""
    if esperada in EXTS_POR_FAMILIA:
        return (ext or "").lower() in EXTS_POR_FAMILIA[esperada]
    return ext == esperada


def detectar_columnas(fila):
    """Localiza los índices de las columnas conocidas a partir de la fila de encabezado."""
    idx = {"nombre": None, "categoria": None, "tipo": None, "enlace": None,
           "semana": None, "unidad": None, "tema": None}
    for i, celda in enumerate(fila):
        v = normalizar(celda)
        if "nombre del recurso" in v and idx["nombre"] is None:
            idx["nombre"] = i
        elif v == "categoria" and idx["categoria"] is None:
            idx["categoria"] = i
        elif "tipo de recurso" in v and idx["tipo"] is None:
            idx["tipo"] = i
        elif "enlace" in v and idx["enlace"] is None:
            idx["enlace"] = i
        elif "semana" in v and idx["semana"] is None:
            idx["semana"] = i
        elif v == "unidad" and idx["unidad"] is None:
            idx["unidad"] = i
    # La columna del código de sub-tema (p.ej. "1.1") está vacía en el encabezado
    # y vive justo antes de "Nombre del recurso".
    if idx["nombre"] is not None and idx["nombre"] > 0:
        idx["tema"] = idx["nombre"] - 1
    return idx


def leer_matriz(ruta):
    """Lee la matriz desde un archivo .csv y devuelve (recursos, advertencias)."""
    advertencias = []

    if not ruta.lower().endswith(".csv"):
        advertencias.append(
            f"La matriz debe ser un archivo .csv (recibido: {ruta}). "
            "Si tu matriz es de Excel, exporta la hoja como CSV.")
        return [], advertencias

    # utf-8-sig tolera el BOM que agrega Excel al exportar a CSV.
    # errors="replace" evita que un carácter raro tumbe toda la lectura.
    with open(ruta, newline="", encoding="utf-8-sig", errors="replace") as fh:
        filas = [[c.strip() for c in fila] for fila in csv.reader(fh)]

    return _parsear_filas_matriz(filas)


def leer_matriz_texto(texto):
    """Parsea una matriz CSV ya cargada en memoria como texto.

    Lo usa la interfaz cuando el navegador envía el contenido del .csv
    en lugar de una ruta de archivo.
    """
    filas = [[c.strip() for c in fila] for fila in csv.reader(texto.splitlines())]
    return _parsear_filas_matriz(filas)


def _parsear_filas_matriz(filas):
    """Convierte las filas ya leídas de la matriz en recursos auditables."""
    advertencias = []

    # Buscar la fila de encabezado que contiene "Nombre del recurso".
    enc_idx = None
    idx = None
    for i, fila in enumerate(filas):
        if any("nombre del recurso" in normalizar(c) for c in fila):
            enc_idx = i
            idx = detectar_columnas(fila)
            break

    if idx is None or idx["nombre"] is None:
        advertencias.append(
            "No encontré la fila de encabezado con la columna 'Nombre del recurso' "
            "en la matriz. Verifica que sea la matriz de recursos del curso.")
        return [], advertencias

    recursos = []
    unidad_actual = ""
    semana_actual = ""
    tema_actual = ""

    for i in range(enc_idx + 1, len(filas)):
        fila = filas[i] + [""] * 20
        num = i + 1  # número de fila (1-based) para referenciar en el reporte

        def c(col):
            j = idx.get(col)
            return fila[j] if j is not None and j < len(fila) else ""

        celda_unidad = c("unidad")
        celda_nombre = c("nombre")
        celda_cat = c("categoria")
        celda_tipo = c("tipo")
        celda_enlace = c("enlace")
        celda_semana = c("semana")
        celda_tema = c("tema")

        # Arrastrar unidad y semana de las filas que solo las declaran.
        if celda_unidad:
            unidad_actual = celda_unidad
        if celda_semana:
            semana_actual = celda_semana
        # Detectar fila-título de unidad ("Unidad 1: ...") sin recurso.
        if celda_nombre and not celda_cat and normalizar(celda_nombre).startswith("unidad"):
            unidad_actual = celda_nombre
            continue
        # Detectar fila de sub-tema (trae solo el código, p.ej. "1.1", y un texto).
        es_fila_tema = (celda_cat == "" and celda_nombre and
                        re.match(r"^\d+(\.\d+)?$", celda_tema) is not None)
        if es_fila_tema:
            tema_actual = celda_nombre
            continue

        # Fila de recurso real: tiene categoría OVI/OVA/CHALLENGE o, aunque no la
        # tenga, trae algo en la columna Enlace (toda fila con enlace se audita).
        cat_norm = normalizar(celda_cat)
        if cat_norm not in ("ovi", "ova", "challenge") and not celda_enlace:
            continue
        if cat_norm not in ("ovi", "ova", "challenge"):
            advertencias.append(
                f"Fila {num}: «{celda_nombre or celda_enlace}» tiene enlace pero no categoría "
                "OVI/OVA/CHALLENGE; se audita igual.")

        if not celda_nombre:
            advertencias.append(f"Fila {num}: falta el nombre del recurso en la matriz.")

        tipo_norm = normalizar(celda_tipo)
        ext_esperada = EXT_POR_TIPO.get(tipo_norm, "")
        fuera_de_alcance = tipo_norm in TIPOS_FUERA_DE_ALCANCE
        if not ext_esperada and not fuera_de_alcance:
            advertencias.append(
                f"Fila {num}: el «Tipo de recurso» es "
                f"{'vacío' if not tipo_norm else repr(celda_tipo)} para «{celda_nombre}»; "
                f"se audita igual por nombre y por título interno.")

        recursos.append({
            "fila": num,
            "semana": semana_actual,
            "unidad": unidad_actual,
            "tema": tema_actual,
            "nombre": celda_nombre,
            "categoria": celda_cat,
            "tipo": celda_tipo,
            "enlace": celda_enlace,
            "ext_esperada": ext_esperada,
            "fuera_de_alcance": fuera_de_alcance,
        })

    return recursos, advertencias


# ---------------------------------------------------------------------------
# Indexado de archivos y lectura de títulos H5P
# ---------------------------------------------------------------------------

def leer_titulo_h5p(ruta):
    """Devuelve el título interno de un .h5p (que es un ZIP con h5p.json)."""
    try:
        with zipfile.ZipFile(ruta) as z:
            with z.open("h5p.json") as fh:
                datos = json.load(fh)
        return datos.get("title", ""), None
    except zipfile.BadZipFile:
        return None, "no es un ZIP/H5P válido"
    except KeyError:
        return None, "no contiene h5p.json"
    except Exception as exc:  # noqa: BLE001
        return None, f"error al leer: {exc}"


def titulos_visibles_h5p(ruta, tope=40):
    """Títulos que el contenido MUESTRA por dentro (content/content.json).

    Hay .h5p cuyo título de paquete (h5p.json) es un relleno —p. ej. "s"—
    mientras el contenido sí muestra el título real (el capítulo de un Libro
    interactivo, el título de una presentación, etc.). Se usa solo para
    explicar una alerta; si el ZIP no se puede leer, devuelve lista vacía.
    """
    try:
        with zipfile.ZipFile(ruta) as z:
            nombre = next((n for n in z.namelist()
                           if n.replace("\\", "/").lower()
                                .endswith("content/content.json")), None)
            if not nombre:
                return []
            datos = json.loads(z.read(nombre).decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001
        return []
    salida, vistos = [], set()

    def rec(nodo):
        if isinstance(nodo, list):
            for v in nodo:
                rec(v)
                if len(salida) >= tope:
                    return
            return
        if not isinstance(nodo, dict):
            return
        md = nodo.get("metadata")
        if isinstance(md, dict):
            t = md.get("title")
            if isinstance(t, str) and t.strip() and t not in vistos:
                vistos.add(t)
                salida.append(t)
        for v in nodo.values():
            if isinstance(v, (dict, list)):
                rec(v)
                if len(salida) >= tope:
                    return

    if isinstance(datos, dict):
        t = datos.get("title")
        if isinstance(t, str) and t.strip():
            vistos.add(t)
            salida.append(t)
    rec(datos)
    return salida


def titulos_principales_h5p(ruta):
    """Títulos raíz del contenido H5P; no confunde títulos de capítulos con portada."""
    try:
        with zipfile.ZipFile(ruta) as z:
            nombre = next((n for n in z.namelist()
                           if n.replace("\\", "/").lower()
                           .endswith("content/content.json")), None)
            if not nombre:
                return []
            datos = json.loads(z.read(nombre).decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001
        return []
    if not isinstance(datos, dict):
        return []
    titulos = []
    titulo = datos.get("title")
    metadata = datos.get("metadata")
    metadata_titulo = metadata.get("title") if isinstance(metadata, dict) else ""
    for valor in (titulo, metadata_titulo):
        if isinstance(valor, str) and valor.strip() and valor.strip() not in titulos:
            titulos.append(valor.strip())
    return titulos


def aviso_titulo_envuelto(archivo, clave_titulo):
    """Frase de ayuda cuando el título del paquete (h5p.json) no calza:

    ¿el contenido por dentro SÍ muestra el título del recurso? (Caso típico:
    paquete con título de relleno y el título real dentro del capítulo.)
    Usa `titulos_contenido` si el navegador ya los leyó; si no, abre el ZIP.
    """
    if archivo.get("titulo_proveido"):
        visibles = archivo.get("titulos_contenido") or []
    else:
        visibles = titulos_visibles_h5p(archivo.get("ruta") or "")
    coincide = next((t for t in visibles if clave(t) == clave_titulo), None)
    if coincide:
        return (f'; OJO: el contenido SÍ muestra "{coincide}" — lo que no calza es '
                f'el título del paquete (h5p.json); edítalo en el editor (Lumi) y '
                f'vuelve a auditar')
    if visibles:
        return f'; por dentro el contenido muestra "{visibles[0]}"'
    return ""


def indexar_archivos(carpeta):
    """Recorre la carpeta y lista todos los archivos con su clave comparable."""
    archivos = []
    for ruta, _dirs, nombres in os.walk(carpeta):
        for nombre in nombres:
            if nombre.startswith("."):
                continue
            completo = os.path.join(ruta, nombre)
            base, ext = os.path.splitext(nombre)
            archivos.append({
                "nombre": nombre,
                "ruta": completo,
                "rel": os.path.relpath(completo, carpeta),
                "ext": ext.lower(),
                "base": base,
                "clave": clave(base),
                "usado": False,
            })
    archivos.sort(key=lambda a: a["rel"].lower())
    return archivos


# ---------------------------------------------------------------------------
# Lógica de emparejamiento
# ---------------------------------------------------------------------------

def emparejar(recursos, archivos):
    """Cruza cada recurso con su archivo. Devuelve (resultados, huérfanos, avisos).

    Si el nombre no calza exacto, se toma el archivo más parecido cuando llega a
    SIMILITUD_ACEPTAR (51 %): va a OK con el detalle «coincide por similitud».
    """
    resultados = []
    avisos = []

    for rec in recursos:
        if not str(rec.get("nombre") or "").strip():
            resultados.append({**rec, "estado": "alerta", "archivo": None,
                               "detalle": "El nombre del recurso está vacío en la matriz."})
            continue
        if rec["fuera_de_alcance"]:
            # Aun fuera de alcance, consumimos el archivo si coincide por nombre
            # (los videos traen su nombre real en la columna "enlace").
            archivo_asig = None
            # La columna "enlace" de los videos trae el nombre con extensión;
            # la clave del archivo indexado va sin ella, así que la quitamos.
            base_enlace = os.path.splitext(rec["enlace"])[0]
            clave_enlace = clave(base_enlace)
            clave_nom = clave(rec["nombre"])
            for a in archivos:
                if a["usado"]:
                    continue
                if (clave_enlace and a["clave"] == clave_enlace) or \
                   (clave_nom and a["clave"] == clave_nom):
                    a["usado"] = True
                    archivo_asig = a["nombre"]
                    break
            resultados.append({**rec, "estado": "fuera-de-alcance", "archivo": archivo_asig,
                               "detalle": f"tipo '{rec['tipo']}' no se audita (no es H5P/PDF)"})
            continue

        clave_titulo = clave(rec["nombre"])
        esperada = rec["ext_esperada"]
        # Si la matriz no declara el tipo ("ext_esperada" vacía) se audita igual:
        # se acepta cualquier extensión y se valida el título interno si es .h5p.
        sin_tipo = not esperada

        # 1) Candidatos con la extensión correcta (o cualquiera si no hay tipo declarado).
        candidatos = [a for a in archivos
                      if not a["usado"] and a["clave"] and
                      (sin_tipo or ext_coincide(a["ext"], esperada))]

        exactos = [a for a in candidatos if a["clave"] == clave_titulo]
        if not exactos and esperada in EXTS_POR_FAMILIA and rec.get("enlace"):
            # Videos/imágenes: la columna Enlace suele traer el nombre real del archivo.
            clave_enlace = clave(os.path.splitext(rec["enlace"])[0])
            exactos = [a for a in candidatos if clave_enlace and a["clave"] == clave_enlace]
        truncados = [a for a in candidatos
                     if a["clave"] != clave_titulo and es_inicio_exacto(a["clave"], clave_titulo)]

        if exactos or truncados:
            usados = exactos + truncados
            principal = exactos[0] if exactos else truncados[0]
            principal["usado"] = True
            for extra in usados[1:]:
                extra["usado"] = True

            estado = "ok"
            detalle = "nombre exacto" if exactos else "nombre truncado (inicio exacto del título)"
            if sin_tipo:
                detalle += " (la matriz no declara tipo de recurso; se valida por título)"

            # Verificar título interno para H5P.
            if esperada == ".h5p" or principal["ext"] == ".h5p":
                if principal.get("titulo_proveido"):
                    # El navegador ya leyó el título dentro del .h5p.
                    titulo_int = principal.get("titulo") or ""
                    err = principal.get("titulo_error")
                else:
                    titulo_int, err = leer_titulo_h5p(principal["ruta"])
                if err:
                    estado = "alerta"
                    detalle = f"H5P ilegible: {err}"
                else:
                    k_int = clave(titulo_int)
                    if k_int == clave_titulo:
                        detalle += f'; título interno coincide ("{titulo_int}")'
                    else:
                        estado = "alerta"
                        detalle = (f'el título interno NO coincide con la matriz. '
                                   f'Interno="{titulo_int}" vs Matriz="{rec["nombre"]}"'
                                   + aviso_titulo_envuelto(principal, clave_titulo))
            # La alerta de nombre se basa en comparar el título de h5p.json con
            # el nombre del recurso de la matriz. La portada/contenido y la
            # ubicación del archivo no cambian ese resultado.
            # Si el archivo está dentro de una subcarpeta, se informa como nota.
            sub = os.path.dirname(principal.get("rel", "") or "")
            if sub:
                detalle += f"; el archivo está dentro de la subcarpeta «{sub}»"

            if len(usados) > 1:
                estado = "alerta"
                otros = ", ".join(a["nombre"] for a in usados[1:])
                detalle += f'; archivos duplicados para este recurso: {otros}'

            resultados.append({**rec, "estado": estado, "archivo": principal["nombre"],
                               "detalle": detalle})
            continue

        # 2) El único candidato es una copia con sufijo duplicado " (N)".
        #    El recurso SÍ existe y está cargado; solo su nombre trae texto
        #    extra. Se cuenta como OK (con nota), nunca como FALTANTE.
        def _clave_limpia(a):
            return clave(quitar_duplicado(a["base"]))

        dup_exactos = [a for a in candidatos
                       if a["clave"] != clave_titulo and _clave_limpia(a) == clave_titulo]
        dup_trunc = [a for a in candidatos
                     if a["clave"] != clave_titulo and _clave_limpia(a) != clave_titulo
                     and es_inicio_exacto(_clave_limpia(a), clave_titulo)]
        duplicados = dup_exactos + dup_trunc
        if duplicados:
            principal = duplicados[0]
            for d in duplicados:
                d["usado"] = True
            detalle = (f"coincide con '{os.path.basename(principal['nombre'])}' "
                       f"(copia con sufijo duplicado ' (N)' en el nombre)")
            estado = "ok"
            if esperada == ".h5p" or principal["ext"] == ".h5p":
                if principal.get("titulo_proveido"):
                    titulo_int, err = principal.get("titulo"), principal.get("titulo_error")
                else:
                    titulo_int, err = leer_titulo_h5p(principal["ruta"])
                if err:
                    estado = "alerta"
                    detalle += f"; el H5P no se pudo leer: {err}"
                else:
                    k_int = clave(titulo_int)
                    if k_int == clave_titulo:
                        detalle += f'; título interno OK ("{titulo_int}")'
                    else:
                        estado = "alerta"
                        detalle += (f'; ojo: el título interno NO coincide ("{titulo_int}")'
                                    + aviso_titulo_envuelto(principal, clave_titulo))
            sub = os.path.dirname(principal.get("rel", "") or "")
            if sub:
                detalle += f"; el archivo está dentro de la subcarpeta «{sub}»"
            resultados.append({**rec, "estado": estado, "archivo": principal["nombre"],
                               "detalle": detalle})
            continue

        # 3) Con tipo declarado y sin candidatos de extensión correcta: ¿existe
        #    con otra extensión? (Si no hay tipo, cualquier extensión ya sirve.)
        otros_ext = [] if sin_tipo else [a for a in archivos
                     if not a["usado"] and a["clave"] and
                     (a["clave"] == clave_titulo or es_inicio_exacto(a["clave"], clave_titulo))]
        if otros_ext:
            mala = otros_ext[0]
            mala["usado"] = True
            resultados.append({**rec, "estado": "alerta", "archivo": mala["nombre"],
                               "detalle": (f"extensión incorrecta: se esperaba "
                                           f"'{'/'.join(EXTS_POR_FAMILIA.get(esperada, (esperada,)))}' "
                                           f"pero se encontró '{mala['ext']}'")})
            continue

        # 4) Nada que calce: buscar el más parecido para sugerir.
        sugerencia = None
        mejor = 0.0
        for a in archivos:
            if a["usado"] or not a["clave"]:
                continue
            s = similitud(a["clave"], clave_titulo)
            if s > mejor:
                mejor, sugerencia = s, a

        # 4) Si el más parecido llega al umbral (51 % de similitud), se empareja
        #    directamente como OK; queda constancia en el detalle.
        if sugerencia and mejor >= SIMILITUD_ACEPTAR:
            sugerencia["usado"] = True
            s = similitud(sugerencia["clave"], clave_titulo) if sugerencia["clave"] else 0.0
            detalle = (f"coincide por similitud ({s:.0%} ≥ {SIMILITUD_ACEPTAR:.0%}): "
                       f"'{sugerencia['nombre']}'")
            if esperada == ".h5p":
                if sugerencia.get("titulo_proveido"):
                    titulo_int = sugerencia.get("titulo") or ""
                    err = sugerencia.get("titulo_error")
                else:
                    titulo_int, err = leer_titulo_h5p(sugerencia["ruta"])
                if err:
                    detalle += f"; el H5P no se pudo leer: {err}"
                elif clave(titulo_int) == clave_titulo:
                    detalle += f'; título interno OK ("{titulo_int}")'
                else:
                    detalle += (f'; ojo: el título interno NO coincide ("{titulo_int}")'
                                + aviso_titulo_envuelto(sugerencia, clave_titulo))
            resultados.append({**rec, "estado": "ok",
                               "archivo": sugerencia["nombre"], "detalle": detalle})
            continue

        if sugerencia:
            resultados.append({**rec, "estado": "faltante", "archivo": None,
                               "sugerencia": {"archivo": sugerencia["nombre"],
                                              "similitud": round(mejor, 3)},
                               "detalle": (f"no se encontró archivo. El más parecido es "
                                           f"'{sugerencia['nombre']}' (similitud {mejor:.0%}) "
                                           f"— revisar si es ese o falta subirlo")})
        else:
            resultados.append({**rec, "estado": "faltante", "archivo": None,
                               "sugerencia": None,
                               "detalle": "no se encontró ningún archivo que corresponda"})

    huerfanos = [a for a in archivos if not a["usado"]]
    return resultados, huerfanos, avisos


# ---------------------------------------------------------------------------
# Reporte Markdown
# ---------------------------------------------------------------------------

ICONOS = {
    "ok": "OK",
    "alerta": "ALERTA",
    "faltante": "FALTANTE",
    "fuera-de-alcance": "N/A",
}


def contar_extensiones(archivos):
    """Cuenta cuántos archivos hay por extensión. Devuelve (filas, total).

    `filas` es una lista [(extensión, cantidad)] ordenada de mayor a menor.
    """
    cuenta = {}
    for a in archivos:
        ext = a["ext"] or "(sin extensión)"
        cuenta[ext] = cuenta.get(ext, 0) + 1
    filas = sorted(cuenta.items(), key=lambda kv: (-kv[1], kv[0]))
    return filas, len(archivos)


def titulos_h5p(archivos):
    """Obtiene el título interno de cada .h5p (revisión 1 a 1).

    Si el título ya viene leído del navegador (titulo_proveido) lo usa; si no,
    abre el paquete (ZIP) y lee h5p.json. Devuelve una lista ordenada de
    {"archivo", "titulo", "error"}.
    """
    filas = []
    for a in archivos:
        if a["ext"] != ".h5p":
            continue
        if a.get("titulo_proveido"):
            titulo, err = a.get("titulo"), a.get("titulo_error")
        else:
            titulo, err = leer_titulo_h5p(a["ruta"])
        filas.append({"archivo": a["rel"], "titulo": titulo, "error": err})
    filas.sort(key=lambda f: f["archivo"].lower())
    return filas


VIDEO_EXTS = (".webm", ".mp4", ".mov", ".mkv", ".avi")


def verificar_abre(nombre, ext, ruta=None, titulo=None, titulo_error=None):
    """Revisa si un archivo "abre" (se puede leer/verificar). Devuelve (estado, nota).

    - `.h5p`: lee el título interno (h5p.json).
    - `.pdf`: valida la cabecera `%PDF-`.
    - video: valida la cabecera EBML (webm/mkv) o `ftyp` (mp4/mov).
    - otros: solo indica que está presente (el cruce es por nombre).

    `estado` es "ok" o "error". Si `ruta` es None (archivo leído por el navegador)
    y no vienen titulo/titulo_error, se asume "ok" y se marca como presente.
    """
    if ruta and os.path.isfile(ruta) and os.path.getsize(ruta) <= 0:
        return "error", "el archivo está vacío (0 bytes)"
    if ext == ".h5p":
        if titulo_error:
            return "error", f"no se pudo leer: {titulo_error}"
        if titulo is not None:
            return "ok", (f'título: "{titulo}"' if titulo else "abre (sin título interno)")
        if ruta:
            t, err = leer_titulo_h5p(ruta)
            if err:
                return "error", f"no se pudo leer: {err}"
            return "ok", (f'título: "{t}"' if t else "abre (sin título interno)")
        return "ok", "presente"

    if ext == ".pdf":
        if ruta:
            try:
                with open(ruta, "rb") as fh:
                    cab = fh.read(5)
                if cab == b"%PDF-":
                    return "ok", "PDF válido"
                return "error", "no parece un PDF (cabecera incorrecta)"
            except Exception as exc:  # noqa: BLE001
                return "error", f"no se pudo abrir: {exc}"
        return "ok", "presente"

    if ext in VIDEO_EXTS:
        if ruta:
            try:
                with open(ruta, "rb") as fh:
                    cab = fh.read(8)
                if cab[:4] == b"\x1aE\xdf\xa3" or cab[4:8] == b"ftyp":
                    return "ok", "video válido"
                return "error", "no parece un video (cabecera incorrecta)"
            except Exception as exc:  # noqa: BLE001
                return "error", f"no se pudo abrir: {exc}"
        return "ok", "presente"

    return "ok", "solo se cruza por nombre"


def detalles_archivos(archivos):
    """Revisión 1 a 1 de TODOS los archivos: extensión, si abre y un detalle.

    Si el navegador ya calculó `abre`/`nota` los usa; si no (modo disco/CLI),
    verifica cada archivo con `verificar_abre`.
    """
    filas = []
    for a in archivos:
        if a.get("abre") is not None:
            abre, nota = a["abre"], a.get("nota", "")
        else:
            abre, nota = verificar_abre(a["nombre"], a["ext"], a.get("ruta"),
                                        a.get("titulo"), a.get("titulo_error"))
        filas.append({"archivo": a["rel"], "ext": a["ext"], "abre": abre, "nota": nota})
    filas.sort(key=lambda f: f["archivo"].lower())
    return filas


# ---------------------------------------------------------------------------
# Syllabus (opcional): cruce breve contra la matriz
# ---------------------------------------------------------------------------
# Añadido a petición del usuario: si se entrega un syllabus (.docx, .pdf o
# texto), se verifica en UNA sola sección breve que las unidades, los temas,
# el programa, el curso y las semanas coincidan con la matriz. Es OPCIONAL:
# sin syllabus no hay sección, y sus avisos NO cambian el veredicto del curso.

def _texto_docx(datos):
    """Texto de un .docx: es un ZIP con word/document.xml (sin dependencias)."""
    try:
        with zipfile.ZipFile(io.BytesIO(datos)) as z:
            xml = z.read("word/document.xml").decode("utf-8", "replace")
    except Exception as exc:  # noqa: BLE001
        return None, f"no se pudo leer el .docx: {exc}"
    xml = xml.replace("</w:p>", "\n").replace("<w:br/>", "\n").replace("<w:cr/>", "\n")
    xml = xml.replace("<w:tab/>", "\t").replace("</w:tc>", "\t")  # celdas de tabla
    texto = re.sub(r"<[^>]+>", "", xml)
    return html.unescape(texto), None


def _pdf_cadena(cad):
    """Interior de una cadena PDF ((…) ) convertido a texto legible."""
    salida = bytearray()
    i = 0
    while i < len(cad):
        b = cad[i]
        if b == 0x5C and i + 1 < len(cad):          # barra invertida
            i += 1
            nxt = cad[i]
            mapa = {0x6E: 10, 0x72: 13, 0x74: 9, 0x62: 8, 0x66: 12,
                    0x28: 40, 0x29: 41, 0x5C: 92}
            if nxt in mapa:
                salida.append(mapa[nxt])
                i += 1
            elif 0x30 <= nxt <= 0x37:                # octal \ddd
                octal = ""
                while i < len(cad) and 0x30 <= cad[i] <= 0x37 and len(octal) < 3:
                    octal += chr(cad[i])
                    i += 1
                salida.append(int(octal, 8) & 0xFF)
            else:
                salida.append(nxt)
                i += 1
        else:
            salida.append(b)
            i += 1
    return salida.decode("latin-1", "replace")


def _texto_pdf_simple(datos):
    """Respaldo sin dependencias: descomprime los streams del PDF con zlib y
    concatena las cadenas de los operadores de texto (Tj/TJ)."""
    partes = []
    for m in re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", datos, re.S):
        desc = None
        for wbits in (zlib.MAX_WBITS, -zlib.MAX_WBITS):
            try:
                desc = zlib.decompressobj(wbits).decompress(m.group(1))
                break
            except Exception:  # noqa: BLE001
                continue
        if not desc:
            continue
        for op in re.findall(rb"\((?:\\[\s\S]|[^\\()])*\)\s*Tj|\[[\s\S]*?\]\s*TJ", desc):
            for cad in re.findall(rb"\((?:\\[\s\S]|[^\\()])*\)", op):
                partes.append(_pdf_cadena(cad[1:-1]))
    return "\n".join(p for p in partes if p.strip()), None


def _texto_pdf(datos):
    """Texto de un PDF: usa `pdftotext` si está instalado; si no, el lector
    propio básico de arriba (solo alcanza para PDFs con texto literal)."""
    exe = shutil.which("pdftotext")
    if exe:
        ruta = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as fh:
                fh.write(datos)
                ruta = fh.name
            salida = subprocess.run([exe, ruta, "-"], capture_output=True, timeout=60)
            if salida.returncode == 0:
                texto = salida.stdout.decode("utf-8", "replace")
                if texto.strip():
                    return texto, None
        except Exception:  # noqa: BLE001
            pass
        finally:
            if ruta and os.path.exists(ruta):
                os.unlink(ruta)          # el temporal no debe quedar
        return None, ("el PDF no tiene texto extraíble por esta vía "
                      "(¿será un escaneo o una imagen por página?)")
    texto, _ = _texto_pdf_simple(datos)
    if texto and texto.strip():
        return texto, None
    return None, ("este PDF usa fuentes codificadas y aquí no hay `pdftotext` "
                  "(instala poppler: `brew install poppler`) — o pega el "
                  "syllabus en un archivo .txt y repítelo")


def leer_syllabus(datos, nombre=""):
    """Lee un syllabus y devuelve (texto, error).

    `datos` puede ser una ruta (str) o los bytes ya leídos por la interfaz.
    Formatos: .docx, .pdf y texto plano (.txt, .md, .html…).
    """
    if isinstance(datos, str):
        nombre = nombre or datos
        try:
            with open(datos, "rb") as fh:
                datos = fh.read()
        except Exception as exc:  # noqa: BLE001
            return None, f"no se pudo abrir «{nombre}»: {exc}"
    if not datos:
        return None, "el archivo del syllabus está vacío"
    ext = os.path.splitext(nombre or "")[1].lower()
    if datos[:4] == b"PK\x03\x04":        # .docx (o cualquier ZIP)
        ext = ".docx"
    elif datos[:5] == b"%PDF-":
        ext = ".pdf"
    if ext in (".docx", ".zip"):
        texto, err = _texto_docx(datos)
    elif ext == ".pdf":
        texto, err = _texto_pdf(datos)
    else:
        texto, err = datos.decode("utf-8", "replace"), None
    texto = (texto or "").strip()
    if not texto:
        return None, err or "el syllabus no contiene texto extraíble"
    return texto, None


def parse_syllabus(texto):
    """Extrae del syllabus: programa, curso, semanas y bloques (unidad → temas).

    Formato esperado (el de los syllabus reales del programa): etiquetas
    «Programa», «Curso o Asignatura», «Número de semanas: N» y bloques
    «Unidad N: título» con sus temas en viñetas (las viñetas con año entre
    paréntesis se toman por bibliografía y se ignoran).
    """
    datos = {"programa": None, "curso": None, "semanas": None, "unidades": []}
    lineas = texto.splitlines()

    def campo(etiqueta):
        """Valor de una etiqueta: en la misma línea (tras «:», tabulador o
        2+ espacios) o en la siguiente línea no vacía si la etiqueta está sola."""
        solo = re.compile(rf"^\s*{etiqueta}\s*$", re.I)
        traste = re.compile(rf"^\s*{etiqueta}(?:\s*[:\t]|\s{{2,}})(.+)$", re.I)
        relajado = re.compile(rf"^\s*{etiqueta}\s+(.{12,})$", re.I)
        for i, linea in enumerate(lineas):
            m = traste.match(linea)
            if m and m.group(1).strip():
                return m.group(1).strip()
            if solo.match(linea):
                for j in range(i + 1, min(i + 6, len(lineas))):
                    sig = lineas[j].strip()
                    if sig:
                        return sig
        for linea in lineas:                       # respaldo: «Etiqueta valor»
            m = relajado.match(linea)
            if m and m.group(1).strip():
                return m.group(1).strip()
        return None

    datos["programa"] = campo(r"programa")
    datos["curso"] = campo(r"curso\s+o\s+asignatura")

    m = re.search(r"(?i)n[uú]mero\s+de\s+semanas\s*[:\-–]?\s*(\d+)", texto)
    if not m:
        m = re.search(r"(?i)(\d+)\s*semanas\b", texto)
    if m:
        datos["semanas"] = int(m.group(1))

    ROMANOS = {"i": 1, "ii": 2, "iii": 3, "iv": 4, "v": 5, "vi": 6,
               "vii": 7, "viii": 8, "ix": 9, "x": 10, "xi": 11, "xii": 12}
    encabezados = []
    for m in re.finditer(r"(?im)^\s*unidad\s+(\d+|[ivxlcdm]+)\s*[:.\-–]?\s*(.*)$",
                         texto):
        bruto = m.group(1)
        num = int(bruto) if bruto.isdigit() else ROMANOS.get(bruto.lower())
        if num is None:
            continue                                # "unidad de contenidos" y demás
        titulo = (m.group(2) or "").strip().lstrip(" .-–:").strip()
        encabezados.append((num, titulo, m.start()))

    for k, (num, titulo, pos) in enumerate(encabezados):
        fin = encabezados[k + 1][2] if k + 1 < len(encabezados) else len(texto)
        temas, visto = [], set()
        for linea in texto[pos:fin].splitlines():
            l = linea.strip()
            if not l or re.match(r"(?i)unidad\s+\d+", l):
                continue                            # su propia línea de encabezado
            if l.startswith(("-", "•")) or re.search(r"\s-\s", l):
                partes = re.split(r"(?:^|(?<=\s))-\s*|\u2022\s*", l)
            else:
                if temas:
                    break                           # empezó otra sección
                continue                            # restos de tabla: «Temas»…
            for seg in partes:
                seg = seg.strip().strip("·•").strip()
                if len(seg) < 12:                   # restos tipo «a.», «b.»…
                    continue
                if re.search(r"\((?:19|20)\d{2}\)", seg):
                    continue                        # bibliografía (año)
                kk = clave(seg)
                if titulo and kk == clave(titulo):
                    continue
                if not re.search(r"[a-z0-9]", kk):
                    continue
                if kk not in visto:
                    visto.add(kk)
                    temas.append(seg)
        datos["unidades"].append({"numero": num, "titulo": titulo, "temas": temas})
    return datos


def programa_de_matriz(matriz_texto):
    """Primera celda con contenido de las filas previas al encabezado: ahí las
    matrices traen el nombre del programa (p. ej. «Lic en Etnoeducación…»)."""
    if not matriz_texto:
        return None
    try:
        filas = list(csv.reader(io.StringIO(matriz_texto)))
    except Exception:  # noqa: BLE001
        return None
    for i, fila in enumerate(filas):
        celdas = [c.strip() for c in fila if c and c.strip()]
        if not celdas:
            continue
        if any("nombre del recurso" in clave(c) for c in celdas):
            for prev in filas[:i]:                  # filas de título
                for c in prev:
                    if c and c.strip():
                        return c.strip()
            return None
    return None


def auditar_syllabus(texto, recursos, matriz_texto=None, nombre_matriz=None):
    """Cruce breve syllabus ↔ matriz: unidades, temas, programa, curso y semanas.

    Devuelve {"ok", "avisos", "filas": [{ok, campo, detalle}], …}. Los avisos
    son informativos: NO cambian el veredicto del curso.
    """
    s = parse_syllabus(texto)

    # --- lo que dice la matriz (unidades, temas y última semana) ---
    unidades_matriz, temas_matriz, vistos = [], [], set()
    semana_max = 0
    for r in recursos:
        uni = (r.get("unidad") or "").strip()
        m = re.match(r"(?i)unidad\s+(\d+)\s*(?::\s*(.+))?$", uni)
        if m:
            num, tit = int(m.group(1)), (m.group(2) or "").strip() or None
        elif uni:
            m2 = re.search(r"\d+", uni)
            num = int(m2.group()) if m2 else len(unidades_matriz) + 1
            tit = None
        else:
            num = None
        if num is not None and not any(n == num for n, _ in unidades_matriz):
            unidades_matriz.append((num, tit))
        tem = (r.get("tema") or "").strip()
        kk = clave(tem)
        if tem and kk and kk not in vistos:
            vistos.add(kk)
            temas_matriz.append(tem)
        m3 = re.search(r"\d+", r.get("semana") or "")
        if m3:
            semana_max = max(semana_max, int(m3.group()))

    prog_m = programa_de_matriz(matriz_texto)
    curso_m = None
    if nombre_matriz:
        curso_m = os.path.splitext(os.path.basename(nombre_matriz))[0]
        curso_m = re.sub(r"(?i)^\s*semestre\s*\d+\s*[-–—]\s*",
                         "", curso_m).strip() or None

    filas = []

    def comp_texto(campo, val_s, val_m):
        """Comparación genérica de un campo de texto (programa / curso)."""
        if val_s and val_m:
            ks, km = clave(val_s), clave(val_m)
            sim = similitud(ks, km)
            ok = sim >= 0.6 or km in ks or ks in km
            filas.append({"ok": ok, "campo": campo,
                          "detalle": (f"«{val_s}» = matriz «{val_m}»" if ok else
                                      f"NO coincide: syllabus «{val_s}» ≠ matriz «{val_m}» ({sim:.0%})")})
        elif val_s:
            filas.append({"ok": None, "campo": campo,
                          "detalle": f"syllabus «{val_s}» · la matriz no trae ese dato (no se comparó)"})
        elif val_m:
            filas.append({"ok": False, "campo": campo,
                          "detalle": f"no encontré «{campo}» en el syllabus (la matriz dice «{val_m}»)"})
        else:
            filas.append({"ok": None, "campo": campo,
                          "detalle": "sin dato en ninguno de los dos"})

    comp_texto("Programa", s["programa"], prog_m)
    comp_texto("Curso", s["curso"], curso_m)

    # --- unidades ---
    nums_m = [n for n, _ in unidades_matriz]
    nums_s = [u["numero"] for u in s["unidades"]]
    tit_s = {u["numero"]: u["titulo"] for u in s["unidades"]}
    if not nums_s:
        filas.append({"ok": False, "campo": "Unidades",
                      "detalle": "no encontré bloques «Unidad N: …» en el syllabus"})
    elif not nums_m:
        filas.append({"ok": None, "campo": "Unidades",
                      "detalle": f"syllabus {len(nums_s)} unidad(es) · la matriz no declara unidades (no se comparó)"})
    else:
        faltan_u = [n for n in nums_m if n not in nums_s]
        sobran_u = [n for n in nums_s if n not in nums_m]
        titulos_malos = [f"U{n}: matriz «{t}» vs syllabus «{tit_s[n]}»"
                         for n, t in unidades_matriz
                         if t and tit_s.get(n) and similitud(clave(t), clave(tit_s[n])) < 0.6]
        det = (f"matriz: {', '.join(map(str, nums_m))} · "
               f"syllabus: {', '.join(map(str, nums_s))}")
        if faltan_u:
            det += f" · falta en el syllabus: Unidad {', '.join(map(str, faltan_u))}"
        if sobran_u:
            det += f" · sobra en el syllabus: Unidad {', '.join(map(str, sobran_u))}"
        if titulos_malos:
            det += " · títulos distintos: " + "; ".join(titulos_malos)
        filas.append({"ok": not (faltan_u or sobran_u or titulos_malos),
                      "campo": "Unidades", "detalle": det})

    # --- temas (coincidencia exacta o con similitud) ---
    topics_s = [t for u in s["unidades"] for t in u["temas"]]
    usados = [False] * len(topics_s)
    coinciden, parecidos, faltan_t = 0, [], []
    for tm in temas_matriz:
        km = clave(tm)
        idx = next((i for i, t in enumerate(topics_s)
                    if not usados[i] and clave(t) == km), None)
        if idx is None:
            mejor, idx = 0.0, None
            for i, t in enumerate(topics_s):
                if not usados[i]:
                    sim = similitud(km, clave(t))
                    if sim > mejor:
                        mejor, idx = sim, i
            if idx is None or mejor < 0.6:
                faltan_t.append(tm)
                continue
            if mejor < 0.85:
                parecidos.append(f"«{tm}» ≈ «{topics_s[idx]}» ({mejor:.0%})")
        usados[idx] = True
        coinciden += 1
    sobran_t = [topics_s[i] for i, u in enumerate(usados) if not u]

    if not temas_matriz:
        filas.append({"ok": None, "campo": "Temas",
                      "detalle": "la matriz no trae temas (no se comparó)"})
    elif not topics_s:
        filas.append({"ok": False, "campo": "Temas",
                      "detalle": "no encontré temas en el syllabus"})
    else:
        def muestra(lista):
            m = ", ".join(f"«{t}»" for t in lista[:3])
            return m + (f" (+{len(lista) - 3})" if len(lista) > 3 else "")
        det = (f"{coinciden} de {len(temas_matriz)} de la matriz "
               f"están en el syllabus ({len(topics_s)} tema(s) ahí)")
        if faltan_t:
            det += f" · falta en el syllabus: {muestra(faltan_t)}"
        if sobran_t:
            det += f" · sobra en el syllabus: {muestra(sobran_t)}"
        if parecidos:
            det += f" · parecidos no exactos: {muestra(parecidos)}"
        filas.append({"ok": not (faltan_t or sobran_t or parecidos),
                      "campo": "Temas", "detalle": det})

    # --- semanas ---
    sem_s, sem_m = s["semanas"], semana_max or None
    if sem_s and sem_m:
        filas.append({"ok": sem_s == sem_m, "campo": "Semanas",
                      "detalle": f"syllabus declara {sem_s} · la matriz llega a la semana {sem_m}" +
                                ("" if sem_s == sem_m else " (no coinciden)")})
    elif sem_s:
        filas.append({"ok": None, "campo": "Semanas",
                      "detalle": f"syllabus declara {sem_s} · la matriz no trae semanas"})
    else:
        filas.append({"ok": None, "campo": "Semanas",
                      "detalle": "no encontré «Número de semanas» en el syllabus (no se comparó)"})

    avisos = sum(1 for f in filas if f["ok"] is False)
    return {"ok": avisos == 0, "avisos": avisos, "filas": filas,
            "programa": {"syllabus": s["programa"], "matriz": prog_m},
            "curso": {"syllabus": s["curso"], "matriz": curso_m},
            "unidades": {"syllabus": nums_s, "matriz": nums_m},
            "temas": {"matriz": len(temas_matriz), "syllabus": len(topics_s),
                      "coinciden": coinciden, "faltan": faltan_t,
                      "sobran": sobran_t, "parecidos": parecidos},
            "semanas": {"syllabus": sem_s, "matriz": sem_m}}


def generar_reporte(resultados, huerfanos, advertencias, ruta_matriz, origen, carpeta_temp,
                    extensiones=None, total_archivos=None, archivos_detalle=None,
                    syllabus=None):
    conteo = {"ok": 0, "alerta": 0, "faltante": 0, "fuera-de-alcance": 0}
    for r in resultados:
        conteo[r["estado"]] = conteo.get(r["estado"], 0) + 1

    def desplegar(titulo, cuerpo):
        """Sección plegable (<details>) para no llenar el reporte de ruido."""
        bloque = ["<details>", f"<summary>{titulo}</summary>", ""]
        bloque.extend(cuerpo)
        bloque += ["", "</details>", ""]
        return bloque

    def tabla_recursos(filas):
        if not filas:
            return ["_Ninguno._"]
        t = ["| Recurso (matriz) | Tipo | Archivo | Detalle |", "|---|---|---|---|"]
        for r in filas:
            arch = f"`{r['archivo']}`" if r["archivo"] else "—"
            t.append(f"| {r['nombre']} | {r['tipo']} | {arch} | {r['detalle']} |")
        return t

    def por(estado):
        return [r for r in resultados if r["estado"] == estado]

    alertas, faltantes = por("alerta"), por("faltante")
    oks, fuera = por("ok"), por("fuera-de-alcance")
    problemas = alertas + faltantes

    lineas = []
    A = lineas.append
    A("# Auditoría de cruce: matriz del curso vs. archivos")
    A("")
    A(f"- **Fecha:** {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    A(f"- **Matriz:** `{ruta_matriz}`")
    A(f"- **Origen:** `{origen}`" + (" (extraído a temporal)" if carpeta_temp else ""))
    A("")

    # --- Veredicto: ¿el curso quedó cargado completo y correcto? ---
    ilegibles = sum(1 for f in (archivos_detalle or []) if f["abre"] != "ok")
    auditables = conteo["ok"] + conteo["alerta"] + conteo["faltante"]
    # Cero cruces: la matriz no coincide NADA con la carpeta (casi siempre es la
    # carpeta de otro curso). Se avisa aparte para no mostrar 49 falsos faltantes.
    sin_cruce = (auditables > 0 and conteo["ok"] == 0 and conteo["alerta"] == 0
                 and total_archivos and len(huerfanos) == total_archivos)
    completo = conteo["faltante"] == 0 and conteo["alerta"] == 0 and ilegibles == 0
    if sin_cruce:
        A("## 🚨 Nada cruzó: parece la carpeta de otro curso")
        A("")
        A(f"La matriz pide **{auditables}** recurso(s) y **ninguno** coincide con los "
          f"**{total_archivos}** archivo(s) de esa carpeta (todos quedaron como "
          "huérfanos). Elige la carpeta que corresponde a esa matriz —o la matriz de esa "
          "carpeta— y vuelve a auditar.")
    elif completo:
        A("## ✅ Veredicto: curso COMPLETO y CORRECTO")
        A("")
        dv = (f"{conteo['ok']} recurso(s) con su archivo compatible con el título "
              f"(nombre exacto o similitud ≥ {SIMILITUD_ACEPTAR:.0%}).")
        if huerfanos:
            dv += f" Atención: hay {len(huerfanos)} archivo(s) sobrante(s) sin fila en la matriz."
        A(dv)
    else:
        A("## ⚠️ Veredicto: curso INCOMPLETO o con inconsistencias")
        A("")
        partes = []
        if conteo["faltante"]:
            partes.append(f"**{conteo['faltante']}** recurso(s) FALTAN (sin archivo)")
        if conteo["alerta"]:
            partes.append(f"**{conteo['alerta']}** con ALERTA (nombre o título no calza)")
        if ilegibles:
            partes.append(f"**{ilegibles}** archivo(s) que NO abren")
        if huerfanos:
            partes.append(f"**{len(huerfanos)}** sobrante(s) sin fila en la matriz")
        A(" · ".join(partes))
    A("")

    # --- Resumen breve (siempre visible) ---
    A("## Resumen")
    A("")
    if extensiones:
        comp = " · ".join(f"{n} {e}" for e, n in extensiones)
        total = total_archivos if total_archivos is not None else sum(n for _, n in extensiones)
        A(f"**Archivos:** {comp}  →  **total {total}**")
        A("")
    A(f"- OK: **{conteo['ok']}**  ·  Alerta: **{conteo['alerta']}**  ·  "
      f"Faltante: **{conteo['faltante']}**  ·  Fuera de alcance: **{conteo['fuera-de-alcance']}**  ·  "
      f"Huérfanos: **{len(huerfanos)}**")
    A("")
    A("> Cada sección con `<summary>` se puede desplegar. Lo que hay que revisar "
      "queda arriba, sin pliegue.")
    A("")

    # --- Syllabus (opcional): una sola sección breve ---
    if syllabus:
        A("## 📄 Syllabus (opcional)")
        A("")
        if syllabus.get("error"):
            A(f"❌ No se pudo leer el syllabus: {syllabus['error']}")
        else:
            n_av = syllabus.get("avisos", 0)
            if n_av:
                A(f"**⚠️ {n_av} aviso(s)** — revisar contra la matriz "
                  "(no cambia el veredicto del curso):")
            else:
                A("**✅ consistente con la matriz** (unidades, temas, programa, "
                  "curso y semanas).")
            A("")
            for f in syllabus.get("filas", []):
                marca = "✅" if f["ok"] else ("⚠️" if f["ok"] is False else "➖")
                A(f"- {marca} **{f['campo']}:** {f['detalle']}")
        A("")

    # --- Lo que hay que revisar (visible, sin pliegue), en dos listas ---
    A("## Revisar")
    A("")
    A(f"**Alertas ({len(alertas)})** — algo no calza:")
    A("")
    lineas.extend(tabla_recursos(alertas) if alertas else ["_Ninguna._"])
    A("")
    A(f"**Faltantes ({len(faltantes)})** — la matriz pide un recurso sin archivo:")
    A("")
    lineas.extend(tabla_recursos(faltantes) if faltantes else ["_Ninguno._"])
    A("")
    if not problemas:
        A("Nada que revisar: todo calza.")
        A("")

    # --- Secciones plegables ---
    lineas.extend(desplegar(f"OK — {len(oks)} recurso(s) correcto(s)", tabla_recursos(oks)))

    lineas.extend(desplegar(
        f"Fuera de alcance — {len(fuera)} (video/otros, no se auditan)",
        tabla_recursos(fuera)))

    if huerfanos:
        cuerpo = [f"{len(huerfanos)} archivo(s) en la carpeta sin fila en la matriz:", ""]
        cuerpo += [f"- `{a['rel']}`" for a in huerfanos]
    else:
        cuerpo = ["_Ninguno._"]
    lineas.extend(desplegar(f"Huérfanos — {len(huerfanos)}", cuerpo))

    # --- Revisión 1 a 1 de TODOS los archivos (abren y los que no) ---
    if archivos_detalle:
        cuerpo = ["Simbología: **✓** = abre/verificado · **✗** = no abre (revisar).", "",
                  "| | Archivo | Ext | Al abrir / título |", "|---|---|---|---|"]
        for f in archivos_detalle:
            marca = "✓" if f["abre"] == "ok" else "✗"
            cuerpo.append(f"| {marca} | `{f['archivo']}` | `{f['ext']}` | {f['nota']} |")
        lineas.extend(desplegar(
            f"Revisión 1 a 1 — todos los archivos ({len(archivos_detalle)}): "
            "los que abren y los que no", cuerpo))

    if advertencias:
        lineas.extend(desplegar("Advertencias de ejecución",
                                [f"- {adv}" for adv in advertencias]))

    A("---")
    A("")
    A("_Generado por `procesar.py`. Solo verifica y audita; no cargó nada a "
      "Moodle ni modificó archivos originales._")
    A("")
    return "\n".join(lineas)


# ---------------------------------------------------------------------------
# Ejecución de la auditoría (compartida por la CLI y por la interfaz gráfica)
# ---------------------------------------------------------------------------

def _archivos_desde_navegador(lista, origen=None):
    """Convierte la lista [{nombre, rel, titulo, titulo_error}] que manda el
    navegador en los dicts que espera `emparejar`.

    El navegador manda `rel` con la carpeta raíz delante (p. ej.
    "Curso/Archivos revisados/x.pdf"); se quita ese primer segmento para que
    `rel` quede siempre relativa al curso (como en el CLI).
    """
    prefijo = (origen or "").strip("/") + "/" if origen else ""
    archivos = []
    for item in lista:
        nombre = item.get("nombre", "") or ""
        rel = item.get("rel", nombre) or nombre
        if prefijo and rel.startswith(prefijo):
            rel = rel[len(prefijo):]
        base, ext = os.path.splitext(nombre)
        archivos.append({
            "nombre": nombre,
            "ruta": rel,                      # ya no hay ruta en disco que leer
            "rel": rel,
            "ext": ext.lower(),
            "base": base,
            "clave": clave(base),
            "titulo_proveido": True,          # el título ya viene leído
            "titulo": item.get("titulo"),
            "titulo_error": item.get("titulo_error"),
            "titulos_contenido": item.get("titulos_contenido") or [],
            "abre": item.get("abre"),         # "ok"/"error" (si abre/verifica)
            "nota": item.get("nota"),         # detalle al abrir (título, PDF, video…)
            "usado": False,
        })
    archivos.sort(key=lambda a: a["rel"].lower())
    return archivos


def ejecutar_auditoria(origen, matriz, salida="resultados",
                       archivos_proveidos=None, matriz_texto=None,
                       syllabus=None, syllabus_nombre="", matriz_nombre=None):
    """Ejecuta la auditoría completa y devuelve un dict estructurado.

    - `origen`: carpeta o ZIP en disco (el ZIP se extrae a un temporal y se borra).
      Puede ser None si se pasan `archivos_proveidos`.
    - `archivos_proveidos`: lista de {nombre, rel, titulo} ya leída por el navegador.
    - `matriz_texto`: la matriz CSV como texto (alternativa a la ruta `matriz`).
    - `syllabus` (opcional): bytes del syllabus (.docx/.pdf/texto); `syllabus_nombre`
      es su nombre de archivo. Si no se pasa, no hay sección de syllabus.
    - `matriz_nombre` (opcional): nombre del CSV para cruzar el nombre del curso
      del syllabus (en la CLI se deduce de la ruta `matriz`).
    - No modifica los archivos originales.
    - Escribe el reporte .md y .json en `salida` si se indica; con `None`, no persiste reportes.
    """
    carpeta_temp = None
    try:
        if archivos_proveidos is not None:
            origen_descripcion = origen or "archivos leídos por el navegador"
        elif os.path.isfile(origen) and zipfile.is_zipfile(origen):
            carpeta_temp = tempfile.mkdtemp(prefix="cursos_zip_")
            with zipfile.ZipFile(origen) as z:
                z.extractall(carpeta_temp)
            origen_descripcion = origen
        elif os.path.isdir(origen):
            origen_descripcion = origen
        else:
            return {"ok": False,
                    "error": f"El origen no es ni carpeta ni ZIP válido: {origen}"}

        if matriz_texto is not None:
            recursos, advertencias = leer_matriz_texto(matriz_texto)
        else:
            recursos, advertencias = leer_matriz(matriz)
        if not recursos:
            return {"ok": False,
                    "error": "No se leyó ningún recurso de la matriz.",
                    "advertencias": advertencias}

        # --- Syllabus (opcional): cruce breve aparte, no toca el veredicto ---
        res_syllabus = None
        if syllabus:
            texto_s, err_s = leer_syllabus(syllabus, syllabus_nombre)
            if err_s:
                res_syllabus = {"ok": False, "avisos": 1, "filas": [],
                                "error": err_s}
            else:
                nombre_m = matriz_nombre or (matriz and os.path.basename(matriz)) or None
                texto_matriz = matriz_texto
                if texto_matriz is None and matriz and os.path.isfile(matriz):
                    try:
                        with open(matriz, encoding="utf-8-sig",
                                  errors="replace") as fh:
                            texto_matriz = fh.read()
                    except Exception:  # noqa: BLE001
                        texto_matriz = None
                res_syllabus = auditar_syllabus(texto_s, recursos,
                                                texto_matriz, nombre_m)
                res_syllabus["nombre"] = syllabus_nombre or ""

        if archivos_proveidos is not None:
            archivos = _archivos_desde_navegador(archivos_proveidos, origen)
        else:
            archivos = indexar_archivos(carpeta_temp or origen)
        resultados, huerfanos, avisos_emp = emparejar(recursos, archivos)
        advertencias = advertencias + avisos_emp

        extensiones, total_archivos = contar_extensiones(archivos)
        archivos_detalle = detalles_archivos(archivos)

        reporte = generar_reporte(resultados, huerfanos, advertencias,
                                  matriz, origen_descripcion, carpeta_temp,
                                  extensiones, total_archivos, archivos_detalle,
                                  syllabus=res_syllabus)

        destino_md = destino_json = None
        if salida is not None:
            os.makedirs(salida, exist_ok=True)
            # Milisegundos en el nombre: dos auditorías en el mismo segundo no se pisan.
            ahora = datetime.now()
            marca = ahora.strftime("%Y%m%d_%H%M%S_") + f"{ahora.microsecond // 1000:03d}"
            destino_md = os.path.join(salida, f"auditoria_{marca}.md")
            destino_json = os.path.join(salida, f"auditoria_{marca}.json")
            with open(destino_md, "w", encoding="utf-8") as fh:
                fh.write(reporte)
            with open(destino_json, "w", encoding="utf-8") as fh:
                json.dump({"resultados": resultados,
                           "huerfanos": [a["rel"] for a in huerfanos],
                           "advertencias": advertencias,
                           "extensiones": extensiones,
                           "total_archivos": total_archivos,
                           "archivos_detalle": archivos_detalle,
                           "syllabus": res_syllabus},
                          fh, ensure_ascii=False, indent=2)

        conteo = {"ok": 0, "alerta": 0, "faltante": 0, "fuera-de-alcance": 0}
        for r in resultados:
            conteo[r["estado"]] = conteo.get(r["estado"], 0) + 1

        return {
            "ok": True,
            "conteo": conteo,
            "total_auditables": (conteo["ok"] + conteo["alerta"] +
                                 conteo["faltante"]),
            "resultados": resultados,
            "huerfanos": [a["rel"] for a in huerfanos],
            "advertencias": advertencias,
            "extensiones": extensiones,
            "total_archivos": total_archivos,
            "archivos_detalle": archivos_detalle,
            "syllabus": res_syllabus,
            "reporte_md": os.path.abspath(destino_md) if destino_md else None,
            "reporte_json": os.path.abspath(destino_json) if destino_json else None,
            "salida": os.path.abspath(salida) if salida is not None else None,
        }
    finally:
        if carpeta_temp and os.path.isdir(carpeta_temp):
            shutil.rmtree(carpeta_temp, ignore_errors=True)


# ---------------------------------------------------------------------------
# Punto de entrada (línea de comandos)
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Audita el cruce entre la matriz de un curso y sus archivos.")
    parser.add_argument("origen", help="Carpeta o archivo .zip con los recursos")
    parser.add_argument("--matriz", required=True, help="Ruta a la matriz .csv")
    parser.add_argument("--salida", default="resultados", help="Carpeta de salida (por defecto: resultados)")
    parser.add_argument("--syllabus", default=None,
                        help="Ruta al syllabus del curso (.docx, .pdf o .txt): cruce opcional con la matriz")
    args = parser.parse_args()

    origen = os.path.expanduser(args.origen)
    matriz = os.path.expanduser(args.matriz)
    salida = os.path.expanduser(args.salida)
    syllabus = os.path.expanduser(args.syllabus) if args.syllabus else None

    if not os.path.exists(matriz):
        print(f"[ERROR] No existe la matriz: {matriz}", file=sys.stderr)
        return 1
    if not os.path.exists(origen):
        print(f"[ERROR] No existe el origen de recursos: {origen}", file=sys.stderr)
        return 1
    if syllabus and not os.path.exists(syllabus):
        print(f"[ERROR] No existe el syllabus: {syllabus}", file=sys.stderr)
        return 1

    res = ejecutar_auditoria(origen, matriz, salida, syllabus=syllabus,
                             syllabus_nombre=syllabus or "")
    if not res.get("ok"):
        print(f"[ERROR] {res.get('error')}", file=sys.stderr)
        for a in res.get("advertencias", []):
            print(f"  - {a}", file=sys.stderr)
        return 1

    c = res["conteo"]
    print("")
    print("=== RESULTADO DE LA AUDITORÍA ===")
    print(f"  Recursos auditables : {res['total_auditables']}")
    print(f"  OK                  : {c['ok']}")
    print(f"  ALERTA              : {c['alerta']}")
    print(f"  FALTANTE            : {c['faltante']}")
    print(f"  Huérfanos           : {len(res['huerfanos'])}")
    sy = res.get("syllabus")
    if sy:
        if sy.get("error"):
            print(f"  Syllabus            : ❌ no se pudo leer ({sy['error']})")
        elif sy.get("ok"):
            print("  Syllabus            : ✅ consistente con la matriz")
        else:
            print(f"  Syllabus            : ⚠️ {sy.get('avisos', 0)} aviso(s)")
    print("")
    print(f"  Reporte   : {res['reporte_md']}")
    print(f"  Datos JSON: {res['reporte_json']}")
    print("  No se modificó ningún archivo original.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
