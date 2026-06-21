#!/usr/bin/env bash
# Sends one ticket through the workflow. Run after port-forwarding the gateway:
#   kubectl -n triage port-forward svc/api-gateway 8000:8000
set -euo pipefail
API="${API_URL:-http://localhost:8000}"

curl -sS -X POST "${API}/tickets" \
  -H "Content-Type: application/json" \
  -d '{"subject":"Cannot log in","body":"Password error blocking my whole team, urgent."}' \
  | python3 -m json.tool
