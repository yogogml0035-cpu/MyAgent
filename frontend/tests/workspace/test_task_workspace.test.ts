import { describe, it } from "node:test";
import assert from "node:assert";

void describe("use-task-workspace exports", () => {
  void it("should export useTaskWorkspace hook", async () => {
    const mod = await import("../../hooks/use-task-workspace");
    assert.strictEqual(typeof mod.useTaskWorkspace, "function");
  });

  void it("should expose bounded SSE retry helpers", async () => {
    const mod = await import("../../hooks/use-task-workspace");

    assert.strictEqual(mod.MAX_SSE_RETRIES, 5);
    assert.strictEqual(mod.calculateSseRetryDelay(0), 3000);
    assert.strictEqual(mod.calculateSseRetryDelay(1), 6000);
    assert.strictEqual(mod.calculateSseRetryDelay(4), 30000);
  });

  void it("should extract backend SSE error details", async () => {
    const mod = await import("../../hooks/use-task-workspace");

    assert.strictEqual(
      mod.getSseErrorDetail({ type: "error", detail: "流传输异常，请刷新页面。" }),
      "流传输异常，请刷新页面。",
    );
    assert.strictEqual(mod.getSseErrorDetail({ type: "done" }), "");
  });
});
