variable "project" {
  default = "controlador-financiero"
}


variable "global_secondary_index" {
  description = "Definición del índice secundario global (GSI), opcional"
  type = object({
    name            = string
    hash_key        = string
    projection_type = string
  })
  default = null  # Permite que sea opcional
}


variable "dynamo_tables" {
  description = "Lista de tablas de dynamo"

  type = map(object({
    table_name       = string
    hash_key         = string
    range_key        = optional(string)
    attributes       = list(object({
                         name = string
                         type = string
                       }))
    stream_enabled   = optional(bool)
    stream_view_type = optional(string)
    global_secondary_index = optional(list(object({
      name            = string
      hash_key        = string
      range_key       = optional(string)   # <-- nuevo: permite sort key en el GSI
      projection_type = string
    })))
    tags = optional(map(string))
  }))
}
