#!/usr/bin/env python3
"""Prepare real release metadata for the Terraform variables; does not call AWS."""

import datetime
import json
import os
import subprocess
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    commit = 'unavailable'
    dirty = True
    if (ROOT / '.git').exists():
        commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
        dirty = bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip())
    variables = {
        'aws_region': os.environ.get('AWS_REGION', 'us-east-1'),
        'project_name': os.environ.get('PROJECT_NAME', 'amazon-cloudfront-tf'),
        'deployment_id': str(uuid.uuid4()),
        'published_at': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'source_commit': commit,
        'working_tree_dirty': dirty,
    }
    target = ROOT / 'evidence' / 'release.tfvars.json'
    target.parent.mkdir(exist_ok=True)
    target.write_text(json.dumps(variables, indent=2) + '\n')
    print('Variables del despliegue preparadas en evidence/release.tfvars.json')


if __name__ == '__main__':
    main()
