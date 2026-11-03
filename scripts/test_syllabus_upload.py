"""Prueba aislada de la subida de syllabus a PRIZMA (sin matriz ni ZIP).

Abre Chromium, entra a PRIZMA con credenciales de variables de entorno,
navega a «Editar Asignatura por pensum» del curso de prueba y sube un PDF
de syllabus generado por este mismo script. No usa matriz, no usa ZIP de
recursos y no toca actividades: solo la ficha de la asignatura.

Uso (PowerShell, desde la raíz del repositorio):

    $env:AUTO_PRIZMA_URL_PRIZMA = '<URL del ambiente de pruebas>'
    $env:PRIZMA_TEST_USER       = '<usuario>'
    $env:PRIZMA_TEST_PASSWORD   = '<contrasena>'
    .\\.venv\\Scripts\\python scripts\\test_syllabus_upload.py

Opcionales:
    PRIZMA_TEST_FACULTAD, PRIZMA_TEST_PROGRAMA, PRIZMA_TEST_PENSUM,
    PRIZMA_TEST_NIVEL, PRIZMA_TEST_ASIGNATURA (defecto: 005 / Prueba)
    PRIZMA_TEST_HEADLESS=1     oculta el navegador
    PRIZMA_TEST_ESPERA=8       segundos que queda abierto al finalizar

La prueba se niega a correr contra producción salvo que se defina
AUTO_PRIZMA_TEST_ALLOW_PRODUCTION=1 (un cargue real modifica PRIZMA).
"""

import os
import sys
import tempfile

from playwright.sync_api import sync_playwright

# Permite ejecutar el script desde la raíz (python scripts/test_syllabus_upload.py)
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from auto_prizma.automation.prizma import engine  # noqa: E402
from auto_prizma.core.config import (  # noqa: E402
    CHROMIUM_ARGS,
    PRIZMA_ES_PRODUCCION,
    URL_PRIZMA,
    VIEWPORT_NAVEGADOR,
)

# Curso de la prueba: Programa/Pensum/Nivel «005 - Prueba» y asignatura
# «Prueba», según el formulario de PRIZMA del ambiente de pruebas.
CURSO_PRUEBA = {
    "facultad": os.environ.get("PRIZMA_TEST_FACULTAD", "005"),
    "programa": os.environ.get("PRIZMA_TEST_PROGRAMA", "005"),
    "pensum": os.environ.get("PRIZMA_TEST_PENSUM", "005"),
    "nivel": os.environ.get("PRIZMA_TEST_NIVEL", "005"),
    # El código se compara como palabra dentro de la fila: si la asignatura
    # tiene código propio, defínelo con PRIZMA_TEST_CODIGO_ASIGNATURA.
    "codigo_asignatura": os.environ.get("PRIZMA_TEST_CODIGO_ASIGNATURA", "Prueba"),
    "asignatura": os.environ.get("PRIZMA_TEST_ASIGNATURA", "Prueba"),
}


def build_test_syllabus_pdf(ruta):
    """Escribe un PDF mínimo y válido para la prueba de carga.

    Args:
        ruta: destino con extensión .pdf (PRIZMA valida por extensión).
    """
    contenido = (
        b"BT\n/F1 16 Tf\n72 720 Td\n"
        b"(Syllabus de prueba - Auto Prizma) Tj\n"
        b"/F1 12 Tf\n0 -30 Td\n"
        b"(Documento generado por scripts/test_syllabus_upload.py) Tj\n"
        b"0 -20 Td\n"
        b"(Ambiente de pruebas PRIZMA. Prueba aislada sin matriz ni ZIP.) Tj\n"
        b"ET\n"
    )
    objetos = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            b"/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>"
        ),
        (
            b"<< /Length " + str(len(contenido)).encode() + b" >>\n"
            b"stream\n" + contenido + b"endstream"
        ),
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]

    salida = bytearray(b"%PDF-1.4\n")
    offsets = []
    for numero, cuerpo in enumerate(objetos, 1):
        offsets.append(len(salida))
        salida += (str(numero) + " 0 obj\n").encode() + cuerpo + b"\nendobj\n"

    inicio_xref = len(salida)
    salida += b"xref\n0 " + str(len(objetos) + 1).encode() + b"\n"
    salida += b"0000000000 65535 f \n"
    for offset in offsets:
        salida += ("%010d 00000 n \n" % offset).encode()
    salida += (
        b"trailer\n<< /Size " + str(len(objetos) + 1).encode()
        + b" /Root 1 0 R >>\nstartxref\n"
        + str(inicio_xref).encode() + b"\n%%EOF\n"
    )

    with open(ruta, "wb") as archivo:
        archivo.write(salida)


def _instalar_volcado_tabla():
    """Con PRIZMA_TEST_DEBUG=1 guarda la tabla de asignaturas al llegar a ella.

    El botón de edición de la fila no tiene nombre accesible, así que hace
    falta volcar el DOM de la tabla ANTES de que el motor pulse el ojo.
    """
    original = engine._adoptar_pestana_abierta
    estado = {"carpeta": ""}

    def envolver(pagina, paginas_previas, espera_ms=1500):
        nueva = original(pagina, paginas_previas, espera_ms)
        if not estado["carpeta"]:
            try:
                html = nueva.content()
                if (
                    "Asignaturas por pensum" in html
                    and "Acciones" in html
                    and "Ir a unidad" in html
                ):
                    carpeta = tempfile.mkdtemp(prefix="syllabus_debug_tabla_")
                    with open(
                        os.path.join(carpeta, "tabla.html"), "w", encoding="utf-8"
                    ) as archivo:
                        archivo.write(html)
                    nueva.screenshot(
                        path=os.path.join(carpeta, "tabla.png"), full_page=True
                    )
                    estado["carpeta"] = carpeta
                    print("Tabla volcada en:", carpeta)
            except Exception as detalle:
                print("No se pudo volcar la tabla:", detalle)
        return nueva

    engine._adoptar_pestana_abierta = envolver


def main():
    print()
    print("======================================")
    print("PRUEBA AISLADA DE SYLLABUS EN PRIZMA")
    print("======================================")
    print("URL =", URL_PRIZMA)

    usuario = os.environ.get("PRIZMA_TEST_USER", "").strip()
    contrasena = os.environ.get("PRIZMA_TEST_PASSWORD", "").strip()
    if not usuario or not contrasena:
        print()
        print("Faltan las credenciales de la prueba.")
        print("Define PRIZMA_TEST_USER y PRIZMA_TEST_PASSWORD en el entorno.")
        return 2

    if PRIZMA_ES_PRODUCCION and os.environ.get("AUTO_PRIZMA_TEST_ALLOW_PRODUCTION") != "1":
        print()
        print("La URL apunta a PRODUCCION (admin.prizma.site).")
        print("Esta prueba modifica el curso real: usa el ambiente de pruebas")
        print("definiendo AUTO_PRIZMA_URL_PRIZMA con su URL (ver GUIA_DETALLADA.md)")
        print("(o define AUTO_PRIZMA_TEST_ALLOW_PRODUCTION=1 a sabiendas).")
        return 3

    esconder = os.environ.get("PRIZMA_TEST_HEADLESS") == "1"
    espera_ms = int(os.environ.get("PRIZMA_TEST_ESPERA", "8")) * 1000

    if os.environ.get("PRIZMA_TEST_DEBUG") == "1":
        _instalar_volcado_tabla()

    carpeta_temp = tempfile.mkdtemp(prefix="syllabus_test_")
    ruta_syllabus = os.path.join(carpeta_temp, "syllabus_prueba.pdf")
    build_test_syllabus_pdf(ruta_syllabus)

    preparacion = {
        "curso": CURSO_PRUEBA,
        "syllabus": True,
        "video_intro": "",
        "video_cierre": "",
    }

    print("Syllabus de prueba:", ruta_syllabus)
    print("Curso:", CURSO_PRUEBA)
    print("Navegador:", "oculto" if esconder else "visible")

    codigo = 1
    with sync_playwright() as p:
        navegador = p.chromium.launch(
            headless=esconder,
            args=list(CHROMIUM_ARGS),
        )
        pagina = navegador.new_page(viewport=dict(VIEWPORT_NAVEGADOR))
        try:
            print()
            print("Iniciando sesión en PRIZMA...")
            engine.iniciar_sesion_prizma(
                pagina, usuario, contrasena, abrir_actividades=False,
            )

            print()
            print("Navegando al formulario de la asignatura y subiendo syllabus...")
            acciones = engine.prepare_assignment(
                pagina, preparacion, "", ruta_syllabus, carpeta_temp,
            )

            print()
            print("Resumen de la prueba:")
            for accion in acciones:
                marca = {"ok": "✅", "omitido": "➖", "error": "❌"}.get(
                    accion["estado"], "•"
                )
                print(
                    "  " + marca + " " + accion["nombre"] + ": "
                    + (accion["detalle"] or accion["estado"])
                )

            syllabus = next(
                (a for a in acciones if a["nombre"] == "Syllabus"), None
            )
            guardar = next(
                (a for a in acciones if a["nombre"] == "Guardar cambios"), None
            )
            if syllabus and syllabus["estado"] == "ok" and guardar \
                    and guardar["estado"] == "ok":
                print()
                print("✅ PRUEBA EXITOSA: syllabus subido y formulario guardado.")
                codigo = 0
            else:
                print()
                print("⚠️  La prueba no completó la carga del syllabus (ver detalle).")
                codigo = 1
        except Exception as error:
            print()
            print("❌ La prueba falló:", type(error).__name__, "-", error)
            codigo = 1
            # Depuración: guarda la página actual (y el paso anterior con
            # Volver, que suele ser la tabla con el botón de edición).
            try:
                carpeta_debug = tempfile.mkdtemp(prefix="syllabus_debug_")

                def guardar(nombre):
                    with open(
                        os.path.join(carpeta_debug, nombre + ".html"),
                        "w", encoding="utf-8",
                    ) as archivo:
                        archivo.write(pagina.content())
                    pagina.screenshot(
                        path=os.path.join(carpeta_debug, nombre + ".png"),
                        full_page=True,
                    )

                guardar("pagina_actual")
                try:
                    pagina.go_back(wait_until="domcontentloaded", timeout=15000)
                    pagina.wait_for_timeout(1500)
                    guardar("pagina_anterior")
                except Exception:
                    pass
                print("Depuración guardada en:", carpeta_debug)
            except Exception as detalle:
                print("No se pudo guardar la depuración:", detalle)

        if espera_ms > 0:
            print()
            print("Manteniendo el navegador abierto", espera_ms // 1000, "segundos...")
            try:
                pagina.wait_for_timeout(espera_ms)
            except Exception:
                pass
        navegador.close()

    return codigo


if __name__ == "__main__":
    sys.exit(main())
