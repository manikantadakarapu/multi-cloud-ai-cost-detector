variable "aws_region" {
  description = "AWS region for the demo environment."
  type        = string
  default     = "us-east-1"
}

variable "project_name" {
  description = "Short project name used in resource names."
  type        = string
  default     = "cost-detector"
}

variable "environment" {
  description = "Deployment environment name."
  type        = string
  default     = "demo"
}

variable "vpc_cidr" {
  description = "CIDR for the dedicated VPC."
  type        = string
  default     = "10.42.0.0/16"
}

variable "backend_image" {
  description = "Immutable ECR URI and tag for the backend image."
  type        = string
}

variable "frontend_image" {
  description = "Immutable ECR URI and tag for the frontend image."
  type        = string
}

variable "db_name" {
  description = "PostgreSQL database name."
  type        = string
  default     = "mcaicd"
}

variable "db_username" {
  description = "PostgreSQL application username."
  type        = string
  default     = "mcaicd"
}

variable "db_instance_class" {
  description = "Small RDS class for the demo environment."
  type        = string
  default     = "db.t4g.micro"
}

variable "redis_node_type" {
  description = "Small ElastiCache node type for the demo environment."
  type        = string
  default     = "cache.t4g.micro"
}

variable "app_origin" {
  description = "Optional public origin for CORS. Defaults to the ALB HTTP URL."
  type        = string
  default     = ""
}

variable "enable_azure" {
  description = "Enable Azure provider calls in this environment."
  type        = bool
  default     = false
}

variable "enable_gcp" {
  description = "Enable GCP provider calls in this environment."
  type        = bool
  default     = false
}
