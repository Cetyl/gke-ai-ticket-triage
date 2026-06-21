#!/usr/bin/env bash
# Installs Prometheus + Grafana (kube-prometheus-stack) and wires in our services.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace monitoring --create-namespace --wait

kubectl apply -f "${ROOT}/k8s/30-servicemonitor.yaml"

cat <<'EOF'
Observability installed.

Open Grafana:
  kubectl -n monitoring port-forward svc/kube-prometheus-stack-grafana 3000:80
  # then browse http://localhost:3000

Login: admin / (password below)
  kubectl -n monitoring get secret kube-prometheus-stack-grafana \
    -o jsonpath='{.data.admin-password}' | base64 -d ; echo

Import the dashboard: observability/grafana-dashboard.json
EOF
