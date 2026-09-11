resource "random_password" "jwt" {
  length  = 64
  special = false
}

resource "aws_secretsmanager_secret" "app" {
  name                    = "${local.name}/application"
  description             = "Runtime secrets for the Cost Detector backend"
  recovery_window_in_days = 7
}

resource "aws_secretsmanager_secret_version" "app" {
  secret_id = aws_secretsmanager_secret.app.id
  secret_string = jsonencode({
    DATABASE_URL   = "postgresql+asyncpg://${var.db_username}:${random_password.db.result}@${aws_db_instance.postgres.address}:${aws_db_instance.postgres.port}/${var.db_name}"
    JWT_SECRET_KEY = random_password.jwt.result
    REDIS_URL      = "rediss://${aws_elasticache_replication_group.redis.primary_endpoint_address}:6379/0"
  })
}
