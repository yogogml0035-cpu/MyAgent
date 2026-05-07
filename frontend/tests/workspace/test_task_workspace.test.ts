import { describe, it } from "node:test";
import assert from "node:assert";

void describe("use-task-workspace exports", () => {
  void it("should export useTaskWorkspace hook", async () => {
    const mod = await import("../../hooks/use-task-workspace");
    assert.strictEqual(typeof mod.useTaskWorkspace, "function");
  });
});
