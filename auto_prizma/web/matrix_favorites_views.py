"""Vista del catálogo compartido de matrices y recursos favoritos."""

import html
from urllib.parse import urlsplit

from auto_prizma.web.icons import icon
from auto_prizma.web.layout import render_page


_CSS = """
.favoritos{display:grid;gap:20px}.favoritos-header h1{margin:0;font-size:clamp(26px,4vw,36px)}.favoritos-header p{color:var(--texto-2);margin:8px 0 0;line-height:1.6}
.favoritos-form{display:grid;grid-template-columns:1fr 1.5fr auto;gap:12px;align-items:end;padding:20px}.favoritos-form label{display:grid;gap:7px;font-weight:650}.favoritos-form input{width:100%;padding:11px 12px;border:1px solid var(--borde);border-radius:10px;background:var(--fondo);color:var(--texto)}.favoritos-form input:focus-visible{outline:0;border-color:var(--acento);box-shadow:0 0 0 4px var(--foco)}
.favoritos-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(min(100%,340px),1fr));gap:16px}.favorito-card{position:relative;isolation:isolate;overflow:hidden;display:grid;gap:0;min-width:0;padding:0;background:linear-gradient(135deg,var(--panel),var(--acento-suave));transition:transform .18s,border-color .18s,box-shadow .18s}.favorito-card::before{content:"";position:absolute;inset:0 auto 0 0;width:4px;background:linear-gradient(180deg,var(--verde),var(--acento));opacity:.9}.favorito-card:hover{transform:translateY(-3px);border-color:var(--acento-borde);box-shadow:var(--sombra)}.favorito-card-hitarea{position:absolute;inset:0;z-index:1;border-radius:inherit}.favorito-card-hitarea:focus-visible{outline:3px solid var(--acento);outline-offset:-4px}.favorito-card-main{pointer-events:none;position:relative;z-index:0;display:grid;grid-template-columns:48px minmax(0,1fr) auto;align-items:center;gap:14px;padding:19px 20px 15px 22px}.favorito-card-main>.icono-tile{width:48px;height:48px;border-radius:15px;box-shadow:var(--sombra-sm)}.favorito-card-main>.icono-tile .icono{width:23px;height:23px}.favorito-info{min-width:0}.favorito-kind{display:inline-flex;align-items:center;margin:0 0 6px;padding:3px 8px;border-radius:999px;background:var(--verde-suave);color:var(--verde);font-size:10px;line-height:1.2;font-weight:800;letter-spacing:.07em}.favorito-card h2{font-size:17px;line-height:1.3;margin:0;overflow-wrap:anywhere}.favorito-host{display:block;margin-top:4px;color:var(--muted);font-size:12px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}.favorito-open-label{display:inline-flex;align-items:center;gap:7px;padding:9px 12px;border:1px solid var(--acento-borde);border-radius:11px;background:var(--panel);color:var(--acento-texto);font-size:12px;font-weight:750;white-space:nowrap}.favorito-open-label .icono{width:15px;height:15px}.favorito-actions{position:relative;z-index:2;pointer-events:none;display:flex;align-items:center;justify-content:flex-end;gap:15px;margin:0 18px 0 22px;padding:10px 0 12px 62px;border-top:1px solid var(--borde)}.favorito-actions form{margin:0;pointer-events:auto}.favorito-actions>a,.favorito-actions button{pointer-events:auto;display:inline-flex;align-items:center;padding:3px 0;border:0;background:none;color:var(--texto-2);text-decoration:none;font-size:12px;font-weight:700;line-height:1.3;white-space:nowrap;cursor:pointer}.favorito-actions>a:hover{text-decoration:underline;text-underline-offset:3px;color:var(--acento-texto)}.favorito-actions button{color:var(--rojo)}.favorito-actions button:hover{color:var(--rojo-texto,var(--rojo))}.favorito-empty{padding:30px 22px;text-align:center;color:var(--texto-2)}.favorito-error{margin:0}.favorito-cancelar{display:inline-flex;align-items:center;text-decoration:none;padding:10px 12px}
@media(max-width:900px){.favoritos-grid{grid-template-columns:repeat(2,minmax(0,1fr))}.favoritos-form{grid-template-columns:1fr 1fr}.favoritos-form>button{grid-column:1/-1;justify-self:start}}
@media(max-width:600px){.favoritos-grid,.favoritos-form{grid-template-columns:1fr}.favoritos-form>button{grid-column:auto}.favorito-card-main{grid-template-columns:42px minmax(0,1fr);gap:11px;padding:15px 15px 13px 18px}.favorito-card-main>.icono-tile{width:42px;height:42px}.favorito-card-main>.icono-tile .icono{width:20px;height:20px}.favorito-open-label{grid-column:2;justify-self:start;margin-top:2px;padding:7px 10px}.favorito-actions{justify-content:flex-start;gap:14px;margin:0 15px 0 18px;padding:9px 0 11px 53px}}
.favoritos-header{position:relative;isolation:isolate;display:flex;align-items:center;justify-content:space-between;gap:26px;min-height:180px;padding:clamp(24px,4vw,38px);overflow:hidden;border:1px solid var(--borde);border-radius:24px;background:linear-gradient(115deg,var(--panel),color-mix(in srgb,var(--acento-suave) 45%,var(--panel)))}.favoritos-header::after{content:"";position:absolute;z-index:-1;width:360px;height:360px;right:-80px;top:-210px;border-radius:50%;background:radial-gradient(circle,color-mix(in srgb,var(--acento) 18%,transparent),transparent 68%);animation:favoritos-aura 8s ease-in-out infinite alternate}.favoritos-header-copy{max-width:850px;animation:favoritos-rise .5s ease both}.favoritos-header .eyebrow{display:inline-flex;align-items:center;gap:9px;color:var(--acento-texto);font-size:11px;font-weight:850;letter-spacing:.13em}.favoritos-header .eyebrow .icono{width:16px;height:16px}.favoritos-header h1{margin:11px 0 0;font-size:clamp(32px,4vw,46px);letter-spacing:-.045em;line-height:1.05}.favoritos-header p{max-width:760px;margin:12px 0 0;color:var(--texto-2);font-size:15px;line-height:1.65}.favoritos-header-art{position:relative;display:grid;place-items:center;flex:none;width:96px;height:96px;margin:0 7%;border:1px solid var(--acento-borde);border-radius:29px;background:color-mix(in srgb,var(--panel) 86%,transparent);color:var(--acento-texto);box-shadow:var(--sombra);animation:favoritos-float 4s ease-in-out infinite}.favoritos-header-art>.icono{width:42px;height:42px;stroke-width:1.5}.favoritos-header-art::before,.favoritos-header-art::after{content:"";position:absolute;inset:-13px;border:1px solid var(--borde-2);border-radius:37px;animation:favoritos-spin 18s linear infinite}.favoritos-header-art::after{inset:-25px;border-style:dashed;animation-direction:reverse}.favoritos-form-panel{overflow:hidden}.favoritos-form-heading{display:flex;align-items:center;gap:12px;padding:18px 20px 0}.favoritos-form-heading .icono-tile{width:40px;height:40px;border-radius:13px;background:var(--acento-suave);color:var(--acento-texto)}.favoritos-form-heading .icono{width:20px;height:20px}.favoritos-form-heading strong{display:block;font-size:14px}.favoritos-form-heading small{display:block;margin-top:3px;color:var(--muted);font-size:12px}.favoritos-form{padding-top:16px}.favoritos-form>button{min-height:44px;white-space:nowrap}.favorito-card{animation:favoritos-rise .45s ease both}.favorito-card:nth-child(2){animation-delay:.06s}.favorito-card:nth-child(3){animation-delay:.12s}.favorito-card:nth-child(4){animation-delay:.18s}.favorito-card:nth-child(5){animation-delay:.24s}.favorito-card:nth-child(6){animation-delay:.3s}.favorito-card:hover .favorito-card-main>.icono-tile{transform:scale(1.04);box-shadow:0 8px 22px color-mix(in srgb,var(--acento) 18%,transparent)}.favorito-card-main>.icono-tile{transition:transform .2s ease,box-shadow .2s ease}.favorito-card::after{content:"";position:absolute;z-index:-1;width:190px;height:190px;right:-100px;bottom:-120px;border-radius:50%;background:radial-gradient(circle,color-mix(in srgb,var(--acento) 13%,transparent),transparent 70%);opacity:0;transition:opacity .2s ease}.favorito-card:hover::after{opacity:1}
@keyframes favoritos-rise{from{opacity:0;transform:translateY(12px)}to{opacity:1;transform:translateY(0)}}@keyframes favoritos-float{50%{transform:translateY(-6px)}}@keyframes favoritos-spin{to{transform:rotate(360deg)}}@keyframes favoritos-aura{to{transform:translate(-30px,25px);opacity:.65}}
@media(max-width:700px){.favoritos-header{min-height:0;padding:24px}.favoritos-header-art{width:78px;height:78px;margin:0 3% 0 0;border-radius:23px}.favoritos-header-art>.icono{width:34px;height:34px}}
@media(max-width:520px){.favoritos-header{padding:21px}.favoritos-header-art{display:none}.favoritos-form-heading{padding:16px 16px 0}.favoritos-form{padding:14px 16px 16px}.favoritos-form-panel .favoritos-form>button{width:100%}}
@media(prefers-reduced-motion:reduce){.favoritos-header-copy,.favoritos-header-art,.favorito-card{animation:none}.favoritos-header::after,.favoritos-header-art::before,.favoritos-header-art::after{animation:none}.favorito-card,.favorito-card-main>.icono-tile,.favorito-card::after{transition:none}}
"""


def _e(value):
    return html.escape(str(value or ""), quote=True)


def render_favorites_page(favorites, *, editing=None, error=""):
    if editing:
        action = "/matrices-favoritas/" + _e(editing["id"]) + "/editar"
        button = "Guardar cambios"
        name = editing["nombre"]
        url = editing["url"]
        cancel = '<a class="boton secundario favorito-cancelar" href="/matrices-favoritas">Cancelar</a>'
    else:
        action = "/matrices-favoritas/agregar"
        button = "Crear tarjeta"
        name = ""
        url = ""
        cancel = ""

    error_html = (
        '<div class="aviso error favorito-error" role="alert">' + icon("alerta-circulo")
        + "<div><strong>" + _e(error) + "</strong></div></div>"
    ) if error else ""
    form = (
        '<section class="panel favoritos-form-panel"><div class="favoritos-form-heading"><span class="icono-tile">' + icon("mas")
        + '</span><div><strong>' + ("Editar acceso guardado" if editing else "Agregar una matriz")
        + '</strong><small>El nombre será visible en la tarjeta; el enlace se abrirá en una pestaña nueva.</small></div></div>'
        '<form class="favoritos-form" method="post" action="' + action + '">'
        '<label for="favorito-nombre">Nombre de la matriz<input id="favorito-nombre" name="nombre" '
        'maxlength="120" required value="' + _e(name) + '" placeholder="Ej.: Matriz de control de cargue"></label>'
        '<label for="favorito-url">Enlace de la matriz<input id="favorito-url" name="url" type="url" '
        'maxlength="2048" required value="' + _e(url) + '" placeholder="https://docs.google.com/spreadsheets/..."></label>'
        '<button class="boton" type="submit">' + icon("mas") + button + '</button>' + cancel + '</form></section>'
    )

    if favorites:
        cards = []
        for favorite in favorites:
            fid = _e(favorite["id"])
            host = urlsplit(favorite["url"]).hostname or favorite["url"]
            escaped_name = _e(favorite["nombre"])
            escaped_url = _e(favorite["url"])
            cards.append(
                '<article class="panel favorito-card"><a class="favorito-card-hitarea" href="' + escaped_url
                + '" target="_blank" rel="noopener noreferrer" aria-label="Abrir matriz: ' + escaped_name + '"></a>'
                '<div class="favorito-card-main" aria-hidden="true"><span class="icono-tile verde">' + icon("hoja")
                + '</span><div class="favorito-info"><span class="favorito-kind">MATRIZ</span><h2>'
                + escaped_name + '</h2><small class="favorito-host">' + _e(host)
                + '</small></div><span class="favorito-open-label">Abrir matriz ' + icon("externo")
                + '</span></div><div class="favorito-actions"><a href="/matrices-favoritas?editar=' + fid + '">Editar</a>'
                '<form method="post" action="/matrices-favoritas/' + fid
                + '/eliminar" data-confirmar="¿Eliminar esta tarjeta de favoritos?"><button '
                'type="submit">Eliminar</button></form></div></article>'
            )
        list_html = '<section class="favoritos-grid" aria-label="Matrices y recursos guardados">' + "".join(cards) + "</section>"
    else:
        list_html = (
            '<section class="panel favorito-empty"><strong>Aún no tienes matrices guardadas.</strong>'
            '<p>Agrega el nombre y el enlace para crear tu primera tarjeta.</p></section>'
        )

    content = (
        '<div class="favoritos"><header class="favoritos-header"><div class="favoritos-header-copy"><span class="eyebrow">'
        + icon("hoja") + ' ACCESOS GUARDADOS</span><h1>Matrices</h1><p>Guarda aquí las matrices que consultas con más frecuencia. '
        'Se conservan en este equipo hasta que las elimines manualmente; todos los usuarios de esta instalación comparten la lista.</p></div>'
        '<div class="favoritos-header-art" aria-hidden="true">' + icon("hoja") + '</div></header>'
        + error_html + form + list_html + '</div>'
    )
    page_js = r'''document.addEventListener("submit",function(event){var form=event.target.closest("form[data-confirmar]");if(form&&!window.confirm(form.dataset.confirmar))event.preventDefault();});'''
    return render_page("Matrices", content, active="matrices", page_css=_CSS, page_js=page_js)
