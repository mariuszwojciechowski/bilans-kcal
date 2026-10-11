terraform {
  required_version = ">= 1.6"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }
  # Local backend; plik stanu leży obok konfiguracji i jest w .gitignore:
  #   terraform init -backend-config="path=terraform.tfstate"
  backend "local" {}
}

provider "google" {
  project = var.project_id
  region  = var.region
  zone    = var.zone
}
