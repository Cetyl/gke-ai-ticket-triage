#!/usr/bin/env bash
# Edit these, then all other scripts source this file.
export PROJECT_ID="your-gcp-project-id"
export REGION="us-central1"
export ZONE="us-central1-a"
export CLUSTER="triage-poc"
export REPO="triage"
export REGISTRY="${REGION}-docker.pkg.dev/${PROJECT_ID}/${REPO}"
export GCS_BUCKET="${PROJECT_ID}-tickets-poc"
export GSA="triage-poc"   # GCP service account name (for Workload Identity)
