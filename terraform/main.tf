terraform {
  required_providers {
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.30"
    }
  }
}

provider "kubernetes" {
  config_path = "~/.kube/config"
}

variable "image" {
  type    = string
  default = "ghcr.io/vinaygaddam123/ai-sre-agent:latest"
}

variable "replicas" {
  type    = number
  default = 1
}

resource "kubernetes_deployment_v1" "agent" {
  metadata {
    name = "ai-sre-agent"
    labels = { app = "ai-sre-agent" }
  }

  spec {
    replicas = var.replicas

    selector {
      match_labels = { app = "ai-sre-agent" }
    }

    template {
      metadata {
        labels = { app = "ai-sre-agent" }
      }

      spec {
        container {
          name  = "agent"
          image = var.image

          env_from {
            secret_ref {
              name = "agent-secrets"
            }
          }

          env {
            name  = "PROMETHEUS_URL"
            value = "http://monitoring-kube-prometheus-prometheus.monitoring.svc:9090"
          }

          env {
            name  = "POLL_SECONDS"
            value = "60"
          }

          resources {
            requests = { memory = "64Mi" }
            limits   = { memory = "128Mi" }
          }
        }
      }
    }
  }
}