# Desplegar Auto Prizma Pro gratis en Oracle Cloud (Always Free)

Guía para tener la aplicación en internet, con HTTPS, en un servidor gratuito de Oracle Cloud.
Funciona igual que en Railway (mismo `Dockerfile`), pero en una máquina virtual propia.

**Resultado:** la app queda en `https://<tu-subdominio>.duckdns.org`, encendida todo el día, con los usuarios, el historial y los reportes guardados en el disco del servidor.

**Tiempo aproximado:** 1 a 2 horas la primera vez.

**Archivos usados** (carpeta [`deploy/oracle/`](../deploy/oracle/)):

| Archivo | Para qué sirve |
|---|---|
| `setup-server.sh` | Instala Docker y abre los puertos 80/443 del servidor (una sola vez) |
| `docker-compose.yml` | Levanta la app y Caddy (el proxy que pone el HTTPS) |
| `Caddyfile` | Configuración de Caddy: tu dominio → la app |
| `.env.example` | Plantilla de la configuración (se copia a `.env`, que nunca va a git) |

---

## Antes de empezar: lo que debes saber

- **Oracle pide una tarjeta** al crear la cuenta, solo para verificar identidad. Los recursos "Always Free" no se cobran. No crees nada que no diga *Always Free-eligible*.
- **La región principal (home region) no se puede cambiar después.** Elige una cercana; **Bogotá (`sa-bogota-1`)** es la más cercana para Colombia.
- **"Out of capacity":** a veces Oracle no tiene máquinas ARM gratis disponibles en la región. Si pasa, reintenta más tarde o con menos recursos (1 OCPU / 6 GB).
- **Recuperación de máquinas inactivas:** Oracle puede detener una máquina Always Free que pase 7 días casi sin uso (CPU, red y memoria muy bajas). Si te ocurre, se vuelve a encender desde la consola. Pasar la cuenta a *Pay As You Go* lo evita y lo que esté dentro del límite gratis sigue sin costo, pero entonces sí podrían cobrarte si creas recursos fuera de ese límite.
- **Las condiciones del plan gratis cambian:** revisa la página oficial de Oracle Cloud Free Tier antes de crear la cuenta.

---

## Paso 1. Crear la cuenta de Oracle Cloud

1. Entra a <https://www.oracle.com/cloud/free/> → **Start for free**.
2. Completa los datos, elige la **home region** (Bogotá recomendado) y verifica la tarjeta.
3. Espera el correo de bienvenida y entra a la consola: <https://cloud.oracle.com>.

## Paso 2. Crear la máquina virtual

1. En la consola: menú ☰ → **Compute** → **Instances** → **Create instance**.
2. **Name:** `auto-prizma`.
3. **Image and shape** → **Edit**:
   - **Image:** *Change image* → **Canonical Ubuntu 24.04** (o 22.04).
   - **Shape:** *Change shape* → **Ampere** → `VM.Standard.A1.Flex` → **2 OCPU** y **12 GB** de memoria (es suficiente; el máximo gratis es 4 OCPU / 24 GB en total).
4. **Networking:** deja que cree una VCN nueva con subred pública y marca **Assign a public IPv4 address**.
5. **Add SSH keys:** elige **Generate a key pair for me** y **descarga la clave privada** (`.key`). Guárdala bien: sin ella no podrás entrar al servidor.
6. **Boot volume:** puedes dejarlo en 50 GB (el límite gratis total es 200 GB).
7. **Create**. Cuando esté en verde (*Running*), copia la **Public IP address**.

## Paso 3. Abrir los puertos 80 y 443 en Oracle

1. En la página de la instancia → **Subnet** (enlace) → **Security Lists** → *Default Security List*.
2. **Add Ingress Rules** (dos reglas, o una con rango):
   - Source CIDR `0.0.0.0/0`, IP Protocol **TCP**, Destination Port Range **80**.
   - Source CIDR `0.0.0.0/0`, IP Protocol **TCP**, Destination Port Range **443**.

(El firewall interno de Ubuntu se abre en el paso 6 con el script.)

## Paso 4. Conseguir un dominio gratis (DuckDNS)

HTTPS automático de Caddy requiere un nombre de dominio, no una IP.

1. Entra a <https://www.duckdns.org> e inicia sesión (con Google o GitHub).
2. Crea un subdominio, por ejemplo `cargue-prizma` → quedará `cargue-prizma.duckdns.org`.
3. En **current ip** pega la **IP pública** del servidor y pulsa **update ip**.

Si algún día cambia la IP del servidor, solo hay que actualizarla aquí.

## Paso 5. Entrar al servidor por SSH

Desde PowerShell en tu PC (Windows ya trae `ssh`):

```powershell
# Solo la primera vez: restringir permisos de la clave (si no, ssh la rechaza)
icacls "C:\ruta\a\ssh-key.key" /inheritance:r /grant:r "$($env:USERNAME):(R)"

ssh -i "C:\ruta\a\ssh-key.key" ubuntu@<IP_PUBLICA>
```

Todo lo que sigue se escribe **dentro del servidor** (en la sesión SSH).

## Paso 6. Descargar el código y preparar el servidor

```bash
git clone https://github.com/JIMENEZ45/cargue-autom-tico-prizma.site-.git auto-prizma
cd auto-prizma/deploy/oracle
bash setup-server.sh
exit
```

- Si el repositorio es **privado**, `git clone` pedirá usuario y contraseña: el usuario es el de GitHub y la "contraseña" es un **token** (GitHub → *Settings* → *Developer settings* → *Fine-grained tokens* → acceso solo a ese repositorio, permiso *Contents: Read-only*).
- El `exit` es necesario: hay que volver a entrar por SSH para usar Docker sin `sudo`.

## Paso 7. Configurar la app

Vuelve a entrar por SSH y:

```bash
cd ~/auto-prizma/deploy/oracle
cp .env.example .env
openssl rand -hex 32        # copia el resultado: es tu AUTO_PRIZMA_SECRET
nano .env
```

Completa en `.env`:

| Variable | Valor |
|---|---|
| `APP_DOMAIN` | tu subdominio, p. ej. `cargue-prizma.duckdns.org` (sin `https://`) |
| `AUTO_PRIZMA_SECRET` | el resultado de `openssl rand -hex 32` |
| `AUTO_PRIZMA_URL_PRIZMA` | vacío = PRIZMA de producción |

Guardar en `nano`: `Ctrl+O`, `Enter`, `Ctrl+X`.

## Paso 8. Arrancar

```bash
cd ~/auto-prizma/deploy/oracle
docker compose up -d --build
```

La primera vez tarda varios minutos (descarga Python e instala Chromium). Para ver qué pasa:

```bash
docker compose logs -f app      # la app (Ctrl+C para salir del log; la app sigue corriendo)
docker compose logs -f caddy    # el HTTPS: debe decir que obtuvo el certificado
```

## Paso 9. Crear los usuarios de la app

```bash
docker compose exec app python scripts/manage_users.py crear
```

Abre `https://<tu-subdominio>.duckdns.org` e inicia sesión. Las matrices XLSX/CSV, los ZIP de recursos y los DOCX se cargan como archivos locales; no hay conexión con cuentas externas.

---

## Uso diario

| Tarea | Comando (en `~/auto-prizma/deploy/oracle`) |
|---|---|
| Ver estado | `docker compose ps` |
| Ver logs | `docker compose logs -f app` |
| Reiniciar | `docker compose restart app` |
| Actualizar a la última versión de `main` | `git pull` y luego `docker compose up -d --build` |
| Gestionar usuarios | `docker compose exec app python scripts/manage_users.py listar` (o `clave`, `desactivar`...) |
| Apagar todo | `docker compose down` (los datos se conservan) |

- **Actualizar o reiniciar pierde los cargues en curso** (viven en memoria): hazlo cuando nadie esté cargando.
- La app arranca sola si el servidor se reinicia (`restart: unless-stopped`).
- **Datos:** quedan en `~/auto-prizma/deploy/oracle/data/` (usuarios, historial, reportes, tokens). Para respaldarlos, desde tu PC:
  ```powershell
  scp -i "C:\ruta\a\ssh-key.key" -r ubuntu@<IP_PUBLICA>:auto-prizma/deploy/oracle/data .\respaldo-data
  ```
  Ese respaldo contiene secretos: no lo subas a git ni lo compartas.

## Solución de problemas

| Síntoma | Causa probable |
|---|---|
| La página no carga (timeout) | Faltan las reglas del paso 3 o no se ejecutó `setup-server.sh` |
| Error de certificado / Caddy no obtiene HTTPS | DuckDNS no apunta a la IP del servidor, o los puertos 80/443 están cerrados |
| `Falta APP_DOMAIN en .env` | No se creó `.env` o falta esa línea |
| La app se reinicia sola durante un cargue | Poca memoria: sube la máquina a más GB o usa `AUTO_PRIZMA_MAX_SIMULTANEOS=1` |
| El disco se llena con el tiempo | `uploads/` y `temp/` no se limpian solos; `docker compose up -d --build --force-recreate app` los vacía (están dentro del contenedor) |
