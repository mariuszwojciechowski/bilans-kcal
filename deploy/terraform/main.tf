# Fit Krasnal — minimalna, utwardzona infrastruktura na GCP:
# e2-micro (free tier) + Caddy/TLS, 80/443 z internetu, SSH tylko przez IAP,
# konto usługi z dostępem do Vertex AI.
#
# Bootstrap systemu (pakiety, użytkownik, venv, Caddy, sekrety) robi
# deploy/setup-vm.sh, uruchamiany przez SSH/IAP po `terraform apply`
# (patrz output `ssh_command`). Świadomie NIE jako startup-script: skrypt
# generuje sekrety do /etc/fit-krasnal/env i wymaga ręcznego uzupełnienia
# OAuth; przy każdym restarcie VM nie ma potrzeby go powtarzać.

locals {
  apis = [
    "compute.googleapis.com",
    "aiplatform.googleapis.com",
    "iap.googleapis.com",
    "oslogin.googleapis.com",
    "secretmanager.googleapis.com",
    "logging.googleapis.com",
    "storage.googleapis.com",
  ]
}

resource "google_project_service" "apis" {
  for_each                   = toset(local.apis)
  service                    = each.value
  disable_on_destroy         = false
  disable_dependent_services = false
}

# ── Konto usługi VM: tylko Vertex AI + zapis logów, bez kluczy ──────────
resource "google_service_account" "vm" {
  account_id   = "${var.name}-vm"
  display_name = "Fit Krasnal VM (Vertex AI + logi)"
}

resource "google_project_iam_member" "vm_aiplatform" {
  project = var.project_id
  role    = "roles/aiplatform.user"
  member  = "serviceAccount:${google_service_account.vm.email}"
}

resource "google_project_iam_member" "vm_logging" {
  project = var.project_id
  role    = "roles/logging.logWriter"
  member  = "serviceAccount:${google_service_account.vm.email}"
}

# ── Adres statyczny (regionalny, STANDARD tier — tańszy egress) ─────────
resource "google_compute_address" "ip" {
  name         = var.static_ip_name
  region       = var.region
  address_type = "EXTERNAL"
  network_tier = "STANDARD"

  lifecycle {
    prevent_destroy = true
  }
}

# ── Firewall: 80/443 z internetu, 22 tylko z IAP ────────────────────────
resource "google_compute_firewall" "web" {
  name          = "${var.name}-allow-web"
  network       = var.network
  direction     = "INGRESS"
  source_ranges = ["0.0.0.0/0"]
  target_tags   = [var.name]

  allow {
    protocol = "tcp"
    ports    = ["80", "443"]
  }
}

resource "google_compute_firewall" "ssh_iap" {
  name          = "${var.name}-allow-ssh-iap"
  network       = var.network
  direction     = "INGRESS"
  source_ranges = [var.iap_ssh_range]
  target_tags   = [var.name]

  allow {
    protocol = "tcp"
    ports    = ["22"]
  }
}

# ── VM ───────────────────────────────────────────────────────────────────
resource "google_compute_instance" "vm" {
  name         = var.name
  machine_type = var.machine_type
  zone         = var.zone
  tags         = [var.name]

  boot_disk {
    initialize_params {
      image = var.image
      size  = var.disk_size_gb
      type  = "pd-standard"
    }
  }

  network_interface {
    network = var.network
    access_config {
      nat_ip       = google_compute_address.ip.address
      network_tier = "STANDARD"
    }
  }

  service_account {
    email  = google_service_account.vm.email
    scopes = ["cloud-platform"]
  }

  metadata = {
    enable-oslogin = "TRUE"
    # Allowlista logowania — jedno źródło prawdy w GCP. Usługa czyta ją przy
    # każdym starcie (ExecStartPre). Dopisanie usera bez Terraforma:
    #   gcloud compute instances add-metadata fit-krasnal --zone <zone> \
    #     --metadata fit-krasnal-allowed-emails=a@x.com,b@y.com
    #   (potem systemctl restart fit-krasnal) — i uzupełnij tfvars, żeby plan
    #   nie pokazał dryfu.
    fit-krasnal-allowed-emails = join(",", var.allowed_emails)
  }

  shielded_instance_config {
    enable_secure_boot          = true
    enable_vtpm                 = true
    enable_integrity_monitoring = true
  }

  allow_stopping_for_update = true

  depends_on = [google_project_service.apis]
}

# ── Bucket na APK: prywatny, dostęp tylko dla wskazanych kont ───────────
# Pobieranie: https://storage.cloud.google.com/<bucket>/fit-krasnal.apk
# (wymaga zalogowania kontem Google z listy apk_viewers).
resource "google_storage_bucket" "apk" {
  name                        = var.apk_bucket_name
  location                    = upper(var.region)
  storage_class               = "STANDARD"
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"
  force_destroy               = false

  depends_on = [google_project_service.apis]
}

resource "google_storage_bucket_iam_member" "apk_viewers" {
  for_each = toset(var.apk_viewers)
  bucket   = google_storage_bucket.apk.name
  role     = "roles/storage.objectViewer"
  member   = "user:${each.value}"
}

# ── Klient OAuth (Google) w Secret Manager ──────────────────────────────
# Sam sekret (kontener) i uprawnienie odczytu dla konta VM są w Terraformie;
# WERSJĘ (payload: dwie linie FIT_KRASNAL_GOOGLE_CLIENT_ID=… i
# FIT_KRASNAL_GOOGLE_CLIENT_SECRET=…) dodaje operator ręcznie, żeby wartości
# nigdy nie trafiły do stanu Terraforma. Instrukcja: deploy/README.md,
# sekcja „Wariant GCP z logowaniem Google"; komenda do VM: output
# `oauth_secret_load_command`.
resource "google_secret_manager_secret" "oauth" {
  secret_id = var.oauth_secret_name

  replication {
    auto {}
  }

  # Wersję z kluczem dodał operator ręcznie — `terraform destroy` nie może
  # jej skasować po cichu (jak google_compute_address.ip). Uwaga: blokuje też
  # replacement: zmiana `var.oauth_secret_name` lub replikacji = nowy sekret,
  # więc najpierw świadomie usuń ten blok (wersje przepadają); zmiana etykiety
  # zasobu w HCL = `terraform state mv`.
  lifecycle {
    prevent_destroy = true
  }

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_iam_member" "oauth_vm_accessor" {
  secret_id = google_secret_manager_secret.oauth.id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.vm.email}"
}
