import io
import json
import zipfile

from auto_prizma.services.h5p_preview import preview_h5p_titles
from auto_prizma.automation.prizma import engine


def _zip_de_recursos(titulo_paquete, titulo_visible):
    h5p_io = io.BytesIO()
    with zipfile.ZipFile(h5p_io, "w") as h5p:
        h5p.writestr("h5p.json", json.dumps({"title": titulo_paquete}))
        h5p.writestr(
            "content/content.json",
            json.dumps({"title": titulo_visible, "metadata": {"title": titulo_visible}}),
        )
    zip_io = io.BytesIO()
    with zipfile.ZipFile(zip_io, "w") as recursos:
        recursos.writestr("Unidad 1/Actividad de costos.h5p", h5p_io.getvalue())
    return zip_io.getvalue()


def _hojas(nombre="Actividad de costos"):
    return [{
        "hoja": "Curso A",
        "actividades": [{
            "fila": 8,
            "semana": "Semana 1",
            "unidad": "Unidad 1",
            "nombre": nombre,
            "categoria": "OVA",
            "tipo": "H5P",
            "tipo_recurso": "Recurso H5P",
        }],
    }]


def test_previsualizacion_compara_titulo_del_paquete_con_matriz_y_muestra_contenido(tmp_path):
    resultado = preview_h5p_titles(
        _zip_de_recursos("s", "Actividad de costos"), _hojas(), str(tmp_path)
    )

    assert resultado["ok"] is True
    fila = resultado["resultados"][0]
    assert fila["nombre"] == "Actividad de costos"
    assert fila["archivo"] == "Actividad de costos.h5p"
    assert fila["titulo_h5p"] == "s"
    assert fila["estado"] == "alerta"
    assert fila["titulos_contenido"] == ["Actividad de costos"]
    assert "contenido SÍ muestra" in fila["detalle"]


def test_previsualizacion_marca_coincidencia_de_titulo_h5p(tmp_path):
    resultado = preview_h5p_titles(
        _zip_de_recursos("Actividad de costos", "Actividad de costos"),
        _hojas(),
        str(tmp_path),
    )

    assert resultado["resultados"][0]["estado"] == "ok"
    assert 'título interno coincide' in resultado["resultados"][0]["detalle"]


def test_revision_posterior_inspecciona_el_h5p_descargado_de_prizma(monkeypatch):
    paquete = _zip_de_recursos("Título incorrecto", "Título incorrecto")
    descargado = io.BytesIO()
    with zipfile.ZipFile(io.BytesIO(paquete)) as recursos:
        descargado.write(recursos.read("Unidad 1/Actividad de costos.h5p"))
    bytes_h5p = descargado.getvalue()

    class Descarga:
        def save_as(self, ruta):
            with open(ruta, "wb") as fh:
                fh.write(bytes_h5p)

    class ContextoDescarga:
        value = Descarga()

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class Boton:
        def click(self, **_kwargs):
            return None

    class Botones:
        first = Boton()

        def count(self):
            return 1

    class Tarjeta:
        def locator(self, _selector):
            return Botones()

    class Pagina:
        def locator(self, _selector):
            return Tarjeta()

        def expect_download(self, **_kwargs):
            return ContextoDescarga()

    cancelaciones = []
    monkeypatch.setattr(engine, "abrir_edicion", lambda *_args: True)
    monkeypatch.setattr(engine, "archivo_en_recurso", lambda _pagina: "Actividad de costos.h5p")
    monkeypatch.setattr(engine, "cancelar_edicion_segura", lambda _pagina: cancelaciones.append(True))

    detalle = engine._inspeccionar_h5p_montado(
        Pagina(), object(), {"nombre": "Actividad de costos"}
    )

    assert "REVISAR" in detalle
    assert "Título incorrecto" in detalle
    assert cancelaciones
