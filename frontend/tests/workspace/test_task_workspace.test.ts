import { describe, it } from "node:test";
import assert from "node:assert";
import { readFileSync } from "node:fs";

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

  void it("should merge context and memory diagnostics from SSE", async () => {
    const mod = await import("../../hooks/use-task-workspace");

    assert.strictEqual(mod.TASK_WORKSPACE_STREAM_EVENT_TYPES.has("context_loaded"), true);
    assert.strictEqual(mod.TASK_WORKSPACE_STREAM_EVENT_TYPES.has("memory_recalled"), true);
  });

  void it("should extract backend SSE error details", async () => {
    const mod = await import("../../hooks/use-task-workspace");

    assert.strictEqual(
      mod.getSseErrorDetail({ type: "error", detail: "流传输异常，请刷新页面。" }),
      "流传输异常，请刷新页面。",
    );
    assert.strictEqual(mod.getSseErrorDetail({ type: "done" }), "");
  });

  void it("should build HTML artifact previews with a script-disabled sandbox iframe", async () => {
    const mod = await import("../../hooks/use-task-workspace");
    const html = mod.buildSandboxedArtifactPreviewDocument(
      'report"><script>alert(1)</script>.html',
      "blob:http://localhost:3001/safe-preview",
    );

    assert.match(html, /<iframe[^>]+sandbox=""/);
    assert.match(html, /referrerpolicy="no-referrer"/);
    assert.match(html, /src="blob:http:\/\/localhost:3001\/safe-preview"/);
    assert.match(html, /report&quot;&gt;&lt;script&gt;alert\(1\)&lt;\/script&gt;.html/);
    assert.doesNotMatch(html, /<script/i);
  });

  void it("should not top-level navigate opened artifact windows to blob URLs", () => {
    const source = readFileSync(
      new URL("../../hooks/use-task-workspace.ts", import.meta.url),
      "utf-8",
    );

    assert.strictEqual(source.includes("location.replace(objectUrl)"), false);
    assert.strictEqual(source.includes("buildSandboxedArtifactPreviewDocument"), true);
    assert.strictEqual(source.includes("artifactWindow.document.write"), true);
  });

  void it("should block unavailable models before creating tasks or uploading files", () => {
    const source = readFileSync(
      new URL("../../hooks/use-task-workspace.ts", import.meta.url),
      "utf-8",
    );

    assert.strictEqual(source.includes("selectedModelRunnable"), true);
    assert.strictEqual(source.includes('const DEFAULT_MODEL_ID = "deepseek:deepseek-chat";'), true);
    assert.strictEqual(source.includes("当前模型服务未配置，请先在后端配置对应 API Key 后再发送。"), true);
    assert.ok(source.indexOf("if (!selectedModelRunnable)") < source.indexOf("setIsBusy(true)"));
    assert.ok(source.indexOf("if (!selectedModelRunnable)") < source.indexOf("ensureTask()"));
  });

  void it("should keep the model picker UI and expose only DeepSeek chat/reasoner options", () => {
    const source = readFileSync(
      new URL("../../components/chat/ChatComposer.tsx", import.meta.url),
      "utf-8",
    );
    const workspaceSource = readFileSync(
      new URL("../../hooks/use-task-workspace.ts", import.meta.url),
      "utf-8",
    );

    assert.strictEqual(source.includes("modelPicker"), true);
    assert.strictEqual(source.includes("aria-haspopup=\"listbox\""), true);
    assert.strictEqual(source.includes("onModelChange"), true);
    assert.strictEqual(workspaceSource.includes("const ALLOWED_MODEL_IDS = new Set(["), true);
    assert.strictEqual(workspaceSource.includes('"deepseek:deepseek-chat"'), true);
    assert.strictEqual(workspaceSource.includes('"deepseek:deepseek-reasoner"'), true);
    assert.strictEqual(workspaceSource.includes("options.filter((option) => ALLOWED_MODEL_IDS.has(option.id))"), true);
    assert.strictEqual(source.includes("!selectedModelRunnable"), true);
  });
});
