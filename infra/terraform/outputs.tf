output "distribution_url" {
  description = "URL HTTPS del sitio entregado por CloudFront."
  value       = "https://${aws_cloudfront_distribution.site.domain_name}"
}

output "bucket_name" {
  description = "Bucket privado del sitio."
  value       = aws_s3_bucket.site.bucket
}

output "site_outputs" {
  description = "Datos que utiliza scripts/verify.py para comprobar el servicio real."
  value = {
    BucketName      = aws_s3_bucket.site.bucket
    DistributionId  = aws_cloudfront_distribution.site.id
    DistributionUrl = "https://${aws_cloudfront_distribution.site.domain_name}"
    OriginUrl       = "https://${aws_s3_bucket.site.bucket_regional_domain_name}/index.html"
  }
}
