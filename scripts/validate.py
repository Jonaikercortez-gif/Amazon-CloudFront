#!/usr/bin/env python3
"""Validate configuration locally and record evidence without creating AWS resources."""

import datetime
import hashlib
import json
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    commands = [
        ('CloudFormation schema and references', [shutil.which('cfn-lint') or str(Path(sys.executable).with_name('cfn-lint')), 'infra/cloudfront.yaml']),
        ('Deployment script syntax', ['bash', '-n', 'scripts/deploy.sh']),
        ('Browser script syntax', ['node', '--check', 'site/app.js']),
        ('Infrastructure and verifier tests', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v']),
        ('Browser panel tests', ['node', 'tests/site.test.cjs']),
    ]
    evidence_dir = ROOT / 'evidence'
    evidence_dir.mkdir(exist_ok=True)
    commit = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    dirty = bool(subprocess.check_output(['git', 'status', '--porcelain'], cwd=ROOT, text=True).strip())
    report = {
        'scope': 'configuration_validation',
        'live_aws_verified': False,
        'status': 'failed',
        'verified_at': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'commit': commit,
        'working_tree_dirty': dirty,
        'template_sha256': hashlib.sha256((ROOT / 'infra/cloudfront.yaml').read_bytes()).hexdigest(),
        'checks': [],
    }
    report_path = evidence_dir / 'configuration-validation.json'
    # Replace any earlier success before starting a new attempt.
    report_path.write_text(json.dumps(report, indent=2) + '\n')
    log_path = evidence_dir / 'configuration-validation.log'
    with log_path.open('w') as log:
        for name, command in commands:
            heading = f'\n{name}: {shlex.join(command)}\n'
            print(heading, end='', flush=True)
            log.write(heading)
            try:
                result = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=300)
                code, output = result.returncode, result.stdout
            except (OSError, subprocess.TimeoutExpired) as error:
                code, output = 1, str(error) + '\n'
            print(output, end='', flush=True)
            log.write(output)
            report['checks'].append({'name': name, 'command': command, 'exit_code': code, 'status': 'passed' if code == 0 else 'failed'})
    passed = all(check['exit_code'] == 0 for check in report['checks'])
    report['status'] = 'passed' if passed else 'failed'
    report_path.write_text(json.dumps(report, indent=2) + '\n')
    summary = f"Configuración: {report['status']}. Informe: evidence/configuration-validation.json\n"
    summary += 'Alcance: validación local; no comprueba un servicio activo ni crea recursos AWS.\n'
    print(summary)
    if os.environ.get('GITHUB_STEP_SUMMARY'):
        with open(os.environ['GITHUB_STEP_SUMMARY'], 'a') as summary_file:
            summary_file.write('## Validación de la configuración CloudFront\n\n' + summary + '\n')
            summary_file.write('| Comprobación | Resultado |\n| --- | --- |\n')
            for check in report['checks']:
                summary_file.write(f"| {check['name']} | {check['status']} |\n")
    return 0 if passed else 1


if __name__ == '__main__':
    sys.exit(main())
