output "alb_url" {
  description = "Initial HTTP URL for the demo ALB."
  value       = "http://${aws_lb.app.dns_name}"
}

output "alb_dns_name" {
  description = "ALB DNS name for optional Route 53/ACM setup."
  value       = aws_lb.app.dns_name
}

output "ecr_backend_repository_url" {
  value = aws_ecr_repository.backend.repository_url
}

output "ecr_frontend_repository_url" {
  value = aws_ecr_repository.frontend.repository_url
}

output "ecs_cluster_name" {
  value = aws_ecs_cluster.main.name
}

output "ecs_backend_service_name" {
  value = aws_ecs_service.backend.name
}

output "ecs_frontend_service_name" {
  value = aws_ecs_service.frontend.name
}

output "rds_endpoint" {
  description = "Private RDS endpoint; not publicly reachable."
  value       = aws_db_instance.postgres.address
}

output "redis_endpoint" {
  description = "Private Redis endpoint; not publicly reachable."
  value       = aws_elasticache_replication_group.redis.primary_endpoint_address
}

output "task_role_arn" {
  description = "ECS task role used for Cost Explorer and STS."
  value       = aws_iam_role.task.arn
}

output "private_subnet_ids" {
  value = [for subnet in aws_subnet.private : subnet.id]
}

output "ecs_security_group_id" {
  value = aws_security_group.ecs.id
}

output "application_secret_arn" {
  value     = aws_secretsmanager_secret.app.arn
  sensitive = true
}
