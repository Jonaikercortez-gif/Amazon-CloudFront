variable "aws_region" {
  description = "Región de AWS donde se almacena el sitio en S3."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Nombre del proyecto; se añade un sufijo único al bucket."
  type        = string
  default     = "amazon-cloudfront-tf"

  validation {
    condition     = can(regex("^[a-z][a-z0-9-]{1,22}[a-z0-9]$", var.project_name))
    error_message = "Usa entre 3 y 24 caracteres: letras minúsculas, números y guiones, sin un guion al final."
  }
}

variable "cache_ttl" {
  description = "Duración predeterminada de la caché, en segundos."
  type        = number
  default     = 60

  validation {
    condition     = var.cache_ttl >= 1 && var.cache_ttl <= 86400 && floor(var.cache_ttl) == var.cache_ttl
    error_message = "El TTL debe ser un número entero entre 1 y 86400 segundos."
  }
}

variable "deployment_id" {
  description = "Identificador de esta publicación, generado por scripts/prepare_release.py."
  type        = string

  validation {
    condition     = length(trimspace(var.deployment_id)) > 0
    error_message = "El identificador del despliegue no puede estar vacío."
  }
}

variable "published_at" {
  description = "Fecha UTC de preparación del despliegue en formato RFC3339."
  type        = string

  validation {
    condition     = can(formatdate("YYYY-MM-DD", var.published_at))
    error_message = "La fecha debe tener formato RFC3339, por ejemplo 2026-01-01T12:00:00Z."
  }
}

variable "source_commit" {
  description = "Commit del contenido que se va a publicar."
  type        = string
  default     = "manual"
}

variable "working_tree_dirty" {
  description = "Indica si había cambios locales al preparar la publicación."
  type        = bool
  default     = true
}
