terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

# 1. BigQuery Dataset
resource "google_bigquery_dataset" "retail_analytics" {
  dataset_id  = "retail_analytics"
  location    = var.region
  description = "Dataset for AI Retail Analytics Agent"
}

# 2. Service Account for Cloud Run
resource "google_service_account" "retail_agent_sa" {
  account_id   = "retail-agent-sa"
  display_name = "Retail Analytics Agent Service Account"
}

# 3. IAM Roles for BigQuery
resource "google_project_iam_member" "bq_user" {
  project = var.project_id
  role    = "roles/bigquery.user"
  member  = "serviceAccount:${google_service_account.retail_agent_sa.email}"
}

resource "google_project_iam_member" "bq_data_editor" {
  project = var.project_id
  role    = "roles/bigquery.dataEditor"
  member  = "serviceAccount:${google_service_account.retail_agent_sa.email}"
}

# 4. Artifact Registry for Docker Image
resource "google_artifact_registry_repository" "docker_repo" {
  repository_name = "retail-agent"
  location        = var.region
  format          = "DOCKER"
  description     = "Docker repository for Retail Agent"
}

# 5. Cloud Run Service
resource "google_cloud_run_v2_service" "retail_agent" {
  name     = "retail-agent"
  location = var.region
  
  template {
    service_account = google_service_account.retail_agent_sa.email
    timeout         = 300 # 5 min timeout for AI agent

    containers {
      image = "${var.region}-docker.pkg.dev/${var.project_id}/retail-agent/retail-agent:latest"
      ports {
        container_port = 8000
      }
      
      env {
        name  = "APP_ENV"
        value = "production"
      }
      env {
        name  = "GCP_PROJECT_ID"
        value = var.project_id
      }
      env {
        name  = "GCP_BIGQUERY_DATASET"
        value = "retail_analytics"
      }
      
      # Secrets from Secret Manager
      dynamic "env" {
        for_each = var.secrets
        content {
          name = env.key
          value_from {
            secret_key_ref {
              secret  = env.value
              version = "latest"
            }
          }
        }
      }

      resources {
        limits = {
          cpu    = "2"
          memory = "2Gi"
        }
      }
    }
  }
}

# 6. Allow public access (optional)
resource "google_cloud_run_v2_service_iam_member" "public" {
  location  = google_cloud_run_v2_service.retail_agent.location
  name      = google_cloud_run_v2_service.retail_agent.name
  role      = "roles/run.invoker"
  member    = "allUsers"
}

variable "project_id" { type = string }
variable "region" { type = string, default = "us-central1" }
variable "secrets" { 
  type = map(string)
  default = {
    OPENAI_API_KEY = "openai-api-key"
  }
}

output "service_url" {
  value = google_cloud_run_v2_service.retail_agent.uri
}