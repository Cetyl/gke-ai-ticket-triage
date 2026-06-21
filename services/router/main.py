import os
import time
import uuid

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import Response
from pydantic import BaseModel
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

from storage import get_backend

SERVICE = "router"
NOTIFIER_URL = os.getenv("NOTIFIER_URL", "http://notifier:8000")

app = FastAPI(title=SERVICE)
backend = get_backend()

REQUESTS = Counter("app_requests_total", "Total HTTP requests",
                   ["service", "endpoint", "method", "status"])
LATENCY = Histogram("app_request_latency_seconds", "Request latency",
                    ["service", "endpoint"])
ROUTED = Counter("tickets_routed_total", "Tickets routed by priority",
                 ["service", "priority"])
STORE_ERRORS = Counter("storage_errors_total", "Storage write errors", ["service"])


class Enriched(BaseModel):
    subject: str
    body: str
    category: str
    urgency: str
    model: str | None = None
    ai_ok: bool | None = None


def priority_for(urgency: str) -> str:
    return {"high": "P1", "medium": "P2"}.get(urgency, "P3")


@app.middleware("http")
async def metrics_mw(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    LATENCY.labels(SERVICE, request.url.path).observe(time.time() - start)
    REQUESTS.labels(SERVICE, request.url.path, request.method, str(response.status_code)).inc()
    return response


@app.get("/healthz")
def healthz():
    return {"status": "ok", "service": SERVICE}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/route")
async def route(t: Enriched):
    ticket_id = str(uuid.uuid4())
    priority = priority_for(t.urgency)
    record = {**t.model_dump(), "ticket_id": ticket_id, "priority": priority}

    try:
        store_info = backend.save(ticket_id, record)
    except Exception as exc:  # keep the workflow alive during the POC
        STORE_ERRORS.labels(SERVICE).inc()
        store_info = {"backend": "error", "detail": str(exc)}

    ROUTED.labels(SERVICE, priority).inc()

    async with httpx.AsyncClient(timeout=30) as client:
        try:
            await client.post(f"{NOTIFIER_URL}/notify", json={
                "ticket_id": ticket_id,
                "priority": priority,
                "category": t.category,
                "urgency": t.urgency,
                "subject": t.subject,
            })
        except Exception:
            pass  # notification failure should not fail routing

    return {"ticket_id": ticket_id, "priority": priority, "storage": store_info}
