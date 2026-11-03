#!/usr/bin/env bash
set -euo pipefail
export AWS_PAGER=""
export AWS_EC2_METADATA_DISABLED="${AWS_EC2_METADATA_DISABLED:-true}"

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
AWS_REGION=${AWS_REGION:-us-east-1}
STACK_NAME=${STACK_NAME:-amazon-cloudfront-demo}
export AWS_REGION

for tool in aws python3; do
  command -v "$tool" >/dev/null || { echo "Falta $tool. Consulta README.md." >&2; exit 1; }
done
if [[ ! "$STACK_NAME" =~ ^[a-zA-Z][a-zA-Z0-9-]{0,39}$ ]]; then
  echo "STACK_NAME debe comenzar con una letra y tener hasta 40 caracteres alfanuméricos o guiones." >&2
  exit 1
fi

echo "Comprobando la identidad AWS antes de crear recursos…"
aws sts get-caller-identity --region "$AWS_REGION" --query '{Account:Account,Arn:Arn}' --output json
echo "Desplegando $STACK_NAME en $AWS_REGION. Esta operación puede generar cargos AWS."
aws cloudformation deploy \
  --template-file "$ROOT/infra/cloudfront.yaml" \
  --stack-name "$STACK_NAME" --region "$AWS_REGION" \
  --no-fail-on-empty-changeset --tags Project=amazon-cloudfront-demo

mkdir -p "$ROOT/evidence"
# Remove old successful evidence before attempting a new publication.
rm -f "$ROOT/evidence/verification.json"
TEMP_DIR=$(mktemp -d)
trap 'rm -rf -- "$TEMP_DIR"' EXIT
aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$AWS_REGION" \
  --query 'Stacks[0].Outputs' --output json > "$TEMP_DIR/stack-outputs.json"
python3 - "$TEMP_DIR/stack-outputs.json" "$TEMP_DIR/outputs.json" <<'PY'
import json
import sys
from pathlib import Path
outputs = {item['OutputKey']: item['OutputValue'] for item in json.loads(Path(sys.argv[1]).read_text())}
for key in ('BucketName', 'DistributionId', 'DistributionUrl', 'OriginUrl'):
    if not outputs.get(key):
        raise SystemExit(f'Falta el output {key} en el stack.')
Path(sys.argv[2]).write_text(json.dumps(outputs, indent=2) + '\n')
PY
cp "$TEMP_DIR/outputs.json" "$ROOT/evidence/outputs.json"
BUCKET_NAME=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["BucketName"])' "$TEMP_DIR/outputs.json")
DISTRIBUTION_ID=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["DistributionId"])' "$TEMP_DIR/outputs.json")
cp -R "$ROOT/site" "$TEMP_DIR/site"
python3 - "$ROOT" "$TEMP_DIR/site/deployment.json" <<'PY'
import datetime
import json
import subprocess
import sys
import uuid
from pathlib import Path
root = Path(sys.argv[1])
commit = 'unavailable'
dirty = None
if (root / '.git').exists():
    commit = subprocess.check_output(['git', '-C', str(root), 'rev-parse', 'HEAD'], text=True).strip()
    dirty = bool(subprocess.check_output(['git', '-C', str(root), 'status', '--porcelain'], text=True).strip())
metadata = {'deployment_id': str(uuid.uuid4()), 'published_at': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'commit': commit, 'working_tree_dirty': dirty}
Path(sys.argv[2]).write_text(json.dumps(metadata, indent=2) + '\n')
PY
# This bucket belongs to the stack. Keep metadata explicit even for unchanged files.
aws s3 cp "$TEMP_DIR/site/" "s3://$BUCKET_NAME/" --recursive \
  --region "$AWS_REGION" --cache-control 'public,max-age=60' --only-show-errors
INVALIDATION_ID=$(aws cloudfront create-invalidation --distribution-id "$DISTRIBUTION_ID" \
  --paths '/*' --query 'Invalidation.Id' --output text --region "$AWS_REGION")
echo "Esperando propagación de CloudFront e invalidación $INVALIDATION_ID…"
aws cloudfront wait distribution-deployed --id "$DISTRIBUTION_ID" --region "$AWS_REGION"
aws cloudfront wait invalidation-completed --distribution-id "$DISTRIBUTION_ID" \
  --id "$INVALIDATION_ID" --region "$AWS_REGION"

DEPLOYMENT_ID=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["deployment_id"])' "$TEMP_DIR/site/deployment.json")
python3 "$ROOT/scripts/verify.py" --outputs "$ROOT/evidence/outputs.json" \
  --expected-deployment-id "$DEPLOYMENT_ID" --output "$ROOT/evidence/verification.json"
python3 - "$ROOT/evidence/outputs.json" <<'PY'
import json
import sys
print('Despliegue verificado: ' + json.load(open(sys.argv[1]))['DistributionUrl'])
print('Evidencias: evidence/outputs.json y evidence/verification.json')
PY
