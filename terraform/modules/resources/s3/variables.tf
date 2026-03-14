
variable "s3_buckets" {
  type = map(object({
    name            = string
    website         = bool
    public_access   = bool
    lifecycle_days  = optional(number)
    versioning      = optional(bool, false)
  }))
}

variable "project" {
  default = "control-financiero"
}
