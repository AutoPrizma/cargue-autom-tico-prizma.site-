"""Pruebas de la validacion profunda de archivos de la auditoria de curso.

Un PDF sano trae cabecera, hojas y texto/imagenes por dentro (se inspecciona
con zlib, sin librerias externas); un paquete H5P sano trae h5p.json,
content/content.json legible y bibliotecas. El veredicto por actividad
compara el titulo que se ve al abrir el recurso con el nombre del curso.
"""

import json
import os
import tempfile
import zipfile
import zlib

from auto_prizma.automation.content_checks import (
    ESTADO_OK,
    ESTADO_REVISAR,
    ESTADO_SIN_RECURSO,
    evaluar_recurso_auditoria,
    inspeccionar_h5p_archivo,
    inspeccionar_pdf_bytes,
    titulo_coincide,
)


def _pdf_bytes(hojas=1, con_texto=True, comprimido=True):
    """PDF minimo sintetico: cabecera, hojas y un stream de contenido."""
    if con_texto:
        stream = b"BT /F1 12 Tf 72 720 Td (Titulo de la portada) Tj ET"
    else:
        stream = b""
    if comprimido:
        stream = zlib.compress(stream)
    partes = [b"%PDF-1.4\n"]
    for numero in range(1, hojas + 1):
        partes.append(
            ("1 0 obj\n<< /Type /Page /Parent 0 0 R /Contents 2 0 R >>\nendobj\n").encode()
        )
    partes.append(
        b"2 0 obj\n<< /Length " + str(len(stream)).encode() + b" >>\nstream\n"
        + stream + b"\nendstream\nendobj\n"
    )
    return b"".join(partes)


def _h5p_bytes(tmp_path, titulo="Mi recurso", con_content=True, con_libraries=True, content_titulo=None):
    ruta = tmp_path / "recurso.h5p"
    with zipfile.ZipFile(ruta, "w") as paquete:
        paquete.writestr("h5p.json", json.dumps({"title": titulo, "mainLibrary": "H5P.Book"}))
        if con_content:
            paquete.writestr(
                "content/content.json",
                json.dumps({
                    "title": content_titulo or titulo,
                    "chapters": [{"metadata": {"title": "Capítulo 1"}}]},
                ),
            )
        if con_libraries:
            paquete.writestr("libraries/H5P.Book-1.0/library.json", "{}")
    return str(ruta)


def test_pdf_valido_con_texto_comprimido():
    inspeccion = inspeccionar_pdf_bytes(_pdf_bytes(hojas=2))

    assert inspeccion["ok"] is True
    assert inspeccion["paginas"] == 2
    assert inspeccion["con_contenido"] is True
    assert "contenido visible" in inspeccion["detalle"]


def test_pdf_sin_texto_como_si_estuviera_en_blanco():
    inspeccion = inspeccionar_pdf_bytes(_pdf_bytes(con_texto=False, comprimido=False))

    assert inspeccion["ok"] is True
    assert inspeccion["con_contenido"] is False
    assert "en blanco" in inspeccion["detalle"]


def test_pdf_con_texto_sin_comprimir_tambien_cuenta():
    inspeccion = inspeccionar_pdf_bytes(_pdf_bytes(con_texto=True, comprimido=False))

    assert inspeccion["ok"] is True
    assert inspeccion["con_contenido"] is True


def test_pdf_falso_no_pasa_por_cabecera():
    inspeccion = inspeccionar_pdf_bytes(b"esto no es un pdf, es texto plano")

    assert inspeccion["ok"] is False
    assert inspeccion["detalle"].startswith("No es un PDF")


def test_pdf_vacio_no_explota():
    inspeccion = inspeccionar_pdf_bytes(b"")

    assert inspeccion["ok"] is False


def test_h5p_sano_trae_titulo_y_bibliotecas(tmp_path):
    ruta = _h5p_bytes(tmp_path, titulo="Portada del recurso")

    inspeccion = inspeccionar_h5p_archivo(ruta)

    assert inspeccion["ok"] is True
    assert inspeccion["titulo_paquete"] == "Portada del recurso"
    assert "Capítulo 1" in inspeccion["titulos_visibles"]
    assert inspeccion["bibliotecas"] == 1


def test_h5p_sin_content_json_es_invalido(tmp_path):
    ruta = _h5p_bytes(tmp_path, con_content=False)

    inspeccion = inspeccionar_h5p_archivo(ruta)

    assert inspeccion["ok"] is False
    assert "content/content.json" in inspeccion["detalle"]


def test_h5p_con_content_danado_es_invalido(tmp_path):
    ruta = tmp_path / "danado.h5p"
    with zipfile.ZipFile(ruta, "w") as paquete:
        paquete.writestr("h5p.json", json.dumps({"title": "x"}))
        paquete.writestr("content/content.json", "{esto no es json")
        paquete.writestr("libraries/H5P.X-1.0/library.json", "{}")

    inspeccion = inspeccionar_h5p_archivo(str(ruta))

    assert inspeccion["ok"] is False
    assert "dañado" in inspeccion["detalle"]


def test_h5p_sin_bibliotecas_no_puede_renderizar(tmp_path):
    ruta = _h5p_bytes(tmp_path, con_libraries=False)

    inspeccion = inspeccionar_h5p_archivo(ruta)

    assert inspeccion["ok"] is False
    assert "bibliotecas" in inspeccion["detalle"]


def test_h5p_que_no_es_zip():
    descriptor, ruta = tempfile.mkstemp(suffix=".h5p")
    with os.fdopen(descriptor, "wb") as fh:
        fh.write(b"no soy un zip")
    try:
        inspeccion = inspeccionar_h5p_archivo(ruta)
    finally:
        os.remove(ruta)

    assert inspeccion["ok"] is False
    assert "ZIP" in inspeccion["detalle"]


def test_titulo_coincide_sin_acentos_ni_mayusculas():
    assert titulo_coincide("Gestión Financiera", "gestion financiera") is True
    assert titulo_coincide("Otra cosa", "gestion financiera") is False
    assert titulo_coincide("", "algo") is False


def test_evaluar_sin_archivo_adjunto():
    veredicto = evaluar_recurso_auditoria("Lectura guía", "", None)

    assert veredicto["estado"] == ESTADO_SIN_RECURSO
    assert "campo Recurso" in veredicto["detalle"]


def test_evaluar_pdf_bueno_es_ok():
    veredicto = evaluar_recurso_auditoria(
        "Lectura guía", "Lectura guia.pdf", inspeccionar_pdf_bytes(_pdf_bytes())
    )

    assert veredicto["estado"] == ESTADO_OK
    assert veredicto["tipo"] == "PDF"
    assert veredicto["coincide"] is None


def test_evaluar_pdf_en_blanco_pide_revision():
    veredicto = evaluar_recurso_auditoria(
        "Lectura guía", "Lectura guia.pdf",
        inspeccionar_pdf_bytes(_pdf_bytes(con_texto=False, comprimido=False)),
    )

    assert veredicto["estado"] == ESTADO_REVISAR
    assert "en blanco" in veredicto["detalle"]


def test_evaluar_h5p_con_titulo_igual_al_curso():
    inspeccion = {
        "ok": True,
        "titulo_paquete": "Lectura guía",
        "titulos_portada": ["Lectura guía"],
        "titulos_visibles": ["Capítulo 1"],
        "bibliotecas": 2,
        "detalle": "Paquete H5P válido con sus bibliotecas.",
    }

    veredicto = evaluar_recurso_auditoria("Lectura guía", "Lectura guia.h5p", inspeccion)

    assert veredicto["estado"] == ESTADO_OK
    assert veredicto["tipo"] == "H5P"
    assert veredicto["coincide"] is True


def test_evaluar_h5p_con_titulo_distinto_pide_revision():
    inspeccion = {
        "ok": True,
        "titulo_paquete": "Título de relleno",
        "titulos_portada": ["Título de relleno"],
        "titulos_visibles": ["Capítulo 1"],
        "bibliotecas": 2,
        "detalle": "Paquete H5P válido con sus bibliotecas.",
    }

    veredicto = evaluar_recurso_auditoria("Lectura guía", "Lectura guia.h5p", inspeccion)

    assert veredicto["estado"] == ESTADO_REVISAR
    assert veredicto["coincide"] is False
    assert "REVISAR" in veredicto["detalle"]


def test_h5p_metadato_y_titulo_de_capitulo_no_sustituyen_la_portada():
    veredicto = evaluar_recurso_auditoria(
        "Lectura guía",
        "Lectura guia.h5p",
        {
            "ok": True,
            "titulo_paquete": "Lectura guía",
            "titulos_portada": [],
            "titulos_visibles": ["Lectura guía"],
            "bibliotecas": 1,
        },
    )

    assert veredicto["coincide"] is False
    assert veredicto["titulo_interno"] == ""
    assert "sin título verificable" in veredicto["detalle"]


def test_evaluar_tipo_de_archivo_no_auditable():
    veredicto = evaluar_recurso_auditoria("Lectura guía", "Lectura guia.docx", None)

    assert veredicto["estado"] == ESTADO_REVISAR
    assert veredicto["tipo"] == "DOCX"
