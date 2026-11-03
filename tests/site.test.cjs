// Browser fixtures only: these tests do not claim an AWS deployment exists.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const code = fs.readFileSync(path.join(__dirname, "../site/app.js"), "utf8");

async function render(fetch) {
  const elements = new Map();
  const document = { getElementById(id) {
    if (!elements.has(id)) elements.set(id, { textContent: "old-value", dataset: {}, addEventListener() {} });
    return elements.get(id);
  } };
  vm.runInNewContext(code, { document, window: { location: { hostname: "fixture.cloudfront.net" } }, fetch });
  await new Promise(setImmediate);
  return elements;
}

function response(headers) {
  return { ok: true, headers: new Map(Object.entries(headers)), json: async () => ({
    deployment_id: "fixture-deployment", commit: "fixture-commit", published_at: "fixture-time"
  }) };
}

test("shows received CloudFront headers and deployment metadata", async () => {
  const elements = await render(async () => response({
    "x-amz-cf-id": "fixture-request", "x-amz-cf-pop": "TEST1", "via": "1.1 fixture (CloudFront)",
    "x-cache": "Hit from cloudfront", "age": "3"
  }));
  assert.equal(elements.get("status").dataset.state, "passed");
  assert.equal(elements.get("cache").textContent, "Hit from cloudfront");
  assert.equal(elements.get("deployment").textContent, "fixture-deployment");
  assert.equal(elements.get("verify").disabled, false);
});

test("does not identify a local response as CloudFront", async () => {
  const elements = await render(async () => response({}));
  assert.equal(elements.get("status").dataset.state, "failed");
  assert.equal(elements.get("pop").textContent, "No recibido");
});

test("missing deployment metadata produces an explicit failure and clears old evidence", async () => {
  const elements = await render(async () => ({ ok: false, status: 404 }));
  assert.equal(elements.get("status").dataset.state, "failed");
  assert.match(elements.get("status").textContent, /HTTP 404/);
  assert.equal(elements.get("cache").textContent, "—");
  assert.equal(elements.get("verify").disabled, false);
});

test("network errors do not leave a success indicator", async () => {
  const elements = await render(async () => { throw new Error("network unavailable"); });
  assert.equal(elements.get("status").dataset.state, "failed");
  assert.match(elements.get("status").textContent, /network unavailable/);
});
