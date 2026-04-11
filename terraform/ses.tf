resource "aws_sesv2_email_identity" "sender" {
  email_identity = var.ses_sender_email

  tags = {
    Project     = var.project
  }
}

data "aws_sesv2_email_identity" "sender" {
  email_identity = var.ses_sender_email
}

data "aws_sesv2_email_identity" "recipient" {
  email_identity = var.ses_recipient_email
}
