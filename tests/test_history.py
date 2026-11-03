"""Pruebas del historial de cargues y reportes (auto_prizma/services/history.py)."""

import json
import re
from datetime import datetime, timedelta

import pytest

from auto_prizma.services import history


@pytest.fixture
def historial_temporal(monkeypatch, tmp_path):
    ruta = tmp_path / "historial.json"
    monkeypatch.setattr(history, "HISTORIAL_PATH", str(ruta))
    return ruta


def _reporte(tmp_path, nombre="reporte.csv"):
    ruta = tmp_path / nombre
    ruta.write_text("Fila Excel,Resultado\n5,OK\n", encoding="utf-8-sig")
    return str(ruta)


def test_agregar_registro_writes_once_per_id(historial_temporal, tmp_path):
    ruta = _reporte(tmp_path)
    cursos = [{"curso": "Contabilidad I", "programa": "Administración"}]

    assert history._agregar_registro_historial("t1", ruta, cursos, "finalizado", "ana") is True
    assert history._agregar_registro_historial("t1", ruta, cursos, "finalizado", "ana") is False

    registros = json.loads(historial_temporal.read_text(encoding="utf-8"))
    assert len(registros) == 1
    assert registros[0]["archivo_reporte"] == "reporte.csv"
    assert registros[0]["usuario_app"] == "ana"
    assert "tipo" not in registros[0]


def test_agregar_registro_requires_existing_report_file(historial_temporal, tmp_path):
    faltante = str(tmp_path / "no_existe.csv")

    assert history._agregar_registro_historial("t2", faltante, [], "error", "ana") is False
    assert not historial_temporal.exists()


def test_historial_del_usuario_only_returns_own_records(historial_temporal, tmp_path):
    ruta = _reporte(tmp_path)
    history._agregar_registro_historial("a", ruta, [], "finalizado", "Ana")
    history._agregar_registro_historial("b", ruta, [], "finalizado", "beto")
    history._agregar_registro_historial("c", ruta, [], "finalizado", None)  # registro antiguo sin dueno

    assert [r["id"] for r in history._historial_del_usuario("ana")] == ["a"]
    assert [r["id"] for r in history._historial_del_usuario("BETO")] == ["b"]


def test_registrar_historial_test_marks_type_and_course(historial_temporal, tmp_path):
    ruta = _reporte(tmp_path)

    history._registrar_historial_test(
        "test1", ruta, {"asignatura": "Finanzas", "programa": "Contaduría"}, "finalizado", "ana"
    )

    registro = history._historial_del_usuario("ana")[0]
    assert registro["tipo"] == "test"
    assert registro["cursos"] == [{"curso": "Test Evaluativo: Finanzas", "programa": "Contaduría"}]


def test_registrar_reporte_final_marks_job_as_registered(historial_temporal, tmp_path):
    trabajo = {
        "id": "t3",
        "ruta_reporte": _reporte(tmp_path),
        "cursos": [],
        "etapa": "finalizado",
        "usuario_app": "ana",
    }

    history._registrar_reporte_final(trabajo)

    assert trabajo["historial_registrado"] is True


def test_leer_reporte_csv_skips_empty_rows(tmp_path):
    ruta = tmp_path / "r.csv"
    ruta.write_text("A,B\n1,2\n,\n3,4\n", encoding="utf-8-sig")

    assert history._leer_reporte_csv(str(ruta)) == (["A", "B"], [["1", "2"], ["3", "4"]])


def test_nombre_reporte_format_and_sanitization():
    nombre = history._nombre_reporte(
        [{"curso": 'Gestión: "Finanzas"/I', "programa": "Contaduría"}, {"curso": "Otro", "programa": "X"}],
        "abcdef123456",
    )

    assert re.fullmatch(
        r"\d{4}-\d{2}-\d{2}_\d{2}-\d{2}-\d{2} - Gestión- -Finanzas-I - Contaduría_y_1_curso_mas - abcdef\.csv",
        nombre,
    ), nombre


def test_limpiar_historial_viejo_elimina_registro_y_csv_y_conserva_reciente(
    historial_temporal, tmp_path, monkeypatch
):
    reportes = tmp_path / "reportes"
    reportes.mkdir()
    monkeypatch.setattr(history, "RESULTADOS_DIR", str(reportes))
    ahora = datetime.fromisoformat("2026-10-27T12:00:00-05:00")
    monkeypatch.setattr(history, "_ahora_colombia", lambda: ahora)
    viejo_csv = reportes / "viejo.csv"
    nuevo_csv = reportes / "nuevo.csv"
    viejo_csv.write_text("viejo", encoding="utf-8")
    nuevo_csv.write_text("nuevo", encoding="utf-8")
    historial_temporal.write_text(json.dumps([
        {
            "id": "viejo", "fecha_iso": (ahora - timedelta(days=16)).isoformat(),
            "archivo_reporte": viejo_csv.name, "usuario_app": "ana",
        },
        {
            "id": "nuevo", "fecha_iso": (ahora - timedelta(days=14)).isoformat(),
            "archivo_reporte": nuevo_csv.name, "usuario_app": "ana",
        },
    ]), encoding="utf-8")

    history.limpiar_historial_viejo()

    assert [r["id"] for r in json.loads(historial_temporal.read_text(encoding="utf-8"))] == ["nuevo"]
    assert not viejo_csv.exists()
    assert nuevo_csv.exists()
