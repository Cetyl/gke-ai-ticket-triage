#!/usr/bin/env bash
# Builds and pushes all four service images. --platform linux/amd64 so images
# built on an Apple Silicon Mac run on GKE nodes.
set -euo pipefail
source "$(dirname "$0")/env.sh"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

gcloud auth configure-docker "${REGION}-docker.pkg.dev" -q

for svc in api-gateway classifier router notifier; do
  echo "==> building $svc"
  docker build --platform linux/amd64 -t "${REGISTRY}/${svc}:latest" "${ROOT}/services/${svc}"
  docker push "${REGISTRY}/${svc}:latest"
done

echo "Images pushed. Next: scripts/03-deploy.sh"
