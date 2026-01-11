
variable "s3_buckets" {
  type = map(object({
    name            = string
    website         = bool
    public_access   = bool
    lifecycle_days  = optional(number)
  }))
}

variable "project" {
  default = "control-financiero"
}
