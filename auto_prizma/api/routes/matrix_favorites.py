"""Rutas para administrar tarjetas compartidas de matrices y recursos favoritos."""

from fastapi import Form
from fastapi.responses import HTMLResponse, RedirectResponse

from auto_prizma.core.application import app
from auto_prizma.services.matrix_favorites import (
    add_favorite,
    delete_favorite,
    get_favorite,
    list_favorites,
    update_favorite,
)
from auto_prizma.web.matrix_favorites_views import render_favorites_page


@app.get("/matrices-favoritas", response_class=HTMLResponse)
def matrices_favoritas(editar: str = ""):
    editing = get_favorite(editar) if editar else None
    return render_favorites_page(list_favorites(), editing=editing)


@app.post("/matrices-favoritas/agregar", response_class=HTMLResponse)
def agregar_matriz_favorita(nombre: str = Form(""), url: str = Form("")):
    try:
        add_favorite(nombre, url)
    except ValueError as error:
        return HTMLResponse(
            render_favorites_page(list_favorites(), error=str(error)),
            status_code=400,
        )
    return RedirectResponse("/matrices-favoritas", status_code=303)


@app.post("/matrices-favoritas/{favorite_id}/editar", response_class=HTMLResponse)
def editar_matriz_favorita(favorite_id: str, nombre: str = Form(""), url: str = Form("")):
    try:
        updated = update_favorite(favorite_id, nombre, url)
    except ValueError as error:
        return HTMLResponse(
            render_favorites_page(
                list_favorites(),
                editing={"id": favorite_id, "nombre": nombre, "url": url},
                error=str(error),
            ),
            status_code=400,
        )
    if updated is None:
        return HTMLResponse("No se encontró esa tarjeta.", status_code=404)
    return RedirectResponse("/matrices-favoritas", status_code=303)


@app.post("/matrices-favoritas/{favorite_id}/eliminar")
def eliminar_matriz_favorita(favorite_id: str):
    if not delete_favorite(favorite_id):
        return HTMLResponse("No se encontró esa tarjeta.", status_code=404)
    return RedirectResponse("/matrices-favoritas", status_code=303)
