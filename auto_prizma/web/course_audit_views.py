"""Paginas de la auditoria profunda de curso: PRIZMA y Moodle.

La auditoria no usa matriz, CSV ni syllabus: entra al curso publicado,
recorre sus actividades y valida cada recurso por si mismo. Aqui solo se
monta la cara de usuario (formulario, avance y reporte); los trabajos
viven en services/.
"""

import html

from auto_prizma.web.icons import icon
from auto_prizma.web.layout import render_page


def _e(value):
    return html.escape(str(value if value is not None else ""), quote=True)


_ESTADOS_AUDITORIA = {
    "ok": ("badge-verde", "Completo"),
    "revisar": ("badge-ambar", "Revisar"),
    "falta": ("badge-rojo", "Sin recurso"),
    "no procesado": ("badge-gris", "No procesado"),
}

_RENDER_LABELS = {
    "si": "Sí",
    "no": "No",
    "no_comprobable": "No comprobable",
    "": "—",
}


def _alerta(error):
    if not error:
        return ""
    return (
        '<div class="aviso rojo" role="alert">' + icon("alerta")
        + "<div><strong>No se pudo iniciar la auditoría</strong><p>"
        + _e(error) + "</p></div></div>"
    )


def _pasos(items):
    return (
        '<div class="auditoria-pasos">'
        + "".join(
            '<div class="auditoria-paso"><span class="icono-tile">'
            + icon(nombre) + "</span><div><strong>" + _e(titulo)
            + "</strong><p>" + _e(texto) + "</p></div></div>"
            for nombre, titulo, texto in items
        )
        + "</div>"
    )


def render_prizma_audit_page(*, error="", usuario_prizma="", recordar_usuario=True):
    """Formulario de la auditoria de curso PRIZMA (credenciales y listo)."""
    contenido = (
        '<div class="auditoria-page">'
        '<header class="encabezado"><div class="encabezado-titulo">'
        '<span class="icono-tile grande">' + icon("buscar") + "</span>"
        "<div><h1>Auditar curso en PRIZMA</h1>"
        "<p>Busca primero el curso en PRIZMA por su línea académica (programa, "
        "pensum y asignatura), nivel de pensum y, opcionalmente, facultad. Luego "
        "pulsa Vista previa para abrir el curso publicado y auditar sus actividades. "
        "Comprueba "
        "que el recurso exista, que el PDF tenga hojas y contenido o que el H5P "
        "abra con su paquete y su título, y que ese título sea el nombre que "
        "muestra el curso. No usa matriz, CSV ni syllabus y no cambia nada.</p>"
        "</div></div></header>"
        + _alerta(error)
        + _pasos((
            ("libro", "Selecciona el curso", "Usa la línea académica, el nivel de pensum y, si aplica, la facultad."),
            ("ver", "Abre la vista previa", "PRIZMA muestra el curso elegido antes de recorrer sus actividades."),
            ("libro", "Recorre las pestañas del curso", "OVI, OVA y Retos Evaluativos, con las actividades que el curso muestra."),
            ("descargar", "Abre y baja cada recurso", "En modo solo lectura: nada se edita ni se guarda."),
            ("check-circulo", "Valida el archivo por dentro", "PDF: hojas y texto/imagenes. H5P: paquete valido, bibliotecas y título de portada."),
            ("reportes", "Te deja el reporte", "Tabla con estado por actividad y CSV descargable."),
        ))
        + '<form class="panel auditoria-form" method="post" action="/auditor-curso">'
        "<h2>¿Qué curso quieres auditar?</h2>"
        '<p class="form-pista">Usa el mismo dato académico que en Tests. '
        "Ejemplo: <code>V1130 11301 30S01 COMPETENCIAS MATEMÁTICAS I</code>. "
        "PRIZMA abrirá Vista previa; la auditoría no sube ni modifica nada.</p>"
        '<div class="form-fila">'
        "<label>Línea académica (programa, pensum y asignatura)"
        '<input type="text" name="linea_academica" placeholder="V1130 11301 30S01 COMPETENCIAS MATEMÁTICAS I" autocomplete="off" required></label>'
        "<label>Nivel de pensum"
        '<input type="text" name="nivel_pensum" placeholder="Ej. 1, 2, tercero..." autocomplete="off" required></label>'
        "<label>Facultad (opcional)"
        '<input type="text" name="facultad" autocomplete="off"></label>'
        "</div><div class=\"form-fila\">"
        "<label>Usuario PRIZMA"
        '<input type="text" name="usuario_prizma" autocomplete="username" value="'
        + _e(usuario_prizma) + '" required></label>'
        "<label>Contraseña PRIZMA"
        '<input type="password" name="contrasena_prizma" autocomplete="current-password" required></label>'
        "<label>Modo de navegador"
        '<select name="modo_navegador"><option value="segundo_plano" selected>En segundo plano (sin ventana)</option>'
        '<option value="visual">Visual (ventana Chromium)</option></select></label>'
        '</div><label class="auditoria-recordar"><input type="checkbox" '
        'name="recordar_credenciales" value="1"'
        + (" checked" if recordar_usuario else "")
        + '> Recordar usuario en este equipo</label>'
        '<p class="form-pista">El modo visual abre Chromium en este equipo mientras se busca y audita el curso.</p>'
        '<div class="form-acciones">'
        '<button type="submit" class="boton">' + icon("buscar")
        + "Buscar curso y auditar</button></div>"
        "</form></div>"
    )
    return render_page(
        "Auditar curso PRIZMA",
        contenido,
        active="curso-auditor",
        page_css=_CSS_AUDITORIA,
    )


def _estado_badge(estado):
    tono, etiqueta = _ESTADOS_AUDITORIA.get(str(estado or ""), ("badge-gris", "Sin dato"))
    return '<span class="badge ' + tono + '">' + _e(etiqueta) + "</span>"


def _filas_resultado(job):
    filas = []
    for item in job.get("results") or []:
        coincide = item.get("coincide")
        if coincide is True:
            coincide_texto, tono = "Sí", "verde"
        elif coincide is False:
            coincide_texto, tono = "No", "rojo"
        else:
            coincide_texto, tono = "—", "gris"
        filas.append(
            "<tr><td>" + _e(item.get("semana")) + "</td>"
            + "<td><strong>" + _e(item.get("actividad")) + "</strong></td>"
            + "<td>" + _e((item.get("tipo") or "").upper()) + "</td>"
            + "<td>" + _estado_badge(item.get("estado")) + "</td>"
            + "<td>" + _e(_RENDER_LABELS.get(item.get("renderiza"), item.get("renderiza"))) + "</td>"
            + '<td class="auditoria-titulo">' + _e(item.get("titulo_interno") or "—") + "</td>"
            + '<td class="auditoria-coincide badge-' + tono + '">' + _e(coincide_texto) + "</td>"
            + "<td>" + _e(item.get("matriz_recurso") or "—") + "</td>"
            + "<td>" + _e(item.get("matriz_estado") or "—") + "</td>"
            + '<td class="auditoria-detalle">' + _e(item.get("detalle")) + "</td></tr>"
        )
    return "".join(filas) or '<tr><td colspan="10">Todavía no hay recursos revisados.</td></tr>'


def _resumen_tarjetas(resumen):
    tarjetas = (
        (resumen.get("ok", 0), "Completos", "verde"),
        (resumen.get("revisar", 0), "Por revisar", "ambar"),
        (resumen.get("falta", 0), "Sin recurso", "rojo"),
        (resumen.get("total", 0), "Recursos", "azul"),
    )
    return (
        '<div class="auditoria-numeros">'
        + "".join(
            '<div class="panel auditoria-numero"><span class="icono-tile ' + tono + '">'
            + icon("check-circulo" if tono == "verde" else "alerta-circulo" if tono in {"rojo", "ambar"} else "buscar")
            + "</span><div><span>" + _e(etiqueta)
            + "</span><strong>" + str(int(valor)) + "</strong></div></div>"
            for valor, etiqueta, tono in tarjetas
        )
        + "</div>"
    )


def render_moodle_audit_page(
    job=None, *, error="", local=True
):
    """Pagina de la auditoria Moodle: formulario, avance en vivo y reporte."""
    if not local:
        contenido = (
            '<div class="auditoria-page"><div class="aviso ambar" role="status">'
            + icon("info")
            + "<div><strong>Esta herramienta solo está disponible desde una instancia local.</strong>"
            + "<p>Abre Auto Prizma en el equipo donde se abrirá Chromium: "
            "<code>http://127.0.0.1:8000</code>.</p></div></div></div>"
        )
        return render_page(
            "Auditar curso Moodle", contenido, active="moodle-auditor-curso",
            page_css=_CSS_AUDITORIA,
        )

    encabezado = (
        '<header class="encabezado"><div class="encabezado-titulo">'
        '<span class="icono-tile grande">' + icon("moodle") + "</span>"
        "<div><h1>Auditar curso en Moodle</h1>"
        "<p>Abre el curso publicado en la ventana de Chromium de este equipo, recorre "
        "sus semanas y entra a cada recurso para comprobar que renderice de verdad "
        "y que el título que se ve sea el nombre de la actividad. Puedes adjuntar "
        "una matriz opcional para comparar nombres y semanas. No "
        "cambia nada del curso.</p></div></div></header>"
    )

    if job is None:
        formulario = (
            '<form class="panel auditoria-form" method="post" enctype="multipart/form-data" action="/moodle-auditor-curso/iniciar">'
            "<h2>Empezar la auditoría</h2>"
            '<p class="form-pista">Pega el enlace completo del curso. Se abrirá Chromium visible '
            "con el mismo perfil del Cargue Moodle. Inicia sesión en esa ventana si el campus lo solicita; "
            "al terminar, Auto Prizma vuelve a abrir este enlace y audita sin activar la edición ni modificar nada.</p>"
            '<div class="form-fila">'
            "<label>Enlace del curso en Moodle"
            '<input type="url" name="course_url" placeholder="https://prizma.americana.edu.co/course/view.php?id=695" required></label>'
            "<label>Matriz de referencia (opcional, CSV o XLSX)"
            '<span class="moodle-label-file auditoria-matriz-drop">'
            + icon("subir")
            + '<strong>Adjunta la matriz de referencia</strong>'
            + '<small>Archivo .csv o .xlsx · opcional</small>'
            + '<span class="boton secundario moodle-label-file-button">Seleccionar archivo</span>'
            + '<span class="moodle-label-file-name" data-matriz-nombre>Ningún archivo seleccionado</span>'
            + '<input id="auditoria-matriz" type="file" name="matriz" accept=".csv,.xlsx">'
            + "</span></label>"
            "</div>"
            '<p class="form-pista">La matriz solo se usa para comparar semana y nombre del recurso con lo publicado. No adjuntes el syllabus; no se solicita ni descarga.</p>'
            '<div class="form-acciones">'
            '<button type="submit" class="boton">' + icon("buscar")
            + "Auditar el curso completo</button></div>"
            "</form>"
        )
        contenido = (
            '<div class="auditoria-page">' + encabezado + _alerta(error)
            + _pasos((
                ("moodle", "Inicio de sesión", "Inicia sesión manualmente en el Chromium visible, igual que en Cargue Moodle."),
                ("girar", "Recorre semana por semana", "Todas las secciones, con los recursos que el curso muestra."),
                ("check-circulo", "Abre cada recurso", "H5P montado, PDF embebido o archivo descargable validado por dentro."),
                ("reportes", "Te deja el reporte", "Tabla por recurso y CSV/JSON descargables."),
            ))
            + formulario + "</div>"
        )
        return render_page(
            "Auditar curso Moodle", contenido, active="moodle-auditor-curso",
            page_css=_CSS_AUDITORIA, page_js=_JS_AUDITORIA_FORM,
        )

    progreso = job.get("progress") or {}
    estado = str(job.get("status") or "")
    corriendo = not job.get("finished")
    report = job.get("report") or {}
    resumen = report.get("summary") or {}
    rutas = job.get("report_paths") or {}

    etiquetas_estado = {
        "logging_in": "Esperando inicio de sesión",
        "auditing": "Auditando el curso",
        "completed": "Completada",
        "cancelled": "Cancelada",
        "error": "Con error",
    }
    tonos_estado = {
        "logging_in": "badge-azul",
        "auditing": "badge-ambar",
        "completed": "badge-verde",
        "cancelled": "badge-gris",
        "error": "badge-rojo",
    }

    controles = ""
    if corriendo:
        controles = (
            '<div class="auditoria-controles">'
            '<button type="button" class="boton peligro" data-auditoria-control="cancelar">'
            + icon("cerrar") + "Cancelar auditoría</button></div>"
        )
    else:
        controles = (
            '<div class="auditoria-controles"><a class="boton secundario" '
            'href="/moodle-auditor-curso?nueva=1">Iniciar otra auditoría</a></div>'
        )

    descargas = (
        '<div class="auditoria-descargas">'
        '<a class="enlace-accion" href="/moodle-auditor-curso/' + _e(job["id"])
        + '/reporte?formato=csv">' + icon("descargar") + "Descargar CSV</a>"
        '<a class="enlace-accion" href="/moodle-auditor-curso/' + _e(job["id"])
        + '/reporte?formato=json">' + icon("descargar") + "Descargar JSON</a></div>"
        if rutas else ""
    )

    contenido = (
        '<div class="auditoria-page" id="auditoria-moodle" data-job-id="' + _e(job["id"]) + '">'
        + encabezado + _alerta(error)
        + '<section class="panel auditoria-progreso">'
        '<div class="auditoria-progreso-cab">'
        '<div><h2>Auditoría en curso</h2>'
        '<span class="badge ' + tonos_estado.get(estado, "badge-gris")
        + '" id="auditoria-estado">' + _e(etiquetas_estado.get(estado, "En curso")) + "</span></div>"
        '<strong id="auditoria-porcentaje">0%</strong></div>'
        '<progress id="auditoria-barra" max="'
        + str(max(1, int(progreso.get("total") or 1))) + '" value="'
        + str(len(job.get("results") or [])) + '"></progress>'
        '<p class="auditoria-mensaje" id="auditoria-mensaje" aria-live="polite">'
        + _e(job.get("message")) + "</p>"
        + controles + "</section>"
        + _resumen_tarjetas(resumen)
        + '<section class="panel tabla-panel auditoria-tabla">'
        + '<div class="tabla-cabecera"><div><h2>Recursos del curso</h2>'
        + "<p>Cada fila es un recurso abierto y validado por la auditoría.</p></div>"
        + descargas + "</div>"
        + '<div class="tabla-scroll"><table class="tabla"><thead><tr>'
        + "<th>Semana</th><th>Recurso</th><th>Tipo</th><th>Estado</th>"
        + "<th>Renderiza</th><th>Título interno</th><th>Coincide con actividad</th><th>Nombre en matriz</th><th>Comparación matriz</th><th>Detalle</th>"
        + "</tr></thead><tbody id=\"auditoria-filas\">" + _filas_resultado(job)
        + "</tbody></table></div></section>"
        + '<p class="auditoria-pie">Si es la primera vez, inicia sesión en la ventana de '
        + "Chromium de este equipo y no la cierres hasta terminar.</p></div>"
    )
    return render_page(
        "Auditar curso Moodle",
        contenido,
        active="moodle-auditor-curso",
        page_css=_CSS_AUDITORIA,
        page_js=_JS_AUDITORIA,
    )


_CSS_AUDITORIA = r"""
.auditoria-page { display: grid; gap: 20px; }
.auditoria-pasos { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 14px; }
.auditoria-paso { display: grid; grid-template-columns: 44px minmax(0, 1fr); gap: 12px; align-items: start; padding: 16px; border: 1px solid var(--borde); border-radius: 14px; background: var(--panel); }
.auditoria-paso .icono-tile { width: 44px; height: 44px; border-radius: 12px; }
.auditoria-paso strong { display: block; margin: 2px 0 4px; font-size: 13.5px; }
.auditoria-paso p { margin: 0; color: var(--muted); font-size: 12.5px; line-height: 1.5; }
.auditoria-form { padding: 24px; display: grid; gap: 16px; }
.auditoria-form h2 { margin: 0; font-size: 19px; font-weight: 800; }
.auditoria-form .form-fila { display: grid; grid-template-columns: repeat(auto-fit, minmax(230px, 1fr)); gap: 14px; align-items: start; }
.auditoria-form label { display: grid; gap: 7px; font-size: 13px; font-weight: 700; color: var(--texto-2); }
.auditoria-form input:not([type="checkbox"]), .auditoria-form select { min-height: 44px; width: 100%; padding: 10px 13px; border: 1px solid var(--borde); border-radius: 11px; background: var(--panel-2); color: var(--texto); font-size: 14px; }
.auditoria-form label > input[type="url"] { align-self: start; height: 48px; box-sizing: border-box; }
.auditoria-form input:focus, .auditoria-form select:focus { outline: 2px solid var(--acento); outline-offset: 1px; }
.auditoria-form .auditoria-recordar { display: flex; align-items: center; gap: 9px; width: fit-content; margin: 0; cursor: pointer; }
.auditoria-form .auditoria-recordar input[type="checkbox"] { appearance: auto; accent-color: var(--acento); width: 17px; height: 17px; min-height: 17px; margin: 0; padding: 0; border: 0; box-shadow: none; }
.auditoria-form .form-acciones { display: flex; gap: 10px; flex-wrap: wrap; }
.auditoria-matriz-drop { display:grid!important; grid-template-columns:36px minmax(0,1fr) auto; grid-template-rows:auto auto auto; align-items:center; justify-items:start; gap:3px 12px; width:100%; min-height:78px; box-sizing:border-box; margin-top:7px; padding:12px 16px; border:2px dashed var(--acento-borde); border-radius:12px; background:var(--panel-2); text-align:left; cursor:pointer; transition:border-color .15s,background .15s; }
.auditoria-matriz-drop:hover { border-color:var(--acento); background:var(--acento-suave); }
.auditoria-matriz-drop > .icono { grid-column:1; grid-row:1/4; width:26px; height:26px; color:var(--acento-texto); }
.auditoria-matriz-drop > strong { grid-column:2; grid-row:1; font-size:13px; color:var(--texto); }
.auditoria-matriz-drop > small { grid-column:2; grid-row:2; color:var(--muted); font-size:11px; }
.auditoria-matriz-drop > .moodle-label-file-button { grid-column:3; grid-row:1/3; justify-self:end; white-space:nowrap; }
.auditoria-matriz-drop .moodle-label-file-name { max-width:100%; color:var(--muted); font-size:12px; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
.auditoria-matriz-drop > .moodle-label-file-name { grid-column:2/4; grid-row:3; }
.auditoria-matriz-drop input[type=file] { position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden; clip:rect(0,0,0,0); clip-path:inset(50%); white-space:nowrap; border:0; }
.auditoria-matriz-drop:focus-within { outline:3px solid var(--foco); outline-offset:3px; }
@media (max-width:600px) { .auditoria-matriz-drop { grid-template-columns:28px minmax(0,1fr); } .auditoria-matriz-drop > .moodle-label-file-button { grid-column:2; grid-row:3; justify-self:start; margin-top:6px; } .auditoria-matriz-drop > .moodle-label-file-name { grid-column:2; grid-row:4; } .auditoria-matriz-drop > .icono { grid-row:1/3; } }
.form-pista { margin: 0; color: var(--muted); font-size: 13px; line-height: 1.55; }
.auditoria-progreso { padding: 22px 24px; display: grid; gap: 14px; }
.auditoria-progreso-cab { display: flex; justify-content: space-between; align-items: center; gap: 16px; flex-wrap: wrap; }
.auditoria-progreso-cab h2 { margin: 0 0 8px; font-size: 19px; font-weight: 800; }
.auditoria-progreso-cab strong { font-size: 20px; color: var(--acento-texto); }
.auditoria-progreso progress { width: 100%; height: 12px; }
.auditoria-mensaje { margin: 0; color: var(--texto-2); font-size: 13.5px; line-height: 1.5; }
.auditoria-controles { display: flex; justify-content: flex-end; }
.auditoria-numeros { display: grid; grid-template-columns: repeat(auto-fit, minmax(170px, 1fr)); gap: 14px; }
.auditoria-numero { display: flex; align-items: center; gap: 14px; padding: 18px 20px; }
.auditoria-numero > div span { display: block; color: var(--muted); font-size: 12.5px; }
.auditoria-numero > div strong { display: block; font-size: 24px; font-weight: 800; }
.auditoria-tabla { padding: 22px 24px; }
.auditoria-titulo, .auditoria-detalle { color: var(--muted); font-size: 12px; white-space: normal; overflow-wrap: anywhere; min-width: 150px; }
.auditoria-coincide { font-weight: 800; font-size: 12px; }
.auditoria-descargas { display: flex; gap: 14px; flex-wrap: wrap; }
.auditoria-pie { margin: 0; color: var(--muted); font-size: 12.5px; text-align: center; }
"""

_JS_AUDITORIA = r"""
(function(){
  var root=document.getElementById('auditoria-moodle');
  if(!root)return;
  var id=root.getAttribute('data-job-id');
  var base='/moodle-auditor-curso/'+encodeURIComponent(id);
  var LABELS={logging_in:'Esperando inicio de sesión',auditing:'Auditando el curso',completed:'Completada',cancelled:'Cancelada',error:'Con error'};
  var TONES={logging_in:'badge-azul',auditing:'badge-ambar',completed:'badge-verde',cancelled:'badge-gris',error:'badge-rojo'};
  var ESTADOS={ok:['badge-verde','Completo'],revisar:['badge-ambar','Revisar'],falta:['badge-rojo','Sin recurso'],'no procesado':['badge-gris','No procesado']};
  var RENDERS={si:'Sí',no:'No',no_comprobable:'No comprobable','':''};
  function el(tag,cls,text){var node=document.createElement(tag);if(cls)node.className=cls;if(text!=null)node.textContent=text;return node;}
  function render(job){
    var p=job.progress||{};var results=job.results||[];var total=p.total||0;
    document.getElementById('auditoria-mensaje').textContent=job.message||'';
    document.getElementById('auditoria-estado').textContent=job.cancel_requested?'Cancelando':(LABELS[job.status]||'Auditando');
    document.getElementById('auditoria-estado').className='badge '+(TONES[job.status]||'badge-gris');
    document.getElementById('auditoria-porcentaje').textContent=(total?Math.floor(results.length*100/total):0)+'%';
    var bar=document.getElementById('auditoria-barra');bar.max=Math.max(1,total);bar.value=results.length;
    var counts={};results.forEach(function(r){counts[r.estado]=(counts[r.estado]||0)+1;});
    var numeros=document.querySelectorAll('.auditoria-numero strong');
    if(numeros.length===4){numeros[0].textContent=counts.ok||0;numeros[1].textContent=counts.revisar||0;numeros[2].textContent=counts.falta||0;numeros[3].textContent=results.length;}
    var tbody=document.getElementById('auditoria-filas');tbody.textContent='';
    if(!results.length){var empty=document.createElement('tr');var td=document.createElement('td');td.colSpan=10;td.textContent='Todavía no hay recursos revisados.';empty.appendChild(td);tbody.appendChild(empty);}
    results.forEach(function(r){
      var row=document.createElement('tr');
      row.appendChild(el('td',null,r.semana||''));
      var nombre=document.createElement('td');nombre.appendChild(el('strong',null,r.actividad||''));row.appendChild(nombre);
      row.appendChild(el('td',null,(r.tipo||'').toUpperCase()));
      var estado=ESTADOS[r.estado]||['badge-gris','Sin dato'];var celda=document.createElement('td');celda.appendChild(el('span','badge '+estado[0],estado[1]));row.appendChild(celda);
      row.appendChild(el('td',null,RENDERS[r.renderiza]||r.renderiza||'—'));
      row.appendChild(el('td','auditoria-titulo',r.titulo_interno||'—'));
      row.appendChild(el('td','auditoria-coincide badge-'+(r.coincide===true?'verde':r.coincide===false?'rojo':'gris'),r.coincide===true?'Sí':r.coincide===false?'No':'—'));
      row.appendChild(el('td',null,r.matriz_recurso||'—'));
      row.appendChild(el('td',null,r.matriz_estado||'—'));
      row.appendChild(el('td','auditoria-detalle',r.detalle||''));
      tbody.appendChild(row);
    });
    var cancel=document.querySelector('[data-auditoria-control="cancelar"]');
    if(cancel)cancel.disabled=!!job.cancel_requested;
  }
  var cancel=document.querySelector('[data-auditoria-control="cancelar"]');
  if(cancel)cancel.addEventListener('click',async function(){
    cancel.disabled=true;
    document.getElementById('auditoria-mensaje').textContent='Enviando solicitud para detener la auditoría…';
    try{var response=await fetch(base+'/cancelar',{method:'POST',headers:{'Accept':'application/json'}});var data=await response.json();if(!response.ok){window.alert(data.error||'No se pudo cancelar.');}else{render(data);}}
    catch(_){window.alert('No se pudo contactar con Auto Prizma.');}
  });
  async function poll(){
    try{
      var response=await fetch(base+'/estado',{headers:{'Accept':'application/json'}});
      if(!response.ok){window.setTimeout(poll,3000);return;}
      var job=await response.json();
      if(job.finished){window.location.reload();return;}
      render(job);window.setTimeout(poll,1500);
    }catch(_){window.setTimeout(poll,3000);}
  }
  poll();
})();
"""

_JS_AUDITORIA_FORM = r"""
(function(){
  var input=document.getElementById('auditoria-matriz');
  var name=document.querySelector('[data-matriz-nombre]');
  if(!input||!name)return;
  input.addEventListener('change',function(){
    name.textContent=input.files&&input.files.length?input.files[0].name:'Ningún archivo seleccionado';
  });
})();
"""


__all__ = [
    "render_moodle_audit_page",
    "render_prizma_audit_page",
]
