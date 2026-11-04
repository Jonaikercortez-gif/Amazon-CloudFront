"""Local fixtures test the verifier; these are not AWS deployment evidence."""

import importlib.util
import json
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("verify", Path(__file__).resolve().parents[1] / "scripts/verify.py")
verify = importlib.util.module_from_spec(spec)
spec.loader.exec_module(verify)

URL = "https://example.cloudfront.net"
ORIGIN = "https://example.s3.us-east-1.amazonaws.com/index.html"
OUTPUTS = {"DistributionUrl": URL, "OriginUrl": ORIGIN, "DistributionId": "TEST-FIXTURE"}


class VerificationTests(unittest.TestCase):
    def fake_server(self, *, cache="Hit from cloudfront", origin_status=403, deployment_id="current", missing_header=None, redirect=None, page_status=200):
        headers = {"x-cache": cache, "x-amz-cf-id": "fixture-request", "x-amz-cf-pop": "TEST1",
                   "via": "1.1 fixture.cloudfront.net (CloudFront)", "age": "2"}
        if missing_header:
            headers.pop(missing_header)

        def fetch(url):
            if url.startswith("http://"):
                return {"status": 301, "headers": {"location": redirect or URL + "/"}, "body": b""}
            if url == ORIGIN:
                return {"status": origin_status, "headers": {}, "body": b""}
            body = {
                "/": b"<h1>Amazon CloudFront</h1>",
                "/styles.css": b":root { color-scheme: dark; }",
                "/app.js": b"function verifyDelivery() {}",
                "/deployment.json": json.dumps({"deployment_id": deployment_id, "published_at": "fixture-time", "commit": "fixture-commit"}).encode(),
            }[url.removeprefix(URL)]
            return {"status": page_status if url == URL + "/" else 200, "headers": headers.copy(), "body": body}
        return fetch

    def check(self, **kwargs):
        return verify.collect_evidence(OUTPUTS, "current", fetch=self.fake_server(**kwargs), pause=lambda _: None, attempts=2)

    def test_collects_headers_and_deployment_for_valid_response(self):
        evidence = self.check()
        self.assertEqual(evidence["status"], "passed")
        self.assertTrue(all(evidence["checks"].values()))
        self.assertEqual(evidence["direct_s3_request"]["status"], 403)
        self.assertEqual(evidence["deployment"]["deployment_id"], "current")

    def test_rejects_public_s3_origin(self):
        with self.assertRaisesRegex(verify.VerificationError, "devolvió 200"):
            self.check(origin_status=200)

    def test_rejects_stale_deployment(self):
        with self.assertRaisesRegex(verify.VerificationError, "obsoleto"):
            self.check(deployment_id="old")

    def test_rejects_permanent_cache_miss(self):
        with self.assertRaisesRegex(verify.VerificationError, "No se observó Hit"):
            self.check(cache="Miss from cloudfront")

    def test_rejects_origin_error_from_cloudfront(self):
        with self.assertRaisesRegex(verify.VerificationError, "HTTP 403"):
            self.check(page_status=403)

    def test_rejects_missing_cloudfront_identity(self):
        for header in ("x-amz-cf-id", "x-amz-cf-pop", "via", "x-cache"):
            with self.subTest(header=header), self.assertRaises(verify.VerificationError):
                self.check(missing_header=header)

    def test_rejects_redirect_to_another_site(self):
        with self.assertRaisesRegex(verify.VerificationError, "mismo dominio"):
            self.check(redirect="https://other.example/")

    def test_rejects_non_cloudfront_url(self):
        outputs = dict(OUTPUTS, DistributionUrl="https://example.com")
        with self.assertRaisesRegex(verify.VerificationError, "cloudfront.net"):
            verify.collect_evidence(outputs, fetch=self.fake_server())

    def test_observes_miss_then_hit(self):
        server = self.fake_server()
        calls = []

        def fetch(url):
            response = server(url)
            if url.endswith("/deployment.json"):
                calls.append(url)
                if len(calls) == 1:
                    response["headers"]["x-cache"] = "Miss from cloudfront"
            return response

        evidence = verify.collect_evidence(OUTPUTS, "current", fetch=fetch, pause=lambda _: None)
        self.assertEqual(len(evidence["cache_samples"]), 2)


if __name__ == "__main__":
    unittest.main()
