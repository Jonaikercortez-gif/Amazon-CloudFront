mock_provider "aws" {
  override_during = plan

  mock_resource "aws_s3_bucket" {
    defaults = {
      id                          = "fixture-private-bucket"
      bucket                      = "fixture-private-bucket"
      arn                         = "arn:aws:s3:::fixture-private-bucket"
      bucket_regional_domain_name = "fixture-private-bucket.s3.us-east-1.amazonaws.com"
    }
  }

  mock_resource "aws_cloudfront_distribution" {
    defaults = {
      id          = "FIXTURE-DISTRIBUTION"
      arn         = "arn:aws:cloudfront::123456789012:distribution/FIXTURE-DISTRIBUTION"
      domain_name = "fixture.cloudfront.net"
    }
  }

  mock_resource "aws_cloudfront_origin_access_control" {
    defaults = {
      id = "FIXTURE-OAC"
    }
  }

  mock_resource "aws_cloudfront_cache_policy" {
    defaults = {
      id = "00000000-0000-0000-0000-000000000001"
    }
  }

  mock_resource "aws_cloudfront_response_headers_policy" {
    defaults = {
      id = "00000000-0000-0000-0000-000000000002"
    }
  }
}

variables {
  deployment_id = "test-fixture-release"
  published_at  = "2000-01-01T00:00:00Z"
  source_commit = "test-fixture-commit"
}

run "private_origin_https_and_cache" {
  command = plan

  assert {
    condition = (
      aws_s3_bucket_public_access_block.site.block_public_acls &&
      aws_s3_bucket_public_access_block.site.block_public_policy &&
      aws_s3_bucket_public_access_block.site.ignore_public_acls &&
      aws_s3_bucket_public_access_block.site.restrict_public_buckets
    )
    error_message = "El bucket debe bloquear todas las formas de acceso público."
  }

  assert {
    condition = (
      aws_cloudfront_origin_access_control.site.signing_behavior == "always" &&
      aws_cloudfront_origin_access_control.site.signing_protocol == "sigv4" &&
      aws_cloudfront_origin_access_control.site.origin_access_control_origin_type == "s3"
    )
    error_message = "CloudFront debe usar OAC con solicitudes S3 firmadas mediante SigV4."
  }

  assert {
    condition = alltrue([
      for origin in aws_cloudfront_distribution.site.origin :
      origin.domain_name == aws_s3_bucket.site.bucket_regional_domain_name &&
      origin.origin_access_control_id == aws_cloudfront_origin_access_control.site.id &&
      origin.origin_id == aws_cloudfront_distribution.site.default_cache_behavior[0].target_origin_id
    ])
    error_message = "La distribución debe usar este bucket privado y su OAC."
  }

  assert {
    condition = (
      aws_cloudfront_distribution.site.enabled &&
      aws_cloudfront_distribution.site.default_root_object == "index.html" &&
      aws_cloudfront_distribution.site.default_cache_behavior[0].viewer_protocol_policy == "redirect-to-https" &&
      toset(aws_cloudfront_distribution.site.default_cache_behavior[0].allowed_methods) == toset(["GET", "HEAD"]) &&
      toset(aws_cloudfront_distribution.site.default_cache_behavior[0].cached_methods) == toset(["GET", "HEAD"])
    )
    error_message = "El sitio debe estar habilitado con HTTPS, página inicial y métodos de solo lectura."
  }

  assert {
    condition = (
      aws_cloudfront_cache_policy.site.min_ttl == 0 &&
      aws_cloudfront_cache_policy.site.default_ttl == var.cache_ttl &&
      aws_cloudfront_cache_policy.site.max_ttl >= var.cache_ttl &&
      aws_cloudfront_distribution.site.default_cache_behavior[0].cache_policy_id == aws_cloudfront_cache_policy.site.id &&
      aws_cloudfront_distribution.site.default_cache_behavior[0].compress
    )
    error_message = "La política de caché debe estar conectada a la distribución y tener TTL efectivos."
  }

  assert {
    condition = (
      jsondecode(aws_s3_bucket_policy.site.policy).Statement[0].Principal.Service == "cloudfront.amazonaws.com" &&
      jsondecode(aws_s3_bucket_policy.site.policy).Statement[0].Action == "s3:GetObject" &&
      jsondecode(aws_s3_bucket_policy.site.policy).Statement[0].Resource == "${aws_s3_bucket.site.arn}/*" &&
      jsondecode(aws_s3_bucket_policy.site.policy).Statement[0].Condition.StringEquals["AWS:SourceArn"] == aws_cloudfront_distribution.site.arn &&
      length([for statement in jsondecode(aws_s3_bucket_policy.site.policy).Statement : statement if statement.Effect == "Allow"]) == 1
    )
    error_message = "La lectura de S3 debe limitarse al servicio CloudFront de esta distribución."
  }

  assert {
    condition = (
      jsondecode(aws_s3_bucket_policy.site.policy).Statement[1].Effect == "Deny" &&
      jsondecode(aws_s3_bucket_policy.site.policy).Statement[1].Principal == "*" &&
      jsondecode(aws_s3_bucket_policy.site.policy).Statement[1].Action == "s3:*" &&
      jsondecode(aws_s3_bucket_policy.site.policy).Statement[1].Condition.Bool["aws:SecureTransport"] == "false" &&
      toset(jsondecode(aws_s3_bucket_policy.site.policy).Statement[1].Resource) == toset([aws_s3_bucket.site.arn, "${aws_s3_bucket.site.arn}/*"])
    )
    error_message = "La política debe denegar conexiones inseguras al bucket y a sus objetos."
  }

  assert {
    condition = (
      aws_cloudfront_distribution.site.default_cache_behavior[0].response_headers_policy_id == aws_cloudfront_response_headers_policy.site.id &&
      aws_cloudfront_response_headers_policy.site.security_headers_config[0].frame_options[0].frame_option == "DENY" &&
      aws_cloudfront_response_headers_policy.site.security_headers_config[0].content_type_options[0].override
    )
    error_message = "Las cabeceras de seguridad deben estar asociadas a la distribución."
  }

  assert {
    condition = (
      contains(keys(aws_s3_object.site), "index.html") &&
      contains(keys(aws_s3_object.site), "styles.css") &&
      contains(keys(aws_s3_object.site), "app.js") &&
      aws_s3_object.deployment.key == "deployment.json" &&
      jsondecode(aws_s3_object.deployment.content).deployment_id == var.deployment_id
    )
    error_message = "Terraform debe publicar el sitio y los metadatos que utiliza el verificador."
  }
}

run "reject_invalid_project_name" {
  command = plan
  variables {
    project_name = "Invalid_Name"
  }
  expect_failures = [var.project_name]
}

run "reject_invalid_cache_ttl" {
  command = plan
  variables {
    cache_ttl = 0
  }
  expect_failures = [var.cache_ttl]
}

run "reject_invalid_publication_date" {
  command = plan
  variables {
    published_at = "not-a-date"
  }
  expect_failures = [var.published_at]
}
