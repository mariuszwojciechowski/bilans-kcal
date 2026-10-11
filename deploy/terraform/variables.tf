variable "project_id" {
  description = "ID projektu GCP."
  type        = string
}

variable "region" {
  description = "Region (np. us-central1 — free tier e2-micro)."
  type        = string
}

variable "zone" {
  description = "Strefa VM (np. us-central1-a)."
  type        = string
}

variable "domain" {
  description = "Publiczna nazwa hosta aplikacji (Caddy wystawi na nią TLS)."
  type        = string
}

variable "allowed_emails" {
  description = "E-maile dopuszczone do logowania. Trafiają do metadanych VM (klucz fit-krasnal-allowed-emails), skąd usługa czyta je przy starcie (deploy/fetch-metadata-env.sh → FIT_KRASNAL_ALLOWED_EMAILS)."
  type        = list(string)
}

variable "apk_bucket_name" {
  description = "Nazwa bucketu GCS na plik APK (globalnie unikalna). Prywatny; dostęp przez storage.cloud.google.com po zalogowaniu."
  type        = string
}

variable "apk_viewers" {
  description = "Konta Google (adresy e-mail) z prawem odczytu bucketu APK. Nic więcej nie dostają."
  type        = list(string)
  default     = []
}

variable "name" {
  description = "Prefiks nazw zasobów."
  type        = string
  default     = "fit-krasnal"
}

variable "static_ip_name" {
  description = "Nazwa istniejącego/tworzonego adresu statycznego (regionalnego)."
  type        = string
  default     = "fit-krasnal-ip"
}

variable "machine_type" {
  type    = string
  default = "e2-micro"
}

variable "disk_size_gb" {
  type    = number
  default = 30
}

variable "image" {
  type    = string
  default = "debian-cloud/debian-12"
}

variable "network" {
  description = "Sieć VPC (domyślnie default)."
  type        = string
  default     = "default"
}

variable "vertex_location" {
  description = "Region Vertex AI (FIT_KRASNAL_VERTEX_LOCATION) — tylko do outputu."
  type        = string
  default     = "europe-west1"
}

variable "iap_ssh_range" {
  description = "Zakres źródłowy tuneli IAP TCP (stały, publikowany przez Google)."
  type        = string
  default     = "35.235.240.0/20"
}

variable "oauth_secret_name" {
  description = "Nazwa sekretu w Secret Manager z klientem OAuth Google (payload: dwie linie FIT_KRASNAL_GOOGLE_CLIENT_ID=… / FIT_KRASNAL_GOOGLE_CLIENT_SECRET=…). Wersję dodaje operator, nie Terraform."
  type        = string
  default     = "fit-krasnal-oauth"
}
