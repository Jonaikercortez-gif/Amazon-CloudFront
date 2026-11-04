# Despliegue opcional en AWS

Esta guía permite probar una distribución real de CloudFront. Para la explicación de la práctica y la validación de la configuración, consulta el [README](../README.md).

Ejecuta los comandos desde la raíz del repositorio. Crear recursos en AWS puede generar cargos.

## Desplegar desde AWS CloudShell (opcional)

Abre **AWS CloudShell** en una cuenta que permita crear recursos. Tiene AWS CLI, Python y credenciales de tu sesión. Una cuenta de AWS Academy/Learner Lab puede restringir CloudFront; el laboratorio debe estar activo y sus permisos deben permitir este servicio.

```bash
git clone https://github.com/Jonaikercortez-gif/Amazon-CloudFront.git
cd Amazon-CloudFront
bash scripts/deploy.sh
```

Los archivos están en la rama `main`. También se puede ejecutar el script en un equipo con AWS CLI autenticado. Para un checkout existente, actualízalo sin descartar cambios propios. No guardes credenciales en el repositorio.

Valores predeterminados: región `us-east-1`, stack `amazon-cloudfront-demo`, `PriceClass_100`. Para cambiarlos:

```bash
AWS_REGION=us-east-1 STACK_NAME=mi-demo-cloudfront bash scripts/deploy.sh
```

Se necesitan permisos de CloudFormation (crear/actualizar/describir stacks y change sets), S3 (crear/configurar el bucket y publicar objetos), y CloudFront (distribución, OAC, políticas e invalidaciones), además de `sts:GetCallerIdentity`. No se crean usuarios ni roles IAM. El despliegue puede tardar varios minutos y **puede generar cargos AWS** por recursos, solicitudes y transferencia. `PriceClass_100` limita las ubicaciones utilizadas; no garantiza coste cero.

Al terminar, el script imprime una URL real `https://….cloudfront.net`, y guarda:

- `evidence/outputs.json`: identificadores y endpoints del stack.
- `evidence/verification.json`: resultado de las comprobaciones, fecha UTC, identificador de despliegue y cabeceras recibidas.

El directorio `evidence/` se ignora en Git. Revisa sus identificadores antes de compartirlo. Cada despliegue actualiza estos archivos; conserva una copia si necesitas evidencias de una ejecución anterior.

## Evidencias del servicio activo en AWS (opcional)

1. Abre la URL impresa y captura la página con su dominio y el panel de comprobación.
2. En **CloudFront → Distributions**, captura la distribución con estado `Deployed`, su dominio, origen S3 y OAC.
3. En las herramientas de desarrollo del navegador, captura una respuesta con `X-Cache`, `Via`, `X-Amz-Cf-Pop` y `X-Amz-Cf-Id`. Tras repetir la petición al mismo punto de presencia, el verificador exige `Hit from cloudfront`.
4. Adjunta `verification.json`: debe indicar `status: passed`, redirección HTTP a HTTPS, contenido esperado y acceso directo al objeto de S3 con HTTP 403. El informe vincula la comprobación con el identificador del despliegue y el commit local, cuando existe.

Para repetir la verificación sin desplegar:

```bash
python3 scripts/verify.py --outputs evidence/outputs.json --output evidence/verification.json
```

Si falla, el comando termina con código distinto de cero. No presentes una validación local ni un workflow de lint como evidencia de un despliegue AWS.

## Despliegue desde GitHub Actions (opcional)

El workflow **Deploy CloudFront** se ejecuta manualmente (`workflow_dispatch`) y guarda las evidencias como artefacto. No despliega en cada push.

En GitHub, crea el environment `aws-demo` y estas **variables**, sin claves estáticas:

| Variable | Valor |
| --- | --- |
| `AWS_ROLE_ARN` | ARN de un rol de tu cuenta con los permisos descritos arriba |
| `AWS_REGION` | `us-east-1`, u otra región admitida |
| `STACK_NAME` | `amazon-cloudfront-demo`, o tu nombre elegido |

Un administrador de la cuenta debe configurar el proveedor OIDC `token.actions.githubusercontent.com` (audiencia `sts.amazonaws.com`) y permitir `sts:AssumeRoleWithWebIdentity` al rol. En la relación de confianza, restringe `aud` a `sts.amazonaws.com` y `sub` exactamente a `repo:Jonaikercortez-gif/Amazon-CloudFront:environment:aws-demo`. Limita los branches permitidos en el environment a `main`. El workflow no crea esta confianza ni puede concederse permisos a sí mismo. Si tu laboratorio no permite roles OIDC, usa CloudShell con su sesión temporal.

## Eliminar los recursos de la demostración

Cuando termines, consulta los outputs del stack elegido y comprueba que corresponden a esta demostración. Los comandos siguientes **borran el contenido de ese bucket y el stack**. Ejecuta la limpieza solo cuando ya no necesites el sitio ni sus archivos:

```bash
export AWS_REGION=us-east-1
export STACK_NAME=amazon-cloudfront-demo
BUCKET_NAME=$(aws cloudformation describe-stacks --stack-name "$STACK_NAME" --region "$AWS_REGION" --query 'Stacks[0].Outputs[?OutputKey==`BucketName`].OutputValue | [0]' --output text)
test -n "$BUCKET_NAME" && test "$BUCKET_NAME" != None && aws s3 rm "s3://$BUCKET_NAME/" --recursive --region "$AWS_REGION"
aws cloudformation delete-stack --stack-name "$STACK_NAME" --region "$AWS_REGION"
aws cloudformation wait stack-delete-complete --stack-name "$STACK_NAME" --region "$AWS_REGION"
```

CloudFormation elimina también la distribución; la operación puede tardar. Confirma `DELETE_COMPLETE` o la desaparición del stack y comprueba que no queden recursos de la demo en la cuenta.
