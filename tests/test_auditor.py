"""Pruebas del auditor de recursos integrado (curso-checker).

La logica viene copiada tal cual de ~/Documents/curso-checker a
auto_prizma/auditor/procesar.py. Estas pruebas fijan las reglas
documentadas en su README (prefijos, truncados, copias "(1)", similitud,
titulos internos H5P) para que no se rompan al mantenerla, y cubren la
pagina web /auditor.
"""

import io
import json
import os
import zipfile

from fastapi.testclient import TestClient

from main import app
from auto_prizma.auditor import procesar
from auto_prizma.core.config import DATA_DIR
from auto_prizma.services.auth import _firmar_sesion


def _cliente():
    client = TestClient(app)
    client.cookies.set("ap_sesion", _firmar_sesion("adminlocal"))
    return client


def _escribir(carpeta, archivos):
    for nombre, datos in archivos.items():
        ruta = os.path.join(carpeta, nombre)
        os.makedirs(os.path.dirname(ruta), exist_ok=True)
        with open(ruta, "wb") as fh:
            fh.write(datos)


def _h5p(titulo):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("h5p.json", json.dumps({"title": titulo}))
        z.writestr("content/content.json", json.dumps({"title": titulo}))
    return buf.getvalue()


def _resultados(csv_text, archivos, tmp_path):
    carpeta = tmp_path / "recursos"
    carpeta.mkdir()
    _escribir(str(carpeta), archivos)
    recursos, _adv = procesar.leer_matriz_texto(csv_text)
    lista, _huerfanos, _avisos = procesar.emparejar(
        recursos, procesar.indexar_archivos(str(carpeta))
    )
    return lista


def _de(lista, nombre):
    return next(r for r in lista if r["nombre"] == nombre)


ENCABEZADO = "Semana,Unidad,Nombre del recurso,Categoría,Tipo de recurso,Enlace\n"


# ============================================================
# LECTURA DE LA MATRIZ
# ============================================================

def test_matriz_detecta_columnas_por_nombre_y_arrarra_semana_unidad(tmp_path):
    csv_text = (
        "Nombre del recurso,Categoría,Tipo de recurso,Semana,Unidad\n"
        "Recurso guía,OVI,PDF,3,Unidad 1: Fundamentos\n"
        ",,,4,\n"
        "Segundo recurso,OVA,H5P,,\n"
    )
    recursos, advertencias = procesar.leer_matriz_texto(csv_text)

    assert advertencias == []
    assert len(recursos) == 2
    assert recursos[0]["nombre"] == "Recurso guía"
    assert recursos[1]["semana"] == "4"          # arrastrada
    assert recursos[1]["unidad"] == "Unidad 1: Fundamentos"  # arrastrada
    assert recursos[0]["ext_esperada"] == ".pdf"
    assert recursos[1]["ext_esperada"] == ".h5p"


def test_matriz_ignora_filas_sin_categoria_y_filas_titulo(tmp_path):
    csv_text = (
        ENCABEZADO
        + "3,Unidad 1,Unidad 1: Fundamentos,,,\n"          # fila-título
        + "3,Unidad 1,Nota interna,NOTA,,\n"               # sin OVI/OVA/CHALLENGE
        + "3,Unidad 1,Video de apertura,OVI,Video a cámara,\n"
    )
    recursos, _adv = procesar.leer_matriz_texto(csv_text)

    assert [r["nombre"] for r in recursos] == ["Video de apertura"]
    assert recursos[0]["fuera_de_alcance"] is False
    assert recursos[0]["ext_esperada"] == "video"


def test_quitar_prefijo_reconoce_prefijos_reales():
    assert procesar.clave("ID015-Tema_1-Mi recurso") == "mi recurso"
    assert procesar.clave("U1-T3-Mi recurso") == "mi recurso"
    assert procesar.clave("UUnidad 2-TTema 4-Mi recurso") == "mi recurso"
    assert procesar.clave("PDF - Mi recurso") == "mi recurso"
    assert procesar.clave("Tema 3: Mi recurso") == "mi recurso"


def test_matriz_sin_columna_nombre_da_advertencia():
    recursos, advertencias = procesar.leer_matriz_texto("a,b\n1,2\n")
    assert recursos == []
    assert any("Nombre del recurso" in a for a in advertencias)


# ============================================================
# EMPAREJAMIENTO (reglas del README)
# ============================================================

def test_nombre_exacto_es_ok(tmp_path):
    csv_text = ENCABEZADO + "1,,Recurso guía,OVI,PDF,\n"
    lista = _resultados(
        csv_text, {"Recurso guía.pdf": b"%PDF"}, tmp_path
    )
    r = _de(lista, "Recurso guía")
    assert r["estado"] == "ok"
    assert r["archivo"] == "Recurso guía.pdf"


def test_nombre_truncado_largo_calza_y_el_corto_no(tmp_path):
    csv_text = (
        ENCABEZADO
        + "1,,Secuencia para construir el problema de investigación,OVI,PDF,\n"
        + "1,,Anexo,OVI,PDF,\n"
    )
    lista = _resultados(
        csv_text,
        {
            "Secuencia para construir el problema de inv.pdf": b"x",
            "Zindce general.pdf": b"x",
        },
        tmp_path,
    )
    assert _de(lista, "Secuencia para construir el problema de investigación")[
        "estado"
    ] == "ok"
    assert _de(lista, "Anexo")["estado"] == "faltante"


def test_copia_con_sufijo_unica_cuenta_como_ok(tmp_path):
    csv_text = ENCABEZADO + "1,,Infografía de costos,OVI,H5P,\n"
    lista = _resultados(
        csv_text,
        {"Infografía de costos (1).h5p": _h5p("Infografía de costos")},
        tmp_path,
    )
    assert _de(lista, "Infografía de costos")["estado"] == "ok"


def test_extension_incorrecta_es_alerta(tmp_path):
    csv_text = ENCABEZADO + "1,,Presentación de resultados,OVI,PDF,\n"
    lista = _resultados(
        csv_text, {"Presentación de resultados.pptx": b"x"}, tmp_path
    )
    r = _de(lista, "Presentación de resultados")
    assert r["estado"] == "alerta"
    assert "extensión incorrecta" in r["detalle"]


def test_similitud_alta_empareja_como_ok(tmp_path):
    csv_text = (
        ENCABEZADO
        + "1,,Comparación de técnicas cualitativas y cuantitativas,OVI,PDF,\n"
    )
    lista = _resultados(
        csv_text,
        {
            "Comparacion de tecnicas cualitativas y cuantitavas.pdf": b"x",
        },
        tmp_path,
    )
    r = _de(lista, "Comparación de técnicas cualitativas y cuantitativas")
    assert r["estado"] == "ok"
    assert "coincide por similitud" in r["detalle"]


def test_sin_archivo_parecido_queda_faltante(tmp_path):
    csv_text = ENCABEZADO + "1,,Guía de lectura,OVI,PDF,\n"
    lista = _resultados(
        csv_text, {"Reporte de notas finales.pdf": b"x"}, tmp_path
    )
    r = _de(lista, "Guía de lectura")
    assert r["estado"] == "faltante"
    assert "no se encontró" in r["detalle"]


def test_prefijo_tecnico_del_nombre_del_archivo_se_ignora(tmp_path):
    csv_text = ENCABEZADO + "1,,Taller de escritura,OVI,PDF,\n"
    lista = _resultados(
        csv_text, {"ID004-Tema_Tema 4-Taller de escritura.pdf": b"x"}, tmp_path
    )
    assert _de(lista, "Taller de escritura")["estado"] == "ok"


# ============================================================
# TITULOS INTERNOS H5P
# ============================================================

def test_h5p_con_titulo_interno_correcto_es_ok(tmp_path):
    csv_text = ENCABEZADO + "1,,Taller de escritura,OVI,H5P,\n"
    lista = _resultados(
        csv_text, {"Taller de escritura.h5p": _h5p("Taller de escritura")},
        tmp_path,
    )
    r = _de(lista, "Taller de escritura")
    assert r["estado"] == "ok"
    assert "título interno" in r["detalle"]
    assert "Taller de escritura" in r["detalle"]


def test_h5p_coincidente_sin_titulo_de_portada_no_es_alerta(tmp_path):
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("h5p.json", json.dumps({"title": "Taller de escritura"}))
        z.writestr("content/content.json", json.dumps({"library": "H5P.InteractiveBook"}))
    csv_text = ENCABEZADO + "1,,Taller de escritura,OVI,H5P,\n"

    r = _de(_resultados(csv_text, {"Videos/Taller de escritura.h5p": buf.getvalue()}, tmp_path), "Taller de escritura")

    assert r["estado"] == "ok"
    assert 'título interno coincide ("Taller de escritura")' in r["detalle"]
    assert "portada" not in r["detalle"]
    assert "subcarpeta" in r["detalle"]


def test_h5p_con_titulo_interno_distinto_es_alerta(tmp_path):
    csv_text = ENCABEZADO + "1,,Taller de escritura,OVI,H5P,\n"
    lista = _resultados(
        csv_text, {"Taller de escritura.h5p": _h5p("relleno s")}, tmp_path
    )
    r = _de(lista, "Taller de escritura")
    assert r["estado"] == "alerta"
    assert "NO coincide" in r["detalle"]


def test_h5p_roto_es_alerta(tmp_path):
    csv_text = ENCABEZADO + "1,,Taller de escritura,OVI,H5P,\n"
    lista = _resultados(
        csv_text, {"Taller de escritura.h5p": b"esto no es un zip"}, tmp_path
    )
    assert _de(lista, "Taller de escritura")["estado"] == "alerta"


# ============================================================
# EJECUCION COMPLETA Y REPORTE
# ============================================================

def test_ejecutar_auditoria_completa_escribe_reportes(tmp_path):
    carpeta = tmp_path / "recursos"
    carpeta.mkdir()
    _escribir(str(carpeta), {"Recurso guía.pdf": b"%PDF"})
    csv_text = ENCABEZADO + "1,,Recurso guía,OVI,PDF,\n"
    salida = tmp_path / "salida"

    res = procesar.ejecutar_auditoria(
        str(carpeta), None, str(salida), matriz_texto=csv_text,
        matriz_nombre="matriz.csv",
    )

    assert res["ok"] is True
    assert res["conteo"]["ok"] == 1
    assert os.path.isfile(res["reporte_md"])
    assert os.path.isfile(res["reporte_json"])
    with open(res["reporte_md"], encoding="utf-8") as fh:
        reporte = fh.read()
    assert "Recurso guía" in reporte


def test_ejecutar_auditoria_salida_none_no_persiste_reportes(tmp_path):
    carpeta = tmp_path / "recursos"
    carpeta.mkdir()
    _escribir(str(carpeta), {"Recurso guía.pdf": b"%PDF"})
    res = procesar.ejecutar_auditoria(
        str(carpeta), None, None,
        matriz_texto=ENCABEZADO + "1,,Recurso guía,OVI,PDF,\n",
        matriz_nombre="matriz.csv",
    )
    assert res["ok"] is True
    assert res["reporte_md"] is None
    assert res["reporte_json"] is None
    assert list(tmp_path.iterdir()) == [carpeta]


def test_ejecutar_auditoria_zip_invalido_se_explica(tmp_path):
    archivo = tmp_path / "no.zip"
    archivo.write_bytes(b"basura")
    res = procesar.ejecutar_auditoria(
        str(archivo), None, str(tmp_path / "salida"),
        matriz_texto=ENCABEZADO + "1,,X,OVI,PDF,\n",
    )
    assert res["ok"] is False
    assert "ZIP" in res["error"]


# ============================================================
# PAGINA WEB /auditor
# ============================================================

def test_pagina_auditor_requiere_sesion():
    respuesta = TestClient(app).get("/auditor", follow_redirects=False)
    assert respuesta.status_code == 303
    assert respuesta.headers["location"] == "/login"


def test_pagina_auditor_muestra_formulario_y_nav():
    respuesta = _cliente().get("/auditor")
    assert respuesta.status_code == 200
    assert "aud-form" in respuesta.text
    assert 'href="/auditor"' in respuesta.text  # enlace en el menu


def test_auditor_marca_recurso_sin_nombre_como_alerta():
    recursos, avisos = procesar.leer_matriz_texto(ENCABEZADO + "1,, ,OVI,PDF,\n")
    assert recursos and recursos[0]["nombre"] == ""
    assert any("falta el nombre" in aviso.lower() for aviso in avisos)
    resultado, _, _ = procesar.emparejar(recursos, [])
    assert resultado[0]["estado"] == "alerta"
    assert "vacío" in resultado[0]["detalle"]


def test_archivo_de_cero_bytes_no_pasa_validacion(tmp_path):
    empty = tmp_path / "vacio.pdf"
    empty.write_bytes(b"")
    estado, detalle = procesar.verificar_abre("vacio.pdf", ".pdf", str(empty))
    assert estado == "error"
    assert "vacío" in detalle


def test_auditoria_web_completa_muestra_dictamen(tmp_path):
    csv_text = ENCABEZADO + "1,,Recurso guía,OVI,PDF,\n"
    buf_zip = io.BytesIO()
    with zipfile.ZipFile(buf_zip, "w") as z:
        z.writestr("Recurso guía.pdf", b"%PDF")

    respuesta = _cliente().post(
        "/auditor",
        files={
            "matriz": ("matriz.csv", csv_text.encode(), "text/csv"),
            "recursos": ("recursos.zip", buf_zip.getvalue(), "application/zip"),
        },
    )

    assert respuesta.status_code == 200
    assert "Todo calza" in respuesta.text
    assert "mosaicos" in respuesta.text
    assert "Auditorías anteriores" not in respuesta.text
    assert "/auditor/reporte/" not in respuesta.text
    assert not os.path.exists(os.path.join(DATA_DIR, "auditorias"))


def test_auditoria_web_matriz_no_csv_se_explica():
    respuesta = _cliente().post(
        "/auditor",
        files={
            "matriz": ("matriz.xlsx", b"PK...", "application/vnd.ms-excel"),
            "recursos": ("recursos.zip", b"PK", "application/zip"),
        },
    )
    assert respuesta.status_code == 200
    assert "debe ser un CSV" in respuesta.text


def test_auditoria_web_zip_invalido_se_explica():
    csv_text = ENCABEZADO + "1,,X,OVI,PDF,\n"
    respuesta = _cliente().post(
        "/auditor",
        files={
            "matriz": ("matriz.csv", csv_text.encode(), "text/csv"),
            "recursos": ("recursos.zip", b"basura", "application/zip"),
        },
    )
    assert respuesta.status_code == 200
    assert "no es un ZIP" in respuesta.text


def test_endpoint_de_reportes_anteriores_eliminado():
    assert _cliente().get("/auditor/reporte/auditoria_20260101_000000_000.md").status_code == 404


def test_toda_fila_con_enlace_se_audita_incluidos_videos(tmp_path):
    csv_text = (
        "Semana,Unidad,,Nombre del recurso,Categoria,Tipo de recurso,Enlace\n"
        "Semana 1,Unidad 1,,Video Intro,OVI,Video Intro,intro gestion.webm\n"
        "Semana 8,Unidad 3,,Video Cierre,OVI,Video Cierre,cierre-.webm\n"
        "Semana 8,Unidad 3,,Recurso sin categoria,,PDF,PDF- recurso\n"
        "Semana 8,Unidad 3,,Nota sin enlace,,,\n"
    )
    recursos, advertencias = procesar.leer_matriz_texto(csv_text)
    assert [r["nombre"] for r in recursos] == ["Video Intro", "Video Cierre", "Recurso sin categoria"]
    assert any("sin categoria" in a.lower() or "no categoría" in a for a in advertencias)

    archivos = [
        {"nombre": "Video Intro.webm", "base": "Video Intro", "ext": ".webm", "clave": procesar.clave("Video Intro"), "usado": False, "ruta": ""},
        {"nombre": "cierre-.webm", "base": "cierre-", "ext": ".webm", "clave": procesar.clave("cierre-"), "usado": False, "ruta": ""},
    ]
    resultados, huerfanos, _ = procesar.emparejar(recursos, archivos)
    estados = {r["nombre"]: r["estado"] for r in resultados}
    assert estados["Video Intro"] == "ok"
    assert estados["Video Cierre"] == "ok"
    assert estados["Recurso sin categoria"] == "faltante"
    assert huerfanos == []
