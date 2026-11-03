"""API del catálogo y la ejecución segura de webhooks n8n."""

from fastapi import Request
from fastapi.responses import JSONResponse
from starlette.concurrency import run_in_threadpool

from auto_prizma.core.application import app
from auto_prizma.services.n8n import execute_flow, get_flow_status


@app.post("/automatizaciones-n8n/ejecutar")
async def execute_n8n_automation(request: Request):
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"ok": False, "message": "La solicitud no contiene JSON válido."}, status_code=400)
    if not isinstance(body, dict):
        return JSONResponse({"ok": False, "message": "La solicitud no tiene el formato esperado."}, status_code=400)
    result, status = await run_in_threadpool(
        execute_flow, body.get("flowId"), body.get("payload", {})
    )
    return JSONResponse(result, status_code=status)


@app.get("/automatizaciones-n8n/estado")
async def n8n_automation_status(flowId: str = "", jobId: str = ""):
    result, status = await run_in_threadpool(get_flow_status, flowId, jobId)
    return JSONResponse(result, status_code=status)
