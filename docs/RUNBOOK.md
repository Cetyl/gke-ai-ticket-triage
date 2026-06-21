# Runbook: build it in a day

Estimated time: half a day if GKE and Ollama are new to you.

## Prerequisites

- A Google Cloud account with the $300 free trial active
- `gcloud`, `kubectl`, `helm`, and `docker` installed locally
- Ollama installed on your Mac with the `qwen2.5:7b` model (from your existing setup)
- `cloudflared` installed (`brew install cloudflared`)

## Step 0: configure

Edit `scripts/env.sh` and set `PROJECT_ID` to your GCP project. Adjust region or
zone if you like.

## Step 1: start the local model and tunnel (on your Mac)

```bash
bash scripts/04-tunnel.sh
```

This starts Ollama, pulls the model, and opens a Cloudflare Tunnel. Copy the
`https://<...>.trycloudflare.com` URL it prints. Keep this terminal open and
keep the Mac awake (`caffeinate -i` in another tab on macOS).

## Step 2: create the cluster

```bash
bash scripts/01-gke-setup.sh
```

Creates a single-node Spot zonal cluster (free management tier), an Artifact
Registry repo, a Cloud Storage bucket, and the Workload Identity binding.

## Step 3: build and push images

```bash
bash scripts/02-build-push.sh
```

Builds all four services for `linux/amd64` and pushes them to Artifact Registry.

## Step 4: deploy and wire the tunnel

```bash
bash scripts/03-deploy.sh

# Use the tunnel URL from Step 1:
kubectl -n triage create secret generic triage-secrets \
  --from-literal=OLLAMA_BASE_URL=https://<your-tunnel>.trycloudflare.com \
  --dry-run=client -o yaml | kubectl apply -f -
kubectl -n triage rollout restart deploy/classifier
```

Check everything is up:

```bash
kubectl -n triage get pods
```

## Step 5: install observability

```bash
bash scripts/05-observability.sh
```

Then open Grafana (the script prints the port-forward command and password) and
import `observability/grafana-dashboard.json`.

## Step 6: run the workflow

```bash
kubectl -n triage port-forward svc/api-gateway 8000:8000 &
bash scripts/06-smoke-test.sh
```

You should get JSON back with a category, urgency, priority, and storage info.
Watch the Grafana panels move. Confirm the ticket landed in your bucket:

```bash
gcloud storage ls "gs://$(grep GCS_BUCKET scripts/env.sh | head -1)"
```

(Optional) run the UI:

```bash
cd ui && pip install -r requirements.txt && API_URL=http://localhost:8000 streamlit run streamlit_app.py
```

## Step 7: tear down (do not skip)

```bash
bash scripts/99-cleanup.sh
```

Deletes the cluster and bucket. Stop the tunnel and `pkill ollama` on your Mac.

## Troubleshooting

- **Classifier NotReady / 500s**: the tunnel secret is missing or the URL
  changed. Recreate the secret and restart the deployment.
- **AI errors climbing in Grafana**: Mac asleep, Ollama stopped, or tunnel
  closed. The classifier fails soft and returns a fallback so the workflow
  still completes.
- **Router storage errors**: Workload Identity not bound. Confirm the
  `triage-sa` annotation and the IAM binding from Step 2.
- **No data in Grafana**: confirm the ServiceMonitor `release` label matches the
  Helm release name (`kube-prometheus-stack`).
