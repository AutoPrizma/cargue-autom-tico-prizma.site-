import io
import json
import zipfile

import pytest

from auto_prizma.domain.moodle_resources import destination_for, normalize_key, resolve_resource
from auto_prizma.services import moodle_resources
from auto_prizma.web.moodle_views import _item


def _zip_bytes():
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        archive.writestr("semana/U1-T1-Origen y transformacion de la analitica.pdf", b"%PDF-1.4 test")
        archive.writestr("otros/solo-notas.txt", b"no se indexa")
    return output.getvalue()


def test_matching_preserves_original_moodle_prefix_and_extension_rules():
    row = {
        "category": "OVI",
        "resourceType": "PDF",
        "title": "Origen y transformación de la analítica",
        "linkLabel": "TEXTO - Origen y transformación de la analítica",
    }
    path = "resources/U1-T1-Origen y transformacion de la analitica.pdf"
    assert normalize_key("U1-T1-Origen y transformación de la analítica") == normalize_key(row["title"])
    assert destination_for(row)["block"] == "digital"
    assert resolve_resource(row, [{"path": path, "extension": ".pdf", "key": normalize_key(path.rsplit("/", 1)[-1][:-4])}]) == {
        "status": "matched",
        "path": path,
        "candidates": [path],
    }


def test_matches_matrix_infographic_to_h5p_file_with_h5p_name_prefix():
    row = {
        "category": "OVI",
        "resourceType": "Infografía",
        "title": "Ejemplos comparativos de textos académicos",
        "linkLabel": "Infografía - Ejemplos comparativos de textos académicos",
    }
    path = "resources/H5P - Ejemplos comparativos de textos académicos.h5p"
    indexed_file = {
        "path": path,
        "extension": ".h5p",
        "key": normalize_key("H5P - Ejemplos comparativos de textos académicos"),
    }

    result = resolve_resource(row, [indexed_file])

    assert result == {"status": "matched", "path": path, "candidates": [path]}


def test_prefixed_duplicate_h5p_files_remain_ambiguous():
    row = {
        "category": "OVI",
        "resourceType": "Infografía",
        "title": "Ejemplos comparativos de textos académicos",
        "linkLabel": "Infografía - Ejemplos comparativos de textos académicos",
    }
    paths = (
        "resources/H5P - Ejemplos comparativos de textos académicos.h5p",
        "resources/copia/H5P - Ejemplos comparativos de textos académicos.h5p",
    )
    indexed_files = [
        {"path": path, "extension": ".h5p", "key": normalize_key(path.rsplit("/", 1)[-1][:-5])}
        for path in paths
    ]

    result = resolve_resource(row, indexed_files)

    assert result == {"status": "ambiguous", "candidates": list(paths)}


def test_preview_extracts_only_supported_resources_and_keeps_course_owner(tmp_path, monkeypatch):
    monkeypatch.setattr(moodle_resources, "UPLOADS_DIR", str(tmp_path / "uploads"))
    monkeypatch.setattr(moodle_resources, "DATA_DIR", str(tmp_path / "data"))
    matrix = (
        "Programa,Curso,Semana correspondiente,Unidad,Nombre del recurso,Categoría,Tipo de recurso,Enlace\n"
        "P,C,Semana 1,Unidad 1,Origen y transformación de la analítica,OVI,PDF,TEXTO - Origen y transformación de la analítica\n"
    ).encode("utf-8")

    job = moodle_resources.create_moodle_preview(
        "adminlocal",
        "matriz.csv",
        matrix,
        "recursos.zip",
        _zip_bytes(),
        "https://prizma.americana.edu.co/course/view.php?id=42",
    )

    assert job["owner"] == "adminlocal"
    assert job["summary"]["matched"] == 1
    assert job["entries"][0]["status"] == "matched"
    assert job["entries"][0]["week"] == "Semana 1"
    assert len(moodle_resources.index_resource_files(job["resources_root"])) == 1


def test_moodle_preview_compares_h5p_package_and_visible_titles_to_matrix(tmp_path, monkeypatch):
    monkeypatch.setattr(moodle_resources, "UPLOADS_DIR", str(tmp_path / "uploads"))
    h5p_bytes = io.BytesIO()
    with zipfile.ZipFile(h5p_bytes, "w") as h5p:
        h5p.writestr("h5p.json", json.dumps({"title": "s"}))
        h5p.writestr(
            "content/content.json",
            json.dumps({"title": "Actividad presupuestos", "metadata": {"title": "Actividad presupuestos"}}),
        )
    resources = io.BytesIO()
    with zipfile.ZipFile(resources, "w") as archive:
        archive.writestr("H5P - Actividad presupuestos.h5p", h5p_bytes.getvalue())
    matrix = (
        "Programa,Curso,Semana correspondiente,Unidad,Nombre del recurso,Categoría,Tipo de recurso,Enlace\n"
        "P,C,Semana 1,Unidad 1,Actividad presupuestos,OVI,Infografía,Infografía - Actividad presupuestos\n"
    ).encode("utf-8")

    job = moodle_resources.create_moodle_preview(
        "adminlocal", "matriz.csv", matrix, "recursos.zip", resources.getvalue(),
        "https://prizma.americana.edu.co/course/view.php?id=42",
    )

    preview = job["entries"][0]["h5p_preview"]
    assert preview["status"] == "match"
    assert preview["package_title"] == "s"
    assert preview["visible_titles"] == ["Actividad presupuestos"]
    assert preview["cover_title"] == "Actividad presupuestos"
    assert preview["package_similarity"] < 0.51
    assert "coincide con el de la matriz" in preview["detail"]
    rendered = _item(job["entries"][0], 0, False)
    assert "Título coincide" in rendered
    assert "Título H5P" in rendered
    assert "Actividad presupuestos" in rendered


def test_title_below_threshold_requires_manual_attachment(tmp_path, monkeypatch):
    monkeypatch.setattr(moodle_resources, "UPLOADS_DIR", str(tmp_path / "uploads"))
    h5p_bytes = io.BytesIO()
    with zipfile.ZipFile(h5p_bytes, "w") as h5p:
        h5p.writestr("h5p.json", json.dumps({"title": "ZZZZZZZZZZ"}))
    resources = io.BytesIO()
    with zipfile.ZipFile(resources, "w") as archive:
        archive.writestr("Actividad presupuestos.h5p", h5p_bytes.getvalue())
    matrix = (
        "Programa,Curso,Semana correspondiente,Unidad,Nombre del recurso,Categoría,Tipo de recurso,Enlace\n"
        "P,C,Semana 1,Unidad 1,Actividad presupuestos,OVI,Infografía,Infografía - Actividad presupuestos\n"
    ).encode("utf-8")

    job = moodle_resources.create_moodle_preview(
        "adminlocal", "matriz.csv", matrix, "recursos.zip", resources.getvalue(),
        "https://prizma.americana.edu.co/course/view.php?id=42",
    )

    entry = job["entries"][0]
    assert entry["status"] == "title-review"
    with pytest.raises(ValueError, match="no están disponibles"):
        moodle_resources.publishable_entries(job, [entry["key"]])
    rendered = _item(entry, 0, False)
    assert "Título H5P por revisar" in rendered
    assert "data-manual-resource" in rendered

    attached = moodle_resources.attach_manual_resource(
        job, entry["key"], "H5P corregido.h5p", h5p_bytes.getvalue()
    )
    assert attached["status"] == "matched"
    assert attached["manual_filename"] == "H5P corregido.h5p"
    assert moodle_resources.publishable_entries(job, [entry["key"]]) == [entry]


def test_package_title_match_without_content_title_is_not_auto_approved(tmp_path, monkeypatch):
    monkeypatch.setattr(moodle_resources, "UPLOADS_DIR", str(tmp_path / "uploads"))
    h5p_bytes = io.BytesIO()
    with zipfile.ZipFile(h5p_bytes, "w") as h5p:
        h5p.writestr("h5p.json", json.dumps({"title": "Actividad presupuestos"}))
        h5p.writestr(
            "content/content.json",
            json.dumps({"metadata": {}, "chapters": [{"metadata": {"title": "Actividad presupuestos"}}]}),
        )
    resources = io.BytesIO()
    with zipfile.ZipFile(resources, "w") as archive:
        archive.writestr("Actividad presupuestos.h5p", h5p_bytes.getvalue())
    matrix = (
        "Programa,Curso,Semana correspondiente,Unidad,Nombre del recurso,Categoría,Tipo de recurso,Enlace\n"
        "P,C,Semana 1,Unidad 1,Actividad presupuestos,OVI,Infografía,Infografía - Actividad presupuestos\n"
    ).encode("utf-8")

    job = moodle_resources.create_moodle_preview(
        "adminlocal", "matriz.csv", matrix, "recursos.zip", resources.getvalue(),
        "https://prizma.americana.edu.co/course/view.php?id=42",
    )
    entry = job["entries"][0]

    assert entry["h5p_preview"]["package_similarity"] == 1.0
    assert entry["h5p_preview"]["status"] == "no-cover"
    assert entry["status"] == "title-review"
    assert "no se detectó" in entry["h5p_preview"]["detail"].lower()


def test_h5p_visible_title_must_match_exactly_after_normalization(tmp_path, monkeypatch):
    monkeypatch.setattr(moodle_resources, "UPLOADS_DIR", str(tmp_path / "uploads"))
    h5p_bytes = io.BytesIO()
    with zipfile.ZipFile(h5p_bytes, "w") as h5p:
        h5p.writestr("h5p.json", json.dumps({"title": "Actividad presupuestos"}))
        h5p.writestr(
            "content/content.json",
            json.dumps({"title": "Actividad presupuesto adicional", "metadata": {"title": "Actividad presupuesto adicional"}}),
        )
    resources = io.BytesIO()
    with zipfile.ZipFile(resources, "w") as archive:
        archive.writestr("Actividad presupuestos.h5p", h5p_bytes.getvalue())
    matrix = (
        "Programa,Curso,Semana correspondiente,Unidad,Nombre del recurso,Categoría,Tipo de recurso,Enlace\n"
        "P,C,Semana 1,Unidad 1,Actividad presupuestos,OVI,Infografía,Infografía - Actividad presupuestos\n"
    ).encode("utf-8")

    job = moodle_resources.create_moodle_preview(
        "adminlocal", "matriz.csv", matrix, "recursos.zip", resources.getvalue(),
        "https://prizma.americana.edu.co/course/view.php?id=42",
    )

    assert job["entries"][0]["h5p_preview"]["status"] == "cover-mismatch"
    assert job["entries"][0]["status"] == "title-review"


def test_manual_pdf_can_fill_missing_matrix_row(tmp_path, monkeypatch):
    monkeypatch.setattr(moodle_resources, "UPLOADS_DIR", str(tmp_path / "uploads"))
    matrix = (
        "Programa,Curso,Semana correspondiente,Unidad,Nombre del recurso,Categoría,Tipo de recurso,Enlace\n"
        "P,C,Semana 1,Unidad 1,Lectura de apoyo,OVI,PDF,TEXTO - Lectura de apoyo\n"
    ).encode("utf-8")
    job = moodle_resources.create_moodle_preview(
        "adminlocal", "matriz.csv", matrix, "recursos.zip", _zip_bytes(),
        "https://prizma.americana.edu.co/course/view.php?id=42",
    )
    entry = job["entries"][0]
    assert entry["status"] == "missing"

    moodle_resources.attach_manual_resource(job, entry["key"], "lectura.pdf", b"%PDF-test")

    assert entry["status"] == "matched"
    assert job["summary"]["matched"] == 1
    assert moodle_resources.publishable_entries(job, [entry["key"]]) == [entry]


def test_manual_upload_rejects_wrong_extension_and_invalid_h5p(tmp_path, monkeypatch):
    monkeypatch.setattr(moodle_resources, "UPLOADS_DIR", str(tmp_path / "uploads"))
    matrix = (
        "Programa,Curso,Semana correspondiente,Unidad,Nombre del recurso,Categoría,Tipo de recurso,Enlace\n"
        "P,C,Semana 1,Unidad 1,Actividad,OVI,Infografía,Infografía - Actividad\n"
    ).encode("utf-8")
    job = moodle_resources.create_moodle_preview(
        "adminlocal", "matriz.csv", matrix, "recursos.zip", _zip_bytes(),
        "https://prizma.americana.edu.co/course/view.php?id=42",
    )
    entry = job["entries"][0]
    with pytest.raises(ValueError, match="necesita un archivo .h5p"):
        moodle_resources.attach_manual_resource(job, entry["key"], "recurso.pdf", b"%PDF")
    with pytest.raises(ValueError, match="no es válido"):
        moodle_resources.attach_manual_resource(job, entry["key"], "recurso.h5p", b"mal h5p")


def test_preview_rejects_course_from_another_host(tmp_path, monkeypatch):
    monkeypatch.setattr(moodle_resources, "UPLOADS_DIR", str(tmp_path / "uploads"))
    with pytest.raises(ValueError, match="ID numérico"):
        moodle_resources.validate_course_url("https://example.com/course/view.php?id=42")


@pytest.mark.parametrize("url", [
    "https://prizma.americana.edu.co/course/view.php",
    "https://prizma.americana.edu.co/course/view.php?id=",
    "https://prizma.americana.edu.co/course/view.php?id=abc",
    "https://prizma.americana.edu.co/course/other.php?id=42",
])
def test_course_url_requires_moodle_course_path_and_numeric_id(url):
    with pytest.raises(ValueError, match="ID numérico"):
        moodle_resources.validate_course_url(url)


def test_invalid_matrix_does_not_leave_an_uploaded_job_directory(tmp_path, monkeypatch):
    uploads = tmp_path / "uploads"
    monkeypatch.setattr(moodle_resources, "UPLOADS_DIR", str(uploads))
    with pytest.raises(ValueError, match="encabezados requeridos"):
        moodle_resources.create_moodle_preview(
            "adminlocal",
            "matriz.csv",
            b"esta no es la matriz requerida\n",
            "recursos.zip",
            _zip_bytes(),
            "https://prizma.americana.edu.co/course/view.php?id=42",
        )
    assert not (uploads / "moodle").exists()


def test_publishable_entries_rejects_unmatched_keys():
    job = {"entries": [{"key": "matched", "status": "matched", "sourceRow": 2}]}
    assert moodle_resources.publishable_entries(job, ["matched"])[0]["key"] == "matched"
    with pytest.raises(ValueError, match="no están disponibles"):
        moodle_resources.publishable_entries(job, ["missing"])


def test_publishable_entries_start_from_week_one():
    job = {"entries": [
        {"key": "s10", "status": "matched", "sourceRow": 2, "week": "Semana 10"},
        {"key": "s2", "status": "matched", "sourceRow": 3, "week": "Semana 2"},
        {"key": "s1b", "status": "matched", "sourceRow": 9, "week": "Semana 1"},
        {"key": "s1a", "status": "matched", "sourceRow": 4, "week": "Semana 1"},
    ]}
    keys = [entry["key"] for entry in moodle_resources.publishable_entries(job, ["s10", "s2", "s1b", "s1a"])]
    assert keys == ["s1a", "s1b", "s2", "s10"]
