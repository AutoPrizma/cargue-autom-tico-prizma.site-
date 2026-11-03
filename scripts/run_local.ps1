# Arranca AUTO PRIZMA PRO en este equipo.
#
# Uso:  powershell -ExecutionPolicy Bypass -File scripts\run_local.ps1 [-Puerto <puerto>]
#
# Desde 127.0.0.1 la app entra directamente, sin usuario ni contraseña.
# Las credenciales de PRIZMA de cada cargue se siguen pidiendo. Nunca usar en un servidor.
param(
    [int]$Puerto = 8000
)

$raiz = Split-Path -Parent $PSScriptRoot
Set-Location $raiz

$python = Join-Path $raiz ".venv\Scripts\python.exe"
if (-not (Test-Path $python)) { $python = "python" }

# Evita UnicodeEncodeError del motor cuando la salida no es UTF-8 (ver CLAUDE.md).
$env:PYTHONIOENCODING = "utf-8"

& $python -m uvicorn main:app --reload --host 127.0.0.1 --port $Puerto
