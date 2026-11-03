"""Middleware que exige sesion y maneja el login.
"""

from fastapi import (
    Form,
    Request as FastAPIRequest,
)
from fastapi.responses import (
    HTMLResponse,
    JSONResponse,
    RedirectResponse,
)
import html

from auto_prizma.core.application import app
from auto_prizma.web.icons import icon
from auto_prizma.web.layout import render_public_page
from auto_prizma.services.auth import (
    SESION_COOKIE,
    SESION_HORAS,
    USUARIO_ACTUAL,
    _autenticar,
    _bloqueado,
    _cargar_usuarios,
    _cookie_segura,
    _firmar_sesion,
    _limpiar_fallos,
    _normalizar_usuario,
    _registrar_fallo,
    _usuario_de_request,
    local_identity_for,
    ACCESO_LOCAL_DIRECTO,
)


# ============================================================
# GOOGLE OAUTH - CONECTAR / CALLBACK / DESCONECTAR
# ============================================================

# ============================================================
# LOGIN
# ============================================================

RUTAS_PUBLICAS = {
    "/login",
    "/favicon.ico",
    "/auto-prizma-logo.png",
    "/app.css",
    "/app.js",
}


_CSS_LOGIN = """
.marca-login { display: flex; align-items: center; gap: 12px; margin: 0 0 26px; }
.marca-login img { width: 46px; height: 46px; object-fit: contain; }
"""


def _pagina_login(error="", usuario_previo=""):
    plantilla = """
<form class="panel tarjeta-formulario" method="post" action="/login">
  <div class="marca-login">
    <img src="/auto-prizma-logo.png" alt="" width="46" height="46">
    <span class="marca-texto"><strong>Cargue Prizma Pro</strong><small>Cargue Prizma</small></span>
  </div>
  <h1>Ingresar</h1>
  <p class="sub">Usa el usuario que te entregaron.</p>
  __ERROR__
  <label for="usuario">Usuario</label>
  <input id="usuario" name="usuario" autocomplete="username" required
         value="__USUARIO__" autofocus>
  <label for="contrasena">Contraseña</label>
  <input id="contrasena" name="contrasena" type="password"
         autocomplete="current-password" required>
  <button class="boton" type="submit">Entrar</button>
  <p class="pie">Cada persona ve únicamente sus propios cargues,<br>su historial y sus reportes.</p>
</form>"""

    bloque_error = ""
    if error:
        bloque_error = (
            '<div class="aviso error" role="alert">' + icon("alerta-circulo")
            + "<div><strong>" + html.escape(str(error)) + "</strong></div></div>"
        )

    contenido = plantilla.replace(
        "__ERROR__",
        bloque_error,
    ).replace(
        "__USUARIO__",
        html.escape(str(usuario_previo or ""), quote=True),
    )
    return render_public_page("Ingresar", contenido, page_css=_CSS_LOGIN)


@app.middleware("http")
async def exigir_sesion(request: FastAPIRequest, call_next):
    ruta = request.url.path

    if ruta in RUTAS_PUBLICAS:
        return await call_next(request)

    # En el equipo local se usa una identidad fija; fuera de loopback se exige sesión.
    identidad_local = local_identity_for(request)
    usuario = identidad_local or _usuario_de_request(request)

    if not usuario:
        acepta = str(request.headers.get("accept") or "")

        if ruta.startswith("/estado/") or "application/json" in acepta:
            return JSONResponse(
                {"error": "Sesion expirada", "login": "/login"},
                status_code=401,
            )

        return RedirectResponse("/login", status_code=303)

    testigo = USUARIO_ACTUAL.set(usuario)
    testigo_local = ACCESO_LOCAL_DIRECTO.set(identidad_local is not None)
    request.state.usuario = usuario

    try:
        return await call_next(request)
    finally:
        ACCESO_LOCAL_DIRECTO.reset(testigo_local)
        USUARIO_ACTUAL.reset(testigo)


@app.get("/login", response_class=HTMLResponse)
def login_formulario(request: FastAPIRequest):
    if _usuario_de_request(request) or local_identity_for(request):
        return RedirectResponse("/", status_code=303)

    return HTMLResponse(_pagina_login())


@app.post("/login", response_class=HTMLResponse)
def login_enviar(
    request: FastAPIRequest,
    usuario: str = Form(...),
    contrasena: str = Form(...),
):
    if local_identity_for(request):
        return RedirectResponse("/", status_code=303)

    usuario = _normalizar_usuario(usuario)

    origen = str(
        request.client.host if request.client else "desconocido"
    )
    clave_intentos = usuario + "|" + origen

    espera = _bloqueado(clave_intentos)

    if espera:
        return HTMLResponse(
            _pagina_login(
                "Demasiados intentos fallidos. Espera "
                + str(espera)
                + " segundos.",
                usuario,
            ),
            status_code=429,
        )

    if not _cargar_usuarios():
        return HTMLResponse(
            _pagina_login(
                "Todavia no hay usuarios creados. Ejecuta: "
                "python scripts/manage_users.py crear",
                usuario,
            ),
            status_code=503,
        )

    autenticado = _autenticar(usuario, contrasena)

    if not autenticado:
        _registrar_fallo(clave_intentos)
        return HTMLResponse(
            _pagina_login("Usuario o contrasena incorrectos.", usuario),
            status_code=401,
        )

    _limpiar_fallos(clave_intentos)

    respuesta = RedirectResponse("/", status_code=303)
    respuesta.set_cookie(
        SESION_COOKIE,
        _firmar_sesion(autenticado),
        max_age=SESION_HORAS * 3600,
        httponly=True,
        samesite="lax",
        secure=_cookie_segura(),
        path="/",
    )

    print("Login OK:", autenticado, "desde", origen)

    return respuesta
