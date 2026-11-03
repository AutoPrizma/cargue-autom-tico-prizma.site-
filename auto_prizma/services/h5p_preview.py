"""Comparación previa de los títulos H5P de la matriz y el ZIP."""

import csv
import io
import os
import tempfile
import zipfile

from auto_prizma.auditor import procesar as auditor


def preview_h5p_titles(zip_bytes, hojas, temp_root=None):
    """Audita títulos H5P antes del cargue sin modificar el ZIP original."""
    filas = [[
        "Semana correspondiente", "Unidad", "Tema", "Nombre del recurso",
        "Categoria", "Tipo de recurso", "Enlace",
    ]]
    for hoja in hojas or []:
        for actividad in hoja.get("actividades") or []:
            filas.append([
                str(actividad.get("semana") or ""),
                str(actividad.get("unidad") or ""),
                "",
                str(actividad.get("nombre") or ""),
                str(actividad.get("categoria") or ""),
                str(actividad.get("tipo_recurso") or actividad.get("tipo") or ""),
                str(actividad.get("enlace") or ""),
            ])
    matriz_io = io.StringIO(newline="")
    csv.writer(matriz_io).writerows(filas)

    try:
        if temp_root:
            os.makedirs(temp_root, exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="revision_h5p_", dir=temp_root) as temporal:
            zip_path = os.path.join(temporal, "recursos.zip")
            salida = os.path.join(temporal, "auditoria")
            with open(zip_path, "wb") as archivo:
                archivo.write(zip_bytes)
            resultado = auditor.ejecutar_auditoria(
                zip_path,
                None,
                salida=salida,
                matriz_texto=matriz_io.getvalue(),
            )
            if not resultado.get("ok"):
                return {"ok": False, "error": resultado.get("error") or "No se pudo leer el ZIP."}

            entradas_h5p = [
                fila for fila in resultado.get("resultados", [])
                if fila.get("ext_esperada") == ".h5p"
                or os.path.splitext(str(fila.get("archivo") or ""))[1].lower() == ".h5p"
            ]
            metadatos = {}
            with zipfile.ZipFile(zip_path) as paquete:
                for miembro in paquete.namelist():
                    if miembro.endswith("/") or os.path.splitext(miembro)[1].lower() != ".h5p":
                        continue
                    nombre_base = os.path.basename(miembro)
                    ruta_temporal = os.path.join(temporal, "h5p_" + str(len(metadatos)) + ".h5p")
                    with open(ruta_temporal, "wb") as salida_h5p:
                        salida_h5p.write(paquete.read(miembro))
                    titulo, error = auditor.leer_titulo_h5p(ruta_temporal)
                    metadatos.setdefault(nombre_base.casefold(), []).append({
                        "titulo": titulo or "",
                        "error": error or "",
                        "titulos_contenido": auditor.titulos_visibles_h5p(ruta_temporal),
                    })

            filas_salida = []
            for fila in entradas_h5p:
                candidatos = metadatos.get(os.path.basename(str(fila.get("archivo") or "")).casefold()) or []
                metadata = candidatos.pop(0) if candidatos else {}
                filas_salida.append({
                    "fila": fila.get("fila"),
                    "nombre": fila.get("nombre") or "",
                    "archivo": fila.get("archivo") or "",
                    "titulo_h5p": metadata.get("titulo") or "",
                    "titulos_contenido": metadata.get("titulos_contenido") or [],
                    "estado": fila.get("estado") or "alerta",
                    "detalle": fila.get("detalle") or metadata.get("error") or "Sin detalle.",
                })
            return {"ok": True, "resultados": filas_salida}
    except Exception as exc:
        return {"ok": False, "error": "No se pudo inspeccionar el ZIP H5P: " + str(exc)[:180]}
