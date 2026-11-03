"""Pagina de inicio y analisis de la matriz y los recursos antes del cargue.
"""

from fastapi import (
    UploadFile,
    File,
    Form,
)
from fastapi.responses import (
    HTMLResponse,
    RedirectResponse,
)
import zipfile

from auto_prizma.core.application import app
from auto_prizma.core.clock import _ahora_colombia_iso
from auto_prizma.core.config import FORMATOS_RECURSO_INTERACTIVO, TEMP_DIR
from auto_prizma.services.auth import _usuario_actual
from auto_prizma.services.course_state import preseleccion_faltantes
from auto_prizma.services.upload_jobs import create_analyzed_job
from auto_prizma.services.h5p_preview import preview_h5p_titles
from auto_prizma.services.matrix_analysis import (
    _normalizar_contenido_matriz_archivo,
    _parsear_datos_academicos,
    analizar_excel,
    analizar_zip,
)
from auto_prizma.web.views import generar_html


# ============================================================
# INICIO
# ============================================================

@app.get("/prizma", response_class=HTMLResponse)
def inicio_prizma():
    return generar_html()


# ============================================================
# ANALIZAR
# ============================================================

@app.post(
    "/analizar",
    response_class=HTMLResponse,
)
async def analizar(
    recursos: UploadFile | None = File(default=None),
    matriz_archivo: UploadFile | None = File(default=None),
    ovi: str | None = Form(default=None),
    ova: str | None = Form(default=None),
    retos: str | None = Form(default=None),
    test_evaluativo: str | None = Form(default=None),
    test_archivo_docx: UploadFile | None = File(default=None),
    formato_recurso: str = Form(default="H5P"),
    syllabus_archivo: UploadFile | None = File(default=None),
    linea_academica: str = Form(default=""),
    nivel_pensum: str = Form(default=""),
):

    try:
        procesar_ovi = ovi is not None
        procesar_ova = ova is not None
        procesar_retos = retos is not None
        procesar_test = test_evaluativo is not None
        procesar_recursos = procesar_ovi or procesar_ova or procesar_retos

        if not procesar_recursos and not procesar_test:
            return generar_html(
                error="Selecciona al menos una categoría: OVI, OVA, Retos Evaluativos o Test Evaluativo."
            )

        # ====================================================
        # PREPARACIÓN DE LA ASIGNATURA (syllabus + línea académica)
        # ====================================================
        # Todo es opcional; si no hay línea académica ni nivel, la
        # preparación se omite y el cargue continúa normal.
        linea_academica = str(linea_academica or "").strip()
        nivel_pensum = str(nivel_pensum or "").strip()

        if bool(linea_academica) != bool(nivel_pensum):
            return generar_html(
                error=(
                    "Para preparar la asignatura completa «Línea académica» y "
                    "«Nivel de pensum», o deja ambos vacíos."
                )
            )

        if linea_academica and _parsear_datos_academicos(linea_academica) is None:
            return generar_html(
                error=(
                    "La «Línea académica» debe ser: código de programa, código "
                    "de pensum, código de asignatura y nombre de la asignatura "
                    "(p. ej. «V1130 11301 30S01 COMPETENCIAS MATEMÁTICAS I»)."
                )
            )

        contenido_syllabus = None
        nombre_syllabus = ""
        if syllabus_archivo is not None and str(syllabus_archivo.filename or "").strip():
            if not procesar_recursos:
                return generar_html(
                    error=(
                        "El syllabus se adjunta junto con el cargue de recursos "
                        "(OVI, OVA o Retos); con solo Test Evaluativo no se "
                        "prepara la asignatura."
                    )
                )
            if not linea_academica:
                return generar_html(
                    error=(
                        "El syllabus se carga en la ficha de la asignatura: "
                        "indica también la «Línea académica» y el «Nivel de "
                        "pensum», o quita el syllabus."
                    )
                )
            nombre_syllabus = str(syllabus_archivo.filename or "").strip()
            if not nombre_syllabus.lower().endswith(".pdf"):
                return generar_html(error="El syllabus debe ser un archivo PDF.")
            contenido_syllabus = await syllabus_archivo.read()
            if not contenido_syllabus:
                return generar_html(error="El archivo de syllabus está vacío.")

        test_job_id = None
        nom_test = ""
        document_test = None
        if procesar_test:
            from auto_prizma.evaluative_tests.routes import _extraer_bytes_docx_request
            from auto_prizma.evaluative_tests.state import register_test_job
            from auto_prizma.evaluative_tests.parser import parse_docx_bytes

            content_test, nom_test, err_test = await _extraer_bytes_docx_request(
                test_archivo_docx
            )
            if err_test or not content_test:
                return generar_html(error=err_test or "El documento de test está vacío.")

            try:
                document_test = parse_docx_bytes(content_test, source_name=nom_test)
            except Exception as exc_p:
                return generar_html(error=f"Error al procesar documento de test: {exc_p}")

            if procesar_recursos:
                from auto_prizma.evaluative_tests.models import Severity
                from auto_prizma.evaluative_tests.validation import validate_document

                errores_test = [
                    issue.message
                    for issue in validate_document(document_test)
                    if issue.severity == Severity.ERROR
                ]
                if errores_test:
                    detalle = " · ".join(errores_test)
                    return generar_html(
                        error=(
                            "No se inició el cargue combinado porque el Test Evaluativo "
                            "tiene errores. Corrige el documento o revísalo desde Test: "
                            + detalle
                        )
                    )

            test_job_id = register_test_job(
                _usuario_actual(),
                document_test,
                _ahora_colombia_iso(),
            )

            if not procesar_recursos:
                return RedirectResponse(f"/tests/{test_job_id}/revision", status_code=303)

        formato_recurso = str(formato_recurso or "").strip().upper() or "H5P"
        if formato_recurso not in FORMATOS_RECURSO_INTERACTIVO:
            return generar_html(
                error="Formato de recurso no válido: elige H5P o HTML."
            )

        nombre_archivo_matriz = str(getattr(matriz_archivo, "filename", "") or "").strip()
        if not nombre_archivo_matriz or not nombre_archivo_matriz.lower().endswith((".xlsx", ".csv")):
            return generar_html(error="Selecciona un archivo XLSX o CSV.")

        if not recursos or not str(recursos.filename or "").lower().endswith(".zip"):
            return generar_html(
                error="Los recursos deben estar en un archivo .zip"
            )

        contenido_original = await matriz_archivo.read()
        contenido_excel, nombre_matriz = _normalizar_contenido_matriz_archivo(
            nombre_archivo_matriz,
            contenido_original,
        )
        contenido_zip = await recursos.read()

        hojas = analizar_excel(
            contenido_excel,
            procesar_ovi,
            procesar_ova,
            procesar_retos,
            formato_recurso=formato_recurso,
        )

        if not hojas:
            return generar_html(
                error="No encontré una matriz PRIZMA válida."
            )

        try:
            zip_info = analizar_zip(contenido_zip, formato_recurso=formato_recurso)
        except zipfile.BadZipFile:
            return generar_html(error="El ZIP no es válido.")

        revision_h5p = None
        if formato_recurso == "H5P":
            revision_h5p = preview_h5p_titles(contenido_zip, hojas, TEMP_DIR)

        # ====================================================
        # CREAR TRABAJO (guarda los archivos seleccionados y lo registra)
        # ====================================================

        test_info = None
        if procesar_test and test_job_id and document_test:
            test_info = {
                "test_job_id": test_job_id,
                "nombre_documento": nom_test,
                "cantidad_tests": len(document_test.tests),
                "cantidad_preguntas": sum(len(sec.questions) for t in document_test.tests for sec in t.sections),
            }

        trabajo_id, resultado = create_analyzed_job(
            contenido_excel,
            contenido_zip,
            hojas,
            zip_info,
            nombre_matriz,
            procesar_ovi,
            procesar_ova,
            procesar_retos,
            _usuario_actual(),
            test_job_id=test_job_id,
            test_info=test_info,
            formato_recurso=formato_recurso,
            contenido_syllabus=contenido_syllabus,
            nombre_syllabus=nombre_syllabus,
            linea_academica=linea_academica,
            nivel_pensum=nivel_pensum,
        )
        resultado_revision = dict(resultado)
        if revision_h5p is not None:
            resultado_revision["revision_h5p"] = revision_h5p

        # ====================================================
        # PRE-SELECCION DE FALTANTES (reintento sin volver a elegir)
        # ====================================================
        # Si este curso ya tuvo cargues con actividades pendientes, se marcan
        # solo esas. Si la matriz no coincide con lo registrado, no se marca
        # nada y se conserva el comportamiento normal (todo marcado).
        faltantes, cursos_faltantes = preseleccion_faltantes(hojas, _usuario_actual())
        aviso_preseleccion = None
        if faltantes:
            cursos_txt = ", ".join(cursos_faltantes) or "este curso"
            aviso_preseleccion = (
                f"Quedaron {len(faltantes)} actividad(es) pendientes de un cargue anterior "
                f"de {cursos_txt}. Se marcaron solo esas para no repetir lo que ya está "
                "en PRIZMA; las demás quedaron sin marca. Si quieres cargar todas, usa "
                "«Seleccionar todo»."
            )

        return generar_html(
            resultado=resultado_revision,
            trabajo_id=trabajo_id,
            seleccion_actual=faltantes or None,
            aviso=aviso_preseleccion,
        )

    except Exception as e:
        return generar_html(error=str(e))
