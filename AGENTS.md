# Instrucciones para agentes

Este archivo contiene reglas de trabajo; no duplica la guía de instalación, la guía funcional ni la arquitectura. La landing actual tiene tarjetas para Matrices, Cargue PRIZMA, Cargue Moodle y Automatizaciones; Control Tower y el acceso a PRIZMA administrativo son accesos directos, no tarjetas.

## Antes de cambiar

- Lee `CLAUDE.md` para arquitectura, convenciones y límites entre capas. Consulta `README.md` para instalación y uso breve, y `GUIA_DETALLADA.md` para el comportamiento funcional detallado; no copies su contenido aquí.
- Revisa `git status`, la rama y los cambios locales antes de editar. No sobrescribas trabajo existente.
- Sigue el flujo y los tests relacionados antes de modificar contratos o automatizaciones.

## Reglas críticas

- Usa siempre `.venv/bin/python` y `.venv/bin/pytest` (en Windows, el venv equivalente).
- No leas ni registres secretos; `.env`, `data/` y los perfiles de navegador son privados.
- PRIZMA apunta a producción por defecto. Prueba cambios de automatización en el ambiente de pruebas; un cargue real modifica la plataforma.
- Moodle solo se automatiza desde la instancia local y con Chromium visible.
- No hagas commit, push, cambio de rama ni descartes cambios sin autorización explícita.
- Mantén los errores para el usuario en lenguaje claro y actualiza `CLAUDE.md` con cada cambio de código. Actualiza `README.md` si cambia la instalación o el uso; `GUIA_DETALLADA.md` si cambia el comportamiento.

## Verificación

Desde la raíz del repositorio:

```bash
./.venv/bin/python -m pytest tests/ -q
git diff --check
```

Instalación, arranque y diagnóstico están en `README.md`; no repitas sus pasos aquí.
