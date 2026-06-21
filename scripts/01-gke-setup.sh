#!/usr/bin/env bash
# Creates a cost-minimal zonal GKE cluster (free management tier), an Artifact
# Registry repo, a Cloud Storage bucket, and Workload Identity for the router.
set -euo pipefail
source "$(dirname "$0")/env.sh"

gcloud config set project "$PROJECT_ID"
gcloud services enable container.googleapis.com artifactregistry.googleapis.com storage.googleapis.com

# Docker registry
gcloud artifacts repositories create "$REPO" \
  --repository-format=docker --location="$REGION" || true

# Zonal cluster = free management tier. Single Spot e2-medium node to minimise cost.
gcloud container clusters create "$CLUSTER" \
  --zone "$ZONE" \
  --num-nodes 1 \
  --machine-type e2-medium \
  --spot \
  --workload-pool="${PROJECT_ID}.svc.id.goog"

gcloud container clusters get-credentials "$CLUSTER" --zone "$ZONE"

# Ticket bucket
gcloud storage buckets create "gs://${GCS_BUCKET}" --location="$REGION" || true

# Workload Identity: GCP service account bound to k8s SA triage/triage-sa
gcloud iam service-accounts create "$GSA" || true
gcloud projects add-iam-policy-binding "$PROJECT_ID" \
  --member="serviceAccount:${GSA}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/storage.objectAdmin"
gcloud iam service-accounts add-iam-policy-binding \
  "${GSA}@${PROJECT_ID}.iam.gserviceaccount.com" \
  --role="roles/iam.workloadIdentityUser" \
  --member="serviceAccount:${PROJECT_ID}.svc.id.goog[triage/triage-sa]"

echo "Cluster ready. Next: scripts/02-build-push.sh"
