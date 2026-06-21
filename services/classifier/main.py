import json
import os
import re
import time

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import Response
from pydantic import BaseModel
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

SERVICE = "classifier"
# In GKE this points at your Cloudflare Tunnel URL (set via Secret).
# Default is for local docker testing against Ollama on the host.
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:7b")

CATEGORIES = ["billing", "technical", "account", "feature_request", "other"]
URGENCIES = ["low", "medium", "high"]

app = FastAPI(title=SERVICE)

REQUESTS = Counter("app_requests_total", "Total HTTP requests",
                   ["service", "endpoint", "method", "status"])
LATENCY = Histogram("app_request_latency_seconds", "Request latency",
                    ["service", "endpoint"])
AI_LATENCY = Histogram("ai_call_latency_seconds", "Local model call latency",
                       ["service", "model"])
CLASSIFICATIONS = Counter("classifications_total", "Classifications produced",
                          ["service", "category", "urgency"])
AI_ERRORS = Counter("ai_call_errors_total", "Local model call errors", ["service"])

PROMPT = (
    "You are a support ticket classifier. Classify the ticket below.\n"
    "Return ONLY compact JSON of the form "
    '{{"category": "<one of {cats}>", "urgency": "<one of {urg}>"}}.\n'
    "Ticket subject: {subject}\n"
    "Ticket body: {body}\n"
    "JSON:"
)


class Ticket(BaseModel):
    subject: str
    body: str


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


def parse_result(text: str):
    """Pull the first JSON object out of the model output and validate it."""
    category, urgency = "other", "low"
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if match:
        try:
            data = json.loads(match.group(0))
            category = str(data.get("category", "other")).lower().strip()
            urgency = str(data.get("urgency", "low")).lower().strip()
        except json.JSONDecodeError:
            pass
    if category not in CATEGORIES:
        category = "other"
    if urgency not in URGENCIES:
        urgency = "low"
    return category, urgency


@app.post("/classify")
async def classify(ticket: Ticket):
    prompt = PROMPT.format(cats=CATEGORIES, urg=URGENCIES,
                           subject=ticket.subject, body=ticket.body)
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
        "options": {"temperature": 0},
    }
    start = time.time()
    try:
        async with httpx.AsyncClient(timeout=120) as client:
            resp = await client.post(f"{OLLAMA_BASE_URL}/api/generate", json=payload)
            resp.raise_for_status()
            output = resp.json().get("response", "")
    except Exception:
        AI_ERRORS.labels(SERVICE).inc()
        AI_LATENCY.labels(SERVICE, OLLAMA_MODEL).observe(time.time() - start)
        # Fail soft so the workflow still completes during the POC.
        return {"category": "other", "urgency": "low", "model": OLLAMA_MODEL, "ai_ok": False}

    AI_LATENCY.labels(SERVICE, OLLAMA_MODEL).observe(time.time() - start)
    category, urgency = parse_result(output)
    CLASSIFICATIONS.labels(SERVICE, category, urgency).inc()
    return {"category": category, "urgency": urgency, "model": OLLAMA_MODEL, "ai_ok": True}
