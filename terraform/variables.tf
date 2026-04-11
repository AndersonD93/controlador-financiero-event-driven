variable "region" {
  default = "us-east-1"
}

variable "project" {
  default = "control-financiero"
}

variable "account_id"{
  default = "122610499801"
}

# =========================
# Variables
# =========================
variable "ses_sender_email" {
  description = "Email remitente verificado en SES"
  type        = string
  default     = "johaoduranse@gmail.com"
}

variable "ses_recipient_email" {
  description = "Email destinatario verificado en SES"
  type        = string
  default     = "johaoduranse@gmail.com"
}