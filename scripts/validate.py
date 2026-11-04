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
    terraform = shutil.which('terraform') or str(ROOT.parent / '.terraform-tools/bin/terraform')
    terraform_command = [terraform, '-chdir=infra/terraform']
    commands = [
        ('Terraform format', terraform_command + ['fmt', '-check', '-recursive']),
        ('Terraform provider initialization', terraform_command + ['init', '-backend=false', '-input=false', '-lockfile=readonly', '-no-color']),
        ('Terraform configuration validation', terraform_command + ['validate', '-no-color']),
        ('Terraform mocked AWS plan tests', terraform_command + ['test', '-no-color']),
        ('Deployment script syntax', ['bash', '-n', 'scripts/deploy.sh']),
        ('Browser script syntax', ['node', '--check', 'site/app.js']),
        ('HTTP verifier tests', [sys.executable, '-m', 'unittest', 'discover', '-s', 'tests', '-v']),
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
        'infrastructure_tool': 'Terraform',
        'terraform_file_sha256': {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
                                 for path in sorted((ROOT / 'infra/terraform').rglob('*'))
                                 if '.terraform' not in path.parts and path.is_file()
                                 and (path.suffix in ('.tf', '.hcl') or path.name == '.terraform.lock.hcl')},
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
                result = subprocess.run(command, cwd=ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, timeout=600)
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
