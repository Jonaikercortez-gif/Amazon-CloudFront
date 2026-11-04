#!/usr/bin/env bash
set -euo pipefail
export AWS_PAGER=""
export AWS_EC2_METADATA_DISABLED="${AWS_EC2_METADATA_DISABLED:-true}"
export TF_IN_AUTOMATION=true
export TF_INPUT=false

ROOT=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
AWS_REGION=${AWS_REGION:-us-east-1}
PROJECT_NAME=${PROJECT_NAME:-amazon-cloudfront-tf}
export AWS_REGION PROJECT_NAME

for tool in aws python3 terraform; do
  command -v "$tool" >/dev/null || { echo "Falta $tool. Consulta README.md." >&2; exit 1; }
done

echo "Comprobando la identidad AWS antes de crear recursos…"
aws sts get-caller-identity --region "$AWS_REGION" --query '{Account:Account,Arn:Arn}' --output json
mkdir -p "$ROOT/evidence"
rm -f "$ROOT/evidence/verification.json"
python3 "$ROOT/scripts/prepare_release.py"

terraform -chdir="$ROOT/infra/terraform" init -input=false -lockfile=readonly -no-color
terraform -chdir="$ROOT/infra/terraform" plan -input=false -no-color \
  -var-file="$ROOT/evidence/release.tfvars.json" \
  -out="$ROOT/evidence/deployment.tfplan"

echo "Aplicando el plan de Terraform. Esta operación puede generar cargos AWS."
terraform -chdir="$ROOT/infra/terraform" apply -input=false -no-color "$ROOT/evidence/deployment.tfplan"
terraform -chdir="$ROOT/infra/terraform" output -json site_outputs > "$ROOT/evidence/outputs.json"

DISTRIBUTION_ID=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["DistributionId"])' "$ROOT/evidence/outputs.json")
INVALIDATION_ID=$(aws cloudfront create-invalidation --distribution-id "$DISTRIBUTION_ID" \
  --paths '/*' --query 'Invalidation.Id' --output text --region "$AWS_REGION")
echo "Esperando invalidación $INVALIDATION_ID…"
aws cloudfront wait invalidation-completed --distribution-id "$DISTRIBUTION_ID" \
  --id "$INVALIDATION_ID" --region "$AWS_REGION"

DEPLOYMENT_ID=$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1]))["deployment_id"])' "$ROOT/evidence/release.tfvars.json")
python3 "$ROOT/scripts/verify.py" --outputs "$ROOT/evidence/outputs.json" \
  --expected-deployment-id "$DEPLOYMENT_ID" --output "$ROOT/evidence/verification.json"
python3 - "$ROOT/evidence/outputs.json" <<'PY'
import json
import sys
print('Despliegue verificado: ' + json.load(open(sys.argv[1]))['DistributionUrl'])
print('Evidencias: evidence/outputs.json y evidence/verification.json')
PY
