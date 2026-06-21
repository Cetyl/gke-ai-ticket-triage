# Migration to AWS

This is the second half of the project: take the exact same workload and run it
on AWS. Because Kubernetes is cloud-agnostic and the cloud-specific code sits
behind a storage interface, this is a swap, not a rewrite.

## What stays the same

- All four service code bases (`services/*/main.py`)
- The container images (rebuild and push to ECR, no code change)
- Every Kubernetes manifest except the image registry and storage config
- The local Ollama model and the Cloudflare Tunnel (cloud-neutral)
- Prometheus and Grafana, including the dashboard

## What changes

| Concern | GCP | AWS |
|---|---|---|
| Kubernetes | GKE | EKS |
| Container registry | Artifact Registry | ECR |
| Object storage | Cloud Storage | S3 |
| Document store | Firestore | DynamoDB |
| Identity for pods | Workload Identity | IRSA (IAM Roles for Service Accounts) |
| CLI / provisioning | `gcloud` | `eksctl` / `aws` |
| Cluster cost | Free zonal management tier | ~$0.10/hr control plane (no free tier) |

## Step by step

1. **Cluster.** Create an EKS cluster:
   ```bash
   eksctl create cluster --name triage-poc --nodes 1 --node-type t3.medium --spot
   ```

2. **Registry.** Create ECR repos and push the same images:
   ```bash
   aws ecr create-repository --repository-name api-gateway   # repeat per service
   # docker build --platform linux/amd64 ... then docker push to the ECR URI
   ```
   Update `REGISTRY_PLACEHOLDER` in the manifests to your ECR registry.

3. **Storage.** No code change. Switch the ConfigMap:
   ```yaml
   STORAGE_BACKEND: "s3"        # or "dynamodb"
   S3_BUCKET: "your-tickets-poc"
   ```
   The `S3Backend` and `DynamoDBBackend` are already implemented in
   `services/router/storage.py`.

4. **Pod identity.** Replace Workload Identity with IRSA: create an IAM role with
   S3 (or DynamoDB) access and annotate `triage-sa`:
   ```yaml
   eks.amazonaws.com/role-arn: arn:aws:iam::<account>:role/triage-poc
   ```

5. **AI and observability.** Nothing to do. Keep the same tunnel secret and the
   same `helm install kube-prometheus-stack`. Optionally use Amazon Managed
   Prometheus and Managed Grafana instead.

6. **Entry point.** The optional GCE Ingress becomes an AWS ALB Ingress (install
   the AWS Load Balancer Controller), or just keep using `kubectl port-forward`.

## The story for a writeup

The value of this migration is the contrast: the application layer (services,
manifests, AI, dashboards) moved unchanged, while only the managed-service
adapters and provisioning commands changed. That is the practical case for
building cloud-portable workloads, and it is exactly the kind of hands-on,
real-tradeoff content that makes a strong thought-leadership piece.

One honest note: AWS does not waive the EKS control plane fee the way GKE waives
the zonal cluster management fee, so budget about $0.10/hour for the AWS run, or
use AWS credits if you have them.
