"""Pruebas de las paginas Reportes, Historial y Detalle del reporte (api/routes/reports.py)."""

import csv
import json
from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from main import app
from auto_prizma.services import history
from auto_prizma.services.auth import _firmar_sesion

CABECERA = ["Fila Excel", "Programa", "Curso", "Semana", "Unidad", "Actividad",
            "Categoría", "Tipo", "Recurso", "Resultado", "Observación"]
FILAS = [
    ["10", "Esp en Fintech", "Seminario de investigación I", "Semana 1", "Unidad 1", "Construcción social",
     "OVA", "H5P", "Construcción social.h5p", "OK", "Carga guardada - PATCH confirmado"],
    ["26", "Esp en Fintech", "Seminario de investigación I", "Semana 3", "Unidad 1", "Principios",
     "OVA", "H5P", "Principios.h5p", "ERROR", "ERROR_ACTIVIDAD_NO_ENCONTRADA"],
    ["33", "Esp en Fintech", "Seminario de investigación I", "Semana 3", "Unidad 2", "Epistemología",
     "OVA", "H5P", "Epistemología.h5p", "ERROR", 'ERROR_X: "algo" <b>'],
]
REGISTROS = [
    ("r1", "2026-09-21T11:18:45-05:00", [{"curso": "Análisis de datos", "programa": "Esp en Fintech"}], "adminlocal"),
    ("r2", "2026-09-23T15:21:11-05:00", [{"curso": "Seminario de investigación I", "programa": "Esp en Fintech"}], "adminlocal"),
    ("r3", "2026-09-22T16:42:10-05:00", [
        {"curso": "Arquitectura", "programa": "Esp en Fintech"},
        {"curso": "Finanzas", "programa": "Contaduría"},
    ], "adminlocal"),
    ("ajeno", "2026-09-24T09:00:00-05:00", [{"curso": "De otra persona", "programa": "Otro"}], "beto"),
]


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setattr(history, "HISTORIAL_PATH", str(tmp_path / "historial.json"))
    monkeypatch.setattr(history, "RESULTADOS_DIR", str(tmp_path))
    monkeypatch.setattr(
        history, "_ahora_colombia",
        lambda: datetime.fromisoformat("2026-09-25T12:00:00-05:00"),
    )

    registros = []
    for registro_id, fecha, cursos, usuario in REGISTROS:
        nombre = registro_id + ".csv"
        with open(tmp_path / nombre, "w", newline="", encoding="utf-8-sig") as archivo:
            escritor = csv.writer(archivo)
            escritor.writerow(CABECERA)
            escritor.writerows(FILAS)
        registros.append({
            "id": registro_id, "fecha_iso": fecha, "archivo_reporte": nombre,
            "cursos": cursos, "estado_final": "finalizado", "usuario_app": usuario,
        })
    (tmp_path / "historial.json").write_text(json.dumps(registros), encoding="utf-8")

    cliente = TestClient(app)
    cliente.cookies.set("ap_sesion", _firmar_sesion("adminlocal"))
    return cliente


def test_reports_page_summarizes_and_lists_newest_first(client):
    html = client.get("/reportes").text

    assert '<strong class="num">3</strong><span>Reportes generados</span>' in html
    assert '<strong class="num">2</strong><span>Programas</span>' in html
    assert '<strong class="num">4</strong><span>Cursos</span>' in html
    assert "<strong>23 sep 2026</strong><span>Último reporte</span>" in html

    # Nombre limpio "Curso - Programa", del mas reciente al mas antiguo.
    seminario = html.index("Seminario de investigación I - Esp en Fintech")
    arquitectura = html.index("Arquitectura - Esp en Fintech (y 1 curso(s) más)")
    analisis = html.index("Análisis de datos - Esp en Fintech")
    assert seminario < arquitectura < analisis

    assert "De otra persona" not in html
    assert 'data-programa="Esp en Fintech|Contaduría"' in html
    assert '<option value="Contaduría">Contaduría</option>' in html
    assert 'data-copiar="/reporte-guardado/r2" data-copiar-url' in html
    assert 'href="/reporte-guardado/r2?descargar=1"' in html


def test_history_lists_each_course(client):
    html = client.get("/historial").text

    assert html.count("<tr data-fila") == 4
    assert "4 registros" in html
    assert "De otra persona" not in html


def test_report_detail_counts_results_and_offers_copy(client):
    html = client.get("/reporte-guardado/r2").text

    assert "<h1>Seminario de investigación I</h1>" in html
    assert "Esp en Fintech · 23/09/2026" in html
    assert '<strong class="num">2</strong><b>Errores encontrados</b>' in html
    assert '<strong class="num">1</strong><b>Registros OK</b>' in html
    assert "Omitidos" not in html
    assert '<span class="resultado ok">' in html
    assert '<span class="resultado error">' in html
    assert '<th class="col-estrecha">Fila Excel</th>' in html
    assert '<th class="col-observacion">Observación</th>' in html
    assert 'data-copiar="ERROR_ACTIVIDAD_NO_ENCONTRADA"' in html
    # El texto del CSV llega escapado tambien dentro de los atributos.
    assert 'data-copiar="ERROR_X: &quot;algo&quot; &lt;b&gt;"' in html
    assert 'href="/reporte-guardado/r2?descargar=1"' in html


def test_report_detail_download_and_ownership(client):
    descarga = client.get("/reporte-guardado/r2", params={"descargar": 1})

    assert descarga.status_code == 200
    assert descarga.headers["content-type"].startswith("text/csv")
    assert client.get("/reporte-guardado/ajeno").status_code == 404
