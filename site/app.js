"use strict";

const button = document.getElementById("verify");
const status = document.getElementById("status");
const fields = ["cache", "pop", "via", "age", "request", "deployment", "commit", "published"];

async function verifyDelivery() {
  button.disabled = true;
  status.textContent = "Consultando una respuesta del servidor…";
  status.dataset.state = "pending";
  fields.forEach((id) => { document.getElementById(id).textContent = "—"; });
  document.getElementById("domain").textContent = window.location.hostname;
  try {
    // Bypass only the browser cache: CloudFront can still serve its cached object.
    const response = await fetch("/deployment.json", { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    const deployment = await response.json();
    const headers = {
      cache: "x-cache", pop: "x-amz-cf-pop", via: "via",
      age: "age", request: "x-amz-cf-id"
    };
    Object.entries(headers).forEach(([id, header]) => {
      document.getElementById(id).textContent = response.headers.get(header) || "No recibido";
    });
    document.getElementById("deployment").textContent = deployment.deployment_id || "No recibido";
    document.getElementById("commit").textContent = deployment.commit || "No recibido";
    document.getElementById("published").textContent = deployment.published_at || "No recibido";
    const isCloudFront = response.headers.get("x-amz-cf-id") && response.headers.get("x-amz-cf-pop") && /cloudfront/i.test(response.headers.get("via") || "");
    status.dataset.state = isCloudFront ? "passed" : "failed";
    status.textContent = isCloudFront
      ? "Respuesta recibida a través de CloudFront. Consulta las cabeceras de esta petición."
      : "Se recibió el archivo, pero no se detectaron las cabeceras de CloudFront.";
  } catch (error) {
    status.dataset.state = "failed";
    status.textContent = `No se pudo comprobar el despliegue (${error.message}). deployment.json se genera al publicar en AWS.`;
  } finally {
    button.disabled = false;
  }
}

button.addEventListener("click", verifyDelivery);
verifyDelivery();
