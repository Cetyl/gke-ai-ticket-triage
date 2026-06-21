import os
import time

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

SERVICE = "api-gateway"
CLASSIFIER_URL = os.getenv("CLASSIFIER_URL", "http://classifier:8000")
ROUTER_URL = os.getenv("ROUTER_URL", "http://router:8000")

app = FastAPI(title=SERVICE)

REQUESTS = Counter("app_requests_total", "Total HTTP requests",
                   ["service", "endpoint", "method", "status"])
LATENCY = Histogram("app_request_latency_seconds", "Request latency",
                    ["service", "endpoint"])
TICKETS = Counter("tickets_submitted_total", "Tickets submitted", ["service"])


class Ticket(BaseModel):
    subject: str
    body: str


@app.middleware("http")
async def metrics_mw(request: Request, call_next):
    start = time.time()
    response = await call_next(request)
    endpoint = request.url.path
    LATENCY.labels(SERVICE, endpoint).observe(time.time() - start)
    REQUESTS.labels(SERVICE, endpoint, request.method, str(response.status_code)).inc()
    return response


@app.get("/healthz")
def healthz():
    return {"status": "ok", "service": SERVICE}


@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.post("/tickets")
async def submit_ticket(ticket: Ticket):
    """Entry point: orchestrate classify -> route across the microservices."""
    TICKETS.labels(SERVICE).inc()
    async with httpx.AsyncClient(timeout=130) as client:
        # 1. Classifier calls the local Ollama model through the tunnel.
        c = await client.post(f"{CLASSIFIER_URL}/classify", json=ticket.model_dump())
        c.raise_for_status()
        classification = c.json()

        # 2. Router stores the ticket and triggers the notifier.
        enriched = {**ticket.model_dump(), **classification}
        r = await client.post(f"{ROUTER_URL}/route", json=enriched)
        r.raise_for_status()
        routing = r.json()

    return JSONResponse({
        "ticket": ticket.model_dump(),
        "classification": classification,
        "routing": routing,
    })
