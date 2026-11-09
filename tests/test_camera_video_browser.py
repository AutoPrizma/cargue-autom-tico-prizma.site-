"""Flujo de video a cámara en Chromium real contra una página local (sin PRIZMA).

La página imita lo observado en la grabación del proceso manual: búsqueda con
temas de nombre parecido, columnas Semana/Unidad, lápiz por fila y un formulario
cuyos Programa/Pensum son listas que muestran su valor en un contenedor visible.
"""

import zipfile

import pytest
from playwright.sync_api import sync_playwright

from auto_prizma.automation.prizma import engine

NOMBRE_TEMA = "Características, Operaciones básicas"
ARCHIVO_VIDEO = "Fundamentos de las listas.webm"

PAGINA_TEMAS = """
<button id="tab-tema">Tema</button>
<input placeholder="Buscar" id="buscar">
<table><tbody id="filas"></tbody></table>
<div id="zona-formulario"></div>
<script>
  window.guardados = [];
  const dibujar = (consultaRecibida) => {
    const consulta = consultaRecibida === undefined
      ? document.getElementById('buscar').value : consultaRecibida;
    const filas = document.getElementById('filas');
    filas.innerHTML = '';
    let visibles = 0;
    window.temas.forEach((tema, indice) => {
      if (consulta && !tema.nombre.includes(consulta)) return;
      // Como PRIZMA, cada respuesta solo pinta la primera página de resultados.
      if (window.limiteFilas && visibles >= window.limiteFilas) return;
      visibles += 1;
      const fila = document.createElement('tr');
      fila.innerHTML = '<td>Activo</td><td>' + (indice + 1) + '</td>'
        + '<td>' + tema.nombre + '</td>'
        + '<td>' + (tema.semana || 'SEMANA 1') + '</td>'
        + '<td>' + (tema.unidad || 'Unidad 1') + '</td>'
        + '<td><button class="btnLila" title="editar">E</button></td>';
      fila.querySelector('button').onclick = () => abrir(indice);
      filas.appendChild(fila);
    });
  };
  const lista = (etiqueta, id) => `
    <div><label>${etiqueta}</label>
      <div class="control"><div id="${id}" class="valor"></div><input value=""></div></div>`;
  const abrir = indice => {
    const tema = window.temas[indice];
    const zona = document.getElementById('zona-formulario');
    const tarjeta = tema.archivo
      ? '<div class="fileItem" style="width:200px;height:20px"><p>' + tema.archivo + '</p></div>'
      : '';
    zona.innerHTML = `
      <div id="formulario">
        ${lista('Facultad', 'facultad')}
        ${lista('Programa', 'programa')}
        ${lista('Pensum', 'pensum')}
        ${lista('Nivel de Pensum', 'nivel')}
        <div><label>Nombre del tema</label>
          <input id="nombre-tema" value="${tema.nombreFormulario || tema.nombre}"></div>
        <div><p class="form-label">Recursos</p>
          <div class="btnFile">${tarjeta}<input type="file"></div></div>
        <button id="cancelar">Cancelar</button>
        <button id="guardar">${window.textoGuardar || 'Guardar'}</button>
      </div>`;
    window.adjunto = null;
    const entrada = zona.querySelector('input[type=file]');
    entrada.addEventListener('change', () => {
      window.adjunto = entrada.files[0] && entrada.files[0].name;
      if (window.modoAdjunto === 'ignorar') return;
      // Como en PRIZMA: al recibir el archivo vacía o quita el input y pinta una tarjeta.
      const bloque = entrada.closest('.btnFile');
      if (window.modoAdjunto === 'quitar') entrada.remove();
      else entrada.value = '';
      const nueva = document.createElement('div');
      nueva.className = 'fileItem';
      nueva.style.cssText = 'width:200px;height:20px';
      nueva.innerHTML = '<p>' + window.adjunto + '</p>';
      bloque.prepend(nueva);
    });
    setTimeout(() => {
      const poner = (id, texto) => {
        const campo = document.getElementById(id);
        if (campo) campo.textContent = texto;
      };
      poner('facultad', 'Virtual - ingeniería de sistemas');
      poner('programa', tema.programa);
      poner('pensum', tema.pensum);
      poner('nivel', 'Cinco');
    }, window.retrasoCodigos || 0);
    document.getElementById('cancelar').onclick = () => {
      zona.innerHTML = '';
      window.cancelados = (window.cancelados || 0) + 1;
      // PRIZMA puede repintar la lista con menos filas al volver de editar.
      if (window.temasAlCancelar) window.temas = window.temasAlCancelar;
      dibujar();
    };
    document.getElementById('guardar').onclick = () => {
      window.guardados.push({ tema: indice, archivo: window.adjunto });
      zona.innerHTML = '';
    };
  };
  window.iniciar = (temas, opciones) => {
    window.temas = temas;
    Object.assign(window, opciones || {});
    dibujar();
  };
  document.getElementById('buscar').addEventListener('input', evento => {
    const consulta = evento.target.value;
    window.pedidos = (window.pedidos || 0) + 1;
    // Lista sin filtrar: lo observado en PRIZMA con un título con coma.
    if (window.ignorarComa && consulta.includes(',')) return;
    // Una consulta vieja puede responder después que las más nuevas.
    const retraso = window.respuestaDesordenada
      ? Math.max(50, 3000 - window.pedidos * 60)
      : (window.retrasoBusqueda || 0);
    if (retraso) setTimeout(() => dibujar(consulta), retraso);
    else dibujar(consulta);
  });
</script>
"""

TEMA_CORRECTO = {
    "nombre": NOMBRE_TEMA,
    "programa": "V2204 - Tecnología en desarrollo de software (vir)",
    "pensum": "22042 - Pensum tecnología en desarrollo de software",
}
TEMA_AJENO = {**TEMA_CORRECTO, "programa": "V9999 - Otro", "pensum": "99999 - Otro"}


def _parecido(sufijo, semana, unidad):
    return {
        **TEMA_CORRECTO,
        "nombre": NOMBRE_TEMA + " " + sufijo,
        "semana": semana,
        "unidad": unidad,
    }


@pytest.fixture(scope="module")
def navegador():
    with sync_playwright() as playwright:
        try:
            chromium = playwright.chromium.launch(headless=True)
        except Exception as error:
            pytest.skip("Chromium no disponible: " + str(error))
        yield chromium
        chromium.close()


@pytest.fixture
def pagina(navegador):
    contexto = navegador.new_context()
    nueva = contexto.new_page()
    nueva.set_content(PAGINA_TEMAS)
    yield nueva
    contexto.close()


@pytest.fixture
def archivos(tmp_path):
    ruta_zip = tmp_path / "recursos.zip"
    with zipfile.ZipFile(ruta_zip, "w") as archivo:
        archivo.writestr(ARCHIVO_VIDEO, b"webm")
    carpeta_temp = tmp_path / "temp"
    carpeta_temp.mkdir()
    return str(ruta_zip), carpeta_temp


def _video(semana="Semana 1", unidad="Unidad 1"):
    return {
        "nombre": NOMBRE_TEMA + ".",
        "miembro_zip": ARCHIVO_VIDEO,
        "fila_excel": 8,
        "semana": semana,
        "unidad": unidad,
    }


def _iniciar(pagina, temas, **opciones):
    pagina.evaluate("([temas, opciones]) => window.iniciar(temas, opciones)", [temas, opciones])


def _videos_extraidos(carpeta_temp):
    return list(carpeta_temp.glob("video_camara_*/*.webm"))


def test_lee_codigos_de_listas_que_muestran_el_valor_fuera_del_input(pagina, archivos):
    ruta_zip, carpeta_temp = archivos
    _iniciar(pagina, [TEMA_CORRECTO])

    resultado = engine.subir_video_a_tema(
        pagina, _video(), ruta_zip, str(carpeta_temp), "V2204", "22042"
    )

    assert resultado == {"ok": True, "recurso": ARCHIVO_VIDEO}
    assert pagina.evaluate("window.guardados") == [{"tema": 0, "archivo": ARCHIVO_VIDEO}]


def test_elige_el_titulo_exacto_entre_temas_de_nombre_parecido(pagina, archivos):
    """Como en la grabación: el mismo programa con 5 títulos que contienen el buscado."""
    ruta_zip, carpeta_temp = archivos
    _iniciar(
        pagina,
        [
            _parecido("en Estructuras combinadas multinivel", "SEMANA 8", "Unidad 3"),
            _parecido("en Multilistas", "SEMANA 7", "Unidad 3"),
            TEMA_CORRECTO,
            _parecido("en bicolas", "SEMANA 5", "Unidad 2"),
        ],
    )

    resultado = engine.subir_video_a_tema(
        pagina, _video(), ruta_zip, str(carpeta_temp), "V2204", "22042"
    )

    assert resultado["ok"] is True
    assert pagina.evaluate("window.guardados") == [{"tema": 2, "archivo": ARCHIVO_VIDEO}]


def test_no_sube_si_el_tema_exacto_es_de_otra_semana(pagina, archivos):
    ruta_zip, carpeta_temp = archivos
    _iniciar(pagina, [{**TEMA_CORRECTO, "semana": "SEMANA 8"}])

    resultado = engine.subir_video_a_tema(
        pagina, _video(), ruta_zip, str(carpeta_temp), "V2204", "22042"
    )

    assert resultado["ok"] is False
    assert "No se encontró el tema" in resultado["error"]
    assert "Semana 1" in resultado["error"]
    # El último intento deja en Buscar el tramo más largo del título.
    assert "Buscar tenía «Operaciones básicas»" in resultado["error"]
    assert pagina.evaluate("window.guardados") == []
    assert _videos_extraidos(carpeta_temp) == []


def test_no_duplica_si_recursos_ya_tiene_un_archivo(pagina, archivos):
    """Como en la grabación: el tema ya muestra un .webm en Recursos."""
    ruta_zip, carpeta_temp = archivos
    _iniciar(pagina, [{**TEMA_CORRECTO, "archivo": "CLASE1-ESTRUCTURA DE DATOS.webm"}])

    resultado = engine.subir_video_a_tema(
        pagina, _video(), ruta_zip, str(carpeta_temp), "V2204", "22042"
    )

    assert resultado["ok"] is True
    assert resultado["omitido"] is True
    assert resultado["recurso"] == ARCHIVO_VIDEO
    assert "CLASE1-ESTRUCTURA DE DATOS.webm" in resultado["observacion"]
    assert "No se subió ni se reemplazó" in resultado["observacion"]
    assert pagina.evaluate("window.guardados") == []
    assert pagina.locator("#formulario").count() == 0
    assert _videos_extraidos(carpeta_temp) == []


def test_espera_los_codigos_que_el_formulario_carga_tarde(pagina, archivos):
    ruta_zip, carpeta_temp = archivos
    _iniciar(pagina, [TEMA_CORRECTO], retrasoCodigos=1000)

    resultado = engine.subir_video_a_tema(
        pagina, _video(), ruta_zip, str(carpeta_temp), "V2204", "22042"
    )

    assert resultado == {"ok": True, "recurso": ARCHIVO_VIDEO}


def test_no_sube_si_el_candidato_validado_desaparece_de_la_lista(pagina, archivos):
    """Sin candidato validado no se extrae ni se adjunta el video a ningún tema."""
    ruta_zip, carpeta_temp = archivos
    _iniciar(
        pagina,
        [TEMA_AJENO, TEMA_CORRECTO],
        temasAlCancelar=[TEMA_AJENO],
    )

    resultado = engine.subir_video_a_tema(
        pagina, _video(), ruta_zip, str(carpeta_temp), "V2204", "22042"
    )

    assert resultado["ok"] is False
    assert "Programa: se esperaba V2204 y PRIZMA mostró V9999." in resultado["error"]
    assert pagina.evaluate("window.guardados") == []
    assert _videos_extraidos(carpeta_temp) == []


def test_prueba_el_segundo_candidato_si_el_primero_es_de_otro_programa(pagina, archivos):
    ruta_zip, carpeta_temp = archivos
    _iniciar(pagina, [TEMA_AJENO, TEMA_CORRECTO])

    resultado = engine.subir_video_a_tema(
        pagina, _video(), ruta_zip, str(carpeta_temp), "V2204", "22042"
    )

    assert resultado["ok"] is True
    assert pagina.evaluate("window.guardados") == [{"tema": 1, "archivo": ARCHIVO_VIDEO}]


def test_fallo_cierra_el_formulario_y_el_siguiente_video_sigue(pagina, archivos):
    ruta_zip, carpeta_temp = archivos
    _iniciar(pagina, [TEMA_AJENO])

    fallido = engine.upload_video_with_recovery(
        pagina, _video(), ruta_zip, str(carpeta_temp), "V2204", "22042"
    )

    assert fallido["ok"] is False
    assert "Captura:" in fallido["error"]
    assert (carpeta_temp / "sin_patch_fila_8.png").exists()
    assert pagina.locator("#formulario").count() == 0
    assert pagina.evaluate("window.guardados") == []

    _iniciar(pagina, [TEMA_CORRECTO])
    siguiente = engine.upload_video_with_recovery(
        pagina, _video(), ruta_zip, str(carpeta_temp), "V2204", "22042"
    )
    assert siguiente["ok"] is True


def test_encuentra_el_tema_si_una_consulta_vieja_responde_al_final(pagina, archivos):
    """La lista no debe quedarse con los resultados de un texto incompleto."""
    ruta_zip, carpeta_temp = archivos
    parecidos = [
        _parecido(str(numero), "SEMANA 9", "Unidad 9") for numero in range(4)
    ]
    relleno = [
        {**TEMA_CORRECTO, "nombre": "Características " + str(numero)}
        for numero in range(5)
    ]
    _iniciar(
        pagina,
        relleno + parecidos + [TEMA_CORRECTO],
        limiteFilas=5,
        respuestaDesordenada=True,
    )

    resultado = engine.subir_video_a_tema(
        pagina, _video(), ruta_zip, str(carpeta_temp), "V2204", "22042"
    )

    assert resultado == {"ok": True, "recurso": ARCHIVO_VIDEO}
    assert pagina.evaluate("window.guardados") == [{"tema": 9, "archivo": ARCHIVO_VIDEO}]


def test_espera_una_busqueda_de_prizma_que_tarda_varios_segundos(pagina, archivos):
    ruta_zip, carpeta_temp = archivos
    _iniciar(pagina, [TEMA_CORRECTO], retrasoBusqueda=9000)
    pagina.evaluate("document.getElementById('filas').innerHTML = ''")

    resultado = engine.subir_video_a_tema(
        pagina, _video(), ruta_zip, str(carpeta_temp), "V2204", "22042"
    )

    assert resultado == {"ok": True, "recurso": ARCHIVO_VIDEO}


def test_encuentra_el_tema_si_prizma_no_filtra_el_titulo_con_coma(pagina, archivos):
    ruta_zip, carpeta_temp = archivos
    relleno = [
        {**TEMA_CORRECTO, "nombre": "Otro tema " + str(numero)} for numero in range(5)
    ]
    _iniciar(pagina, relleno + [TEMA_CORRECTO], limiteFilas=5, ignorarComa=True)
    video = {**_video(), "nombre": "Características, Operaciones básicas."}
    pagina.evaluate(
        "(nombre) => { window.temas[5].nombre = nombre; }",
        "Características, Operaciones básicas",
    )

    resultado = engine.subir_video_a_tema(
        pagina, video, ruta_zip, str(carpeta_temp), "V2204", "22042"
    )

    assert resultado == {"ok": True, "recurso": ARCHIVO_VIDEO}
    assert pagina.evaluate("window.guardados") == [{"tema": 5, "archivo": ARCHIVO_VIDEO}]


def test_intentos_de_busqueda_terminan_en_el_tramo_mas_largo():
    assert engine._topic_search_attempts("Características, Operaciones básicas.") == [
        ("Características, Operaciones básicas", False, 15),
        ("Características, Operaciones básicas", True, 20),
        ("Operaciones básicas", False, 15),
    ]
    assert engine._topic_search_attempts("Tema sin coma")[2] == ("Tema sin coma", False, 15)


def test_no_sube_si_el_formulario_abierto_es_de_otro_tema(pagina, archivos):
    ruta_zip, carpeta_temp = archivos
    _iniciar(pagina, [{**TEMA_CORRECTO, "nombreFormulario": "Otro tema"}])

    resultado = engine.subir_video_a_tema(
        pagina, _video(), ruta_zip, str(carpeta_temp), "V2204", "22042"
    )

    assert resultado["ok"] is False
    assert "no corresponde al tema buscado" in resultado["error"]
    assert pagina.evaluate("window.guardados") == []
    assert _videos_extraidos(carpeta_temp) == []


@pytest.mark.parametrize("modo", ["vaciar", "quitar"])
def test_confirma_el_adjunto_por_la_tarjeta_aunque_prizma_vacie_el_input(
    pagina, archivos, modo
):
    """Reproduce el fallo real: el archivo llega, pero `input.files` queda vacío."""
    ruta_zip, carpeta_temp = archivos
    _iniciar(pagina, [TEMA_CORRECTO], modoAdjunto=modo, textoGuardar="Editar")

    resultado = engine.subir_video_a_tema(
        pagina, _video(), ruta_zip, str(carpeta_temp), "V2204", "22042"
    )

    assert resultado == {"ok": True, "recurso": ARCHIVO_VIDEO}
    assert pagina.evaluate("window.guardados") == [{"tema": 0, "archivo": ARCHIVO_VIDEO}]


def test_no_guarda_si_el_archivo_no_aparece_en_recursos(pagina, archivos, monkeypatch):
    ruta_zip, carpeta_temp = archivos
    espera_original = engine._wait_for_attached_video
    monkeypatch.setattr(
        engine,
        "_wait_for_attached_video",
        lambda pagina, indice, nombre: espera_original(
            pagina, indice, nombre, espera_segundos=1
        ),
    )
    _iniciar(pagina, [TEMA_CORRECTO], modoAdjunto="ignorar")
    pagina.evaluate(
        """() => document.addEventListener('change', evento => {
            if (evento.target.type === 'file') evento.target.value = '';
        })"""
    )

    resultado = engine.upload_video_with_recovery(
        pagina, _video(), ruta_zip, str(carpeta_temp), "V2204", "22042"
    )

    assert resultado["ok"] is False
    assert "PRIZMA no mostró el archivo adjunto" in resultado["error"]
    assert pagina.evaluate("window.guardados") == []
    assert pagina.locator("#formulario").count() == 0
    copia = carpeta_temp / "campo_recursos_fila_8.html"
    assert "Recursos" in copia.read_text(encoding="utf-8")


def test_ubicacion_de_fila_compara_semana_y_unidad_por_numero():
    celdas = ["Activo", "1", NOMBRE_TEMA, "SEMANA 1", "Unidad 1", "3"]

    assert engine._topic_row_matches_location(celdas, "", "Semana 1", "Unidad 1")
    assert not engine._topic_row_matches_location(celdas, "", "Semana 8", "Unidad 1")
    assert not engine._topic_row_matches_location(celdas, "", "Semana 1", "Unidad 3")
    assert engine._topic_row_matches_location(celdas, "", "", "")
    # El número 11 en otra columna (Orden) no se confunde con la semana.
    assert engine._topic_row_matches_location(
        ["Activo", "11", "Tema", "SEMANA 8"], "", "Semana 8", ""
    )
    assert engine._topic_row_matches_location(
        [], NOMBRE_TEMA + "\nSEMANA 1\nUnidad 1", "Semana 1", "Unidad 1"
    )
    # El texto de un <tr> llega separado por tabuladores.
    assert not engine._topic_row_matches_location(
        [], NOMBRE_TEMA + "\tSEMANA 8\tUnidad 1", "Semana 1", "Unidad 1"
    )


def test_el_error_indica_el_paso_de_playwright_que_fallo():
    error = TimeoutError(
        "Locator.click: Timeout 15000ms exceeded.\n"
        "Call log:\n"
        "  - <div class=\"overlay\"> intercepts pointer events\n"
    )

    detalle = engine._describe_video_error(error)

    assert "Locator.click: Timeout 15000ms exceeded." in detalle
    assert "intercepts pointer events" in detalle
    assert engine._describe_video_error(TimeoutError("")) == ""
