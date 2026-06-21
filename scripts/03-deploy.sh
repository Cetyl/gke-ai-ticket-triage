#!/usr/bin/env bash
# Substitutes placeholders in the manifests and deploys the app (no Ingress).
set -euo pipefail
source "$(dirname "$0")/env.sh"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TMP="$(mktemp -d)"

cp "${ROOT}"/k8s/*.yaml "$TMP"/
sed -i.bak "s|REGISTRY_PLACEHOLDER|${REGISTRY}|g; s|PROJECT_ID|${PROJECT_ID}|g" "$TMP"/*.yaml

kubectl apply -f "$TMP"/00-namespace-config.yaml
kubectl apply -f "$TMP"/10-api-gateway.yaml
kubectl apply -f "$TMP"/11-classifier.yaml
kubectl apply -f "$TMP"/12-router.yaml
kubectl apply -f "$TMP"/13-notifier.yaml
kubectl apply -f "$TMP"/21-hpa.yaml

# Link the k8s service account to the GCP service account (Workload Identity).
kubectl annotate serviceaccount triage-sa -n triage \
  "iam.gke.io/gcp-service-account=${GSA}@${PROJECT_ID}.iam.gserviceaccount.com" --overwrite

echo "Deployed. Create the tunnel secret next: scripts/04-tunnel.sh"
echo "The classifier will stay NotReady until OLLAMA_BASE_URL secret exists."
