variable "prefix" {
  description = "Prefijo del sistema (ej: flujo-caja)"
  type        = string
}

variable "catalogo_path" {
  description = "Ruta al JSON del catálogo de conceptos"
  type        = string
}

variable "reglas_path" {
  description = "Ruta al JSON de reglas de compensación"
  type        = string
}

variable "proyeccion_fija_path" {
  description = "Ruta al JSON de proyecciones fijas"
  type        = string
}

variable "conceptos_persistentes_path" {
  description = "Ruta al JSON de conceptos de proyección que persisten en el cierre mensual"
  type        = string
}

