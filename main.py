"""Punto de entrada de Auto Prizma Pro.

Arma la aplicacion web a partir del paquete auto_prizma:

    uvicorn main:app

El orden de los imports importa: primero se aplican los ajustes sobre el
motor de PRIZMA (auto_prizma.automation.prizma.engine) y luego se registran
las rutas en el mismo orden de siempre. El modulo de tests evaluativos se
monta al final.
"""

from auto_prizma.core.application import app

# Rutas. Cada modulo registra sus rutas sobre `app` al importarse.
import auto_prizma.api.routes.static_files  # noqa: F401
import auto_prizma.api.routes.auth  # noqa: F401
import auto_prizma.api.routes.home  # noqa: F401
import auto_prizma.api.routes.matrix_favorites  # noqa: F401
import auto_prizma.api.routes.n8n  # noqa: F401
import auto_prizma.api.routes.analysis  # noqa: F401
import auto_prizma.api.routes.uploads  # noqa: F401
import auto_prizma.api.routes.reports  # noqa: F401
import auto_prizma.api.routes.courses  # noqa: F401
import auto_prizma.api.routes.course_audit  # noqa: F401
import auto_prizma.api.routes.auditor  # noqa: F401
import auto_prizma.api.routes.health  # noqa: F401
import auto_prizma.api.routes.moodle_resources  # noqa: F401
import auto_prizma.api.routes.moodle_audit  # noqa: F401

from auto_prizma.core.config import PRIZMA_BASE_URL, PRIZMA_ES_PRODUCCION, RESULTADOS_DIR
from auto_prizma.services.history import _historial_del_usuario
from auto_prizma.services.upload_jobs import TRABAJOS


# ============================================================
# MODULO TESTS
# ============================================================

from auto_prizma.evaluative_tests.routes import router as tests_evaluativos_router

app.state.trabajos_cargue = TRABAJOS
app.state.historial_cargues = _historial_del_usuario
app.state.resultados_dir = RESULTADOS_DIR
app.include_router(tests_evaluativos_router)

print(
    "PRIZMA:",
    PRIZMA_BASE_URL,
    "(produccion)" if PRIZMA_ES_PRODUCCION else "(AMBIENTE DE PRUEBAS)",
)
