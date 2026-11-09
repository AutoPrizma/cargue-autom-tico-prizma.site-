"""Lectura de matrices CSV/Excel y analisis de la matriz y del ZIP.
"""

from io import BytesIO
from openpyxl import (
    load_workbook,
    Workbook,
)
from auto_prizma.automation.prizma.engine import (
    determinar_tipo_archivo,
    normalizar_categoria,
    normalizar_texto,
)
import zipfile
import csv
import os
import re
from urllib.parse import unquote, urlparse

from auto_prizma.core.config import EXTENSIONES_HTML


def detectar_videos_a_camara(contenido_excel, contenido_zip):
    """Asocia cada recurso Video a cámara con el tema padre y el .webm del ZIP.

    El título del tema se hereda de la fila de subtema (código en C, título en
    D); el archivo del ZIP se relaciona por el nombre del recurso de la fila
    marcada como Video a cámara, nunca por el título del tema ni por orden.
    """
    try:
        libro = load_workbook(BytesIO(contenido_excel), data_only=True)
        with zipfile.ZipFile(BytesIO(contenido_zip), "r") as archivo_zip:
            miembros_webm = [
                nombre for nombre in archivo_zip.namelist()
                if not nombre.endswith("/")
                and os.path.splitext(nombre)[1].lower() == ".webm"
            ]
    except (ValueError, zipfile.BadZipFile, OSError):
        return []

    def clave_tema(valor):
        texto = str(valor or "").strip()
        if texto.endswith("."):
            texto = texto[:-1].rstrip()
        return normalizar_texto(texto)

    def clave_archivo(valor):
        texto = str(valor or "").strip().replace("\\", "/")
        if not texto:
            return ""
        url = urlparse(texto)
        texto = unquote(url.path if url.scheme or url.netloc else texto)
        return os.path.basename(texto).casefold()

    miembros_por_nombre = {}
    miembros_por_clave = {}
    for miembro in miembros_webm:
        base = os.path.basename(miembro)
        miembros_por_nombre.setdefault(base.casefold(), []).append(miembro)
        clave_base = clave_tema(os.path.splitext(base)[0])
        miembros_por_clave.setdefault(clave_base, []).append(miembro)
        if clave_base.startswith("video "):
            miembros_por_clave.setdefault(clave_base[len("video "):].strip(), []).append(miembro)

    filas = []
    for nombre_hoja in libro.sheetnames:
        hoja = libro[nombre_hoja]
        cabecera = None
        for fila in range(1, min(hoja.max_row, 30) + 1):
            if normalizar_texto(hoja.cell(fila, 1).value) == normalizar_texto(
                "Semana correspondiente"
            ):
                cabecera = fila
                break
        if cabecera is None:
            continue

        semana_actual = ""
        tema_actual = ""
        for numero_fila in range(cabecera + 1, hoja.max_row + 1):
            semana_celda = hoja.cell(numero_fila, 1).value
            if semana_celda:
                semana_actual = str(semana_celda).strip()
            titulo = str(hoja.cell(numero_fila, 4).value or "").strip()
            codigo_tema = str(hoja.cell(numero_fila, 3).value or "").strip()
            categoria = str(hoja.cell(numero_fila, 5).value or "").strip()
            tipo = normalizar_texto(hoja.cell(numero_fila, 6).value)
            referencia = str(hoja.cell(numero_fila, 7).value or "").strip()

            if (
                titulo
                and re.fullmatch(r"\d+(?:\.\d+)?", codigo_tema)
                and not categoria
                and not tipo
            ):
                tema_actual = titulo
                continue

            if not titulo or tipo != "video a camara":
                continue
            filas.append({
                "hoja": nombre_hoja,
                "fila": numero_fila,
                "semana": semana_actual,
                "unidad": str(hoja.cell(numero_fila, 2).value or "").strip(),
                "nombre": tema_actual,
                "nombre_recurso": titulo,
                "referencia": referencia,
                "miembro_zip": "",
            })

    for item in filas:
        referencia = item.get("referencia") or ""
        nombre_archivo = clave_archivo(referencia)
        coincidencias = (
            miembros_por_nombre.get(nombre_archivo, [])
            if nombre_archivo.endswith(".webm")
            else []
        )

        # En algunas matrices Enlace apunta al archivo fuente externo, pero el
        # ZIP renombra el video con el nombre del recurso. Usar solo esa
        # coincidencia exacta; jamás elegir por orden ni por nombre del tema.
        if not coincidencias:
            base_recurso = os.path.splitext(item.get("nombre_recurso") or "")[0].strip()
            clave_recurso = clave_tema(base_recurso)
            if clave_recurso.startswith("video "):
                clave_recurso = clave_recurso[len("video "):].strip()
            coincidencias = miembros_por_clave.get(clave_recurso, [])
        if len(coincidencias) == 1:
            item["miembro_zip"] = coincidencias[0]

    return filas


# ============================================================
# CONVERTIR CSV A XLSX INTERNO
# ============================================================

def _parsear_datos_academicos(texto: str) -> dict | None:
    """Parsea el campo único de datos académicos:
    'codigo_programa - codigo_pensum - codigo_asignatura - nombre_asignatura'
    Soporta separadores por espacios, guiones o combinaciones.
    Los primeros 3 tokens corresponden a los códigos y el resto al nombre de la asignatura.
    """
    texto = (texto or "").strip()
    if not texto:
        return None

    # Primero intentar separar por guiones explícitos (' - ' o '-')
    partes_guion = [p.strip() for p in re.split(r"\s*[-–—]\s*", texto) if p.strip()]
    if len(partes_guion) >= 4:
        return {
            "programa": partes_guion[0],
            "pensum": partes_guion[1],
            "codigo_asignatura": partes_guion[2],
            "asignatura": " - ".join(partes_guion[3:]),
        }

    # Separación por espacios
    tokens = texto.split()
    if len(tokens) >= 4:
        return {
            "programa": tokens[0],
            "pensum": tokens[1],
            "codigo_asignatura": tokens[2],
            "asignatura": " ".join(tokens[3:]),
        }

    return None



def _extension_matriz_archivo(nombre_archivo):
    extension = os.path.splitext(str(nombre_archivo or ""))[1].lower()
    if extension not in {".xlsx", ".csv"}:
        raise ValueError("La matriz local debe ser un archivo .xlsx o .csv.")
    return extension


def convertir_csv_a_xlsx(
    contenido_csv,
):

    texto = None

    for codificacion in [
        "utf-8-sig",
        "utf-8",
        "cp1252",
        "latin-1",
    ]:

        try:

            texto = contenido_csv.decode(
                codificacion
            )

            break

        except UnicodeDecodeError:
            continue

    if texto is None:
        raise ValueError(
            "No fue posible leer el archivo CSV."
        )

    muestra = texto[:10000]

    try:

        dialecto = csv.Sniffer().sniff(
            muestra,
            delimiters=",;\t|",
        )

        delimitador = dialecto.delimiter

    except csv.Error:

        delimitador = ","

    filas = list(
        csv.reader(
            texto.splitlines(),
            delimiter=delimitador,
        )
    )

    if not filas:
        raise ValueError(
            "El archivo CSV está vacío."
        )

    libro = Workbook()

    hoja = libro.active
    hoja.title = "Matriz"

    for numero_fila, fila in enumerate(
        filas,
        start=1,
    ):

        for numero_columna, valor in enumerate(
            fila,
            start=1,
        ):

            hoja.cell(
                row=numero_fila,
                column=numero_columna,
                value=valor,
            )

    salida = BytesIO()
    libro.save(salida)

    return salida.getvalue()


def _normalizar_contenido_matriz_archivo(nombre_archivo, contenido):
    nombre_visible = os.path.basename(str(nombre_archivo or "").strip())
    extension = _extension_matriz_archivo(nombre_visible)
    if not contenido:
        raise ValueError("La matriz local está vacía.")

    if extension == ".csv":
        contenido_xlsx = convertir_csv_a_xlsx(contenido)
    else:
        contenido_xlsx = bytes(contenido)
        try:
            libro_prueba = load_workbook(
                BytesIO(contenido_xlsx),
                read_only=True,
                data_only=False,
            )
            libro_prueba.close()
        except Exception as error:
            raise ValueError("El archivo XLSX no es válido.") from error

    return contenido_xlsx, nombre_visible


# ============================================================
# ANALIZAR MATRIZ
# ============================================================

def analizar_excel(
    contenido_excel,
    procesar_ovi=True,
    procesar_ova=True,
    procesar_retos=True,
    formato_recurso="H5P",
):
    # formato_recurso: "H5P" o "HTML". En modo HTML las actividades de
    # recurso interactivo (H5P) se muestran y cuentan como HTML.
    modo_html = str(formato_recurso or "").strip().upper() == "HTML"

    libro = load_workbook(
        BytesIO(contenido_excel),
        data_only=True,
    )

    hojas_validas = []

    for nombre_hoja in libro.sheetnames:

        hoja = libro[
            nombre_hoja
        ]

        fila_cabecera = None

        for fila in range(
            1,
            min(
                hoja.max_row,
                30,
            ) + 1,
        ):

            valor = hoja.cell(
                row=fila,
                column=1,
            ).value

            if normalizar_texto(
                valor
            ) == normalizar_texto(
                "Semana correspondiente"
            ):

                fila_cabecera = fila
                break

        if fila_cabecera is None:
            continue

        programa = hoja.cell(
            row=1,
            column=1,
        ).value

        curso = hoja.cell(
            row=2,
            column=1,
        ).value

        actividades = []

        cantidad_ovi = 0
        cantidad_ova = 0
        cantidad_retos = 0
        cantidad_h5p = 0
        cantidad_pdf = 0
        cantidad_html = 0

        for fila in range(
            fila_cabecera + 1,
            hoja.max_row + 1,
        ):

            semana = hoja.cell(
                row=fila,
                column=1,
            ).value

            unidad = hoja.cell(
                row=fila,
                column=2,
            ).value

            nombre = hoja.cell(
                row=fila,
                column=4,
            ).value

            categoria = hoja.cell(
                row=fila,
                column=5,
            ).value

            tipo_recurso = hoja.cell(
                row=fila,
                column=6,
            ).value

            enlace = hoja.cell(
                row=fila,
                column=7,
            ).value

            if not nombre:
                continue

            if not categoria:
                continue

            categoria_prizma = normalizar_categoria(
                categoria
            )

            if categoria_prizma not in [
                "OVI",
                "OVA",
                "CHALLENGE",
            ]:
                continue

            if (
                categoria_prizma == "OVI"
                and not procesar_ovi
            ):
                continue

            if (
                categoria_prizma == "OVA"
                and not procesar_ova
            ):
                continue

            if (
                categoria_prizma == "CHALLENGE"
                and not procesar_retos
            ):
                continue

            tipo_archivo = determinar_tipo_archivo(
                categoria,
                tipo_recurso,
                enlace,
            )

            if tipo_archivo is None:
                continue

            if modo_html and tipo_archivo == "H5P":
                tipo_archivo = "HTML"

            if categoria_prizma == "OVI":
                cantidad_ovi += 1

            if categoria_prizma == "OVA":
                cantidad_ova += 1

            if categoria_prizma == "CHALLENGE":
                cantidad_retos += 1

            if tipo_archivo == "H5P":
                cantidad_h5p += 1

            if tipo_archivo == "PDF":
                cantidad_pdf += 1

            if tipo_archivo == "HTML":
                cantidad_html += 1

            actividades.append(
                {
                    "fila": fila,

                    "semana": (
                        str(semana).strip()
                        if semana
                        else ""
                    ),

                    "unidad": (
                        str(unidad).strip()
                        if unidad
                        else ""
                    ),

                    "nombre": str(
                        nombre
                    ).strip(),

                    "categoria":
                        categoria_prizma,

                    "tipo":
                        tipo_archivo,

                    "tipo_recurso": (
                        str(tipo_recurso).strip()
                        if tipo_recurso
                        else tipo_archivo
                    ),
                }
            )

        hojas_validas.append(
            {
                "hoja":
                    nombre_hoja,

                "programa": (
                    str(programa).strip()
                    if programa
                    else ""
                ),

                "curso": (
                    str(curso).strip()
                    if curso
                    else nombre_hoja
                ),

                "actividades":
                    actividades,

                "ovi":
                    cantidad_ovi,

                "ova":
                    cantidad_ova,

                "retos":
                    cantidad_retos,

                "h5p":
                    cantidad_h5p,

                "pdf":
                    cantidad_pdf,

                "html":
                    cantidad_html,
            }
        )

    return hojas_validas


# ============================================================
# ANALIZAR ZIP
# ============================================================

def analizar_zip(
    contenido_zip,
    formato_recurso="H5P",
):
    # El total cuenta los archivos que se usaran en el cargue: H5P o HTML
    # (segun el formato elegido) mas los PDF.
    modo_html = str(formato_recurso or "").strip().upper() == "HTML"

    cantidad_h5p = 0
    cantidad_pdf = 0
    cantidad_html = 0

    with zipfile.ZipFile(
        BytesIO(contenido_zip),
        "r",
    ) as archivo_zip:

        for miembro in archivo_zip.namelist():

            if miembro.endswith("/"):
                continue

            nombre = os.path.basename(
                miembro
            )

            extension = os.path.splitext(
                nombre
            )[1].lower()

            if extension == ".h5p":

                cantidad_h5p += 1

            elif extension == ".pdf":

                cantidad_pdf += 1

            elif extension in EXTENSIONES_HTML:

                cantidad_html += 1

    return {
        "h5p":
            cantidad_h5p,

        "pdf":
            cantidad_pdf,

        "html":
            cantidad_html,

        "total":
            (cantidad_html if modo_html else cantidad_h5p)
            + cantidad_pdf,
    }
