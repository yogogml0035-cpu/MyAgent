import { describe, it } from "node:test";
import assert from "node:assert";

void describe("task-api exports", () => {
  void it("should export expected functions", async () => {
    const api = await import("../../lib/task-api");
    assert.strictEqual(typeof api.requestTaskJson, "function");
    assert.strictEqual(typeof api.fetchTask, "function");
    assert.strictEqual(typeof api.fetchTaskEvents, "function");
    assert.strictEqual(typeof api.createTask, "function");
    assert.strictEqual(typeof api.uploadTaskFiles, "function");
    assert.strictEqual(typeof api.fetchSkillOptions, "function");
    assert.strictEqual(typeof api.postTaskMessage, "function");
    assert.strictEqual(typeof api.cancelTask, "function");
    assert.strictEqual(typeof api.renameTask, "function");
    assert.strictEqual(typeof api.deleteTask, "function");
    assert.strictEqual(typeof api.fetchArtifactBlob, "function");
  });

  void it("should fetch browser-safe skill options through the shared request adapter", async () => {
    const api = await import("../../lib/task-api");
    const originalFetch = globalThis.fetch;

    globalThis.fetch = (async (input, init) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      const headers = init?.headers as Record<string, string>;

      assert.strictEqual(url.endsWith("/api/skills"), true);
      assert.strictEqual(headers["Content-Type"], "application/json");

      return new Response(
        JSON.stringify([
          {
            name: "web-research",
            description: "Search the web",
            path: "/private/path/SHOULD_NOT_RENDER",
          },
          { name: 42, description: "invalid" },
        ]),
        { status: 200 },
      );
    }) as typeof fetch;

    try {
      assert.deepStrictEqual(await api.fetchSkillOptions(), [
        {
          name: "web-research",
          description: "Search the web",
        },
      ]);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });

  void it("should post selected skill names without changing message payload fields", async () => {
    const api = await import("../../lib/task-api");
    const originalFetch = globalThis.fetch;
    let requestBody = "";

    globalThis.fetch = (async (input, init) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.toString() : input.url;
      const headers = init?.headers as Record<string, string>;

      assert.strictEqual(url.endsWith("/api/tasks/task-1/messages"), true);
      assert.strictEqual(headers["Content-Type"], "application/json");
      requestBody = String(init?.body ?? "");

      return new Response(JSON.stringify({}), { status: 200 });
    }) as typeof fetch;

    try {
      await api.postTaskMessage("task-1", "hello", "deepseek-v4-flash", [
        "web-research",
        "code-review",
      ]);
    } finally {
      globalThis.fetch = originalFetch;
    }

    assert.deepStrictEqual(JSON.parse(requestBody), {
      content: "hello",
      message: "hello",
      model: "deepseek-v4-flash",
      mode: "auto",
      skills: ["web-research", "code-review"],
    });
  });
});
