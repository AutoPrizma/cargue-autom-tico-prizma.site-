"""Landing y página de enlaces de automatizaciones externas."""

import html

from auto_prizma.web.icons import icon
from auto_prizma.web.layout import CONTROL_TOWER_URL, render_page
from auto_prizma.services.n8n import public_flow_catalog


_LANDING_CSS = """
.landing{display:grid;gap:22px;max-width:1500px;margin:0 auto}
.landing-hero{position:relative;isolation:isolate;display:grid;grid-template-columns:minmax(0,1.2fr) minmax(260px,.8fr);gap:30px;align-items:center;min-height:330px;padding:clamp(28px,5vw,58px);overflow:hidden;background:linear-gradient(120deg,var(--panel),color-mix(in srgb,var(--acento-suave) 48%,var(--panel)))}
.landing-hero::before{content:"";position:absolute;z-index:-1;width:460px;height:460px;right:-90px;top:-210px;border-radius:50%;background:radial-gradient(circle,color-mix(in srgb,var(--acento) 13%,transparent),transparent 68%);animation:landing-glow 8s ease-in-out infinite alternate}
.landing-hero-copy{max-width:760px;animation:landing-rise .65s ease both}
.landing-eyebrow{display:inline-flex;align-items:center;gap:9px;margin-bottom:17px;color:var(--acento-texto);font-size:11px;font-weight:850;letter-spacing:.13em;text-transform:uppercase}
.landing-eyebrow::before{content:"";width:8px;height:8px;border-radius:50%;background:var(--acento);box-shadow:0 0 0 5px var(--acento-suave)}
.landing-hero h1{max-width:760px;margin:0;font-size:clamp(34px,5.2vw,62px);font-weight:850;line-height:1.02;letter-spacing:-.055em}
.landing-hero h1 span{color:var(--acento-texto)}
.landing-hero-copy>p{max-width:650px;margin:17px 0 0;color:var(--texto-2);font-size:clamp(15px,1.5vw,17px);line-height:1.65}
.landing-hero-actions{display:flex;gap:11px;flex-wrap:wrap;margin-top:24px}
.landing-hero-actions .boton{min-height:46px;padding-inline:17px}
.landing-hero-actions .boton.secundario{background:var(--panel)}
.landing-art{position:relative;display:grid;place-items:center;min-height:245px;animation:landing-rise .75s .08s ease both}
.landing-orbit{position:absolute;width:220px;aspect-ratio:1;border:1px solid var(--borde-2);border-top-color:var(--acento);border-radius:50%;animation:landing-spin 24s linear infinite}
.landing-orbit::before,.landing-orbit::after{content:"";position:absolute;width:8px;height:8px;border-radius:50%;background:var(--acento);box-shadow:0 0 0 5px var(--acento-suave)}
.landing-orbit::before{left:27px;top:37px}.landing-orbit::after{right:14px;bottom:50px;width:6px;height:6px}
.landing-orbit-inner{width:150px;border:1px dashed var(--borde-2);border-right-color:var(--acento);animation:landing-spin 18s linear infinite reverse}
.landing-core{position:relative;display:grid;place-items:center;width:104px;height:104px;border:1px solid var(--acento-borde);border-radius:30px;background:var(--panel);color:var(--acento-texto);box-shadow:0 16px 50px color-mix(in srgb,var(--acento) 15%,transparent);animation:landing-float 4s ease-in-out infinite}
.landing-core .icono{width:45px;height:45px;stroke-width:1.55}
.landing-art-label{position:absolute;right:3%;bottom:5%;display:flex;align-items:center;gap:9px;padding:11px 14px;border:1px solid var(--borde);border-radius:14px;background:var(--panel);color:var(--texto-2);font-size:12px;font-weight:750;box-shadow:var(--sombra-sm)}
.landing-art-label .icono{width:17px;height:17px;color:var(--acento-texto)}
.landing-section-heading{display:flex;justify-content:space-between;align-items:end;gap:14px;padding:0 2px}
.landing-section-heading h2{margin:0;font-size:18px;letter-spacing:-.02em}
.landing-section-heading p{margin:0;color:var(--muted);font-size:12px}
.landing-cards{display:grid;grid-template-columns:repeat(4,minmax(0,1fr));gap:14px}
.landing-card{position:relative;display:flex;flex-direction:column;align-items:stretch;min-width:0;min-height:252px;padding:20px;text-decoration:none;color:var(--texto);overflow:hidden;animation:landing-rise .5s ease both;transition:transform .2s ease,border-color .2s ease,box-shadow .2s ease,background .2s ease}
.landing-card:nth-child(2){animation-delay:.06s}.landing-card:nth-child(3){animation-delay:.12s}.landing-card:nth-child(4){animation-delay:.18s}
.landing-card::after{content:"";position:absolute;inset:auto -30% -64% -30%;height:150px;border-radius:50%;background:radial-gradient(ellipse,color-mix(in srgb,var(--acento) 9%,transparent),transparent 70%);opacity:0;transition:opacity .2s ease;pointer-events:none}
.landing-card:hover{transform:translateY(-4px);border-color:var(--acento-borde);box-shadow:var(--sombra);background:var(--panel)}.landing-card:hover::after{opacity:1}
.landing-card:focus-visible{outline:3px solid var(--foco);outline-offset:3px}
.landing-card-top{display:flex;justify-content:space-between;align-items:center;gap:10px}
.landing-card .icono-tile{width:48px;height:48px;border-radius:14px;background:var(--acento-suave);color:var(--acento-texto)}
.landing-card .icono-tile .icono{width:23px;height:23px}
.landing-card-index{color:var(--muted);font-size:10px;font-weight:800;letter-spacing:.1em}
.landing-card h3{margin:23px 0 0;font-size:19px;letter-spacing:-.025em}
.landing-card p{margin:8px 0 24px;color:var(--muted);font-size:13px;line-height:1.6}
.landing-card-link{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-top:auto;padding-top:14px;border-top:1px solid var(--borde);color:var(--acento-texto);font-size:13px;font-weight:800}
.landing-card-link .icono{width:18px;height:18px;transition:transform .2s ease}.landing-card:hover .landing-card-link .icono{transform:translateX(4px)}
.landing-footnote{display:flex;align-items:center;gap:11px;padding:14px 18px;color:var(--texto-2);font-size:12px;line-height:1.5}
.landing-footnote .icono{width:18px;height:18px;flex:none;color:var(--acento-texto)}
.n8n-empty{display:grid;justify-items:center;text-align:center;gap:12px;padding:50px 24px}.n8n-empty .icono-tile{width:64px;height:64px}.n8n-empty h2{margin:4px 0 0}.n8n-empty p{max-width:570px;margin:0;color:var(--muted);line-height:1.6}
.n8n-hero{position:relative;isolation:isolate;display:flex;align-items:center;justify-content:space-between;gap:24px;min-height:190px;padding:clamp(24px,4vw,42px);overflow:hidden;border:1px solid var(--borde);border-radius:24px;background:linear-gradient(115deg,var(--panel),color-mix(in srgb,var(--acento-suave) 46%,var(--panel)))}.n8n-hero::after{content:"";position:absolute;z-index:-1;width:390px;height:390px;right:-95px;top:-210px;border-radius:50%;background:radial-gradient(circle,color-mix(in srgb,var(--acento) 20%,transparent),transparent 68%);animation:n8n-aura 8s ease-in-out infinite alternate}.n8n-hero-copy{max-width:720px;animation:landing-rise .55s ease both}.n8n-hero .eyebrow{display:inline-flex;align-items:center;gap:9px;color:var(--acento-texto);font-size:11px;font-weight:850;letter-spacing:.13em}.n8n-hero h1{margin:12px 0 0;font-size:clamp(32px,4vw,48px);letter-spacing:-.045em;line-height:1.05}.n8n-hero p{margin:12px 0 0;color:var(--texto-2);font-size:16px;line-height:1.6}.n8n-hero-mark{position:relative;display:grid;place-items:center;flex:none;width:112px;height:112px;margin:0 7%;border:1px solid var(--acento-borde);border-radius:32px;background:color-mix(in srgb,var(--panel) 85%,transparent);color:var(--acento-texto);box-shadow:var(--sombra);animation:landing-float 4s ease-in-out infinite}.n8n-hero-mark>.icono{width:48px;height:48px;stroke-width:1.5}.n8n-hero-mark::before,.n8n-hero-mark::after{content:"";position:absolute;inset:-15px;border:1px solid var(--borde-2);border-radius:40px;animation:n8n-orbit 16s linear infinite}.n8n-hero-mark::after{inset:-29px;border-style:dashed;animation-direction:reverse}.n8n-flow-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:16px}.n8n-flow{position:relative;isolation:isolate;padding:24px;display:flex;flex-direction:column;align-items:flex-start;min-height:260px;overflow:hidden;animation:landing-rise .48s ease both;transition:transform .2s ease,border-color .2s ease,box-shadow .2s ease,background .2s ease}.n8n-flow:nth-child(2){animation-delay:.06s}.n8n-flow:nth-child(3){animation-delay:.12s}.n8n-flow:nth-child(4){animation-delay:.18s}.n8n-flow:nth-child(5){animation-delay:.24s}.n8n-flow:nth-child(6){animation-delay:.3s}.n8n-flow::after{content:"";position:absolute;z-index:-1;width:210px;height:210px;right:-100px;bottom:-120px;border-radius:50%;background:radial-gradient(circle,color-mix(in srgb,var(--acento) 13%,transparent),transparent 70%);opacity:0;transition:opacity .2s ease}.n8n-flow:hover{transform:translateY(-4px);border-color:var(--acento-borde);box-shadow:var(--sombra);background:var(--panel)}.n8n-flow:hover::after{opacity:1}.n8n-flow-top{display:flex;align-items:center;justify-content:space-between;gap:12px;width:100%}.n8n-flow-icon{display:grid;place-items:center;width:46px;height:46px;border:1px solid var(--acento-borde);border-radius:14px;background:var(--acento-suave);color:var(--acento-texto)}.n8n-flow-icon .icono{width:23px;height:23px}.n8n-flow .eyebrow{display:flex;align-items:center;gap:7px;color:var(--texto-2);font-size:12px;font-weight:750}.n8n-flow h2{margin:18px 0 0;font-size:21px;letter-spacing:-.025em}.n8n-flow p{color:var(--muted);line-height:1.55}.n8n-flow .boton{margin-top:auto;cursor:pointer}.n8n-flow .boton .icono{transition:transform .2s ease}.n8n-flow .boton:hover .icono{transform:translateX(4px)}.n8n-code{padding:4px 7px;border:1px solid var(--acento-borde);border-radius:7px;background:var(--acento-suave);font:750 10px ui-monospace,monospace;color:var(--acento-texto)}.n8n-state{display:inline-flex;align-items:center;gap:7px;font-size:12px;color:var(--texto-2);margin:0 0 12px}.n8n-state[data-configured="true"]::before{content:"";width:7px;height:7px;border-radius:50%;background:var(--verde);box-shadow:0 0 0 4px color-mix(in srgb,var(--verde) 14%,transparent)}.n8n-state[data-configured="false"]{color:var(--muted)}.n8n-dialog{position:fixed;inset:0;z-index:1000;background:color-mix(in srgb,var(--texto) 58%,transparent);display:none;place-items:center;padding:18px}.n8n-dialog[open]{display:grid}.n8n-dialog-card{position:relative;width:min(580px,100%);max-height:90vh;overflow:auto;padding:28px;background:var(--panel);color:var(--texto);border:1px solid var(--borde);border-radius:20px;box-shadow:var(--sombra)}.n8n-dialog-card h2{margin:8px 40px 8px 0}.n8n-close{position:absolute;right:18px;top:18px}.n8n-form{display:grid;gap:16px;margin-top:22px}.n8n-form label{display:grid;gap:7px;font-weight:650}.n8n-form input,.n8n-form select{width:100%;padding:12px;border:1px solid var(--borde);border-radius:10px;background:var(--fondo);color:var(--texto)}.n8n-hint{font-size:12px;color:var(--muted);font-weight:400}.n8n-result{padding:16px;border:1px solid var(--borde);border-radius:12px;margin-top:18px;white-space:pre-wrap}.n8n-result[data-ok="false"]{border-color:var(--rojo)}
.n8n-result[data-loading="true"]{border-color:var(--acento)}.n8n-result[data-loading="true"] strong::before{content:"";display:inline-block;width:12px;height:12px;margin-right:8px;border:2px solid var(--acento);border-right-color:transparent;border-radius:50%;vertical-align:-1px;animation:n8n-giro .8s linear infinite}@keyframes n8n-giro{to{transform:rotate(360deg)}}.n8n-result a{display:inline-block;margin-top:12px}.n8n-result a+a{margin-left:16px}.n8n-result ul{margin:6px 0 0;padding-left:18px;white-space:normal}.n8n-hidden{display:none!important}
.n8n-dialog{inset:0;width:100%;max-width:none;height:100%;max-height:none;margin:0;padding:18px;border:0;background:transparent;color:var(--texto)}.n8n-dialog::backdrop{background:var(--superposicion);backdrop-filter:blur(4px);-webkit-backdrop-filter:blur(4px)}
.n8n-form input:focus-visible,.n8n-form select:focus-visible{outline:0;border-color:var(--acento);box-shadow:0 0 0 4px var(--foco)}.n8n-form input::placeholder{color:var(--tenue)}
@keyframes landing-rise{from{opacity:0;transform:translateY(14px)}to{opacity:1;transform:translateY(0)}}
@keyframes landing-spin{to{transform:rotate(360deg)}}
@keyframes landing-float{50%{transform:translateY(-7px)}}
@keyframes landing-glow{to{transform:translate(-45px,38px);opacity:.65}}
@media(max-width:1250px){.landing-cards{grid-template-columns:repeat(3,minmax(0,1fr))}}
@media(max-width:1100px){.landing-cards{grid-template-columns:repeat(2,minmax(0,1fr))}.landing-hero{grid-template-columns:minmax(0,1fr) 250px}.landing-orbit{width:190px}.landing-orbit-inner{width:130px}}
@media(max-width:760px){.landing-hero{grid-template-columns:1fr;min-height:0}.landing-art{display:none}.landing-hero h1{font-size:clamp(34px,8vw,52px)}}
@keyframes n8n-orbit{to{transform:rotate(360deg)}}@keyframes n8n-aura{to{transform:translate(-35px,30px);opacity:.65}}
@media(max-width:760px){.n8n-hero-mark{margin:0 5% 0 0;width:84px;height:84px;border-radius:25px}.n8n-hero-mark>.icono{width:38px;height:38px}}
@media(max-width:560px){.landing{gap:16px}.landing-hero{padding:24px 20px}.landing-cards,.n8n-flow-grid{grid-template-columns:1fr}.landing-card{min-height:210px;padding:18px}.landing-card h3{margin-top:18px}.landing-section-heading{align-items:start;flex-direction:column;gap:4px}.landing-footnote{align-items:flex-start}.n8n-dialog-card{padding:22px}.n8n-hero{min-height:0;padding:24px 20px}.n8n-hero-mark{display:none}.n8n-flow{min-height:235px;padding:20px}}
@media(prefers-reduced-motion:reduce){.landing-hero-copy,.landing-art,.landing-card,.n8n-hero-copy,.n8n-flow{animation:none}.landing-hero::before,.landing-orbit,.landing-core,.n8n-hero::after,.n8n-hero-mark,.n8n-hero-mark::before,.n8n-hero-mark::after{animation:none}.landing-card,.landing-card-link .icono,.n8n-flow,.n8n-flow .boton .icono{transition:none}.n8n-result[data-loading="true"] strong::before{animation:none}}
"""


def render_landing_page():
    cards = (
        ("01", "Matrices", "Guarda y abre rápidamente las matrices de uso frecuente del equipo.", "/matrices-favoritas", "hoja", "Ver matrices", False),
        ("02", "Cargue PRIZMA", "Audita recursos y administra cargues, tests, cursos e historial desde un espacio dedicado.", "/auditor", "subir", "Abrir espacio PRIZMA", False),
        ("03", "Cargue Moodle", "Audita primero la matriz y los recursos, o publícalos desde Moodle.", "/moodle-auditor", "moodle", "Abrir auditor", False),
        ("04", "Automatizaciones", "Accede a herramientas del equipo para generar pruebas, matrices y recursos.", "/automatizaciones-n8n", "codigo", "Ver herramientas", False),
    )
    html_cards = "".join(
        '<a class="panel landing-card" href="' + ruta + '"'
        + (' target="_blank" rel="noopener noreferrer" aria-label="Control Tower (abre en una pestaña nueva)"' if externo else "")
        + '><span class="landing-card-top"><span class="icono-tile">' + icon(icono)
        + '</span><span class="landing-card-index">' + numero + ' / ESPACIO</span></span>'
        + '<h3>' + titulo + '</h3><p>' + descripcion + '</p><span class="landing-card-link">'
        + texto_boton + icon("flecha-derecha") + '</span></a>'
        for numero, titulo, descripcion, ruta, icono, texto_boton, externo in cards
    )
    content = (
        '<div class="landing"><section class="panel landing-hero"><div class="landing-hero-copy">'
        '<span class="landing-eyebrow">CENTRO DE OPERACIONES ACADÉMICAS</span>'
        '<h1>Tus herramientas de trabajo,<br><span>en un mismo lugar.</span></h1>'
        '<p>Gestiona cursos, revisa recursos y coordina las tareas del equipo desde espacios claros, conectados en una sola plataforma.</p>'
        '<div class="landing-hero-actions"><a class="boton" href="https://admin.prizma.site/" target="_blank" rel="noopener noreferrer">Entrar a PRIZMA ' + icon("flecha-derecha") + '</a>'
        '<a class="boton secundario" href="' + CONTROL_TOWER_URL + '" target="_blank" rel="noopener noreferrer">Control Tower ' + icon("externo") + '</a></div></div>'
        '<div class="landing-art" aria-hidden="true"><span class="landing-orbit"></span><span class="landing-orbit landing-orbit-inner"></span>'
        '<span class="landing-core">' + icon("paquete") + '</span><span class="landing-art-label">'
        + icon("torre") + 'Un espacio para cada tarea</span></div></section>'
        '<section class="landing-section-heading"><h2>Elige tu espacio de trabajo</h2></section>'
        '<section class="landing-cards" aria-label="Espacios de trabajo">' + html_cards + '</section></div>'
    )
    return render_page("Inicio", content, active="inicio", page_css=_LANDING_CSS)


def render_n8n_page():
    flow_order = {"descargar-recursos": 0, "matriz-csv": 1}
    flows = sorted(
        public_flow_catalog(),
        key=lambda flow: flow_order.get(flow["id"], len(flow_order)),
    )
    icons = ("documento", "zip", "hoja", "paquete")
    cards = []
    dialogs = []
    for flow, icon_name in zip(flows, icons):
        fid = html.escape(flow["id"], quote=True)
        fields = []
        for key, label, kind, placeholder, hint in flow["fields"]:
            name = html.escape(key, quote=True)
            label_html = html.escape(label)
            hint_html = ('<small class="n8n-hint">' + html.escape(hint) + '</small>') if hint else ""
            if kind == "select":
                if key == "dividirPorUnidad":
                    options = '<option value="No" selected>No</option><option value="Si">Sí</option>'
                else:
                    options = ''.join('<option value="' + str(row) + '"' + (' selected' if str(row) == placeholder else '') + '>' + str(row) + '</option>' for row in ("3", "4", "5", "6", "7"))
                control = '<select name="' + name + '" required>' + options + '</select>'
            else:
                control = '<input name="' + name + '" type="' + kind + '" placeholder="' + html.escape(placeholder, quote=True) + '" required autocomplete="off">'
            fields.append('<label>' + label_html + control + hint_html + '</label>')
        configured = "true" if flow["configured"] else "false"
        action = '<button class="boton secundario" type="button" data-open-n8n="' + fid + '">' + html.escape(flow["action"]) + ' ' + icon("flecha-derecha") + '</button>'
        status = 'Listo para ejecutar' if flow["configured"] else 'Webhook pendiente de configuración'
        cards.append(
            '<article class="panel n8n-flow"><div class="n8n-flow-top"><span class="n8n-flow-icon">' + icon(icon_name)
            + '</span><span class="eyebrow">' + html.escape(flow["category"])
            + '<span class="n8n-code">' + html.escape(flow["code"]) + '</span></span></div><h2>' + html.escape(flow["name"])
            + '</h2><p>' + html.escape(flow["description"]) + '</p><p class="n8n-state" data-configured="' + configured + '">'
            + status + '</p>' + action + '</article>'
        )
        dialogs.append(
            '<dialog class="n8n-dialog" id="n8n-' + fid + '" aria-labelledby="title-' + fid + '"><section class="n8n-dialog-card">'
            + '<button class="boton secundario n8n-close" type="button" data-close-n8n aria-label="Cerrar">' + icon("cerrar") + '</button>'
            + '<span class="eyebrow">' + html.escape(flow["category"]) + ' · ' + html.escape(flow["code"]) + '</span>'
            + '<h2 id="title-' + fid + '">' + html.escape(flow["name"]) + '</h2><p>' + html.escape(flow["description"])
            + '</p><form class="n8n-form" data-flow-id="' + fid + '">' + ''.join(fields)
            + '<button class="boton" type="submit">' + html.escape(flow["action"]) + '</button><p class="n8n-hint">'
            + html.escape(flow["footer"]) + '</p></form><div class="n8n-result n8n-hidden" role="status"></div></section></dialog>'
        )
    content = (
        '<div class="landing"><header class="n8n-hero"><div class="n8n-hero-copy"><span class="eyebrow">' + icon("torre") + ' CENTRO DE OPERACIONES</span>'
        '<h1>Automatizaciones</h1><p>Herramientas del equipo, listas para convertir tareas repetitivas en trabajo resuelto.</p></div>'
        '<div class="n8n-hero-mark" aria-hidden="true">' + icon("codigo") + '</div></header>'
        '<section class="n8n-flow-grid" aria-label="Automatizaciones disponibles">'
        + '<article class="panel n8n-flow"><span class="eyebrow">PRIZMA<span class="n8n-code">API</span></span>'
        + '<h2>API de PRIZMA</h2><p>Acceso a la API de PRIZMA.</p>'
        + '<p class="n8n-state">api.prizma.site</p><a class="boton secundario" href="https://api.prizma.site/" target="_blank" rel="noopener noreferrer">'
        + 'Abrir API de PRIZMA ' + icon("flecha-derecha") + '</a></article>'
        + '<article class="panel n8n-flow"><span class="eyebrow">PRIZMA<span class="n8n-code">Acceso directo</span></span>'
        + '<h2>Crear semanas de curso</h2><p>Abre la herramienta de importación CSV de PRIZMA para crear las semanas del curso.</p>'
        + '<p class="n8n-state">Herramienta de PRIZMA</p><a class="boton secundario" href="https://api.prizma.site/v1/utilities/mydev/001/import-csv-view/" target="_blank" rel="noopener noreferrer">'
        + 'Crear semanas de curso ' + icon("flecha-derecha") + '</a></article>'
        + ''.join(cards) + '</section>'
        + ''.join(dialogs) + '</div>'
    )
    page_js = r"""
var N8N_LABELS={totalTests:"Archivos generados",totalArchivos:"Archivos copiados",errores:"Archivos que no se pudieron copiar",folderName:"Carpeta",fileName:"Archivo",expiresInMinutes:"Disponible por (minutos)"};
var N8N_POLL_MS=8000,N8N_MAX_MS=45*60*1000,N8N_MAX_FALLOS=6;
function n8nEspera(ms){return new Promise(function(r){setTimeout(r,ms);});}
function n8nTiempo(inicio){var s=Math.max(0,Math.round((Date.now()-inicio)/1000)),m=Math.floor(s/60);return(m?m+" min ":"")+(s%60)+" s";}
function n8nEnlace(box,url,texto){if(typeof url==="string"&&/^https:\/\//i.test(url)){var a=document.createElement("a");a.href=url;a.target="_blank";a.rel="noopener noreferrer";a.textContent=texto||"Abrir en Google Drive";box.appendChild(a);}}
function n8nAvisos(box,avisos){if(!Array.isArray(avisos)||!avisos.length)return;var t=document.createElement("p");t.textContent="Posibles inconsistencias detectadas:";box.appendChild(t);var ul=document.createElement("ul");avisos.forEach(function(v){var li=document.createElement("li");li.textContent=String(v).replace(/<[^>]*>/g," ").replace(/\s+/g," ").trim();ul.appendChild(li);});box.appendChild(ul);}
function n8nMostrar(box,result){var data=result.data||{};box.dataset.loading="false";box.textContent=result.message||"La automatización terminó correctamente.";Object.keys(N8N_LABELS).forEach(function(key){var v=data[key];if(v===undefined||v===null||v==="")return;if(key==="errores"&&!Number(v))return;var p=document.createElement("p");p.textContent=N8N_LABELS[key]+": "+v;box.appendChild(p);});n8nAvisos(box,data.avisos);n8nEnlace(box,data.folderUrl);n8nEnlace(box,data.downloadUrl,"Descargar archivo");}
function n8nCargando(box,inicio){box.dataset.ok="true";box.dataset.loading="true";box.textContent="";var t=document.createElement("strong");t.textContent="Cargando recursos…";var d=document.createElement("p");d.textContent="Se están copiando todos los recursos de la matriz a Google Drive. Tiempo transcurrido: "+n8nTiempo(inicio)+". Puedes dejar esta ventana abierta; aquí aparecerá la carpeta cuando estén listos.";box.appendChild(t);box.appendChild(d);}
async function n8nSeguir(flowId,inicial,box,button){var inicio=Date.now(),fallos=0,jobId=String(inicial.data.jobId);button.textContent="Cargando…";while(Date.now()-inicio<N8N_MAX_MS){n8nCargando(box,inicio);await n8nEspera(N8N_POLL_MS);try{var r=await fetch("/automatizaciones-n8n/estado?flowId="+encodeURIComponent(flowId)+"&jobId="+encodeURIComponent(jobId),{cache:"no-store"});var res=await r.json();if(r.ok&&res.ok!==false){fallos=0;if(res.status==="done"){n8nMostrar(box,res);return;}}else if(r.status===400){throw new Error(res.message||"No se pudo consultar el avance.");}else{fallos++;}}catch(err){if(err instanceof Error&&/no es válido/.test(err.message))throw err;fallos++;}if(fallos>=N8N_MAX_FALLOS)throw new Error("Se perdió la comunicación con n8n mientras se copiaban los recursos. Revisa la carpeta en Drive o vuelve a intentarlo.");}
box.dataset.loading="false";box.dataset.ok="false";box.textContent="La descarga está tardando más de lo normal. Revisa la carpeta en Google Drive; los recursos pueden seguir apareciendo.";n8nEnlace(box,inicial.data.folderUrl);}
document.addEventListener("click",function(e){var open=e.target.closest("[data-open-n8n]");if(open){document.getElementById("n8n-"+open.dataset.openN8n).showModal();}var close=e.target.closest("[data-close-n8n]");if(close)close.closest("dialog").close();if(e.target.matches("dialog.n8n-dialog"))e.target.close();});
document.addEventListener("submit",async function(e){var form=e.target.closest(".n8n-form");if(!form)return;e.preventDefault();var flowId=form.dataset.flowId,button=form.querySelector("button[type=submit]"),box=form.parentElement.querySelector(".n8n-result"),payload=Object.fromEntries(new FormData(form).entries());button.disabled=true;button.textContent="Ejecutando…";box.classList.remove("n8n-hidden");box.dataset.ok="true";box.dataset.loading="true";box.textContent=flowId==="descargar-recursos"?"Cargando recursos… Preparando la carpeta en Google Drive.":"Procesando… Esto puede tardar hasta un minuto; no cierres esta ventana.";try{var response=await fetch("/automatizaciones-n8n/ejecutar",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({flowId:flowId,payload:payload})});var result=await response.json();if(!response.ok||result.ok===false)throw new Error(result.message||"No se pudo ejecutar el flujo.");box.dataset.ok="true";var data=result.data||{};if(data.status==="processing"&&data.jobId){await n8nSeguir(flowId,result,box,button);}else{n8nMostrar(box,result);}}catch(error){box.dataset.loading="false";box.dataset.ok="false";box.textContent=error instanceof Error?error.message:"Ocurrió un error inesperado.";}finally{button.disabled=false;button.textContent=flowId==="aut-tests"?"Generar tests":flowId==="descargar-recursos"?"Descargar recursos":flowId==="matriz-csv"?"Generar matriz":"Generar plantilla";}});
"""
    return render_page("Automatizaciones", content, active="n8n", page_css=_LANDING_CSS, page_js=page_js)
