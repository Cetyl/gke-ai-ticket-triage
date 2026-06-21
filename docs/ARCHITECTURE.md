# Architecture

## Goal

Prove that a microservices workload on GKE can be fully observable while the AI
runs for free on a local machine. Only cloud infrastructure is billed, and the
design is portable so the same workload can later move to AWS.

## Flow

```
Client / Streamlit UI
        |
        v
  API Gateway  --calls-->  Classifier  --(Cloudflare Tunnel)-->  Ollama / Qwen2.5  (your Mac)
        |                      |
        |                      v
        +-------------->     Router  --writes-->  Cloud Storage (or Firestore)
                               |
                               v
                            Notifier  (alert)

Prometheus scrapes /metrics on every service  -->  Grafana dashboard  -->  You
```

The black path is the request flow. The one hop that leaves the cloud is the
Classifier to your Mac, which is what keeps AI cost at zero. Prometheus and
Grafana observe everything inside the cluster.

## Why each piece exists

- **Four services, not one app.** Each has a single responsibility and its own
  Deployment, so they scale and deploy independently. This is what makes
  Kubernetes a real fit rather than decoration.
- **Local AI over a tunnel.** The Classifier reads `OLLAMA_BASE_URL` (a Secret)
  and POSTs to your Mac's Ollama. Swapping to a paid API later means changing
  one URL.
- **Swappable storage.** `services/router/storage.py` hides the datastore behind
  one interface, with backends for Cloud Storage, Firestore, S3, and DynamoDB.
  This is the seam that makes the AWS migration a config change.
- **Observability built in.** Every service exposes Prometheus metrics at
  `/metrics`. A ServiceMonitor tells the kube-prometheus-stack Operator to
  scrape them; Grafana renders one dashboard.

## Kubernetes objects

| Object | Purpose |
|---|---|
| Namespace `triage` | Isolates the app |
| ConfigMap `triage-config` | Non-secret config (service URLs, model, storage backend) |
| Secret `triage-secrets` | The Cloudflare Tunnel URL for the local model |
| Deployment + Service x4 | One per microservice |
| ServiceAccount `triage-sa` | Workload Identity for storage access |
| HPA (classifier) | Autoscales the busiest service on CPU |
| Ingress (optional) | Public entry; skip it and port-forward to save cost |
| ServiceMonitor | Prometheus scrape config for the four services |

## Custom metrics worth watching

- `app_requests_total`, `app_request_latency_seconds` - traffic and latency per service
- `classifications_total{category,urgency}` - what the model is producing
- `ai_call_latency_seconds` - how slow the local model is over the tunnel
- `ai_call_errors_total` - tunnel or model failures
- `tickets_routed_total{priority}`, `notifications_sent_total{priority}` - downstream outcomes

## Deliberate POC simplifications

- Services call each other directly over HTTP. A production version would put a
  queue (Pub/Sub or SQS) between the gateway and the workers for durability.
- The notifier logs instead of sending real Slack/email.
- A single Spot node keeps cost minimal; production would use multiple on-demand nodes.
