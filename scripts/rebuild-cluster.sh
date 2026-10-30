#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

k3d cluster delete sre-cluster || true
k3d cluster create sre-cluster --network bridge --no-lb \
  --k3s-arg "--disable=traefik@server:0" \
  -p "30030:30030@server:0:direct" -p "30090:30090@server:0:direct" \
  --wait --timeout 600s

helm repo add prometheus-community https://prometheus-community.github.io/helm-charts || true
helm repo update
helm upgrade --install monitoring prometheus-community/kube-prometheus-stack \
  -n monitoring --create-namespace -f k8s/monitoring-values.yaml --wait --timeout 10m

kubectl apply -f k8s/fast-alert.yaml -f k8s/broken-app.yaml
kubectl create secret generic agent-secrets --from-env-file=.env \
  --dry-run=client -o yaml | kubectl apply -f -

echo "Cluster ready. Push to main or re-run the workflow to deploy the agent."