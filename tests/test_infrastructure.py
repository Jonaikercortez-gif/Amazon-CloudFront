"""Verify security and routing requirements in the actual CloudFormation template."""

import unittest
from pathlib import Path

from cfnlint.decode import decode


class InfrastructureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.template, errors = decode(str(Path(__file__).resolve().parents[1] / 'infra/cloudfront.yaml'))
        if errors:
            raise AssertionError(f'Cannot parse the CloudFormation template: {errors}')
        cls.resources = cls.template['Resources']

    def properties(self, name):
        return self.resources[name]['Properties']

    def test_s3_blocks_all_public_access(self):
        block = self.properties('SiteBucket')['PublicAccessBlockConfiguration']
        for setting in ('BlockPublicAcls', 'BlockPublicPolicy', 'IgnorePublicAcls', 'RestrictPublicBuckets'):
            with self.subTest(setting=setting):
                self.assertIs(block.get(setting), True)

    def test_origin_uses_signed_oac_requests_to_the_private_bucket(self):
        distribution = self.properties('Distribution')['DistributionConfig']
        behavior = distribution['DefaultCacheBehavior']
        origin = next(origin for origin in distribution['Origins'] if origin['Id'] == behavior['TargetOriginId'])
        self.assertEqual(origin['DomainName'], {'Fn::GetAtt': ['SiteBucket', 'RegionalDomainName']})
        self.assertEqual(origin['OriginAccessControlId'], {'Fn::GetAtt': ['OriginAccessControl', 'Id']})
        self.assertIn('S3OriginConfig', origin)
        oac = self.properties('OriginAccessControl')['OriginAccessControlConfig']
        self.assertEqual(oac['OriginAccessControlOriginType'], 's3')
        self.assertEqual(oac['SigningBehavior'], 'always')
        self.assertEqual(oac['SigningProtocol'], 'sigv4')

    def test_viewer_redirects_to_https_and_only_allows_reads(self):
        distribution = self.properties('Distribution')['DistributionConfig']
        self.assertIs(distribution['Enabled'], True)
        self.assertEqual(distribution['DefaultRootObject'], 'index.html')
        behavior = distribution['DefaultCacheBehavior']
        self.assertEqual(behavior['ViewerProtocolPolicy'], 'redirect-to-https')
        self.assertEqual(set(behavior['AllowedMethods']), {'GET', 'HEAD'})
        self.assertEqual(set(behavior['CachedMethods']), {'GET', 'HEAD'})

    def test_cache_policy_is_attached_and_has_effective_ttls(self):
        behavior = self.properties('Distribution')['DistributionConfig']['DefaultCacheBehavior']
        self.assertEqual(behavior['CachePolicyId'], {'Ref': 'SiteCachePolicy'})
        self.assertIs(behavior['Compress'], True)
        cache = self.properties('SiteCachePolicy')['CachePolicyConfig']
        self.assertGreater(cache['DefaultTTL'], 0)
        self.assertLessEqual(cache['MinTTL'], cache['DefaultTTL'])
        self.assertLessEqual(cache['DefaultTTL'], cache['MaxTTL'])

    def test_bucket_read_grant_is_limited_to_this_distribution(self):
        policy = self.properties('SiteBucketPolicy')
        self.assertEqual(policy['Bucket'], {'Ref': 'SiteBucket'})
        grants = [statement for statement in policy['PolicyDocument']['Statement'] if statement['Effect'] == 'Allow']
        self.assertEqual(len(grants), 1, 'Unexpected additional bucket access grant')
        grant = grants[0]
        self.assertEqual(grant['Principal'], {'Service': 'cloudfront.amazonaws.com'})
        self.assertEqual(grant['Action'], 's3:GetObject')
        self.assertEqual(grant['Resource'], {'Fn::Sub': '${SiteBucket.Arn}/*'})
        self.assertEqual(grant['Condition']['StringEquals']['AWS:SourceArn'], {
            'Fn::Sub': 'arn:${AWS::Partition}:cloudfront::${AWS::AccountId}:distribution/${Distribution}'
        })

    def test_bucket_denies_insecure_transport_for_bucket_and_objects(self):
        statements = self.properties('SiteBucketPolicy')['PolicyDocument']['Statement']
        deny = next(statement for statement in statements if statement['Sid'] == 'DenyInsecureTransport')
        self.assertEqual(deny['Effect'], 'Deny')
        self.assertEqual(deny['Principal'], '*')
        self.assertEqual(deny['Action'], 's3:*')
        self.assertEqual(deny['Condition']['Bool']['aws:SecureTransport'], 'false')
        self.assertIn({'Fn::GetAtt': ['SiteBucket', 'Arn']}, deny['Resource'])
        self.assertIn({'Fn::Sub': '${SiteBucket.Arn}/*'}, deny['Resource'])


if __name__ == '__main__':
    unittest.main()
