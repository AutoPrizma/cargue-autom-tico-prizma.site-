"""Rutas del landing y del espacio de automatizaciones n8n."""

from fastapi.responses import HTMLResponse

from auto_prizma.core.application import app
from auto_prizma.web.landing_views import render_landing_page, render_n8n_page


@app.get("/", response_class=HTMLResponse)
def home():
    return render_landing_page()


@app.get("/automatizaciones-n8n", response_class=HTMLResponse)
def n8n_automations():
    return render_n8n_page()
