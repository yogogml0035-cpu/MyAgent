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
    assert.strictEqual(typeof api.postTaskMessage, "function");
    assert.strictEqual(typeof api.cancelTask, "function");
    assert.strictEqual(typeof api.fetchArtifactBlob, "function");
  });
});
