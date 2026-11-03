# Auto Prizma Pro

App web (Python + FastAPI) que automatiza el cargue de actividades a **PRIZMA**. Corre en local y usa un navegador (Chromium) para operar la plataforma.

---

## Requisitos

- **Python 3.12 o superior**
- **Git**
- **Chromium** se instala solo (paso 2)

---

## Instalación

### macOS / Linux

```bash
git clone https://github.com/JIMENEZ45/cargue-autom-tico-prizma.site-.git
cd cargue-autom-tico-prizma.site-
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
playwright install chromium          # <-- OBLIGATORIO, si no: "Chromium no disponible"
```

### Windows (PowerShell)

```powershell
git clone https://github.com/JIMENEZ45/cargue-autom-tico-prizma.site-.git
cd cargue-autom-tico-prizma.site-
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install chromium          # <-- OBLIGATORIO
```

> Si PowerShell bloquea la activación: `Set-ExecutionPolicy -Scope Process RemoteSigned`

---

## Variables de entorno (opcional)

La app **funciona sin ninguna**. Todas tienen valor por defecto. Solo se definen si las necesitas.

| Variable | Para qué | Por defecto |
|---|---|---|
| `AUTO_PRIZMA_URL_PRIZMA` | URL de PRIZMA. Vacío = producción | `https://admin.prizma.site` |
| `AUTO_PRIZMA_DATA_DIR` | Carpeta de datos | `./data` |
| `AUTO_PRIZMA_MAX_SIMULTANEOS` | Cargues a la vez (1 o 2) | `2` |
| `N8N_WEBHOOK_AUT_TESTS` | Reemplaza el webhook institucional de tests JSON | Webhook institucional configurado en servidor |
| `N8N_WEBHOOK_DESCARGAR_RECURSOS` | Reemplaza el webhook institucional de descarga de recursos | Webhook institucional configurado en servidor |
| `N8N_WEBHOOK_DESCARGAR_RECURSOS_ESTADO` | Reemplaza el webhook (GET) que informa el avance de la descarga de recursos | Webhook institucional configurado en servidor |
| `N8N_WEBHOOK_MATRIZ_CSV` | Reemplaza el webhook institucional de la matriz CSV | Webhook institucional configurado en servidor |
| `N8N_WEBHOOK_PLANTILLAS` | Reemplaza el webhook institucional de plantillas temáticas | Webhook institucional configurado en servidor |
| `N8N_SHARED_SECRET` | Secreto opcional enviado como `x-n8n-secret` | Vacío |

**La app NO lee `.env` automáticamente.** `arrancar.sh` sí carga `.env` si existe; si arrancas Uvicorn manualmente, define las variables en la terminal. Las matrices y los documentos de evaluación se cargan como archivos locales.

---

## Correr la app

### macOS / Linux

```bash
./arrancar.sh                         # carga .env si existe
# o manual:
uvicorn main:app --reload --port 8000
```

### Windows (PowerShell)

```powershell
uvicorn main:app --reload --port 8000
```

Abre **http://127.0.0.1:8000**

---

## Acceso

En local, abre **http://127.0.0.1:8000**: la app entra directamente, sin usuario ni contraseña. Este acceso directo solo se aplica a conexiones desde el mismo equipo; los despliegues remotos conservan su protección de acceso.

Dentro de la app:

- **Inicio** — landing con tarjetas para **Matrices**, **Cargue PRIZMA**, **Cargue Moodle** y **Automatizaciones**, en ese orden (el sidebar también incluye Control Tower antes de Matrices). La cabecera ofrece accesos directos a **Entrar a PRIZMA** (`https://admin.prizma.site/`) y **Control Tower**. La app usa transiciones y animaciones suaves en navegación y controles, y respeta la preferencia de reducir movimiento del sistema.
- **Control Tower** — acceso directo a la herramienta de gestión de tareas; se abre en una pestaña nueva para conservar el inicio de sesión de Google. También está disponible desde el sidebar.
- **Cargue PRIZMA** — abre primero en **Auditor** y reúne en pestañas el cargue, Test, Cursos, En curso, Historial y Reportes. El formulario de cargue incluye la tarjeta opcional **Syllabus y preparación** (PDF de syllabus + línea académica y nivel de pensum): antes de subir recursos, la app actualiza la ficha del curso en PRIZMA (syllabus, videos de intro/cierre del ZIP y campo de descripción vaciado); si algo falla, el cargue continúa con un aviso. Si combinas Test Evaluativo con recursos, se valida el documento antes de iniciar; los errores bloquean el cargue y se muestran para corregirlos. Cursos explica por qué falta cada actividad y permite identificar pendientes para reintento.
- **Cargue Moodle** — mantiene su flujo independiente para publicar PDF/H5P; incluye pestañas de Auditor, **Etiquetas** y reportes. En Etiquetas hay tarjetas independientes para banners, infografías y videos; al cargar una imagen se genera el HTML correspondiente y la imagen se incrusta como Data URL en `src`, sin subirla a Moodle.
- **Automatizaciones** — formularios para ejecutar los cuatro flujos del equipo y un acceso directo a PRIZMA para **Crear semanas de curso** desde CSV. Las URLs de webhook solo se usan desde el servidor y nunca se envían al navegador; sin configurar, los flujos quedan en modo demo.

Los webhooks deben aceptar `POST` con JSON y responder con JSON (por ejemplo, `message`, `folderUrl`, `folderName`, `fileName`, `totalTests` o `expiresInMinutes`). Activa el webhook de producción en n8n. Configura las URLs HTTPS en el entorno del servidor; no guardes valores reales en `.env.example` ni en Git. Si usas autenticación en n8n, configura el mismo valor en `N8N_SHARED_SECRET`.

Para flujos que tardan más de un minuto (Descarga de recursos), el webhook responde de inmediato con `status: "processing"` y un `jobId`; la app muestra **Cargando recursos…** y consulta el webhook de estado hasta recibir `status: "done"`.

---

## Cargue Moodle (local)

En **http://127.0.0.1:8000/moodle** se publican recursos PDF/H5P directamente en un curso de Prizma (Moodle). Solo funciona con la app corriendo **en tu propio equipo**, porque abre un Chromium visible para que inicies sesión a mano (no está disponible en Railway ni en un servidor).

1. Sube la matriz (CSV/XLSX), el ZIP con los PDF/H5P y el enlace del curso (`https://prizma.americana.edu.co/course/view.php?id=...`).
2. Revisa la vista previa por semana: qué está listo, qué falta corregir y qué se sube a mano. Un H5P solo se aprueba automáticamente si su título principal está en la raíz de `content/content.json` y coincide con la matriz (ignorando mayúsculas, tildes y signos); los títulos de capítulos no cuentan como portada. Si no se puede verificar, la fila queda para revisión. En filas pendientes puedes adjuntar manualmente un PDF/H5P (máximo 200 MB).
3. Elige tipos de recurso y semanas, prueba con 1 recurso y luego publica los seleccionados.
4. Inicia sesión en la ventana de Chromium. La app activa el *Modo de edición*, publica desde la semana 1 y no duplica lo que ya está en el curso. Puedes pausar o cancelar.
5. Opcional: al terminar, puede borrar las etiquetas de bloque que la matriz no usa en cada semana publicada.

Pasos detallados y explicación de los estados en **`GUIA_DETALLADA.md`** → *Uso: cargue Moodle*.

La auditoría **Auditar curso** permite adjuntar opcionalmente la matriz CSV/XLSX para comparar semanas y nombres esperados con lo publicado. La matriz se procesa localmente y no se conserva; no se pide ni descarga el syllabus. Consulta **`GUIA_DETALLADA.md`** → *Auditoría profunda de un curso Moodle*.

---

## Problemas comunes

| Problema | Solución |
|---|---|
| `ModuleNotFoundError` | No activaste el venv. `source .venv/bin/activate` (mac) o `.\.venv\Scripts\Activate.ps1` (win) |
| "Chromium no disponible" | `playwright install chromium` |
| Puerto 8000 ocupado | `kill $(lsof -ti :8000)` (mac) o cierra la otra terminal (win) |
| Login bloqueado | Espera 120 s (bloqueo tras 5 intentos fallidos) |
| Un cargue salió con errores | Entra a **Cursos**: te dice cuáles faltan y la causa en español. En el CSV, la columna `Motivo` la explica y `Observación` conserva el código `ERROR_*` |

---

## Despliegue (Railway)

Sube a `main` para desplegar. Ver `Dockerfile` (instala deps + Chromium y arranca uvicorn en el puerto 8000).

Alternativa gratuita: Oracle Cloud Always Free, ver [`docs/DEPLOY_ORACLE.md`](docs/DEPLOY_ORACLE.md).

Documentación completa: ver **`GUIA_DETALLADA.md`**.
