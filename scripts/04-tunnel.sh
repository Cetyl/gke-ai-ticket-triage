#!/usr/bin/env bash
# Run on your Mac. Starts Ollama + a Cloudflare quick tunnel to it, so the
# in-cluster classifier can reach your local model for free.
set -euo pipefail

# Keep the Mac awake while this runs (macOS): run `caffeinate -i` in another tab.
ollama serve >/tmp/ollama.log 2>&1 &
sleep 2
ollama pull qwen2.5:7b

cat <<'EOF'
-----------------------------------------------------------------
Cloudflare Tunnel is starting below. Copy the printed
https://<something>.trycloudflare.com URL, then in another terminal run:

  kubectl -n triage create secret generic triage-secrets \
    --from-literal=OLLAMA_BASE_URL=https://<something>.trycloudflare.com \
    --dry-run=client -o yaml | kubectl apply -f -

  kubectl -n triage rollout restart deploy/classifier

If you restart this tunnel later, the URL changes: re-run the two commands.
-----------------------------------------------------------------
EOF

cloudflared tunnel --url http://localhost:11434
