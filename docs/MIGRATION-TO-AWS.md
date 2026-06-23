# Migrating the workload from GCP to AWS

The same AI ticket triage system, moved from Google Kubernetes Engine to Amazon EKS. Because Kubernetes is cloud agnostic and the storage layer already has an S3 backend (`services/router/storage.py`), this is a swap of managed services and tooling, not a rewrite.

## What carries over unchanged

- All four service code bases (`services/*/main.py`)
- The container images (rebuilt and pushed to ECR, no code change)
- Every Kubernetes manifest except the image path and storage config
- The local Ollama model and the Cloudflare tunnel
- Prometheus and Grafana (same Helm chart)
- The Streamlit UI

## What changes

| Concern | GCP | AWS |
|---|---|---|
| Kubernetes | GKE (`gcloud`) | EKS (`eksctl`) |
| Container registry | Artifact Registry | ECR |
| Object storage | Cloud Storage | S3 |
| Pod identity | Workload Identity | IRSA (IAM Roles for Service Accounts) |
| CLI / provisioning | gcloud | aws CLI |

## Cost note

EKS charges about $0.10 per hour per cluster control plane (roughly $73 per month), with no free-tier waiver, plus the EC2 worker nodes. Unless you have AWS credits, budget for this and delete the cluster when finished. Verify current pricing before starting.

## Prerequisites

- An AWS account
- Tools (all available in AWS CloudShell): `aws`, `eksctl`, `kubectl`, `helm`, `docker`
- On your Mac (unchanged from the GCP build): Ollama with `qwen2.5:7b`, and `cloudflared`

## Step 0: Open AWS CloudShell and get the code

First, make sure your GitHub repo is current. On your Mac:

```bash
cd "path/to/gke-ai-ticket-triage"
git add . && git commit -m "Update before AWS migration" && git push
```

Open the AWS Console, pick your region (top-right), and click the CloudShell icon (the >_ in the top bar). CloudShell already has `aws`, `kubectl`, `git`, and `docker`. Make sure `eksctl` and `helm` are present, and install them if the version check fails:

```bash
eksctl version || { curl -sSL "https://github.com/eksctl-io/eksctl/releases/latest/download/eksctl_Linux_amd64.tar.gz" | tar xz -C /tmp && sudo mv /tmp/eksctl /usr/local/bin; }
helm version  || curl -fsSL https://raw.githubusercontent.com/helm/helm/main/scripts/get-helm-3 | bash
```

Clone your repository. This is how the code gets into AWS, no zip upload needed this time:

```bash
git clone https://github.com/Cetyl/gke-ai-ticket-triage.git
cd gke-ai-ticket-triage
```

Then set these variables once and reuse them in the same CloudShell session:

```bash
export REGION=ap-south-1
export ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
export BUCKET=${ACCOUNT_ID}-triage-poc
export ECR=${ACCOUNT_ID}.dkr.ecr.${REGION}.amazonaws.com
```

## Step 1: Keep the local AI running

On your Mac, exactly as before:

```bash
ollama serve
cloudflared tunnel --url http://localhost:11434 --http-host-header localhost:11434
```

Copy the tunnel URL. Nothing about the AI side changes.

## Step 2: Build and push images to ECR

```bash
aws ecr get-login-password --region $REGION | docker login --username AWS --password-stdin $ECR

for svc in api-gateway classifier router notifier; do
  aws ecr create-repository --repository-name triage/$svc --region $REGION 2>/dev/null || true
  docker build -t $ECR/triage/$svc:latest services/$svc
  docker push $ECR/triage/$svc:latest
done
```

## Step 3: Create the S3 bucket

```bash
aws s3 mb s3://$BUCKET --region $REGION
```

## Step 4: Create the EKS cluster

This creates the VPC, a managed Spot node group, and the OIDC provider needed for IRSA. It takes 15 to 20 minutes (EKS is slower to provision than GKE).

```bash
eksctl create cluster \
  --name triage-poc \
  --region $REGION \
  --managed --spot \
  --instance-types t3.medium \
  --nodes 2 \
  --with-oidc

kubectl get nodes   # eksctl configures kubeconfig automatically
```

## Step 5: Pod identity (IRSA) for S3

Create an IAM policy that allows S3 access to your bucket, then bind it to the Kubernetes service account `triage/triage-sa`. First make the namespace:

```bash
kubectl create namespace triage
```

Create the policy:

```bash
cat > /tmp/triage-s3.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [{
    "Effect": "Allow",
    "Action": ["s3:GetObject", "s3:PutObject", "s3:ListBucket"],
    "Resource": ["arn:aws:s3:::${BUCKET}", "arn:aws:s3:::${BUCKET}/*"]
  }]
}
EOF

aws iam create-policy --policy-name triage-s3 --policy-document file:///tmp/triage-s3.json
```

Create the IRSA service account (eksctl creates `triage-sa` with the right IAM role annotation):

```bash
eksctl create iamserviceaccount \
  --cluster triage-poc --region $REGION \
  --namespace triage --name triage-sa \
  --attach-policy-arn arn:aws:iam::${ACCOUNT_ID}:policy/triage-s3 \
  --approve
```

## Step 6: Adjust config and deploy

The manifests are the same. Two changes: the image path points at ECR, and the storage backend switches to S3. Note: do not apply the GCP service account from `00-namespace-config.yaml` (it has a Workload Identity annotation). eksctl already created `triage-sa` in step 5.

```bash
# point images at ECR and set the project-style placeholders
sed -i "s|REGISTRY_PLACEHOLDER|$ECR/triage|g" k8s/10-api-gateway.yaml k8s/11-classifier.yaml k8s/12-router.yaml k8s/13-notifier.yaml

# switch storage backend in the ConfigMap
#   STORAGE_BACKEND: "s3"
#   S3_BUCKET: "<your bucket>"
# edit k8s/00-namespace-config.yaml: set STORAGE_BACKEND to s3, add S3_BUCKET,
# and REMOVE the ServiceAccount block (eksctl owns triage-sa now).
```

Apply (ConfigMap, services, deployments, HPA), then the secret:

```bash
kubectl apply -f k8s/00-namespace-config.yaml   # namespace + configmap only (SA removed)
kubectl apply -f k8s/10-api-gateway.yaml -f k8s/11-classifier.yaml \
              -f k8s/12-router.yaml -f k8s/13-notifier.yaml -f k8s/21-hpa.yaml

kubectl -n triage create secret generic triage-secrets \
  --from-literal=OLLAMA_BASE_URL=https://<your-tunnel>.trycloudflare.com

kubectl -n triage get pods -w
```

The `STORAGE_BACKEND=s3` setting makes the router use the `S3Backend` already in `storage.py`. No code change.

## Step 7: Observability (identical to GCP)

```bash
helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
helm repo update
helm install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
  --namespace monitoring --create-namespace
kubectl apply -f k8s/30-servicemonitor.yaml
```

Grafana access and dashboard import are the same as the GCP runbook.

## Step 8: Test

```bash
kubectl -n triage port-forward svc/api-gateway 8000:8000 &
curl -X POST http://localhost:8000/tickets -H "Content-Type: application/json" \
  -d '{"subject":"Payment failed","body":"Charged twice, urgent refund needed."}'

aws s3 ls s3://$BUCKET/tickets/
```

## Step 9: Cleanup (important, EKS is not free)

```bash
eksctl delete cluster --name triage-poc --region $REGION
aws s3 rb s3://$BUCKET --force
# on your Mac: stop the tunnel and run: pkill ollama
```

## The takeaway

The application layer (services, manifests, AI, dashboards) moved unchanged. Only the managed-service adapters (S3 vs Cloud Storage), the identity mechanism (IRSA vs Workload Identity), and the provisioning commands (eksctl/aws vs gcloud) changed. That is the practical case for building cloud-portable workloads.
