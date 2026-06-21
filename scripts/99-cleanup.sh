#!/usr/bin/env bash
# Deletes the cluster (the main cost) and the bucket. RUN THIS WHEN YOU ARE DONE.
set -euo pipefail
source "$(dirname "$0")/env.sh"

gcloud container clusters delete "$CLUSTER" --zone "$ZONE" -q || true
gcloud storage rm -r "gs://${GCS_BUCKET}" -q || true

echo "Cluster and bucket deleted."
echo "On your Mac: stop the tunnel (Ctrl-C) and run 'pkill ollama'."
