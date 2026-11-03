"""HTML del modulo de tests: revision del documento y tarjeta de estado.

_layout arma cada pagina con el marco comun (auto_prizma/web/layout.py), que
ya incluye "Test" en el menu de todas las paginas.
"""

from __future__ import annotations

import html
import json
import re

from auto_prizma.core.config import PRIZMA_HOST
from auto_prizma.web.layout import render_page

from .models import Severity, document_to_dict
from .validation import validate_document
from .state import (
    _cargar_credenciales_prizma,
    _issue_counts,
)


# Estilos propios del modulo (el marco y los colores comunes estan en static/app.css).
_CSS_TESTS = r"""
.contenido{--morado:var(--boton);--amarillo:var(--ambar)}
.layout-tests{display:grid;grid-template-columns:1fr 340px;gap:24px;align-items:start}
.panel{padding:26px;margin-bottom:18px}
.panel-ayuda{padding:24px;background:var(--panel);border:1px solid var(--borde);border-radius:18px}
.panel-ayuda h3{margin:0 0 18px;font-size:17px;color:var(--texto)}
.paso-ayuda{display:grid;grid-template-columns:30px 1fr;gap:12px;align-items:start;margin-bottom:16px;color:var(--texto-2);font-size:13px;line-height:1.5}
.paso-ayuda b{width:28px;height:28px;border-radius:50%;background:var(--acento-suave);color:var(--acento-texto);display:grid;place-items:center;font-size:13px;font-weight:800}
.ayuda-separador{height:1px;background:var(--borde);margin:22px 0}
.titulo-consejos{color:var(--acento-texto);font-size:16px;margin:0 0 12px}
.consejo{color:var(--texto-2);font-size:13px;line-height:1.55;margin:0 0 10px}
h1{margin:0 0 8px;font-size:29px}
h2{margin:0 0 12px;font-size:20px}
p{color:var(--muted);line-height:1.5;margin:0 0 14px}
.pasos{display:flex;gap:8px;flex-wrap:wrap;margin:18px 0 24px}
.paso{padding:8px 14px;border-radius:999px;background:var(--acento-suave);color:var(--acento-texto);font-size:12px;font-weight:800}
.dropzone{display:grid;place-items:center;border:2px dashed var(--acento-borde);border-radius:14px;padding:32px 20px;text-align:center;background:var(--panel-2);cursor:pointer;transition:all .2s}
.dropzone:hover,.dropzone.dragover{border-color:var(--acento);background:var(--acento-suave)}
input,textarea,select{width:100%;border:1px solid var(--borde-2);border-radius:10px;padding:11px 13px;font:inherit;color:inherit;background:var(--panel)}
textarea{min-height:78px;resize:vertical}
label{display:block;font-size:12px;font-weight:800;margin:13px 0 6px;color:var(--texto-2)}
button,.boton{display:inline-flex;align-items:center;justify-content:center;gap:8px;border:1px solid transparent;border-radius:12px;padding:12px 18px;background:var(--boton);color:var(--boton-texto);font-weight:800;font-size:14px;text-decoration:none;cursor:pointer}
button:hover,.boton:hover{opacity:.93}
button.secundario,.boton.secundario{background:var(--panel);color:var(--acento-texto);border:1px solid var(--acento-borde)}
.boton.secundario.peligro{border-color:var(--rojo-borde);color:var(--rojo)}
.acciones{display:flex;gap:12px;flex-wrap:wrap;margin-top:22px}
.test-card{border:1px solid var(--borde);border-radius:16px;padding:22px;margin-top:18px;background:var(--panel-2);box-shadow:var(--sombra-sm)}
.section{border-left:4px solid var(--acento);padding-left:16px;margin:20px 0}
.question{background:var(--panel);border:1px solid var(--borde);border-radius:12px;padding:16px;margin:14px 0;transition:all .2s;scroll-margin-top:24px}
.question.question-error{border:2px solid var(--rojo);background:var(--rojo-suave);box-shadow:0 0 0 4px var(--rojo-foco)}
.badge{display:inline-block;border-radius:999px;padding:5px 10px;font-size:12px;font-weight:800;margin:3px 6px 3px 0}
.badge.ok{background:var(--verde-suave);color:var(--verde)}
.badge.warn{background:var(--ambar-suave);color:var(--ambar)}
.badge.error{background:var(--rojo-suave);color:var(--rojo)}
.issue{padding:12px 14px;border-radius:10px;margin:8px 0;font-size:13px;line-height:1.5}
.issue.error{background:var(--rojo-suave);color:var(--rojo);border:1px solid var(--rojo-borde)}
.issue.warning{background:var(--ambar-suave);color:var(--ambar);border:1px solid var(--ambar-borde)}
.issue.ok{background:var(--verde-suave);color:var(--verde);border:1px solid var(--verde-borde)}
.issue-link{color:var(--acento-texto)}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:14px}
.option-row,.pair-row{display:grid;grid-template-columns:42px 1fr auto;gap:10px;align-items:center;margin-top:8px}
.pair-row{grid-template-columns:1fr 1fr}
.muted{color:var(--muted);font-size:12px}
@media(max-width:1100px){.layout-tests{grid-template-columns:1fr}.panel-ayuda{order:2}}
@media(max-width:900px){.grid2{grid-template-columns:1fr}}

/* ---- Estados dinamicos reutilizables (banners, kpis, badges, tarjeta en vivo) ---- */
.status-banner{display:flex;gap:14px;align-items:flex-start;margin-bottom:20px;border-radius:14px;padding:20px;border:2px solid transparent;box-shadow:var(--sombra-sm)}
.status-banner .status-icon{width:40px;height:40px;border-radius:50%;display:grid;place-items:center;font-size:22px;font-weight:900;flex-shrink:0;background:var(--panel)}
.status-banner h3{margin:0 0 6px;font-size:17px;font-weight:800}
.status-banner p{margin:0 0 12px;font-size:14px;line-height:1.5;color:var(--texto-2)}
.status-banner .acciones{margin-top:0}
.status-banner--ok{background:var(--verde-suave);border-color:var(--verde-borde)}
.status-banner--ok .status-icon,.status-banner--ok h3,.status-banner--ok p{color:var(--verde)}
.status-banner--error{background:var(--rojo-suave);border-color:var(--rojo-borde)}
.status-banner--error .status-icon,.status-banner--error h3{color:var(--rojo)}
.status-banner--warn{background:var(--ambar-suave);border-color:var(--ambar-borde)}
.status-banner--warn .status-icon,.status-banner--warn h3{color:var(--ambar)}

.kpi-card{background:var(--panel);border:1px solid var(--borde);border-radius:12px;padding:16px;box-shadow:var(--sombra-sm)}
.kpi-card .kpi-label{font-size:12px;font-weight:700;text-transform:uppercase;color:var(--muted)}
.kpi-card .kpi-valor{font-size:28px;font-weight:900;margin-top:4px;color:var(--texto)}
.kpi-card--ok{background:var(--verde-suave);border-color:var(--verde-borde)}
.kpi-card--ok .kpi-label,.kpi-card--ok .kpi-valor{color:var(--verde)}
.kpi-card--warn{background:var(--ambar-suave);border-color:var(--ambar-borde)}
.kpi-card--warn .kpi-label,.kpi-card--warn .kpi-valor{color:var(--ambar)}
.kpi-card--error{background:var(--rojo-suave);border-color:var(--rojo-borde)}
.kpi-card--error .kpi-label,.kpi-card--error .kpi-valor{color:var(--rojo)}

.badge-dinamico{display:inline-block;border-radius:999px;padding:5px 10px;font-size:12px;font-weight:800}
.badge-dinamico--pendiente{background:var(--panel-2);color:var(--texto-2)}
.badge-dinamico--proceso{background:var(--ambar-suave);color:var(--ambar)}
.badge-dinamico--ok{background:var(--verde-suave);color:var(--verde)}
.badge-dinamico--error{background:var(--rojo-suave);color:var(--rojo)}
.badge-dinamico--detenido{background:var(--panel-2);color:var(--muted)}
.badge-dinamico--omitido{background:var(--ambar-suave);color:var(--ambar)}

.live-card{border-radius:16px;padding:20px 24px;box-shadow:var(--sombra-sm);border:2px solid transparent;margin-bottom:24px;transition:all .3s ease}
.live-card--running{background:var(--acento-suave);border-color:var(--acento)}
.live-card--waiting{background:var(--rojo-suave);border-color:var(--rojo)}
.live-card h3{margin:0;font-size:16px;font-weight:800;color:var(--texto)}
.live-card p{margin:3px 0 0;font-size:13px;color:var(--muted)}

.progress-track{background:var(--borde);border-radius:999px;height:9px;overflow:hidden}
.progress-fill{background:var(--boton);height:100%;transition:width .4s ease}

.mode-option{flex:1;min-width:180px;border:1px solid var(--borde);border-radius:12px;padding:14px;cursor:pointer;background:var(--panel);transition:all .2s}
.mode-option strong{margin-left:7px;font-size:14px}
.mode-option span{display:block;margin:5px 0 0 25px;color:var(--muted);font-size:12px}
.mode-option--activo{border-color:var(--acento);background:var(--acento-suave)}

.alert-soft{margin-top:14px;border-radius:12px;padding:14px;display:flex;gap:12px;align-items:center}
.alert-soft--ok{background:var(--verde-suave);border:1px solid var(--verde-borde);color:var(--verde)}
.alert-soft--warn{background:var(--ambar-suave);border:1px solid var(--ambar-borde);color:var(--ambar);align-items:flex-start}
.alert-soft a{color:var(--acento-texto);font-weight:700}

.test-card-header{background:var(--panel-2);border-bottom:1px solid var(--borde)}
.chip-morado{display:inline-block;font-size:12px;background:var(--acento-suave);padding:3px 8px;border-radius:6px;color:var(--acento-texto);font-weight:600}
.bloque-prizma{margin-top:28px;border:2px solid var(--acento) !important;background:var(--acento-suave) !important;scroll-margin-top:24px}

#btn-guardar-correcciones.is-dirty{background:var(--acento);color:var(--boton-texto);font-weight:800;box-shadow:0 0 0 4px var(--foco)}
"""

# Etiqueta del menu -> clave de web/layout.NAV_ITEMS (los llamadores pasan la etiqueta).
_CLAVES_MENU = {
    "Inicio": "inicio",
    "Test": "test",
    "Cargue actual": "cargue",
    "Historial": "historial",
    "Reportes": "reportes",
}


def _layout(title: str, body: str, active: str = "Test") -> str:
    return render_page(title, body, active=_CLAVES_MENU.get(active, "test"), page_css=_CSS_TESTS)


def _render_issues(issues) -> str:
    if not issues:
        return '<span class="badge ok" id="badge-todas-validadas">✓ Todas las preguntas y claves validadas</span>'
    items = []
    for issue in issues:
        m = re.match(r"tests\[(\d+)\]\.sections\[(\d+)\]\.questions\[(\d+)\]", issue.path)
        if m:
            t_idx, s_idx, q_idx = m.groups()
            anchor = f"#pregunta-{t_idx}-{s_idx}-{q_idx}"
            target_id = f"pregunta-{t_idx}-{s_idx}-{q_idx}"
            items.append(
                f'<div class="issue {issue.severity.value}" data-issue-target="{target_id}" data-original-msg="{html.escape(issue.message, quote=True)}" style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:8px;">'
                f'<div class="issue-text"><strong>{issue.severity.value.title()}</strong>: {html.escape(issue.message)}</div>'
                f'<a class="issue-link" href="{anchor}" onclick="irAPregunta(\'{target_id}\', {t_idx}); return false;" style="font-weight:700;text-decoration:underline;font-size:12px;cursor:pointer;">Ir a la pregunta ➔</a>'
                f'</div>'
            )
        else:
            items.append(f'<div class="issue {issue.severity.value}"><div class="issue-text"><strong>{issue.severity.value.title()}</strong>: {html.escape(issue.message)}</div></div>')
    return "".join(items)


def _render_review(job_id: str, job: dict, message: str = "") -> str:
    document: TestDocument = job["document"]
    issues = validate_document(document)
    counts = _issue_counts(issues)
    state = json.dumps(document_to_dict(document), ensure_ascii=False).replace("<", "\\u003c")
    issues_by_path: dict[str, list] = {}
    for issue in issues:
        issues_by_path.setdefault(issue.path, []).append(issue)

    owner = job.get("owner", "")
    creds = _cargar_credenciales_prizma(owner)

    job_creds = job.get("credenciales_prizma") or {}
    usuario_prizma_val = job_creds.get("usuario") or creds.get("usuario", "")
    clave_prizma_val = job_creds.get("clave", "")

    cascada_datos = job.get("cascada_datos") or {}
    cascada_facultad_val = cascada_datos.get("facultad", "")
    cascada_programa_val = cascada_datos.get("programa") or document.program or ""
    cascada_pensum_val = cascada_datos.get("pensum", "")
    cascada_nivel_val = cascada_datos.get("nivel", "")
    linea_academica_val = cascada_datos.get("linea_academica") or " ".join(
        parte for parte in (
            cascada_programa_val,
            cascada_pensum_val,
            cascada_datos.get("codigo_asignatura", ""),
            cascada_datos.get("asignatura", ""),
        ) if parte
    )



    cards = []
    for test_index, test in enumerate(document.tests):
        sections = []
        for section_index, section in enumerate(test.sections):
            questions = []
            for question_index, question in enumerate(section.questions):
                q_path = f"tests[{test_index}].sections[{section_index}].questions[{question_index}]"
                q_issues = issues_by_path.get(q_path, [])
                has_q_error = any(i.severity == Severity.ERROR for i in q_issues)
                error_class = " question-error" if has_q_error else ""
                
                error_alert = ""
                if q_issues:
                    error_items = "".join(f'<li style="margin:3px 0;">{html.escape(i.message)}</li>' for i in q_issues)
                    error_alert = f'<div class="issue error" style="margin:0 0 12px 0;"><strong>⚠️ Corrección requerida en Pregunta {question_index + 1}:</strong><ul style="margin:4px 0 0 18px;padding:0;">{error_items}</ul></div>'
                
                badge_estado = '<span class="badge error">❌ Requiere atención</span>' if has_q_error else '<span class="badge ok">✓ Válida</span>'

                option_html = ""
                if section.code == "trueOrFalse":
                    value = "true" if question.answer is True else "false" if question.answer is False else ""
                    option_html = f'<div style="margin-top:10px;"><label>Respuesta Correcta</label><select style="max-width:200px;" data-test="{test_index}" data-section="{section_index}" data-question="{question_index}" data-field="answer"><option value="">Selecciona una opción</option><option value="true" {"selected" if value == "true" else ""}>Verdadero</option><option value="false" {"selected" if value == "false" else ""}>Falso</option></select></div>'
                elif section.code == "multipleChoice":
                    option_html = "<div style='margin-top:10px;'><label>Opciones y Clave (marca la casilla de la respuesta correcta)</label>" + "".join(
                        f'<div class="option-row"><strong>{html.escape(option.letter.upper())}</strong><input data-test="{test_index}" data-section="{section_index}" data-question="{question_index}" data-option="{option_index}" data-field="option_text" value="{html.escape(option.text, quote=True)}"><label style="margin:0;display:flex;align-items:center;gap:5px;cursor:pointer;"><input type="checkbox" style="width:auto;" data-test="{test_index}" data-section="{section_index}" data-question="{question_index}" data-option="{option_index}" data-field="option_correct" {"checked" if option.letter in question.correct_option_letters else ""}> Correcta</label></div>'
                        for option_index, option in enumerate(question.options)
                    ) + "</div>"
                elif section.code == "matching":
                    option_html = "<div style='margin-top:10px;'><label>Parejas Concepto - Definición</label>" + "".join(
                        f'<div class="pair-row"><input placeholder="Concepto (Col A)" data-test="{test_index}" data-section="{section_index}" data-question="{question_index}" data-pair="{pair_index}" data-field="pair_left" value="{html.escape(pair.left, quote=True)}"><input placeholder="Descripción (Col B)" data-test="{test_index}" data-section="{section_index}" data-question="{question_index}" data-pair="{pair_index}" data-field="pair_right" value="{html.escape(pair.right, quote=True)}"></div>'
                        for pair_index, pair in enumerate(question.pairs)
                    ) + "</div>"
                questions.append(
                    f'<div class="question{error_class}" id="pregunta-{test_index}-{section_index}-{question_index}">'
                    f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px;">'
                    f'<label style="margin:0;font-weight:800;font-size:13px;">Pregunta {question_index + 1}</label>'
                    f'{badge_estado}'
                    f'</div>'
                    f'{error_alert}'
                    f'<textarea data-test="{test_index}" data-section="{section_index}" data-question="{question_index}" data-field="prompt">{html.escape(question.prompt)}</textarea>'
                    f'{option_html}'
                    f'</div>'
                )
            sections.append(f'<div class="section"><h3>{html.escape(section.name)} ({len(section.questions)} pregunta{"s" if len(section.questions)!=1 else ""})</h3>{"".join(questions)}</div>')
        num_preguntas_test = sum(len(sec.questions) for sec in test.sections)
        cards.append(f'''<article class="test-card" id="test-card-{test_index}" style="margin-bottom:16px;padding:0;overflow:hidden;">
            <div class="test-card-header" onclick="toggleTestCard({test_index})" style="display:flex;justify-content:space-between;align-items:center;padding:14px 18px;cursor:pointer;user-select:none;">
                <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap;">
                    <span class="badge ok" style="font-weight:700;">Test {test_index + 1} de {len(document.tests)}</span>
                    <strong style="font-size:15px;">{html.escape(test.title or f"Evaluación {test_index + 1}")}</strong>
                    <span class="chip-morado">{num_preguntas_test} pregunta{'s' if num_preguntas_test != 1 else ''}</span>
                    <span class="muted" style="font-size:12px;">Semana {html.escape(test.week or "N/A")} | Corte {html.escape(test.cut or "N/A")}</span>
                </div>
                <div style="display:flex;align-items:center;gap:8px;">
                    <span id="test-toggle-text-{test_index}" style="font-size:12px;font-weight:700;color:var(--acento-texto);">{"Contraer ▲" if test_index == 0 else "Desplegar ▼"}</span>
                </div>
            </div>
            <div class="test-card-body" id="test-card-body-{test_index}" style="padding:18px;{'display:block;' if test_index == 0 else 'display:none;'}">
                <div class="grid2">
                    <div><label>Título del test</label><input data-test="{test_index}" data-field="title" value="{html.escape(test.title, quote=True)}"></div>
                    <div class="grid2">
                        <div><label>Semana</label><input data-test="{test_index}" data-field="week" value="{html.escape(test.week, quote=True)}"></div>
                        <div><label>Corte</label><input data-test="{test_index}" data-field="cut" value="{html.escape(test.cut, quote=True)}"></div>
                    </div>
                </div>
                <label>Indicaciones / Descripción</label>
                <textarea data-test="{test_index}" data-field="description">{html.escape(test.description)}</textarea>
                {"".join(sections)}
            </div>
        </article>''')
    message_html = f'<div class="issue ok">{html.escape(message)}</div>' if message else ''
    error_badge_style = "" if counts["error"] else "display:none;"
    ok_badge_style = "" if not counts["error"] else "display:none;"

    body = f'''<h1>Revisión de Tests</h1><p>Analiza, audita y corrige preguntas antes de conectar la plataforma PRIZMA.</p>
    <div class="pasos"><span class="paso">1 Entrada ✓</span><span class="paso">2 Revisión activa</span><span class="paso">3 Configuración PRIZMA</span><span class="paso">4 Carga en cola</span></div>
    {message_html}
    <section class="panel">
        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px;margin-bottom:12px;">
            <div style="display:flex;gap:8px;flex-wrap:wrap;align-items:center;">
                <span class="badge ok">{len(document.tests)} test(s) detectado(s)</span>
                <span class="badge error" id="badge-contador-errores" style="{error_badge_style}"><span id="num-errores">{counts['error']}</span> error(es) pendiente(s)</span>
                <span class="badge ok" id="badge-sin-errores" style="{ok_badge_style}">✓ Todas las preguntas y claves validadas</span>
                <span class="badge {'warn' if counts['warning'] else 'ok'}">{counts['warning']} advertencia(s)</span>
            </div>
            <a href="#bloque-acceso-prizma" class="boton" style="text-decoration:none;padding:8px 16px;font-size:13px;">
                ⚡ Ir a Carga en PRIZMA ↓
            </a>
        </div>
        <div id="contenedor-issues" style="margin-top:14px">{_render_issues(issues)}</div>
    </section>
    <form id="review-form" class="panel" method="post" action="/tests/{job_id}/guardar">
        <input type="hidden" name="payload" id="payload">
        <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:14px;flex-wrap:wrap;gap:10px;">
            <div style="display:flex;gap:8px;">
                <button type="button" class="boton secundario" onclick="expandirTodosTests()" style="font-size:12px;padding:6px 12px;cursor:pointer;">＋ Expandir todos</button>
                <button type="button" class="boton secundario" onclick="contraerTodosTests()" style="font-size:12px;padding:6px 12px;cursor:pointer;">－ Contraer todos</button>
            </div>
        </div>
        {"".join(cards)}
        <div class="acciones">
            <button type="submit" id="btn-guardar-correcciones" style="transition:all .3s ease;padding:12px 22px;border-radius:10px;font-weight:700;">💾 Guardar correcciones</button>
            <a class="boton secundario" href="/tests/{job_id}/descargar">⬇ Descargar respaldo (JSON)</a>
            <a class="boton secundario" href="/tests">＋ Nuevo análisis</a>
        </div>
    </form>

    <section id="bloque-acceso-prizma" class="panel bloque-prizma">
        <div style="display:flex;align-items:center;gap:14px;margin-bottom:16px;">
            <div style="width:42px;height:42px;border-radius:12px;background:var(--acento);color:var(--boton-texto);display:grid;place-items:center;font-size:22px;flex-shrink:0;">🛡</div>
            <div>
                <h2 style="margin:0;font-size:20px;">Fase 3: Publicación y Carga en PRIZMA</h2>
                <p style="margin:3px 0 0;font-size:13px;">Automatización con Playwright en tiempo real contra <strong>{html.escape(PRIZMA_HOST)}</strong></p>
            </div>
        </div>

        <form id="form-prizma" method="post" action="/tests/{job_id}/ejecutar-prizma">
            <div class="grid2">
                <div>
                    <label>Usuario PRIZMA</label>
                    <input name="prizma_usuario" placeholder="Ej. 1020304050" value="{html.escape(usuario_prizma_val)}" required>
                </div>
                <div>
                    <label>Contraseña PRIZMA</label>
                    <input type="password" name="prizma_clave" placeholder="••••••••" value="{html.escape(clave_prizma_val)}" required>
                </div>
            </div>

            <div style="display:flex;gap:18px;margin:14px 0 18px;flex-wrap:wrap;align-items:center;">
                <label style="display:inline-flex;align-items:center;gap:8px;cursor:pointer;font-weight:600;font-size:13px;">
                    <input type="checkbox" name="recordar_credenciales" value="1" style="width:auto;" {"checked" if creds.get("recordar", True) else ""}>
                    Recordar usuario en este equipo
                </label>
                <label style="display:inline-flex;align-items:center;gap:8px;cursor:pointer;font-weight:700;font-size:13px;">
                    <input id="solo-simulacion-prizma" type="checkbox" name="solo_simulacion" value="1" style="width:auto;" checked>
                    Validar en PRIZMA sin guardar (recomendado)
                </label>
            </div>

            <div style="border-top:1px dashed var(--borde);padding-top:16px;margin-top:10px;">
                <h3 style="margin:0 0 8px;font-size:15px;">Datos del curso</h3>
                <label for="linea-academica">Línea académica del curso</label>
                <input id="linea-academica" name="linea_academica" placeholder="V1130 11301 30S01 COMPETENCIAS MATEMÁTICAS I" value="{html.escape(linea_academica_val, quote=True)}" required>
                <small style="display:block;margin:6px 0 14px;">Pega aquí la fila completa: Código de programa · Código de pensum · Código de asignatura · Nombre. Semana y corte se toman de cada test del Word.</small>
                <div class="grid2">
                    <div>
                        <label>Facultad <small style="font-weight:normal;">(Opcional)</small></label>
                        <input name="cascada_facultad" placeholder="Ej. Virtual - Derecho" value="{html.escape(cascada_facultad_val, quote=True)}">
                    </div>
                    <div>
                        <label>Nivel de pensum</label>
                        <input name="cascada_nivel" placeholder="Ej. 3 o Semestre 3" value="{html.escape(cascada_nivel_val, quote=True)}" required>
                    </div>
                </div>
            </div>

            <div class="acciones" style="margin-top:22px;">
                <button type="submit" id="btn-lanzar-prizma" class="boton grande">
                    ⚡ Validar en PRIZMA sin guardar
                </button>
            </div>
        </form>
    </section>

    <script>
    (() => {{
        const form = document.getElementById('form-prizma');
        const simulacion = document.getElementById('solo-simulacion-prizma');
        const boton = document.getElementById('btn-lanzar-prizma');
        const actualizar = () => {{
            if (!boton || !simulacion) return;
            boton.textContent = simulacion.checked
                ? '⚡ Validar en PRIZMA sin guardar'
                : '⚡ Crear y Publicar Evaluación en PRIZMA';
        }};
        if (simulacion) simulacion.addEventListener('change', actualizar);
        if (form) form.addEventListener('submit', () => {{
            if (!boton) return;
            boton.disabled = true;
            boton.textContent = simulacion && simulacion.checked
                ? '⏳ Validando sin guardar...'
                : '⏳ Creando y publicando...';
        }});
    }})();
    </script>

    <script>
    const initial={state};
    function val(q){{return q.type==='checkbox'?q.checked:q.value}}

    function verificarPreguntaValida(qBox) {{
        const selAnswer = qBox.querySelector('[data-field="answer"]');
        if (selAnswer) {{
            return selAnswer.value === 'true' || selAnswer.value === 'false';
        }}
        const checkboxes = qBox.querySelectorAll('[data-field="option_correct"]');
        if (checkboxes.length > 0) {{
            return Array.from(checkboxes).some(cb => cb.checked);
        }}
        const promptArea = qBox.querySelector('[data-field="prompt"]');
        if (promptArea) {{
            return promptArea.value.trim().length > 0;
        }}
        return true;
    }}

    function actualizarEstadoPreguntaEnVivo(qBox) {{
        if (!qBox) return;
        const targetId = qBox.id;
        const issueTop = document.querySelector(`[data-issue-target="${{targetId}}"]`);
        const esValida = verificarPreguntaValida(qBox);

        if (esValida) {{
            qBox.classList.remove('question-error');
            const errAlert = qBox.querySelector('.issue.error');
            if (errAlert) errAlert.style.display = 'none';
            const badge = qBox.querySelector('.badge');
            if (badge) {{
                badge.className = 'badge warn';
                badge.textContent = '✎ Modificado (por guardar)';
            }}
            if (issueTop) {{
                issueTop.className = 'issue ok';
                issueTop.dataset.resolved = 'true';
                const textDiv = issueTop.querySelector('.issue-text');
                if (textDiv) textDiv.innerHTML = '<strong>✓ Resuelto:</strong> Corrección aplicada (recuerda guardar cambios)';
                const link = issueTop.querySelector('.issue-link');
                if (link) link.style.display = 'none';
            }}
        }} else {{
            qBox.classList.add('question-error');
            const errAlert = qBox.querySelector('.issue.error');
            if (errAlert) errAlert.style.display = 'block';
            const badge = qBox.querySelector('.badge');
            if (badge) {{
                badge.className = 'badge error';
                badge.textContent = '❌ Requiere atención';
            }}
            if (issueTop) {{
                issueTop.className = 'issue error';
                delete issueTop.dataset.resolved;
                const textDiv = issueTop.querySelector('.issue-text');
                if (textDiv) textDiv.innerHTML = '<strong>Error</strong>: ' + (issueTop.dataset.originalMsg || '');
                const link = issueTop.querySelector('.issue-link');
                if (link) link.style.display = 'inline';
            }}
        }}

        // Recalcular errores pendientes
        const pendientes = document.querySelectorAll('#contenedor-issues .issue.error').length;
        const badgeContador = document.getElementById('badge-contador-errores');
        const badgeSinErrores = document.getElementById('badge-sin-errores');
        const numSpan = document.getElementById('num-errores');
        if (numSpan) numSpan.textContent = pendientes;
        if (pendientes === 0) {{
            if (badgeContador) badgeContador.style.display = 'none';
            if (badgeSinErrores) {{
                badgeSinErrores.style.display = 'inline-block';
                badgeSinErrores.textContent = '✓ Todas las preguntas corregidas (listo para guardar o cargar)';
            }}
        }} else {{
            if (badgeContador) badgeContador.style.display = 'inline-block';
            if (badgeSinErrores) badgeSinErrores.style.display = 'none';
        }}
    }}

    document.querySelectorAll('[data-field="answer"], [data-field="option_correct"], [data-field="prompt"]').forEach(el => {{
        el.addEventListener('change', () => actualizarEstadoPreguntaEnVivo(el.closest('.question')));
        el.addEventListener('input', () => actualizarEstadoPreguntaEnVivo(el.closest('.question')));
    }});

    document.getElementById('review-form').addEventListener('submit',()=>{{
        const data=structuredClone(initial);
        document.querySelectorAll('[data-field]').forEach(el=>{{
            const t=+el.dataset.test,s=el.dataset.section,q=el.dataset.question,f=el.dataset.field;
            if(f==='title'||f==='description'||f==='week'||f==='cut')data.tests[t][f]=val(el);
            if(f==='prompt')data.tests[t].sections[s].questions[q].prompt=val(el);
            if(f==='answer')data.tests[t].sections[s].questions[q].answer=val(el)==='true'?true:val(el)==='false'?false:null;
            if(f==='option_text')data.tests[t].sections[s].questions[q].options[+el.dataset.option].text=val(el);
            if(f==='option_correct'){{const o=data.tests[t].sections[s].questions[q].options[+el.dataset.option];o.correct=val(el);}}
            if(f==='pair_left')data.tests[t].sections[s].questions[q].pairs[+el.dataset.pair].left=val(el);
            if(f==='pair_right')data.tests[t].sections[s].questions[q].pairs[+el.dataset.pair].right=val(el);
        }});
        data.tests.forEach(t=>t.sections.forEach(sec=>sec.questions.forEach(q=>{{
            if(sec.code==='multipleChoice')q.correct_option_letters=q.options.filter(o=>o.correct).map(o=>o.letter);
        }})));
        document.getElementById('payload').value=JSON.stringify(data);
    }});

    function toggleTestCard(idx) {{
        const body = document.getElementById(`test-card-body-${{idx}}`);
        const txt = document.getElementById(`test-toggle-text-${{idx}}`);
        if (!body) return;
        if (body.style.display === 'none') {{
            body.style.display = 'block';
            if (txt) txt.textContent = 'Contraer ▲';
        }} else {{
            body.style.display = 'none';
            if (txt) txt.textContent = 'Desplegar ▼';
        }}
    }}

    function expandirTodosTests() {{
        document.querySelectorAll('.test-card-body').forEach(b => b.style.display = 'block');
        document.querySelectorAll('[id^="test-toggle-text-"]').forEach(t => t.textContent = 'Contraer ▲');
    }}

    function contraerTodosTests() {{
        document.querySelectorAll('.test-card-body').forEach(b => b.style.display = 'none');
        document.querySelectorAll('[id^="test-toggle-text-"]').forEach(t => t.textContent = 'Desplegar ▼');
    }}

    function irAPregunta(targetId, testIndex) {{
        const body = document.getElementById(`test-card-body-${{testIndex}}`);
        const txt = document.getElementById(`test-toggle-text-${{testIndex}}`);
        if (body) {{
            body.style.display = 'block';
            if (txt) txt.textContent = 'Contraer ▲';
        }}
        const qEl = document.getElementById(targetId);
        if (qEl) {{
            qEl.scrollIntoView({{ behavior: 'smooth', block: 'center' }});
            qEl.style.transition = 'all 0.3s ease';
            qEl.style.boxShadow = '0 0 0 4px var(--foco)';
            setTimeout(() => {{ qEl.style.boxShadow = ''; }}, 2200);
            const firstInput = qEl.querySelector('input, select, textarea');
            if (firstInput) firstInput.focus();
        }}
    }}

    function marcarCambiosPendientes() {{
        const btn = document.getElementById('btn-guardar-correcciones');
        if (btn && !btn.dataset.dirty) {{
            btn.dataset.dirty = 'true';
            btn.classList.add('is-dirty');
            btn.innerHTML = '💾 Guardar correcciones * (Cambios pendientes)';
        }}
    }}

    document.querySelectorAll('#review-form input, #review-form textarea, #review-form select').forEach(el => {{
        el.addEventListener('input', marcarCambiosPendientes);
        el.addEventListener('change', marcarCambiosPendientes);
    }});
    </script>'''
    return _layout("Revisión de Tests", body)


def _render_tarjeta_estado_test(info: dict | None) -> str:
    """Tarjeta de monitoreo en vivo en /tests. Solo se llama mientras el
    test esta realmente en curso (ver _obtener_estado_test_activo) - en
    cuanto termina, deja de mostrarse solo, sin intervencion del usuario."""
    if not info:
        return ""
    jid = html.escape(str(info.get("job_id") or ""))
    st = info.get("estado", "")
    titulo = html.escape(str(info.get("titulo_doc") or info.get("asignatura") or "Test Evaluativo"))
    asignatura = html.escape(str(info.get("asignatura") or ""))
    mensaje = html.escape(str(info.get("mensaje") or ""))
    pct = int(info.get("progreso_porcentaje") or 0)
    total = int(info.get("total") or 0)
    exit = int(info.get("exitosos") or 0)
    fall = int(info.get("fallidos") or 0)

    if st == "esperando_asignatura":
        clase_card = "live-card--waiting"
        badge = '<span class="badge-dinamico badge-dinamico--error">⚠️ Selección requerida</span>'
        icono = "⚠️"
    else:
        clase_card = "live-card--running"
        badge = f'<span class="badge-dinamico badge-dinamico--proceso">⏳ En proceso ({pct}%)</span>'
        icono = "🔄"

    asig_html = f' · Asignatura: <strong>{asignatura}</strong>' if asignatura else ''

    return f'''
    <section id="card-estado-test-activo" class="panel live-card {clase_card}">
        <div style="display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:14px;margin-bottom:12px;">
            <div style="display:flex;gap:12px;align-items:center;">
                <span style="font-size:26px;">{icono}</span>
                <div>
                    <div style="display:flex;align-items:center;gap:10px;flex-wrap:wrap;">
                        <h3>Cargue de Test en PRIZMA</h3>
                        <span id="card-badge-estado">{badge}</span>
                    </div>
                    <p>Documento: <strong>{titulo}</strong>{asig_html}</p>
                </div>
            </div>
            <a href="/tests/{jid}/estado-prizma" class="boton" style="text-decoration:none;padding:10px 18px;font-size:13px;">
                ⚡ Ver monitor en vivo ➔
            </a>
        </div>

        <div style="margin:12px 0 8px;">
            <div style="display:flex;justify-content:space-between;font-size:12px;margin-bottom:5px;font-weight:600;">
                <span id="card-txt-avance" class="muted">{exit} de {total} tests guardados exitosamente</span>
                <span id="card-txt-pct" style="color:var(--acento-texto);font-weight:800;">{pct}%</span>
            </div>
            <div class="progress-track">
                <div id="card-barra-progreso" class="progress-fill" style="width:{pct}%;"></div>
            </div>
        </div>

        <div style="display:flex;justify-content:space-between;align-items:center;font-size:12px;margin-top:10px;flex-wrap:wrap;gap:8px;">
            <span id="card-mensaje" class="muted" style="font-style:italic;">💬 {mensaje}</span>
            <span id="card-stats" class="muted" style="font-weight:600;">Exitosos: {exit} · Fallidos: {fall} · Total: {total}</span>
        </div>
    </section>
    '''
