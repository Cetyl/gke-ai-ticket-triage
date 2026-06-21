import logging
import time

from fastapi import FastAPI, Request
from fastapi.responses import Response
from pydantic import BaseModel
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Histogram, generate_latest

SERVICE = "notifier"

app = FastAPI(title=SERVICE)
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger(SERVICE)

REQUESTS = Counter("app_requests_total", "Total HTTP requests",
                   ["service", "endpoint", "method", "status"])
LATENCY = Histogram("app_request_latency_seconds", "Request latency",
                    ["service", "endpoint"])
NOTIFICATIONS = Counter("notifications_sent_total", "Notifications sent",
                        ["service", "priority"])


class Notification(BaseModel):
    ticket_id: str
    priority: str
    category: str
    urgency: str
    subject: str


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


@app.post("/notify")
def notify(n: Notification):
    NOTIFICATIONS.labels(SERVICE, n.priority).inc()
    # For the POC the "alert" is a structured log line. Swap for Slack/email later.
    log.info("ALERT [%s] %s/%s ticket=%s subject=%s",
             n.priority, n.category, n.urgency, n.ticket_id, n.subject)
    return {"notified": True, "ticket_id": n.ticket_id, "priority": n.priority}
