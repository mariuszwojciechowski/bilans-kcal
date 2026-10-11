output "public_ip" {
  value = google_compute_address.ip.address
}

output "service_account_email" {
  value = google_service_account.vm.email
}

output "ssh_command" {
  value = "gcloud compute ssh ${google_compute_instance.vm.name} --project ${var.project_id} --zone ${var.zone} --tunnel-through-iap"
}

output "setup_command" {
  description = "Do uruchomienia na VM po pierwszym SSH."
  value       = "curl -fsSL <RAW_URL_setup-vm.sh> | sudo FIT_DOMAIN=${var.domain} bash"
}

output "env_hints" {
  description = "Wartości do /etc/fit-krasnal/env (setup-vm.sh wstawia je, gdy dostanie zmienne)."
  value = {
    FIT_KRASNAL_PUBLIC_URL      = "https://${var.domain}"
    FIT_KRASNAL_ALLOWED_HOSTS   = var.domain
    FIT_KRASNAL_ALLOWED_EMAILS  = join(",", var.allowed_emails)
    FIT_KRASNAL_VERTEX_PROJECT  = var.project_id
    FIT_KRASNAL_VERTEX_LOCATION = var.vertex_location
    OAUTH_REDIRECT_URI          = "https://${var.domain}/auth/google/callback"
  }
}

output "apk_download_url" {
  value = "https://storage.cloud.google.com/${google_storage_bucket.apk.name}/fit-krasnal.apk"
}

output "apk_upload_command" {
  value = "gcloud storage cp android-app/dist/fit-krasnal-debug.apk gs://${google_storage_bucket.apk.name}/fit-krasnal.apk"
}

output "oauth_secret_load_command" {
  description = "Do uruchomienia na VM: kopiuje loader poza checkout (root-owned) i pobiera klienta OAuth z Secret Manager (gcloud z konta usługi VM), podmienia linie w /etc/fit-krasnal/env i restartuje usługę. Nie wypisuje wartości sekretu."
  value       = "sudo install -o root -g root -m 0755 /opt/fit-krasnal/deploy/load-oauth-secret.sh /usr/local/sbin/load-oauth-secret && sudo /usr/local/sbin/load-oauth-secret ${google_secret_manager_secret.oauth.secret_id}"
}
