# Despliegue de CloudFront con Terraform

Esta guía crea recursos reales: un bucket S3 privado, una distribución CloudFront con OAC, sus políticas y los objetos del sitio. Puede generar cargos. La validación sin crear recursos está explicada en el [README](../README.md).

## Requisitos

- Terraform **1.17.1**, Python 3 y AWS CLI.
- Una cuenta AWS habilitada y credenciales disponibles mediante una sesión o perfil autorizado.
- Permisos para crear y administrar S3, CloudFront, OAC y políticas. No se crean roles ni usuarios IAM.
- Acceso de descarga a `registry.terraform.io` y `releases.hashicorp.com`.

No guardes claves en los archivos `.tf`, en Git ni en capturas. Puedes comprobar la sesión con `aws sts get-caller-identity`. Si CloudShell o CloudFront siguen restringidos por la verificación de una cuenta nueva, Terraform también puede encontrar ese bloqueo.

## Preparar el proyecto

```bash
git clone https://github.com/Jonaikercortez-gif/Amazon-CloudFront.git
cd Amazon-CloudFront
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements-dev.txt
terraform version
```

Instala la versión indicada de Terraform con la [guía oficial](https://developer.hashicorp.com/terraform/install). Si ya tienes un checkout, actualízalo sin descartar tus cambios locales.

## Crear o actualizar el sitio

Desde la raíz del proyecto:

```bash
bash scripts/deploy.sh
```

Valores predeterminados: región `us-east-1`, proyecto `amazon-cloudfront-tf`, `PriceClass_100` y caché de 60 segundos. El bucket recibe un sufijo único.

Para elegir otra región o nombre:

```bash
AWS_REGION=us-east-1 PROJECT_NAME=mi-cloudfront-tf bash scripts/deploy.sh
```

El script realiza estas operaciones:

1. Comprueba la identidad AWS.
2. Genera `evidence/release.tfvars.json` con la región, el proyecto, el commit, la fecha UTC y un identificador de publicación.
3. Inicializa Terraform y guarda un plan en `evidence/deployment.tfplan`.
4. Aplica ese plan y publica el contenido de `site/` y `deployment.json` mediante recursos `aws_s3_object`.
5. Espera la invalidación de caché y comprueba el sitio real.

El comando termina correctamente solo si la infraestructura y la verificación final funcionan. La propagación de CloudFront puede tardar varios minutos.

## Revisar el plan antes de aplicar manualmente

También puedes separar los pasos y revisar el plan:

```bash
python3 scripts/prepare_release.py
terraform -chdir=infra/terraform init -input=false -lockfile=readonly
terraform -chdir=infra/terraform plan -var-file=../../evidence/release.tfvars.json -out=../../evidence/deployment.tfplan
terraform -chdir=infra/terraform show ../../evidence/deployment.tfplan
```

Cuando hayas revisado el plan, puedes ejecutarlo con:

```bash
terraform -chdir=infra/terraform apply ../../evidence/deployment.tfplan
terraform -chdir=infra/terraform output -json site_outputs > evidence/outputs.json
```

En actualizaciones de un sitio existente, el script de despliegue también invalida la caché para comprobar el contenido nuevo.

## Estado de Terraform

Al ejecutar desde un equipo, Terraform usa un estado local en `infra/terraform/terraform.tfstate`. Consérvalo junto con el archivo de variables de tu despliegue; ambos están excluidos de Git. No publiques estados ni planes como evidencia del trabajo.

Usa el mismo estado para volver a desplegar o eliminar los recursos. Un clon nuevo sin ese estado no conoce lo que ya creaste y puede intentar crear recursos adicionales.

Terraform puede dejar recursos creados y registrados en el estado si un `apply` falla a mitad del proceso. Conserva ese estado y revisa el error antes de repetir o limpiar.

## Evidencias del uso real

Al finalizar el script se guardan:

- `evidence/outputs.json`: dominio, identificador de distribución y origen S3.
- `evidence/verification.json`: resultados y cabeceras HTTP reales.

Para el documento puedes capturar:

1. La distribución habilitada en CloudFront, con el despliegue completado, su dominio y origen.
2. La página abierta desde la URL `https://….cloudfront.net`.
3. Las cabeceras `X-Cache`, `Via`, `X-Amz-Cf-Pop` y `X-Amz-Cf-Id` de una petición real.
4. El informe con `status: passed`, acierto de caché y HTTP 403 al solicitar directamente el objeto de S3.

Para repetir la comprobación sin crear recursos nuevos:

```bash
python3 scripts/verify.py --outputs evidence/outputs.json --output evidence/verification.json
```

## Desplegar desde GitHub Actions (opcional)

El workflow **Deploy CloudFront** se ejecuta manualmente sobre `main`. Autentica mediante OIDC y exige guardar el estado en un bucket S3 existente, separado del bucket del sitio.

En el environment `aws-demo` configura estas variables:

| Variable | Valor |
| --- | --- |
| `AWS_ROLE_ARN` | Rol AWS autorizado para el despliegue mediante OIDC. |
| `AWS_REGION` | Región del sitio; predeterminado `us-east-1`. |
| `PROJECT_NAME` | Nombre del proyecto; predeterminado `amazon-cloudfront-tf`. |
| `TF_STATE_BUCKET` | Bucket existente donde conservar el estado. Obligatorio. |
| `TF_STATE_KEY` | Ruta del estado; predeterminado `amazon-cloudfront-tf/terraform.tfstate`. |
| `TF_STATE_REGION` | Región del bucket de estado; usa `AWS_REGION` si se omite. |

El bucket de estado debe ser privado, con cifrado y versionado habilitados. El rol necesita permisos sobre el estado y su archivo de bloqueo. El backend utiliza `use_lockfile = true` para coordinar las operaciones.

Un administrador debe configurar el proveedor OIDC `token.actions.githubusercontent.com`, audiencia `sts.amazonaws.com`, y restringir la confianza del rol al subject `repo:Jonaikercortez-gif/Amazon-CloudFront:environment:aws-demo`. Limita los branches del environment a `main`.

El workflow genera un archivo ignorado `infra/terraform/backend.auto.tf.json` con la configuración del backend. Si vas a administrar esos mismos recursos desde otro equipo, configura ese mismo backend antes de inicializar Terraform. No uses un estado local nuevo para gestionar los recursos de GitHub Actions.

Solo se publican como artefactos los outputs y la verificación HTTP; el estado y el plan no se suben como artefactos.

## Limpiar los recursos

Cuando ya no necesites el sitio, desde el mismo checkout y con el mismo estado o backend del despliegue:

```bash
terraform -chdir=infra/terraform plan -destroy -var-file=../../evidence/release.tfvars.json
terraform -chdir=infra/terraform destroy -var-file=../../evidence/release.tfvars.json
```

Revisa el plan de destrucción antes de confirmar. Esto elimina los objetos administrados, la distribución y el bucket del sitio. El bucket no tiene `force_destroy` activado: si agregaste otros archivos fuera de Terraform, revisa su contenido antes de retirarlos.

No elimines el bucket del estado hasta haber terminado la limpieza y conservado el registro necesario.

## Pila anterior de CloudFormation

La plantilla `infra/cloudfront.yaml` se conserva como referencia. Terraform crea recursos nuevos con otro nombre de proyecto y no importa ni elimina automáticamente una pila anterior.

Si el intento de CloudFormation quedó en `ROLLBACK_COMPLETE`, revisa las pestañas Recursos y Eventos para comprobar qué quedó. No administres un mismo recurso con CloudFormation y Terraform simultáneamente. Esta guía no realiza una migración de recursos existentes.
