import assert from "node:assert/strict";
import test from "node:test";

import { API_BASE_URL, requestJson } from "../lib/api.mjs";

test("requestJson explains when the local API cannot be reached", async () => {
  await assert.rejects(
    requestJson("/runs", undefined, async () => {
      throw new TypeError("fetch failed");
    }),
    new RegExp(`Cannot reach the local API at ${API_BASE_URL}`),
  );
});

test("requestJson surfaces FastAPI error details", async () => {
  await assert.rejects(
    requestJson(
      "/runs",
      undefined,
      async () => new Response(JSON.stringify({ detail: "source_pdf must be an existing PDF" }), { status: 400 }),
    ),
    /source_pdf must be an existing PDF/,
  );
});

test("requestJson returns successful JSON responses", async () => {
  const data = await requestJson(
    "/health",
    undefined,
    async () => Response.json({ status: "ok" }),
  );

  assert.deepEqual(data, { status: "ok" });
});
