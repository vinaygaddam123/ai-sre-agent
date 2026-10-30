# AI SRE Agent

A small incident-response agent for Kubernetes. It polls Prometheus for firing alerts, sends each one to the Google Gemini API, and logs a root-cause analysis with steps to confirm and fix it.

> **Credit:** I built this by following Viswa Teja Payam's "AI SRE Agent" guide, typing and running every step myself in my own repo and Codespace, and adapting it where my environment differed. See "Differences from the guide" below.

## What it does

1. A deliberately broken app (`broken-app`) is deployed with a 10 MiB memory limit, so it gets OOMKilled and then goes into CrashLoopBackOff.
2. Prometheus (via kube-prometheus-stack) fires alerts such as `PodOOMKilled` and `PodCrashLooping`.
3. The agent (Python) polls `/api/v1/alerts` every 60 seconds, ignores noise alerts, and asks Gemini for a root-cause analysis.
4. The result is printed to the pod logs.

## Stack

k3d (k3s in Docker), Helm, kube-prometheus-stack (Prometheus and Grafana), Python, Google Gemini API, Docker, GitHub Actions, GitHub Container Registry.

## Repository layout

- `agent/` : the agent code, `requirements.txt` and `Dockerfile`
- `k8s/` : monitoring Helm values, the alert rules, the broken app, the agent deployment
- `.github/workflows/build-agent.yml` : builds the image and pushes it to GHCR on every change to `agent/`
- `screenshots/` : evidence of the running system

## Screenshots

![Agent analysis](screenshots/01-agent-analysis.png)

## Problems I hit and fixed

- **k3d cluster never became ready:** containers on k3d's own Docker network had no internet access in Codespaces, so system pods could not pull images. Fixed by creating the cluster on Docker's default network with `--no-lb`.
- **Gemini calls returned 401 and 404:** the `AQ.` key returned `ACCESS_TOKEN_TYPE_UNSUPPORTED` on the ListModels call, and a malformed `.env` produced an empty model name. Fixed the `.env`, and used `generateContent` directly.
- **Gemini 503 and timeouts:** added retries with backoff and a shorter timeout, and switched to a lighter model.
- **No logs from the container:** Python buffered its output, so I set `PYTHONUNBUFFERED=1` in the Dockerfile.
- **Workflow never ran:** I had saved it outside `.github/workflows/`. Moved it.

## Differences from the guide

- Terraform / GCP VM deployment: not done. The agent runs in the local k3d cluster.
- Gemini model and request handling adapted to the current API.

## Possible improvements

The agent sends only the alert labels to Gemini, so the analysis is generic. Next step would be adding the pod's events and previous logs to the prompt.
## How to run it

Prerequisites: Docker, k3d, kubectl, Helm, a Gemini API key.

1. **Create the cluster** (on Docker's default network, no load balancer):
   ```bash
   k3d cluster create sre-cluster --network bridge --no-lb \
     --k3s-arg "--disable=traefik@server:0" \
     -p "30030:30030@server:0:direct" -p "30090:30090@server:0:direct"
   ```
2. **Install monitoring:**
   ```bash
   helm repo add prometheus-community https://prometheus-community.github.io/helm-charts
   helm upgrade --install monitoring prometheus-community/kube-prometheus-stack \
     -n monitoring --create-namespace -f k8s/monitoring-values.yaml --wait
   ```
3. **Add the alert rules and the broken app:**
   ```bash
   kubectl apply -f k8s/fast-alert.yaml
   kubectl apply -f k8s/broken-app.yaml
   ```
4. **Create a `.env` file** with `GEMINI_API_KEY=...` and `GEMINI_MODEL=...` (it is git-ignored), then store it as a secret:
   ```bash
   kubectl create secret generic agent-secrets --from-env-file=.env
   ```
5. **Deploy the agent:**
   ```bash
   kubectl apply -f k8s/agent-deployment.yaml
   kubectl logs -f deployment/ai-sre-agent
   ```

## Deployment workflow

A push that changes `agent/` triggers GitHub Actions, which builds the Docker image and pushes it to GitHub Container Registry. Deploying the new image to the cluster is a manual step (`kubectl rollout restart deployment/ai-sre-agent`).

## Operating notes

- Alerts ignored by the agent: `Watchdog`, `PrometheusNotConnectedToAlertmanagers`, `InfoInhibitor`.
- If Gemini returns 429, 500 or 503, the agent retries with a growing wait. A timeout is retried on the next poll.
- To rotate the API key: update `.env`, then delete and recreate the `agent-secrets` secret and run `kubectl rollout restart deployment/ai-sre-agent`.
- To run the agent locally against the cluster: `POLL_SECONDS=15 python agent/main.py`.
## Pipeline run

![Pipeline: build and deploy](screenshots/02-github-actions.png)
