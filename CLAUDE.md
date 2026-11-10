# AUTO PRIZMA PRO

Guía principal para cualquier sesión de Claude (o persona) que trabaje en este repositorio.
Complementa a `README.md` (instalación, uso y despliegue). Si algo de este archivo contradice el código, **manda el código**: corrige este archivo.

> **Regla permanente del usuario:** cada cambio de código debe ir acompañado de la actualización de este `CLAUDE.md` en la misma tarea.

## Propósito

Aplicación web interna (FastAPI) que automatiza tareas en la plataforma educativa **PRIZMA** (`https://admin.prizma.site`) con un navegador Chromium controlado por Playwright:

1. **Cargue de recursos**: usa una matriz local `.xlsx`/`.csv` y un ZIP con archivos `.h5p`/`.pdf` y videos a cámara `.webm`; los recursos se resuelven solo desde ese ZIP. Los videos a cámara se cargan en Tema → Recurso tras validar programa y tema. Genera un reporte CSV por cargue.
2. **Tests evaluativos**: a partir de un `.docx` local crea cuestionarios en PRIZMA. Puede ejecutarse solo (`/tests`) o junto con el cargue de recursos.
3. **Cargue Moodle local**: sección `/moodle` que analiza matriz CSV/XLSX y ZIP de PDF/H5P, muestra vista previa y publica en el curso Prizma con Chromium visible e inicio de sesión manual.
4. **Matrices**: `/matrices-favoritas` permite a los usuarios autenticados guardar, editar y eliminar enlaces compartidos a matrices; los datos se guardan de forma atómica en `data/matrices_favoritas.json` y permanecen hasta su eliminación manual. La vista incluye encabezado ilustrado, formulario destacado y tarjetas con animaciones sutiles compatibles con `prefers-reduced-motion`.
5. **Automatizaciones**: `/automatizaciones-n8n` ofrece formularios con puente servidor-servidor a webhooks HTTPS privados; las cuatro tarjetas, incluida Descarga de recursos, usan el mismo modal nativo. El orden de tarjetas inicia con API de PRIZMA, Crear semanas de curso, Descarga de recursos y Matriz de importación CSV; después aparecen las restantes. La vista tiene encabezado de operaciones, iconografía por flujo, estados visuales, animaciones sutiles y soporte para `prefers-reduced-motion`. La landing ofrece además acceso directo a PRIZMA administrativo (`https://admin.prizma.site/`), que abre en pestaña nueva. La tecnología n8n se mantiene como detalle interno.
6. **Auditoría profunda de curso**: `/auditor-curso` (PRIZMA administrativo) y `/moodle-auditor-curso` (Moodle, Chromium visible) recorren actividades publicadas (PRIZMA: pestañas OVI/OVA/CHALLENGE del listado; Moodle: semanas y módulos) y abren recursos para comprobar contenido y títulos. Moodle admite una matriz CSV/XLSX opcional para comparar nombres/semanas esperados; actividades cuyo título identifica el syllabus/sílabo se marcan omitidas y no se abren ni descargan. También puede auditarse sin matriz. Reutiliza el perfil del Cargue Moodle, espera el login manual, reabre el enlace del curso y no activa el modo edición. Lee el nombre del módulo (no etiquetas «H5P»/«File»), descubre secciones por enlaces y DOM y limita a unos 30 segundos la espera por recurso; detiene el recorrido después de tres timeouts consecutivos. Cancelar deja solo los resultados ya revisados y el recurso en curso. Solo lectura: no sube, edita ni borra nada. Deja tabla y reporte CSV/JSON.

En la auditoría PRIZMA, las acciones de Programas y selección de curso adoptan una pestaña nueva si la plataforma la abre. En la auditoría Moodle, el enlace debe ser HTTPS de `prizma.americana.edu.co/course/view.php` e incluir un `id` numérico; otras rutas, hosts o enlaces sin ID se rechazan antes de abrir Chromium. El login detecta la sesión autenticada mediante el estado de Moodle, no por buscar una etiqueta localizada como «Curso».

La auditoría Moodle reutiliza una pestaña para los recursos y captura los eventos de descarga directa; valida PDFs descargados con la sesión activa para no confundir una descarga iniciada con un recurso que agotó el tiempo de apertura.

El selector opcional de matriz de la auditoría Moodle usa el mismo componente visual de carga de archivos que el resto de la app (dropzone temática, botón y nombre del archivo), no el control nativo sin estilo del navegador. En el formulario se mantiene compacto y los campos se alinean arriba para que la dropzone no estire el enlace del curso. Las rutas Playwright permanecen síncronas; las cargas `UploadFile` de rutas sync se leen desde `.file`.

En la auditoría Moodle, el enlace debe ser HTTPS de `prizma.americana.edu.co/course/view.php` e incluir un `id` numérico; otras rutas, hosts o enlaces sin ID se rechazan antes de abrir Chromium.

En uso local no hay cuentas de Auto Prizma: las peticiones loopback usan la identidad fija `local` y acceden directamente. Los despliegues remotos conservan usuarios autenticados y separación de datos por cuenta.

## Arquitectura

Monolito FastAPI en capas, dentro del paquete `auto_prizma/`. El HTML se genera en el servidor como strings de Python (no hay framework de frontend ni templates).

```
Navegador ──HTTP──> api/routes/* ──> services/* ──> automation/prizma/engine.py ──Playwright──> PRIZMA
                         ├──> services/n8n.py ──HTTPS──> webhooks n8n
                         └──> web/views.py y vistas de cada ruta ──> web/layout.py + static/app.css / app.js
evaluative_tests/  = módulo de funcionalidad completo (rutas, estado, parser, automatización, vistas)
core/config.py     = toda la configuración; core/application.py = instancia FastAPI compartida
```

- Las rutas se registran **al importar** cada módulo de `api/routes/` sobre la instancia compartida `auto_prizma.core.application.app` (decoradores `@app.get/@app.post`). `evaluative_tests/routes.py` usa un `APIRouter` que `main.py` incluye al final.
- Estado de trabajos en memoria (`TRABAJOS`, cola, jobs de tests). El inicio reserva atómicamente la etapa antes de validar credenciales en PRIZMA (sin sostener el lock durante esa consulta); una cancelación durante la validación impide el encolado. En el flujo combinado, el job de Test solo se registra después de validar matriz y ZIP. Persistencia en archivos JSON/CSV bajo `DATA_DIR`.
- Cada cargue corre en su propio hilo con su propio Chromium; máximo 2 simultáneos.
- **Interfaz**: todas las páginas se arman con el marco común `web/layout.py` (`render_page`; el login remoto con `render_public_page`): menú lateral con íconos, estado real del servicio, barra superior con tema claro/oscuro y aviso de ambiente de pruebas. El marco común reorganiza menú, pestañas, tablas, formularios y paneles para tablet y móvil, evitando desbordamientos horizontales. Cada módulo conserva puntos de quiebre propios para sus grillas y controles (Cargue PRIZMA, Moodle, tests, auditorías, cursos, progreso, landing y matrices favoritas). Los paneles comparten una superficie de tarjeta con acento suave, borde y elevación coherentes; las vistas destacadas pueden añadir iconografía y animación breve. Las zonas de selección de archivos muestran un brillo animado en el borde hasta elegir/soltar un archivo; el estado usa `tiene-archivo`, independiente de la tarjeta resumen `.archivo-listo`, y la animación se detiene al quedar listo o deshabilitado respetando `prefers-reduced-motion`. El menú de perfil solo se muestra en sesiones autenticadas remotas; se oculta en el acceso local directo. El aspecto común vive en `static/app.css` y el comportamiento común en `static/app.js`.

El estado y los planes de trabajo se documentan en la tarea o issue correspondiente, no como una cronología duplicada aquí.

## Estructura del proyecto

```
auto-prizma-pro/
├── main.py                         # Arma la app, importa rutas y monta /tests
├── auto_prizma/
│   ├── core/
│   │   ├── application.py          # app = FastAPI(...)
│   │   ├── storage.py              # read_json / write_json_atomic / write_text_atomic (escritura atómica)
│   │   └── clock.py                # _ahora_colombia / _ahora_colombia_iso
│   ├── api/routes/
│   │   ├── static_files.py         # Logo, /app.css y /app.js (públicos)
│   │   ├── auth.py                 # Middleware de sesión y login
│   │   ├── home.py                 # / landing del sistema y /automatizaciones-n8n
│   │   ├── matrix_favorites.py     # /matrices-favoritas: catálogo compartido CRUD, sin vencimiento
│   │   ├── n8n.py                  # POST /automatizaciones-n8n/ejecutar y GET /automatizaciones-n8n/estado
│   │   ├── analysis.py             # /prizma y POST /analizar; valida el test antes de combinarlo con recursos y la preparación (syllabus/línea académica) antes del test
│   │   ├── uploads.py              # /iniciar, /cargue-actual, /proceso, /estado, /cancelar
│   │   ├── reports.py              # /historial, /reportes, /reporte, /reporte-guardado
│   │   ├── health.py               # /estado-servicio (JSON con el estado de Chromium y PRIZMA)
│   │   ├── moodle_resources.py     # /moodle: análisis, revisión, publicación y reportes Moodle locales
│   │   ├── course_audit.py         # /auditor-curso: auditoría profunda de un curso PRIZMA publicado (solo lectura)
│   │   └── moodle_audit.py         # /moodle-auditor-curso: auditoría profunda de un curso Moodle (solo loopback)
│   ├── services/
│   │   ├── auth.py                 # Usuarios (usuarios.json), PBKDF2, cookies HMAC, bloqueo por intentos
│   │   ├── matrix_analysis.py      # CSV→XLSX, análisis local de matriz y ZIP
│   │   ├── upload_jobs.py          # TRABAJOS, cola/hilos, test dentro del cargue y servicios de las rutas
│   │   │                           # (create_analyzed_job, validate_access_and_enqueue, active_jobs, cancel_job, public_job_status)
│   │   ├── history.py              # historial.json, nombres/rutas de reportes, consulta por usuario, lectura del CSV
│   │   ├── h5p_preview.py           # Comparación previa de matriz, archivo ZIP y títulos internos H5P (reutiliza Auditor)
│   │   ├── health.py               # Estado real: Chromium instalado y PRIZMA responde (con memoria de unos minutos)
│   │   ├── n8n.py                  # Catálogo, validación y puente privado a webhooks
│   │   ├── matrix_favorites.py     # Lectura y CRUD persistente de enlaces a matrices
│   │   ├── moodle_resources.py     # Vista previa, extracción ZIP, comparación de títulos H5P, jobs y reportes Moodle
│   │   └── moodle_audit.py         # Trabajos de auditoría de curso Moodle (hilo propio, reporte CSV/JSON, cancelación)
│   ├── automation/
│   │   ├── content_checks.py       # Validación por bytes de archivos descargados (PDF con zlib, H5P con zipfile)
│   │   ├── prizma/
│   │   │   ├── engine.py           # Motor de cargue PRIZMA (Playwright) + lectura de matriz + reporte CSV
│   │   │   └── html_field.py       # Formato HTML: leer el .html, escribirlo en el campo Html, quitar el archivo previo de Recurso
│   │   └── moodle/
│   │       └── client.py           # Chromium visible, login manual y publicación Moodle PDF/H5P (+ recorrido de auditoría)
│   ├── domain/
│   │   ├── file_names.py           # file_base_name / exact_name_key (nombres de archivo)
│   │   ├── moodle_resources.py     # Reglas de destinos y matching Moodle
│   │   └── moodle_audit.py         # Reglas puras de la auditoría de curso Moodle (semanas, recursos, veredictos)
│   ├── web/
│   │   ├── layout.py               # Marco común y pestañas internas para PRIZMA/Moodle
│   │   ├── icons.py                # Íconos SVG (icon(nombre))
│   │   ├── landing_views.py         # Landing con cuatro tarjetas, accesos directos y movimiento reducido; automatizaciones n8n
│   │   ├── matrix_favorites_views.py # Catálogo de matrices favoritas y formularios
│   │   ├── course_audit_views.py    # Páginas de la auditoría de curso (PRIZMA y Moodle)
│   │   ├── views.py                # Cargue PRIZMA (encabezado de página y etapas; formulario responsive sin saludo, grilla de archivos autoajustable, tarjeta de syllabus/preparación y revisión con bloque `_preparation_block`)
│   │   ├── moodle_views.py         # /moodle: formulario, vista previa, progreso/reporte y pestaña de plantillas HTML para etiquetas Moodle
│   │   └── moodle_report_views.py  # «Ver» un reporte Moodle guardado (cargue o auditoría) con búsqueda, filtros y paginación
│   └── evaluative_tests/           # Módulo de tests evaluativos
│       ├── models.py, parser.py, validation.py, serializer.py
│       ├── automation.py           # PrizmaTestAutomator (Playwright); solicita confirmación si hay opciones ambiguas
│       ├── execution.py            # Ejecución en segundo plano
│       ├── state.py                # Jobs en memoria, usuario PRIZMA recordado
│       ├── views.py                # HTML del módulo; una línea académica, simulación segura por defecto, Facultad opcional y nivel solicitado
│       └── routes.py               # APIRouter /tests/...; encabezado Nuevo Test sigue el patrón común
├── scripts/
│   ├── manage_users.py             # CLI de usuarios
│   ├── check_prizma_connection.py  # Prueba manual: navegador visible, login manual, no modifica nada
│   ├── run_local.ps1               # Lanzador local: uvicorn --reload en 127.0.0.1 con PYTHONIOENCODING=utf-8 (-Puerto)
│   └── test_syllabus_upload.py     # Prueba aislada de subida de syllabus (sin matriz ni ZIP; credenciales por env, se niega contra producción)
├── tests/                          # pytest (PRIZMA y Playwright simulados)
├── static/                        # auto_prizma_logo.png, app.css (estilos comunes) y app.js (comportamiento común)
├── .env.example                    # Variables soportadas (sin valores)
├── requirements.txt                     # pytest ya incluido (no hay requirements-dev.txt)
├── Dockerfile                      # python:3.12, playwright chromium, uvicorn main:app :8000
├── deploy/oracle/                  # Despliegue gratuito en Oracle Cloud: docker-compose (app + Caddy HTTPS),
│                                   # Caddyfile, .env.example, setup-server.sh
├── docs/DEPLOY_ORACLE.md           # Guía paso a paso del despliegue en Oracle Cloud
├── README.md                       # Guía corta: instalar, arrancar, crear usuario, Moodle local
├── GUIA_DETALLADA.md               # Documentación completa (antes era el README largo)
└── data/ uploads/ temp/ resultados/  # Generados en ejecución, no versionados (data/ contiene secretos)
```

## Componentes

| Componente | Responsabilidad | Notas |
|---|---|---|
| `main.py` | Orden de arranque | Importa las rutas y luego `/tests`. Expone `app.state.*` que usa el módulo de tests. |
| `core/config.py` | Única fuente de configuración | Ver sección Configuración. |
| `api/routes/*` | HTTP | Delgadas para análisis, cargues y reportes (delegan en `services/`). Aún contienen el contenido HTML de sus páginas, pero el marco es común (`web/layout.py`); reportes Moodle comparte el patrón visual de encabezado, mosaicos, filtros y tabla con reportes PRIZMA. |
| `web/layout.py` | Marco de todas las páginas | `render_page(...)`; el sidebar lista Inicio, Control Tower (Google Apps Script, en pestaña nueva), Matrices, Cargue PRIZMA, Cargue Moodle y Automatizaciones. Pestañas internas agrupan herramientas PRIZMA/Moodle y normalizan alineación, tamaño de títulos e iconos y márgenes de cabecera; `status_pills()` y `environment_notice()` son componentes comunes. |
| `web/landing_views.py` | Inicio y automatizaciones | Landing con cuatro tarjetas en orden: Matrices, Cargue PRIZMA, Cargue Moodle y Automatizaciones; Control Tower queda como acceso directo en cabecera y sidebar, no como tarjeta. «Entrar a PRIZMA» abre `https://admin.prizma.site/` en pestaña nueva. |
| `services/auth.py` | Identidad local y acceso remoto | `USUARIO_ACTUAL` (contextvar) propaga `local` o la cuenta remota autenticada a endpoints e hilos. |
| `services/matrix_favorites.py` | Matrices | Catálogo compartido de enlaces HTTP(S), con validación y escritura JSON atómica en `DATA_DIR`; sin expiración automática. |
| `services/upload_jobs.py` | Ciclo de vida del cargue | `create_analyzed_job` → `validate_access_and_enqueue` → `_encolar_trabajo` → `_despachar_cargues_pendientes` → hilo → `ejecutar_cargue_con_historial` → `engine.ejecutar_cargue`. `cancel_job`, `public_job_status` y `active_jobs` para las rutas. `create_analyzed_job` acepta `contenido_syllabus`/`nombre_syllabus`/`linea_academica`/`nivel_pensum`, guarda `uploads/<id>/syllabus.pdf` y arma `trabajo["preparacion"]` (`syllabus`, `video_intro`, `video_cierre`, `linea_academica`, `nivel`, `curso`; `curso` solo con línea **y** nivel parseables), que viaja también en `resultado["preparacion"]` y se pasa a `ejecutar_cargue`. |
| `services/history.py` | Historial y reportes | `_agregar_registro_historial` (sin duplicar id), `_historial_del_usuario` (solo registros propios; purga a 15 días junto con CSV), `find_user_record`, `saved_report_path` (solo basename dentro de `RESULTADOS_DIR`). |
| `api/routes/moodle_resources.py` | Reportes Moodle locales | Reportes en una carpeta por usuario; elimina pares CSV/JSON con más de 15 días al consultar o descargar reportes. `/moodle-reportes` lista y descarga los dos tipos (`_MOODLE_REPORT_PREFIXES`: `moodle-cargue-*` y `moodle-auditoria-*`) con columna Tipo; en una auditoría Cargados/Ya estaban se muestran «—» y Pendientes = revisar + falta. Corregido el 2026-11-05: antes solo listaba los de cargue y las auditorías guardadas no aparecían. Cada fila tiene **Ver** (pedido del usuario, 2026-11-05): `GET /moodle-reportes/{archivo}/ver` (solo loopback, nombre validado con `_is_report_filename`, 404 si no existe o venció) pinta el JSON con `web/moodle_report_views.render_moodle_saved_report`: resumen, tabla `data-tabla` (buscar, filtro por estado y por semana, 25 por página) y descargas; los detalles largos muestran la primera línea y el resto en `<details>`. La carpeta depende de la identidad: los reportes hechos con el antiguo usuario de `AUTO_PRIZMA_SIN_LOGIN` quedan en la carpeta de ese usuario, no en la de `local`. |
| `services/moodle_resources.py` | Análisis y jobs Moodle | Lee matriz CSV/XLSX, extrae PDF/H5P de ZIP y aplica matching; rechaza PDF vacío/ilegible y para aprobar H5P exige título raíz de `content/content.json` igual (normalizado) al de la matriz; no usa títulos de capítulos como portada. Sin título raíz coincidente, requiere adjunto manual por fila. |
| `api/routes/course_audit.py` + `automation/content_checks.py` | Auditoría profunda de curso PRIZMA | `/auditor-curso` exige línea académica (programa/pensum/código+nombre de asignatura), nivel de pensum, facultad opcional y credenciales. Recuerda el usuario PRIZMA mediante el mismo token local/por usuario que Tests, con opción para borrar el recordatorio; nunca persiste la contraseña. El formulario permite elegir Chromium en segundo plano o visible. El login estándar entra a Actividades para los cargues; la auditoría lo desactiva para conservar el dashboard. En Programas activa la pestaña Facultad solo si se suministró ese dato; si no, cambia a Programa/Programas (singular o plural) y reporta las pestañas visibles si no logra ubicar la fila. Después busca el código de programa y sigue Programa → Pensum → Nivel → Asignaturas por Pensum. Busca y valida una única fila por código/nombre, entra con la flecha de cada fila y abre la asignatura con el ojo; pulsa Vista previa y solo continúa si aparecen pestañas del curso. Luego recorre OVI/OVA/CHALLENGE. Su progreso usa `GET /auditor-curso/{id}/estado`; el propietario se obtiene de `request.state.usuario` (identidad fijada por el middleware, no del contextvar en la ruta sync), evitando falsos «auditoría no encontrada». `_pagina_progreso` acepta una URL de estado propia y muestra fallos de polling en lenguaje claro (sin valores `undefined`). `content_checks` valida por bytes (sin navegador): PDF con cabecera/hojas/contenido vía zlib y H5P con `h5p.json`, `content.json` legible y bibliotecas; `evaluar_recurso_auditoria` compara exclusivamente los títulos principales de portada en `content/content.json` (nunca `h5p.json` ni títulos de capítulos), normalizados con `auditor.procesar.clave`. Reporte CSV propio en `RESULTADOS_DIR`. |
| `services/moodle_audit.py` + `domain/moodle_audit.py` | Auditoría profunda de curso Moodle | Trabajo propio en memoria (dueño, estado `logging_in/auditing/completed/stopped/cancelled/error`, resultados en vivo, cancelación entre recursos) con Chromium visible, perfil compartido con Cargue Moodle y login manual; después del login abre de nuevo el enlace del curso y no activa edición. La matriz CSV/XLSX es opcional, se procesa en memoria y compara semana/nombre entre filas y actividades encontradas; títulos que identifican syllabus/sílabo se excluyen antes de abrirlos o compararlos. Tres timeouts consecutivos detienen el recorrido y Cancelar no añade filas pendientes. El cliente espera el evento `download` si Playwright informa «Download is starting». `domain` contiene las reglas puras (`parse_week_links`, `parse_activity_cards`, `interpret_activity_probe`, `audit_row`). El cliente `list_weeks`/`open_week_url`/`list_week_activities`/`audit_activity`/`fetch_bytes` recorre el curso y sondea cada recurso (iframe H5P con interior leído si es mismo origen, PDF embebido o descargado y validado con `content_checks`). Reporte `moodle-auditoria-*` en la carpeta por usuario de Moodle (purga a 15 días). La página (`web/course_audit_views.render_moodle_audit_page`) lleva `data-finished` y solo consulta `/estado` (y recarga al terminar) si se pintó con el trabajo en curso; corregido el 2026-11-05: antes consultaba siempre y, ya terminada, recargaba sin fin (la página quedaba cargando y sin scroll). |
| `web/moodle_views.py` | Vistas Moodle | La página local de Cargue Moodle no muestra el aviso redundante de ejecución local; los iconos de encabezado usan el acento temático común. La pestaña `/moodle-etiquetas` presenta tarjetas independientes de banner, infografía y video; los selectores de imagen ocultan el control nativo del navegador y usan el botón visual común, con nombre del archivo visible. Al seleccionar o arrastrar imagen se genera HTML de inmediato, y video se genera desde URL HTTP(S). La plantilla se resuelve internamente, sin selector. La imagen local se codifica como Data URL en `src` (no se sube a Moodle). El HTML completo queda plegado porque el Base64 de la imagen hace extensa la cadena; el botón copia el código íntegro. |
| `api/routes/auditor.py` + `auditor/procesar.py` | Auditoría puntual de matriz/ZIP | `/auditor` y `/moodle-auditor` comparten la validación de archivos y vista de resultados; la alerta de coincidencia H5P compara el título del paquete (`h5p.json`) con el nombre del recurso de la matriz. Una portada ausente o la ubicación en subcarpeta no generan por sí solas alerta; los nombres vacíos, H5P ilegibles y archivos de 0 bytes siguen reportándose. La ruta web pasa `salida=None`: no guarda auditorías ni ofrece historial/descargas. La CLI conserva su salida explícita por defecto. |
| `auditor/procesar.py` (alcance) | Qué filas se auditan | Toda fila con enlace se audita, tenga o no categoría OVI/OVA/CHALLENGE (sin categoría queda una advertencia). Videos (Video Intro/Cierre/a cámara) e imágenes ya no son «fuera de alcance»: `EXT_POR_TIPO` los mapea a las familias de `EXTS_POR_FAMILIA` y se emparejan por nombre del recurso o por el nombre de la columna Enlace. |
| `api/routes/courses.py` + `services/course_state.py` | Estado por curso | Registros aislados por identidad de usuario, con purga de estados con más de 15 días y escrituras JSON atómicas. |
| `automation/moodle/client.py` | Publicación Moodle | Chromium visible local con login manual, detección de duplicados y publicación PDF/H5P. Independiente del motor administrativo. |
| `core/storage.py` | Archivos de datos | Toda escritura de JSON/texto en `data/` debe ser atómica con estas funciones. `data/` y `data/matrices_favoritas.json` están excluidos de Git; los datos locales no se incorporan al bajar cambios. |
| `automation/prizma/engine.py` | Todo lo que toca PRIZMA en el cargue | Funciones clave: `leer_actividades_excel`, `determinar_tipo_archivo`, `resolver_recurso`, `validar_credenciales_prizma`, `iniciar_sesion_prizma`, `procesar_actividad`, `ejecutar_cargue`, `guardar_resultado`, `EQUIVALENCIAS_PROGRAMAS`. `verificar_actividades_prizma` inspecciona el archivo H5P adjunto en modo solo lectura y compara el título del paquete con el nombre de la matriz; no ejecuta el reproductor H5P. Fase de **preparación previa al cargue** (`prepare_assignment`, `detect_assignment_videos`, `extract_zip_member`, `seleccionar_curso_prizma` con `open_action="edit"`, `enter_activities_module`, `set_preparation_details`, `report_preparation_actions`, `empty_description_field`): sube syllabus y videos de intro/cierre a la ficha del curso y **deja vacío el campo de descripción** antes de subir recursos; los fallos no abortan el cargue (se registran como avisos). Los videos a cámara (`.webm`) se emparejan por similitud entre el nombre del recurso de la matriz y el archivo del ZIP, y se cargan en **Tema → Recurso** solo tras validar coincidencia exacta de programa y tema. La verificación en modo solo lectura comprueba tema y programa, sin buscar allí el nombre del recurso. |
| `evaluative_tests/` | Funcionalidad completa de tests | Se integra con el cargue vía `upload_jobs._ejecutar_test_en_cargue` y con historial/reportes vía `app.state`. |

## Convenciones

- Datos como `dict` simples; errores del motor como strings `ERROR_*` que terminan en reportes, historial y UI (no renombrarlos).
- HTML en raw strings con marcadores `__NOMBRE__` + `.replace`, valores escapados con `html.escape`.
- **Páginas**: toda página con sesión se arma con `web/layout.render_page(...)` (nunca copiar el menú ni el `<head>`); el contenido se envuelve en `.contenido-pagina` para usar la separación vertical común. Colores solo con las variables de `static/app.css` (`--panel`, `--texto`, `--acento`, `--verde-suave`, ...), sin colores fijos ni reglas `html[data-theme="dark"] ... !important`; íconos con `web/icons.icon()`. El tema claro usa superficies blancas sobre fondo claro con controles primarios azul marino; el oscuro conserva la composición con fondo negro y acentos morados. Los colores funcionales de éxito/error/aviso se toman también de variables temáticas para conservar contraste. Las pestañas activas sobre fondo `--acento` usan `--boton-texto` para mantener contraste en ambos temas. Los componentes comunes (`.panel`, `.panel-contenido` para paneles con margen interno uniforme, `.boton`, `.chip`, `.badge-*`, `.mosaico`, `.tabla`, `.aviso`, `.dropzone`, `.menu-desplegable`, `.dialogo`) están en `app.css`. Una tabla con `data-tabla` + controles `data-control-tabla="<id>"` obtiene búsqueda, filtros, orden y paginación de `app.js` sin JS propio.
- Si un recurso estático cambia, la URL cambia sola (`?v=<fecha de modificación>`, `layout.asset_url`).
- Archivos de datos: usar `core/storage.py` (`read_json`, `write_json_atomic`, `write_text_atomic`; escritura atómica `*.tmp` + `os.replace`). `read_json` recibe qué errores cuentan como "ilegible": `usuarios.json` solo trata errores de lectura/JSON (otros se propagan para no sobrescribir un archivo dañado al crear un usuario).
- Un servicio que falla por una regla de negocio lanza `ValueError` con el mensaje para el usuario y la ruta lo muestra.
- Logging con `print()` (no hay módulo `logging`).
- Concurrencia con `threading.Lock/RLock/Condition`; fechas de usuario en `America/Bogota` (`ZONA_HORARIA_COLOMBIA`).
- Archivos `.py` del working tree con finales CRLF (`core.autocrlf=true`).
- No guardar copias `*_backup*.py`, `parche_*.py` ni `.zip` (bloqueados en `.gitignore`): git conserva el historial.

## Idioma

| Elemento | Idioma | Regla |
|---|---|---|
| Archivos y carpetas de código | **Inglés** | Obligatorio para todo archivo nuevo. |
| Funciones, clases, variables, módulos **nuevos** | **Inglés** | `get_user()`, `upload_resource()`. |
| Funciones/variables **existentes** en español | Se conservan | No traducir en masa: rompe imports, tests y `patch("...")`. Traducir solo con análisis de consumidores y en un cambio dedicado. |
| Comentarios y docstrings | **Español** | Incluso en código nuevo en inglés. |
| URLs, campos de formulario, claves JSON, env vars, archivos de `data/`, códigos `ERROR_*` | Sin cambios | Son contratos (navegador/JS, Railway, datos históricos). |

`auto_prizma` es el nombre del producto y se mantiene como nombre del paquete (no se usa `app/` porque `import app.x` en `main.py` taparía la instancia `main:app`).

## FastAPI

- Instancia: `auto_prizma.core.application.app`; ASGI: `main:app`.
- Middleware `exigir_sesion` (`api/routes/auth.py`): en loopback asigna `local_identity_for` sin cookie (reutiliza la única cuenta activa existente para conservar su historial/token; si no hay una única, usa `local`); fuera de loopback exige cookie `ap_sesion` y cuenta activa, o responde 303 a `/login` / JSON 401. Fija `request.state.usuario` y `USUARIO_ACTUAL`.
- El acceso local directo no requiere usuarios ni variables especiales y no muestra menú de perfil (sustituye al antiguo `AUTO_PRIZMA_SIN_LOGIN`, que ya no se lee). `scripts/run_local.ps1` solo arranca uvicorn `--reload` en 127.0.0.1 con `PYTHONIOENCODING=utf-8`. La autenticación y gestión de cuentas se conservan solo para despliegues remotos; no exponer la instancia local en una interfaz de red sin protección.
- `/moodle` y sus endpoints de preview/publicación/reportes son solo para loopback, porque Chromium aparece en el mismo escritorio para el login manual al curso. `/moodle-auditor-curso` (auditoría de curso completo) también es solo loopback, por la misma razón, y expone el trabajo por dueño (`/moodle-auditor-curso/{id}/estado|cancelar|reporte`). `/moodle-reportes` lista CSV/JSON persistidos en el directorio aislado por identidad local.
- El sidebar principal contiene Inicio, Control Tower, Matrices, Cargue PRIZMA, Cargue Moodle y Automatizaciones, en ese orden. Cargue Moodle abre primero `/moodle-auditor` tanto desde el menú como desde Inicio; la pestaña Cargue conserva el formulario de publicación en `/moodle`. Las matrices compartidas se mantienen localmente en `data/matrices_favoritas.json` hasta eliminarlas manualmente; Git ignora ese archivo. Estado de cursos, historial y reportes son datos locales: se aíslan por identidad de usuario cuando aplica y los registros/reportes vencen a los 15 días. Cargue PRIZMA abre inicialmente en Auditor; sus pestañas siguen este orden: Auditor, Cargue, Test, Auditar curso (`/auditor-curso`), Cursos, En curso, Historial y Reportes. Moodle tiene pestañas independientes en este orden: Auditor, Cargue, Etiquetas, Auditar curso (`/moodle-auditor-curso`) y Reportes; `/moodle-auditor` reutiliza la auditoría local de matriz/ZIP, `/moodle-etiquetas` ofrece los snippets HTML. La auditoría PRIZMA descubre el curso sin matriz; la auditoría Moodle admite matriz opcional como referencia, pero ninguna de las dos consulta syllabus (solo lectura).
- Rutas principales: ver la documentación funcional. `/docs` requiere autenticación solo en despliegues remotos. `/app.css` y `/app.js` son públicas; `/estado-servicio` devuelve JSON.
- Endpoints que usan Playwright sync deben ser `def` (threadpool) o hilos propios, **nunca `async def`**.

## Services

`auth`, `matrix_analysis`, `upload_jobs`, `history`, `health`, `n8n`. Reglas:
- La lógica de negocio nueva va aquí, no en las rutas. Las funciones nuevas que los servicios exponen a las rutas tienen nombre en inglés (`create_analyzed_job`, `cancel_job`, ...).
- Un servicio no importa módulos de `api/`.
- `upload_jobs` importa `evaluative_tests.state/execution` DENTRO de `_ejecutar_test_en_cargue` a propósito: es enlace tardío y las pruebas parchean `auto_prizma.evaluative_tests.execution.ejecutar_test_job`; no subir ese import a nivel de módulo. `evaluative_tests` ya no importa `upload_jobs` (usa `services/history`), así que no hay ciclo.
- La creación de jobs de test es única: `evaluative_tests.state.register_test_job` (la usan `/tests/analizar` y `/analizar`).
- `health` (decisión del usuario, 2026-10-07: indicadores reales, no texto fijo): `check_chromium` pregunta a Playwright por la ruta del ejecutable (no abre el navegador; también vale `chromium_headless_shell-<rev>`), `check_prizma` hace un GET a `URL_PRIZMA` (cualquier respuesta < 500 = disponible). Cada resultado se guarda `HEALTH_CHROMIUM_TTL_SECONDS` / `HEALTH_PRIZMA_TTL_SECONDS`. Las páginas pintan lo que haya en memoria (`cached_service_status`, nunca bloquea) y `app.js` pide `/estado-servicio` al cargar y cada 5 min.
- `moodle_resources` analiza matriz/ZIP, controla ownership del job y guarda reportes. Realimentación (2026-10-20, a pedido del usuario): las filas con solo «Nombre del recurso» son **títulos de tema** (`reason: "section-heading"`, se informan aparte, no son error); las filas incompletas guardan qué campos faltan (`missing`). Cada entrada lleva `kind` (`domain.resource_kind`: `h5p`, `infografia`, `video-avatar`, `pdf`, `reto`, `otro`) para seleccionar por tipo y semana en la vista. **Pausar/reanudar/cancelar** (`pause_moodle_publish`, `resume_moodle_publish`, `cancel_moodle_publish`; rutas `POST /moodle/{id}/pausar|reanudar|cancelar`, JSON): actúan entre recursos, nunca a mitad de una subida; el estado `paused` espera en `_wait_while_paused`. `/moodle/{id}/estado` (`public_moodle_status`) devuelve también `results` en vivo (`live_results`), `started_at` y las banderas de pausa/cancelación. El reporte guarda `previewKey` y `kind` por fila (solo JSON; el CSV mantiene sus columnas) para el botón «Reintentar los que no se cargaron». Estado final `cancelled` si se canceló. **Vista** (decisión del usuario, 2026-10-21): mientras se publica, `/moodle/{id}` muestra SOLO la pantalla «Cargue Moodle en progreso» (como `/proceso` del cargue PRIZMA: % y barra, contadores, lista `job["queue"]` con cada recurso pendiente/en curso/resultado, panel con recurso actual y Pausar/Reanudar/Cancelar), sin la tabla de la matriz; al terminar muestra el resultado y la matriz solo con `?vista=previa`. **Sin duplicados** (2026-10-21, el usuario vio recursos repetidos en el curso): (1) `open_week` espera a que cargue la página de la semana (`wait_for_url` con `section=N` + `networkidle`; antes revisaba a los 250 ms la página anterior y no veía nada) y `find_existing_resource` espera a que aparezcan los bloques de la semana; (2) `_published_before`: cualquier registro del historial local cuenta como publicado (antes solo los `verified-`), y también uno de otra versión de la matriz con el mismo curso, semana, título y bloque. `automation/moodle/client.py` es un cliente distinto del motor administrativo PRIZMA; inicia Chromium visible, espera login manual hasta 120 s y conserva perfil aislado por usuario en `DATA_DIR/moodle_profiles/`.

## Integrations

- Cualquier integración nueva va en `integrations/<servicio>/` y lee su configuración de `core/config.py`.

## Automation

- `automation/prizma/engine.py`: motor del cargue de recursos (mezcla aún lectura de matriz, índice ZIP, reporte CSV y Playwright; se dividirá en la fase 7). La **auditoría de curso** (`auditar_curso_prizma`) vive aquí porque es navegador puro: `_abrir_sesion_inicial` con credenciales, `entrar_categoria` por pestaña, `enumerar_actividades_curso` (JS que etiqueta cada fila de 3 botones con `data-prizma-scan-id` y toma el nombre de `obtener_nombre_fila`), `auditar_actividad_curso` (abre en modo edición, descarga el archivo con el mismo botón de vista previa/descarga, valida con `content_checks` y cierra con `cancelar_edicion_segura`) y `encontrar_fila_escaneada` (relee el listado en cada visita: los ids de escaneo no sobreviven a un repintado). Cancelable, con progreso en el trabajo y sin tocar formularios de PRIZMA.
- **Preparación de la asignatura antes del cargue** (`prepare_assignment`, invocada por `ejecutar_cargue` cuando `preparacion` trae syllabus o videos): se abre la sesión **sin** entrar a Actividades (`iniciar_sesion_prizma(..., abrir_actividades=False)`), se va al home (`open_prizma_home`), se localiza el curso con `seleccionar_curso_prizma(open_action="edit")` (botón editar de la fila identificado primero por aria-label/title «editar»/«edit»/«pencil»/«lápiz» y, si no lo traen, por la clase `btnLila` dentro de esa misma fila — nunca por posición, para no confundirlo con la papelera `btnWhite`; el respaldo ojo → «Editar» en la ficha no aplica hoy: la página de detalle solo ofrece «Vista previa»/«Volver»), se suben syllabus (`find_field_file_input`/`upload_file_to_field`), videos de intro/cierre extraídos del ZIP (`detect_assignment_videos` + `extract_zip_member`) y se deja **vacío el campo de descripción** (`empty_description_field`: Ctrl+A + Backspace con respaldo por JS, verificado releyendo el DOM; a diferencia de `limpiar_descripcion`, que sigue siendo solo para el placeholder exacto de cada actividad) antes de guardar (`save_assignment_form`). Después la misma sesión vuelve a Actividades (`enter_activities_module`); si falla, relogin completo con `abrir_sesion_limpia`. Cada acción queda como `{"nombre", "estado": "ok"|"omitido"|"error", "detalle"}`: **un fallo de preparación nunca aborta el cargue**, solo agrega avisos. `set_preparation_details` antepone las filas de preparación con `numero: 0` en `detalle_actividades` (`actualizar_detalle_actividad` casa por `numero`, no por índice) y `report_preparation_actions` registra filas CSV «Prep N» con `categoria_prizma: "Preparación"` y resultado OK/OMITIDO/ERROR; el mensaje final añade «Avisos de preparación: ...». La página de progreso muestra el estado `omitido` (➖, `.actividad-omitida`).
- `automation/content_checks.py`: validación profunda **sin navegador**, compartida por PRIZMA y Moodle. `inspeccionar_pdf_bytes` (cabecera `%PDF-`, hojas por `/Type /Page` con respaldo `/Count`, contenido real descomprimiendo streams con zlib y buscando operadores de texto/imagen) e `inspeccionar_h5p_archivo` (zip válido, `h5p.json`, `content/content.json` legible y al menos una carpeta en `libraries/`; los títulos se leen con `auditor.procesar`). `evaluar_recurso_auditoria` combina extensión + inspección + coincidencia de título (`titulo_coincide`, vía `clave`).
- `automation/moodle/client.py`: replica el flujo de MOODLE: pestaña visible de semana, revisión de duplicados en la sección activa, selector original de actividad, nombres manuales para PDF, notificaciones desactivadas, guardado y verificación del módulo. El worker por usuario conserva el Chromium visible entre trabajos.
  - **Modo de edición primero** (decisión del usuario, 2026-10-20): `ensure_edit_mode` activa el interruptor «Modo de edición» (`.editmode-switch-form input[name="setmode"]`, respaldo por rol checkbox) tras el login y en cada `open_course`; si ya está activo no lo pulsa (lo apagaría). Sin él Moodle no muestra «Añade actividad o recursos». Los recursos se publican **desde la semana 1** en adelante (`domain.publish_order`: número de semana y luego fila de la matriz).
  - **Etiquetas sin uso** (decisión del usuario, 2026-10-21): las etiquetas de bloque («Recurso educativo digital», «Recurso educativo audiovisual», «Reto Evaluativo»; `domain.BLOCK_LABELS`) que una semana no usa según la matriz se pueden borrar. `domain.label_cleanup_plan` calcula por semana qué bloques sobran (los videos a cámara/intro/cierre conservan «audiovisual» por precaución; una semana con filas incompletas o de tipo desconocido no se toca) y se guarda en `job["label_plan"]`. Solo si el usuario marca `clean_labels` y en modo `batch` (nunca en la prueba de 1), y solo en las semanas que se están publicando (`job["label_weeks"]`), `_clean_unused_labels` las borra AL FINAL de la publicación (las etiquetas marcan dónde se inserta cada recurso). `client.delete_unused_label`: solo módulos `modtype_label` (o una tarjeta corta con solo ese texto), nunca si hay dos; ⋮ → «Borrar» → confirma «Borrar» solo si el diálogo nombra la etiqueta o el texto de esa misma tarjeta (si no, Cancelar y el error incluye el texto del diálogo). Corregido el 2026-10-21: el diálogo rellena «Esto eliminará X» un instante después de abrirse y X es el nombre interno de la etiqueta (puede diferir en mayúsculas o texto extra); antes se comparaba de inmediato y exacto, y solo se borró 1 de 7. `_dialog_text_with_target` espera hasta 10 s y `_dialog_names_card` compara normalizado. **`open_week`** va directo a la dirección `?section=N` del enlace con el nombre de la semana (aunque esté oculto en el índice lateral); hacer clic fallaba con «element is not visible». Resultado en `job["label_results"]` y `report["labels"]` (`Borrada` / `No estaba` / `No se pudo borrar`). Como pueden faltar etiquetas, `begin_add_resource` inserta antes de la siguiente etiqueta que exista (`_next_present_block`) o con el botón final de la semana; antes daba `DESTINATION_BLOCK_UNAVAILABLE`.
  - **Vista previa organizada** (2026-10-21): resumen en una línea, «Necesitan atención» con lo que hay que corregir, selección por tipo/semana con la opción de etiquetas, y «Recursos por semana» (`<details>` por semana; dentro, un grupo por bloque como en el curso, los bloques sin uso tachados y «Se suben a mano»). Ya no hay tabla plana.
  - **H5P igual que `MOODLE/src/resource-publishers.js`** (corregido el 2026-10-20; el cargue H5P fallaba): (1) **no** se rellena `#id_name` (en "Contenido interactivo" Moodle toma el título del paquete y el campo no es visible: esperarlo agotaba 30 s); (2) el modo Upload se activa con clic en la pestaña visible "Upload" del editor (el radio oculto `input[value="upload"]` solo como respaldo: marcarlo no cambia la pestaña); (3) el `.h5p` se pone directo en el `input[type=file]` del editor (sin el botón «Upload a file» ni diálogo de archivos), luego «Use»; (4) si Moodle rechaza el paquete se pulsa Cancelar y se reporta `H5P_PACKAGE_VALIDATION_FAILED`.
- `evaluative_tests/automation.py`: `PrizmaTestAutomator` para crear tests.

## Playwright

- API **síncrona**, Chromium (`python -m playwright install chromium`; versión fijada `playwright==1.61.0`).
- Config común en `core/config.py`: `CHROMIUM_ARGS` (`--no-sandbox`, `--disable-dev-shm-usage`) y `VIEWPORT_NAVEGADOR` (1440×900). Usar `list(...)`/`dict(...)` al pasarlos.
- Headless en servidor. `scripts/check_prizma_connection.py` abre navegador visible.
- Cada cargue reinicia navegador + login ante errores estructurales (`_es_error_estructural_prizma`), con un reintento por actividad.
- **Sesión inicial con reintentos** (`_abrir_sesion_inicial`): al empezar el cargue, si PRIZMA no responde (p. ej. `Page.goto: Timeout 60000ms exceeded`) se reintenta con las esperas de `config.PRIZMA_ESPERAS_REINTENTO_SESION` (5 s y 15 s → 3 intentos), atendiendo la cancelación. Nunca reintenta `ERROR_LOGIN_PRIZMA` (las credenciales ya se validaron en `/iniciar`; repetir logins fallidos podría bloquear la cuenta). Si se agotan, el usuario ve un mensaje legible con el detalle técnico al final.
- Selectores y textos dependen del DOM de PRIZMA: es la zona más frágil (búsqueda estable, paginación, recuperación de fila, confirmación del PATCH).
- **Confirmación del guardado** (`procesar_actividad`, pasos 10–11): tras pulsar "Guardar" se espera hasta 45 s la respuesta `PATCH .../academic/activity/...` (`expect_response`), luego 2 s el listener global (`esperar_patch`) y, como último respaldo, se reabre la actividad para ver si el archivo quedó (`verificar_guardado_por_reapertura`, busca el nombre del archivo local). Si todo falla → `ERROR_PATCH_NO_CONFIRMADO: <diagnóstico>`. Ojo: un clic en Guardar que no puede ejecutarse (botón tapado por un overlay o deshabilitado) lanza el MISMO `PlaywrightTimeoutError` que la espera del PATCH; `_resumir_error_clic` los distingue leyendo el call log de Playwright. El diagnóstico (`_diagnostico_guardado_sin_patch`) se toma ANTES de reabrir e incluye el motivo del clic fallido, alertas visibles de PRIZMA (`[role="alert"]`, errores de campos MUI), respuestas HTTP no-GET y peticiones fallidas (listener `requestfailed`, guardadas en `captura["fallidas"]`), siempre sin dominio ni query string, y guarda una captura en `temp/<trabajo>/sin_patch_fila_<n>.png` (`_guardar_captura_diagnostico`).

## PRIZMA

- URL: `config.URL_PRIZMA` (`PRIZMA_BASE_URL + "/inicio-sesion"`). Producción por defecto (`admin.prizma.site`); con `AUTO_PRIZMA_URL_PRIZMA` se apunta a otro ambiente, p. ej. el de **pruebas `https://admin.prizma.solutions`** (mismo formulario de login, verificado el 2026-10-07). Fuera de producción la página principal muestra un aviso (`views._aviso_ambiente_prizma`) y `main.py` imprime `PRIZMA: ... (AMBIENTE DE PRUEBAS)`. **Probar cambios del motor siempre en el ambiente de pruebas, nunca en producción.** Decisión del usuario (2026-10-07): la variable se conserva para probar en local; Railway no la define, así que allí siempre se usa producción.
- Credenciales PRIZMA: las escribe el usuario en cada cargue; se validan antes de encolar (`validar_credenciales_prizma`), viajan en el trabajo como `usuario_prizma_temporal`/`contrasena_prizma_temporal` y se eliminan al arrancar el hilo o cancelar. Nunca se persisten. El módulo de tests solo recuerda el **nombre de usuario** PRIZMA (`<raíz>/data/tokens/prizma_<usuario>.json`).
- Equivalencias de nombres de programa: `EQUIVALENCIAS_PROGRAMAS` en `engine.py` (explícitas; sin coincidencia aproximada a propósito).
- Matriz esperada: A1 programa, A2 curso, cabecera "Semana correspondiente" en columna A (primeras 30 filas); columnas A semana, B unidad, C código de tema (p. ej. `1.1` en su fila de título), D nombre del recurso/tema, E categoría, F tipo de recurso y G referencia opcional (no se consulta). Las filas `Video a cámara` conservan el tema previo y buscan el `.webm` por similitud con el nombre del recurso; al consultar el tema en PRIZMA se quita el punto final si lo hay y se valida programa + tema, sin buscar allí el nombre del recurso.
- **Campo Html vs H5P — política TEMPORAL (decisión del usuario, 2026-10-06): mientras se carguen H5P, si el campo "Html" tiene contenido el motor lo VACÍA antes de guardar** (PRIZMA no permite Html y H5P a la vez: "Solo puedes subir un H5P o completar el campo Html, no ambos"). Interruptor: `config.PRIZMA_VACIAR_HTML_CON_H5P` (`True` hoy). Cuando se deje de usar H5P y se implemente HTML, ponerlo en `False`: el motor nunca borrará el Html, cancelará sin guardar y reportará `ERROR_HTML_Y_H5P`.
  - Solo aplica a actividades H5P (o si aparece el aviso). El editor se busca únicamente entre el título "Html" y el título "Recurso…" (`_XPATH_EDITOR_HTML`), así nunca toca la Descripción. Soporta `textarea`, `contenteditable`, CodeMirror y Monaco; se verifica que quedó vacío o que desapareció el aviso (`_vaciar_editor_html`).
  - Dos momentos: antes del primer clic en Guardar (si se detecta contenido) y, si PRIZMA solo avisa al guardar, se vacía y se reintenta el guardado UNA vez (`_resolver_campo_html`, `_intentar_guardado`).
  - El contenido eliminado queda en la columna Observación del reporte CSV (`_observacion_guardado`, clave `html_vaciado` del resultado).
  - Si no se puede vaciar: cancela sin guardar → `ERROR_LIMPIANDO_HTML` + copia de la estructura del campo en `temp/<trabajo>/campo_html_fila_<n>.html` y captura, para ajustar el selector. El editor real es un `<textarea class="htmlCodeField-textarea">` y el selector funciona contra PRIZMA (ambiente de pruebas, 2026-10-07).
- **Formato de los recursos interactivos: H5P o HTML** (decisiones del usuario, 2026-10-06). Se elige en cada cargue (`formato_recurso` en el formulario, el trabajo y el resultado; `FORMATOS_RECURSO_INTERACTIVO`). Solo afecta a las actividades que hoy son H5P (OVA y OVI H5P/infografía): `engine.aplicar_formato_recurso` las convierte a tipo `HTML`; los PDF no cambian. Ojo con los nombres: `tipo_recurso` es el texto de la columna F de la matriz (y los filtros de la tabla); `formato_recurso` es la elección H5P/HTML.
  - Los `.html`/`.htm` vienen en el ZIP (se indexan como `.html`) y se emparejan por nombre con la actividad, con las mismas reglas que el H5P (ambigüedad = fila no cargable). En formato HTML los recursos también se resuelven únicamente dentro del ZIP.
  - En PRIZMA (`procesar_actividad`, rama `es_html`): (1) lee el `.html` completo (`leer_archivo_html`) **antes de tocar el formulario**: si no es UTF-8 o está vacío (`ERROR_HTML_NO_ES_UTF8`/`ERROR_HTML_VACIO`) cancela sin quitar nada de "Recurso"; (2) `_resolver_recurso_para_html` quita **cualquier archivo** que haya en "Recurso", sea H5P o no (decisión del usuario, 2026-10-07: PRIZMA a veces solo muestra el nombre genérico "Archivo"; política `PRIZMA_VACIAR_RECURSO_CON_HTML`, `True` hoy; con `False` cancela y reporta `ERROR_RECURSO_Y_HTML`); (3) `_cargar_html_en_formulario` escribe el código con `fill` y **verifica que el campo quedó idéntico** antes de guardar; (4) guarda y confirma el PATCH como siempre. Si PRIZMA avisa del conflicto al guardar, se quita el archivo y se reintenta una vez. **En formato HTML nunca se borra el Html pegado** (cubierto por `tests/test_html_mode.py`, con pruebas de mutación).
  - Solo se escribe en `textarea`/`input`; con otro tipo de editor se cancela sin guardar (`ERROR_ESCRIBIENDO_HTML: editor no soportado ...`) y se guarda la estructura del campo. Los fallos al quitar el archivo dejan `ERROR_QUITANDO_RECURSO` y `temp/<trabajo>/campo_recurso_fila_<n>.html` (copia del formulario completo).
  - **Estructura real del formulario** (volcada del ambiente de pruebas el 2026-10-07; ver comentario en `html_field.py`): Html = `<textarea class="htmlCodeField-textarea">`; aviso de conflicto = `<p class="form-error">`; archivo = `<p class="form-label">Recurso (H5P)</p>` (en OVI el título es solo "Recurso") + `div.btnFile > div.fileItem` con el nombre (`div.box-info-file > p`) y dos botones **[descargar, papelera]**; la etiqueta de tipo muestra el MIME (`.octet-stream`), no sirve para saber si es H5P. La papelera abre "¿Estás seguro? / ¿Deseas eliminar este archivo?" con Cancelar / **Eliminar**.
  - Retiro del archivo (`quitar_archivo_de_recurso`), tenga el nombre que tenga: pulsa el ÚLTIMO botón de la tarjeta (papelera), exige que aparezca la confirmación (si no, se detiene: así nunca se confunde con el botón de descarga), pulsa Eliminar y verifica que la tarjeta desapareció. Selectores validados en Chromium contra el HTML real volcado (OVA y OVI).
  - Reporte: tipo `HTML` y observación "HTML pegado (N caracteres[, reemplaza el Html previo]) [- se quito el archivo previo de Recurso ("<nombre>")]" (clave `recurso_quitado` del resultado; sin el nombre si PRIZMA no lo muestra).
  - Validación (2026-10-07, ambiente de pruebas): el 1.er intento falló sin guardar nada (el selector suponía una etiqueta `.H5P`; se rehízo con la estructura real), el 2.º también (PRIZMA mostraba el nombre genérico "Archivo" y la regla de entonces solo quitaba `.h5p`) y el 3.º funcionó; el usuario lo aprobó para producción.
- **Ficha del curso (preparación) — DOM validado en el ambiente de pruebas (2026-11-03)**: la fase `prepare_assignment` abre «Editar Asignatura por pensum» (título con «Asignatura», `wait_for_assignment_form`) y usa etiquetas de campo con texto «Syllabus», «Video de introductorio» y «Video de cierre» (constantes `ASSIGNMENT_SYLLABUS_LABELS`/`ASSIGNMENT_INTRO_VIDEO_LABELS`/`ASSIGNMENT_CLOSING_VIDEO_LABELS`) con su `div.btnFile` hermano; en la práctica el formulario expone adicionalmente «Planeador» y «Banner de asignatura» (no usados). La prueba `scripts/test_syllabus_upload.py` confirmó la subida de syllabus y el guardado. La página de detalle (ojo) NO tiene botón Editar (solo «Vista previa»/«Volver»), así que el único camino útil es el lápiz de la fila. Esos botones de la columna **Acciones** no traen `aria-label`/`title`: ojo = clase `btnIndigo`, **editar = `btnIndigo btnLila`** (púrpura), papelera = `btnIndigo btnWhite`; `click_edit_on_row` los identifica primero por nombre y, si no, por `button.btnLila` **dentro de la fila encontrada** (nunca por posición, para no alcanzar la papelera). Al borrar un archivo aparece «Deseas eliminar este archivo» → «Eliminar» (`_confirmar_eliminacion`); el campo de descripción se deja **vacío** siempre (`empty_description_field`, validado en pruebas el 2026-11-03: borró «Prueba» y guardó; el texto previo se informa en el detalle de la acción).
- Un cargue real **modifica PRIZMA**: no ejecutarlo para "probar" sin autorización explícita.

## Acceso remoto

- El uso local no requiere usuario, contraseña ni administración de cuentas.
- Para proteger despliegues remotos se conserva `services/auth.py`: `usuarios.json` en `DATA_DIR`, PBKDF2-SHA256, cookie HMAC (12 h) y bloqueo por intentos fallidos.
- La CLI de usuarios se utiliza solo para aprovisionar instancias remotas:

```powershell
python scripts/manage_users.py listar | crear | clave | desactivar | activar | borrar
```

## Configuración

Todo en `auto_prizma/core/config.py`. Variables de entorno documentadas en `.env.example` (la app **no** lee `.env`; definirlas en el entorno o en Railway):

| Variable | Se lee | Uso |
|---|---|---|
| `AUTO_PRIZMA_DATA_DIR` | al importar | Datos persistentes (def. `<raíz>/data`) |
| `AUTO_PRIZMA_SECRET` | al importar `services/auth` | Clave HMAC de cookies (si falta: `data/secreto_sesion.txt`) |
| `AUTO_PRIZMA_COOKIE_SECURE` | en cada request | `"1"` fuerza cookie Secure |
| `AUTO_PRIZMA_MAX_SIMULTANEOS` | al importar | `1` o `2` (otro valor → 2) |
| `AUTO_PRIZMA_URL_PRIZMA` | al importar | URL de PRIZMA (vacía = producción `https://admin.prizma.site`; pruebas: `https://admin.prizma.solutions`) |
| `N8N_WEBHOOK_AUT_TESTS`, `N8N_WEBHOOK_DESCARGAR_RECURSOS`, `N8N_WEBHOOK_MATRIZ_CSV`, `N8N_WEBHOOK_PLANTILLAS` | en cada ejecución | Webhooks HTTPS; se mantienen en servidor y no se devuelven al navegador. Los cuatro flujos (Tests JSON, Descarga de recursos, Matriz CSV y Plantillas temáticas) tienen webhooks institucionales predeterminados en `N8N_WEBHOOK_DEFAULTS` (`core/config.py`), reemplazables por entorno. |
| `N8N_WEBHOOK_DESCARGAR_RECURSOS_ESTADO` | en cada consulta | Webhook HTTPS GET que devuelve el avance de una descarga (`?jobId=`). Tiene valor predeterminado en `N8N_STATUS_WEBHOOK_DEFAULTS`, reemplazable por entorno. |
| `N8N_SHARED_SECRET` | en cada ejecución | Secreto opcional enviado como header `x-n8n-secret`; no registrar ni devolver. |

El puente usa `N8N_TIMEOUT_SECONDS` (58 s), exige URLs webhook HTTPS, valida los campos de los cuatro flujos y responde en modo demo si no hay URL ni valor predeterminado. `api/routes/n8n.py` delega el I/O bloqueante a un threadpool; las respuestas del webhook se muestran como texto/datos escapados en el navegador.

Flujos largos (hoy, Descarga de recursos): n8n responde de inmediato con `status: "processing"` y un `jobId`, registra el avance en la tabla de datos de n8n «Estado Descarga Recursos» y la marca como `listo` al terminar de copiar. El navegador muestra «Cargando recursos…» y consulta `GET /automatizaciones-n8n/estado?flowId=&jobId=` cada 8 s; el servidor reenvía la consulta al webhook de estado (`get_flow_status`, `N8N_STATUS_TIMEOUT_SECONDS` = 15 s, `jobId` validado) sin exponer su URL. Solo al recibir `status: "done"` se muestran la carpeta, los archivos copiados y los errores; tras 6 fallos seguidos o 45 min se avisa y se ofrece el enlace a la carpeta. En el formulario, «Dividir recursos por unidad» viene en «No» por defecto. Si n8n responde 502/503/504, el puente devuelve 503 con un mensaje claro de servidor no disponible.

Matriz CSV (`/webhook/matriz-csv-portal`, flujo «Generación Archivo de Importacion - PRIZMA [URL]») y Plantillas temáticas (`/webhook/plantillas-tematicas-portal`, flujo «Generacion de Plantillas de recursos») responden de forma síncrona: el mismo flujo de n8n conserva su formulario y, cuando lo llama la app, contesta JSON (`ok`, `message`, `fileName`, `folderUrl`, `downloadUrl`, `avisos`). Si n8n responde `ok: false` (tabla, unidades o temas mal formados, URL inválida, fallo al guardar), el puente devuelve 422 con ese mensaje; un 500 de n8n se traduce en un mensaje de verificar enlace y permisos, y un tiempo de espera agotado en 504 con aviso de revisar Drive. El navegador muestra «Descargar archivo» si llega `downloadUrl` y lista `avisos` como texto plano. Tests JSON usa el flujo «AUT_TESTS (Webhook)» (`/webhook/generar-tests-json`, campo `googleDocUrl`); cuando n8n responde 4xx con JSON `{ok:false, message, recomendacion}`, el puente devuelve 422 con ese mensaje y la recomendación.

Reglas: no leer `os.environ` fuera de `config.py`; añadir constantes nuevas (URLs, límites, timeouts) a `config.py` y a `.env.example` si son variables; mantener el "momento de lectura" al mover algo. Los timeouts de Playwright del motor siguen dispersos en `engine.py` (pendiente fase 7).

## Ejecución

La instalación y los comandos para arrancar están en `README.md`. La URL local es `http://127.0.0.1:8000`; `--reload` reinicia el proceso y **pierde los trabajos en memoria**. Para probar PRIZMA, configura `AUTO_PRIZMA_URL_PRIZMA=https://admin.prizma.solutions` antes de iniciar. Producción usa el `Dockerfile` y se despliega en Railway.


## Tests

- Framework: **pytest** (incluido en `requirements.txt`). `tests/conftest.py` fija `AUTO_PRIZMA_DATA_DIR` en una carpeta temporal y crea el usuario `adminlocal`. PRIZMA y Playwright están simulados (`unittest.mock.patch`).

```bash
python -m pytest tests/ -q                          # suite completa
python -m pytest tests/test_test_parser.py -q       # un archivo
python -m pytest tests/test_automation.py -k nombre # pruebas por nombre
```

- Los `patch("auto_prizma.evaluative_tests....")` usan rutas de módulo en texto: al mover/renombrar módulos hay que actualizarlas.
- **Pruebas de caracterización** (`test_engine_characterization.py`): fijan el comportamiento de lectura de matriz, tipo de archivo, índice ZIP, resolución de recursos, CSV y reglas de Retos.
- `/analizar` escribe en `uploads/` y `temp/` reales (dependen de `BASE_DIR`, no de `AUTO_PRIZMA_DATA_DIR`): las pruebas que lo llamen deben borrar lo que crean (ver la fixture `limpiar_trabajos` en `tests/test_analysis_flow.py`).
- Interfaz: `test_layout.py` (marco en todas las páginas, recursos públicos, contrato de campos del formulario de Inicio), `test_reports_pages.py`, `test_health.py`, `test_sheet_link_check.py`. Para revisar el aspecto: levantar una segunda instancia con `AUTO_PRIZMA_DATA_DIR` temporal (usuario y reportes de ejemplo) en otro puerto y sacar capturas con Playwright en claro/oscuro a 1600 y 400 px; comprobar que `document.documentElement.scrollWidth` no supere el ancho de la ventana.
- Verificación adicional tras refactors: `python -m compileall -q main.py auto_prizma scripts tests` y arrancar Uvicorn comprobando `/` (landing local directo) y `/prizma`.

## Seguridad

- Nunca escribir contraseñas, tokens ni secretos en el código; configuración sensible solo por variables de entorno.
- Nunca versionar `data/`, `.env`, `client_secret*.json` (ya en `.gitignore`). No leer ni mostrar `data/secreto_sesion.txt`, `data/tokens/*` ni hashes de `usuarios.json` salvo necesidad explícita.
- No registrar credenciales PRIZMA en `print()`, reportes, historial ni en la respuesta de `/estado`. Solo pueden vivir en `usuario_prizma_temporal`/`contrasena_prizma_temporal` del trabajo hasta que arranca el hilo o se cancela. (Hasta el 2026-10-06 `_encolar_trabajo` las copiaba además en `trabajo["credenciales_prizma"]`, que nadie leía y retenía la contraseña en memoria; eliminado y cubierto por `tests/test_upload_jobs.py`.)
- `/moodle` se restringe a loopback y comprueba ownership del trabajo; extrae del ZIP solo `.pdf`/`.h5p` y rechaza rutas absolutas o `..`. El perfil persistente contiene la sesión Moodle del usuario y vive en `DATA_DIR/moodle_profiles/`, fuera de Git.
- Mantener: `hmac.compare_digest`, bloqueo por intentos, comprobación de propietario (`_es_de`) en rutas de trabajos y `os.path.basename` al servir reportes.

## Git

- Rama principal: `main` (PRs). **Railway despliega cada push a `main`**: lo que llega a `main` llega a producción. Rama de trabajo del usuario: `Jeremy`. Equipo: Kevin Torres, Luis, danilo0413, JIMENEZ45 (aprueba PRs). Commits en español, con prefijos `fix:`/`refactor:`/`docs:`/`chore:`.
- Antes de cambiar nada:

```powershell
git status
git branch --show-current
git log -1 --oneline
git fetch origin; git rev-list --count HEAD..origin/main   # ¿rama atrasada?
```

- Prohibido salvo autorización explícita: commit, push, force push, borrar ramas, `reset --hard`, sobrescribir cambios locales, cambiar de rama.
- Mover archivos con `git mv` (conserva historial). Los renombrados masivos afectan a ramas de otros: coordinarlos y mantener el PR pequeño.

## Reglas para modificar código

2. Cambios mínimos; no reescribir módulos completos si basta un cambio pequeño.
3. No eliminar funcionalidades ni código sin demostrar que no se usa (`grep` del nombre, también en strings de `patch(...)` y `sys.modules.get(...)`).
4. No cambiar contratos sin analizar consumidores: URLs, campos de formulario, JSON de `/estado`, columnas del CSV, formato de `usuarios.json`/`historial.json`, `app.state.*`.
5. No duplicar lógica: reutilizar `normalizar_texto`, `drive_resource_policy`, helpers de `services/`.
6. Configuración nueva solo en `core/config.py`.
7. Código nuevo en el módulo de su capa (ver "Cómo agregar una nueva funcionalidad").
8. Mantener compatibilidad con Windows (rutas con `os.path`, `encoding="utf-8"`).
9. Ejecutar pruebas después de cada cambio y revisar `git diff`.
10. Actualizar este `CLAUDE.md` (y `README.md` si cambia algo de uso) en la misma tarea.
11. Informar qué archivos se modificaron. No hacer commit ni push salvo petición explícita.

## Archivos que no deben modificarse

| Tipo | Rutas |
|---|---|
| Datos y secretos | `data/` (usuarios, `secreto_sesion.txt`, `tokens/`, `historial.json`, `reportes/`) |
| Generados en ejecución | `uploads/*`, `temp/*`, `resultados/*` (conservar `.gitkeep`) |
| Entornos y caches | `.venv/`, `.venv-1/`, `__pycache__/`, `.pytest_cache/` |
| Binarios | `static/auto_prizma_logo.png` (solo si se pide) |
| Contrato de despliegue | `Dockerfile` (`main:app`, puerto 8000): solo con motivo explícito |

## Cómo agregar una nueva funcionalidad

1. Identificar el dominio y buscar funcionalidad relacionada (`grep`) en `services/`, `integrations/`, `automation/`, `evaluative_tests/`.
2. Revisar contratos afectados (rutas, formularios, JSON, CSV, `app.state`) y los tests existentes.
3. Ubicar cada parte en su capa:
   - Ruta HTTP → `api/routes/<dominio>.py` (fina: valida, llama al servicio, devuelve respuesta). Si es un módulo nuevo, importarlo en `main.py` respetando el orden.
   - Lógica de negocio → `services/<dominio>.py`.
   - API externa → `integrations/<servicio>/`.
   - Navegador/PRIZMA → `automation/prizma/`.
   - Reglas puras sin I/O → `domain/`.
   - HTML → `web/` (o `views.py` del módulo).
   - Constantes/env → `core/config.py` (+ `.env.example`).
   - Persistencia de archivos de datos → `core/storage.py` (no escribir JSON a mano).
   - Funcionalidad grande y autocontenida → paquete propio como `evaluative_tests/`.
4. Nombres de archivos/funciones nuevas en inglés; comentarios y docstrings en español.
6. `python -m pytest -q`, revisar `git diff`, actualizar `CLAUDE.md`/`README.md`.

## Checklist antes de modificar

El flujo previo al cambio está en `AGENTS.md`; consulta ese archivo en vez de mantener una segunda lista equivalente aquí.

## Checklist después de modificar

- [ ] `python -m pytest -q` en verde.
- [ ] Sin errores de importación (`python -c "import main"`).
- [ ] Endpoints afectados probados (en local, `/` y la página funcional afectada; autenticación remota solo si aplica).
- [ ] Integraciones afectadas revisadas.
- [ ] `git diff` revisado; sin secretos.
- [ ] Sin lógica duplicada.
- [ ] Comentarios nuevos en español; archivos nuevos con nombre en inglés.
- [ ] `CLAUDE.md` (y `README.md` si corresponde) actualizados.

## Problemas conocidos

- **Sin confirmar: cuándo borra PRIZMA el archivo de "Recurso"** (2026-10-07). Si la papelera lo borra en el servidor al pulsar Eliminar (y no al guardar), un fallo posterior (pegado o guardado) deja la actividad sin archivo y sin HTML aunque el reporte diga "No se guardo nada". Se arregla volviendo a cargarla en formato HTML (ya no habrá archivo que quitar). Para reducir el riesgo, el `.html` se lee y valida antes de quitar nada.
- **`ERROR_PATCH_NO_CONFIRMADO` en actividades con campo Html** (causa encontrada el 2026-10-06): PRIZMA no envía el guardado si el campo "Html" tiene contenido y se sube un H5P. Ahora se vacía el Html (política temporal, ver PRIZMA). Si vuelve a aparecer `ERROR_PATCH_NO_CONFIRMADO`, el mensaje trae el diagnóstico y la captura `temp/<trabajo>/sin_patch_fila_<n>.png`.
- **`print()` con caracteres no ASCII en el motor** (`→`, emojis): si la salida estándar no es UTF-8 (Windows con la salida redirigida a archivo/pipe, p. ej. `uvicorn ... > log.txt`), `resolver_recurso` y otras funciones lanzan `UnicodeEncodeError` en pleno cargue. En Railway (Linux) no ocurre. Mitigación local: `$env:PYTHONIOENCODING = "utf-8"`. Corrección pendiente (fase 7: logging en lugar de `print`).
- **Ruta de datos inconsistente** en `evaluative_tests/state.py`: el usuario PRIZMA recordado se guarda en `<raíz>/data/tokens/` ignorando `AUTO_PRIZMA_DATA_DIR` (en Railway puede no ser persistente). Las pruebas lo confirman: escriben `data/tokens/prizma_adminlocal.json` en el `data/` real (solo `usuario`/`recordar`, sin contraseña). El nombre de archivo usa el usuario sin sanear. Corregirlo cambia dónde se guarda el dato (los usuarios tendrían que reescribir su usuario PRIZMA una vez).
- **Estado en memoria**: trabajos, cola, jobs de tests se pierden al reiniciar.
- **Sin limpieza** de `uploads/<id>` y `temp/<id>` tras el cargue (solo si falla la prevalidación).
- `resultados/` no se usa (los reportes van a `DATA_DIR/reportes/`).
- `/cargue-actual` muestra cargues activos de **todos** los usuarios (las acciones sí exigen ser el dueño), aunque el README dice "del usuario".
- Duplicaciones pendientes: lógica de login en PRIZMA repetida (motor, validación y tests evaluativos). Nombres de archivo: el nombre base y la clave exacta ya están unificados en `domain/file_names.py`; quedan dos normalizaciones con semántica DISTINTA a propósito — `engine.clave_nombre_archivo_exacto` (ignora mayúsculas) y la normalización canónica (canónica: guiones, espacios y mayúsculas). Unificarlas cambiaría qué archivos se emparejan: requiere decisión del usuario.
- **Interfaz**: en las capturas de página completa el fondo blanco del menú lateral termina a la altura de la ventana (el menú es `sticky`); en el navegador no se nota. El módulo de tests conserva su propio CSS (en `evaluative_tests/views.py`, ya con variables de color) con reglas globales (`button`, `input`, `label`, `p`): los controles del marco usan selectores más específicos para no heredarlas.
- `.venv` local creado antes de que `main` añadiera `python-docx`: ejecutar `python -m pip install -r requirements.txt` o la app no arranca.

## Decisiones arquitectónicas

- **Paquete `auto_prizma/` por capas** (core / api / services / integrations / automation / domain / web) + módulos de funcionalidad autocontenidos (`evaluative_tests/`).
- **`main:app` como contrato** de arranque (Dockerfile/Railway); `main.py` solo ensambla.
- **Rutas delgadas y lógica en servicios**: las rutas validan entradas, llaman a `services/` y renderizan; el historial está separado del ciclo de vida de los trabajos (`services/history.py`).
- **Escritura atómica de archivos de datos** en un único módulo (`core/storage.py`).
- **Configuración centralizada** en `core/config.py`; los módulos reexportan los mismos nombres para no romper consumidores; las variables que se leían en cada llamada siguen leyéndose en cada llamada.
- Los recursos se buscan exclusivamente en el ZIP local; no se consultan enlaces de la matriz.
- **Sesión con cookie HMAC sin estado** y usuarios en JSON local gestionados por CLI.
- **Un hilo + un Chromium por cargue**, máximo 2 simultáneos; cancelación cooperativa entre actividades.
- **Moodle es local y separado**: utiliza su matching por matriz/archivo (normaliza prefijos como `H5P -`, `PDF -` e `Infografía -`), jobs y reportes propios, y Chromium visible con login manual; no consume `/analizar` ni el motor administrativo PRIZMA. Los perfiles y reportes viven bajo `DATA_DIR`; los archivos temporales bajo `uploads/moodle/`.
- **HTML renderizado en servidor con un marco común** (`web/layout.py`) y recursos estáticos versionados (`static/app.css`, `static/app.js`). Tema claro/oscuro por variables CSS, recordado en el navegador (`localStorage` `autoPrizmaTema`). Diseño según las imágenes del usuario (2026-10-07). **Tema oscuro negro + violeta** (imagen del usuario, 2026-10-26): fondo `#000000`, paneles `#0b0b0f`/`#131318`, bordes grises tenues `#26262c`, acento violeta `#8b5cf6`/`#7c3aed` con relleno `#1b1233`, verdes `#22c55e`; solo cambian las variables de `html[data-theme="dark"]` en `app.css` (más el degradado de `.boton.grande` y el fondo de `.prizma-loader`), así aplica a todas las páginas.
- **Hora de Colombia** para historial y nombres de reporte.
- **Formato HTML reutilizando el flujo del H5P**: solo cambia el paso de carga (pegar en el campo Html en lugar de subir el archivo); emparejamiento, reporte, historial, cancelación y reintentos son los mismos. El código nuevo de bajo nivel vive en `automation/prizma/html_field.py`, sin dependencias del motor.
