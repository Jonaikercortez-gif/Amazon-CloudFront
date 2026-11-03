#!/usr/bin/env python3
"""Collect evidence from a real distribution; never substitute local test results."""

import argparse
import datetime
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path


class VerificationError(Exception):
    pass


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def fetch_url(url):
    # Default TLS and proxy settings are preserved. Inspect redirects instead of following them.
    opener = urllib.request.build_opener(NoRedirect)
    request = urllib.request.Request(url, headers={"User-Agent": "CloudFront-Demo-Verifier/1.0"})
    try:
        response = opener.open(request, timeout=30)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        return {
            "status": response.code,
            "headers": {key.lower(): value for key, value in response.headers.items()},
            "body": response.read(),
        }


def require(condition, message):
    if not condition:
        raise VerificationError(message)


def cloudfront_response(response):
    require(response["status"] == 200, f'CloudFront devolvió HTTP {response["status"]}.')
    headers = response["headers"]
    require(headers.get("x-amz-cf-id") and headers.get("x-amz-cf-pop"), "Faltan cabeceras de CloudFront.")
    require("cloudfront" in headers.get("via", "").lower(), "La cabecera Via no identifica CloudFront.")
    require("from cloudfront" in headers.get("x-cache", "").lower(), "Falta X-Cache de CloudFront.")


def summary(url, response):
    # Do not save request authorization, cookies or unrelated response headers.
    names = ("x-cache", "via", "x-amz-cf-id", "x-amz-cf-pop", "age", "date", "cache-control", "location")
    return {"url": url, "status": response["status"], "headers": {
        key: value for key, value in response["headers"].items() if key in names
    }}


def collect_evidence(outputs, expected_deployment_id=None, fetch=fetch_url, pause=time.sleep, attempts=6):
    url = outputs["DistributionUrl"].rstrip("/")
    parsed = urllib.parse.urlsplit(url)
    require(parsed.scheme == "https" and bool(parsed.hostname) and parsed.hostname.endswith(".cloudfront.net")
            and not parsed.username and not parsed.password and not parsed.port
            and not parsed.path and not parsed.query and not parsed.fragment,
            "Se requiere la URL HTTPS raíz de una distribución cloudfront.net.")
    origin_url = outputs["OriginUrl"]
    require(urllib.parse.urlsplit(origin_url).scheme == "https", "El origen debe comprobarse mediante HTTPS.")

    http_url = "http://" + parsed.netloc + "/"
    redirect = fetch(http_url)
    require(redirect["status"] in (301, 302, 307, 308), "HTTP no redirige a HTTPS.")
    require(redirect["headers"].get("location") == url + "/", "La redirección no apunta al mismo dominio con HTTPS.")

    page = fetch(url + "/")
    cloudfront_response(page)
    require(b"<h1>Amazon CloudFront</h1>" in page["body"], "El sitio esperado no aparece en la respuesta.")
    assets = []
    for path, marker in (("/styles.css", b"color-scheme"), ("/app.js", b"verifyDelivery")):
        response = fetch(url + path)
        cloudfront_response(response)
        require(marker in response["body"], f"El recurso {path} no contiene el contenido esperado.")
        assets.append(summary(url + path, response))

    samples = []
    deployment = None
    for attempt in range(attempts):
        response = fetch(url + "/deployment.json")
        cloudfront_response(response)
        try:
            current = json.loads(response["body"])
        except (ValueError, UnicodeDecodeError) as error:
            raise VerificationError("deployment.json no contiene JSON válido.") from error
        require(isinstance(current, dict) and bool(current.get("deployment_id")), "Falta deployment_id.")
        require(bool(current.get("published_at")) and bool(current.get("commit")), "Faltan metadatos de publicación.")
        if expected_deployment_id:
            require(current["deployment_id"] == expected_deployment_id, "CloudFront entrega un despliegue obsoleto.")
        if deployment:
            require(current == deployment, "El contenido cambió durante la comprobación de caché.")
        deployment = current
        samples.append(summary(url + "/deployment.json", response))
        if response["headers"].get("x-cache", "").lower() == "hit from cloudfront":
            break
        if attempt + 1 < attempts:
            pause(2)
    else:
        raise VerificationError("No se observó Hit from cloudfront; revisa la caché y repite la verificación.")

    origin = fetch(origin_url)
    require(origin["status"] == 403, f'El origen S3 debería denegar el acceso (403), devolvió {origin["status"]}.')
    return {
        "status": "passed",
        "verified_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "distribution_id": outputs["DistributionId"],
        "distribution_url": url,
        "deployment": deployment,
        "checks": {"http_to_https": True, "site_and_assets": True, "cloudfront_headers": True,
                   "cache_hit": True, "private_s3_origin": True},
        "http_redirect": summary(http_url, redirect),
        "site": summary(url + "/", page),
        "assets": assets,
        "cache_samples": samples,
        "direct_s3_request": summary(origin_url, origin),
    }


def main():
    parser = argparse.ArgumentParser(description="Comprueba un despliegue CloudFront y guarda evidencias reales.")
    parser.add_argument("--outputs", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-deployment-id")
    args = parser.parse_args()
    try:
        outputs = json.loads(args.outputs.read_text())
        evidence = collect_evidence(outputs, args.expected_deployment_id)
    except (VerificationError, KeyError, ValueError, OSError, urllib.error.URLError) as error:
        # Replace any previous success so a failed run cannot leave stale passing evidence.
        evidence = {"status": "failed", "verified_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "error": str(error)}
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n")
        print(f"Verificación fallida: {error}", file=sys.stderr)
        return 1
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(evidence, indent=2, ensure_ascii=False) + "\n")
    print("PASS: HTTPS, sitio, cabeceras CloudFront, caché y origen S3 privado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
