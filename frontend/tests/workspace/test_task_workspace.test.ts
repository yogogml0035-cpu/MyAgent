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

  void it("should generate run-scoped log download filenames without absolute paths", async () => {
    const mod = await import("../../hooks/use-task-workspace");

    assert.strictEqual(mod.buildRunLogDownloadName("run-42"), "run-42-logs.jsonl");
    assert.strictEqual(mod.buildRunLogDownloadName(" run 42 / debug "), "run-42-debug-logs.jsonl");
    assert.strictEqual(mod.buildRunLogDownloadName(""), "run-logs.jsonl");
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
    assert.strictEqual(source.includes('const DEFAULT_MODEL_ID = "deepseek-v4-flash";'), true);
    assert.strictEqual(source.includes("当前模型服务未配置，请先在后端配置对应 API Key 后再发送。"), true);
    assert.ok(
      source.indexOf("if (!selectedModelRunnable)") < source.indexOf("setIsSubmittingTask(true)"),
    );
    assert.ok(source.indexOf("if (!selectedModelRunnable)") < source.indexOf("ensureTask()"));
  });

  void it("should keep the model picker UI and expose only DeepSeek V4 Flash options", () => {
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
    assert.strictEqual(workspaceSource.includes('"deepseek-v4-flash"'), true);
    assert.strictEqual(workspaceSource.includes('"deepseek-v4-flash-thinking"'), true);
    assert.strictEqual(workspaceSource.includes("options.filter((option) => ALLOWED_MODEL_IDS.has(option.id))"), true);
    assert.strictEqual(source.includes("!selectedModelRunnable"), true);
  });

  void it("should load skill options without blocking existing workspace initialization", () => {
    const source = readFileSync(
      new URL("../../hooks/use-task-workspace.ts", import.meta.url),
      "utf-8",
    );

    assert.strictEqual(source.includes("fetchModelOptions(DEFAULT_MODEL_OPTIONS)"), true);
    assert.strictEqual(source.includes("refreshTaskSummaries().catch"), true);
    assert.strictEqual(source.includes("fetchSkillOptions()"), true);
    assert.strictEqual(source.includes("setSkillOptions(options)"), true);
    assert.strictEqual(source.includes("Skill 列表加载失败："), true);
    assert.ok(source.indexOf("fetchSkillOptions()") > source.indexOf("refreshTaskSummaries().catch"));
  });

  void it("should pass selected skill names with messages and clear them only after success", () => {
    const source = readFileSync(
      new URL("../../hooks/use-task-workspace.ts", import.meta.url),
      "utf-8",
    );
    const submitStart = source.indexOf("const handleSubmit = useCallback");
    const submitEnd = source.indexOf("const handleSelectSkill = useCallback");
    const submitSource = source.slice(submitStart, submitEnd);
    const trySource = submitSource.slice(
      submitSource.indexOf("try {"),
      submitSource.indexOf("} catch (caught)"),
    );
    const catchSource = submitSource.slice(submitSource.indexOf("} catch (caught)"));

    assert.strictEqual(source.includes("const [selectedSkills, setSelectedSkills]"), true);
    assert.strictEqual(source.includes("const selectedSkillNames = useMemo"), true);
    assert.strictEqual(
      submitSource.includes("postTaskMessage(id, taskContent, model, selectedSkillNames)"),
      true,
    );
    assert.ok(trySource.indexOf("postTaskMessage") < trySource.indexOf("setSelectedSkills([])"));
    assert.strictEqual(catchSource.includes("setSelectedSkills([])"), false);
  });

  void it("should expose skill state and handlers across the workspace source boundary", () => {
    const hookSource = readFileSync(
      new URL("../../hooks/use-task-workspace.ts", import.meta.url),
      "utf-8",
    );
    const workspaceSource = readFileSync(
      new URL("../../components/chat/TaskWorkspace.tsx", import.meta.url),
      "utf-8",
    );
    const composerSource = readFileSync(
      new URL("../../components/chat/ChatComposer.tsx", import.meta.url),
      "utf-8",
    );

    assert.strictEqual(hookSource.includes("handleSelectSkill"), true);
    assert.strictEqual(hookSource.includes("handleRemoveSkill"), true);
    assert.strictEqual(
      hookSource.includes("activeTask || isSubmittingTask || isSwitchingConversation"),
      true,
    );
    assert.strictEqual(workspaceSource.includes("skillOptions={workspace.skillOptions}"), true);
    assert.strictEqual(workspaceSource.includes("selectedSkills={workspace.selectedSkills}"), true);
    assert.strictEqual(workspaceSource.includes("isComposerBusy={workspace.isComposerBusy}"), true);
    assert.strictEqual(workspaceSource.includes("currentTaskActive={workspace.currentTaskActive}"), true);
    assert.strictEqual(workspaceSource.includes("onSelectSkill={workspace.handleSelectSkill}"), true);
    assert.strictEqual(workspaceSource.includes("onRemoveSkill={workspace.handleRemoveSkill}"), true);
    assert.strictEqual(composerSource.includes("skillOptions: SkillOption[]"), true);
    assert.strictEqual(composerSource.includes("selectedSkills: SkillOption[]"), true);
    assert.strictEqual(composerSource.includes("currentTaskActive: boolean;"), true);
    assert.strictEqual(composerSource.includes("isComposerBusy: boolean;"), true);
    assert.strictEqual(composerSource.includes("onSelectSkill: (skill: SkillOption) => void"), true);
    assert.strictEqual(composerSource.includes("onRemoveSkill: (skillName: string) => void"), true);
  });

  void it("should scope busy state to current submission and conversation-history mutations", () => {
    const hookSource = readFileSync(
      new URL("../../hooks/use-task-workspace.ts", import.meta.url),
      "utf-8",
    );
    const workspaceSource = readFileSync(
      new URL("../../components/chat/TaskWorkspace.tsx", import.meta.url),
      "utf-8",
    );
    const sidebarSource = readFileSync(
      new URL("../../components/chat/ChatSidebar.tsx", import.meta.url),
      "utf-8",
    );
    const composerSource = readFileSync(
      new URL("../../components/chat/ChatComposer.tsx", import.meta.url),
      "utf-8",
    );

    assert.strictEqual(hookSource.includes("const [isSubmittingTask, setIsSubmittingTask]"), true);
    assert.strictEqual(
      hookSource.includes("const [isSwitchingConversation, setIsSwitchingConversation]"),
      true,
    );
    assert.strictEqual(
      hookSource.includes("const [isMutatingConversation, setIsMutatingConversation]"),
      true,
    );
    assert.strictEqual(hookSource.includes("const [isStoppingTask, setIsStoppingTask]"), true);
    assert.strictEqual(
      hookSource.includes(
        "const isComposerBusy = isSubmittingTask || isSwitchingConversation || isStoppingTask;",
      ),
      true,
    );
    assert.strictEqual(hookSource.includes("const isHistoryBusy ="), true);
    assert.strictEqual(
      hookSource.includes("if (!canSend || activeTask || isSubmittingTask || isSwitchingConversation)"),
      true,
    );
    assert.strictEqual(
      hookSource.includes(
        "isSubmittingTask ||\n        isSwitchingConversation ||\n        isMutatingConversation ||\n        isStoppingTask",
      ),
      true,
    );
    assert.strictEqual(workspaceSource.includes("isHistoryBusy={workspace.isHistoryBusy}"), true);
    assert.strictEqual(sidebarSource.includes("isHistoryBusy: boolean;"), true);
    assert.strictEqual(composerSource.includes("disabled={!canSend || isComposerBusy || !selectedModelRunnable}"), true);
    assert.strictEqual(
      composerSource.includes("const skillPickerEnabled = !currentTaskActive && !isComposerBusy"),
      true,
    );
  });

  void it("should scope composer placeholder and stop affordance to the selected conversation", () => {
    const hookSource = readFileSync(
      new URL("../../hooks/use-task-workspace.ts", import.meta.url),
      "utf-8",
    );
    const workspaceSource = readFileSync(
      new URL("../../components/chat/TaskWorkspace.tsx", import.meta.url),
      "utf-8",
    );
    const composerSource = readFileSync(
      new URL("../../components/chat/ChatComposer.tsx", import.meta.url),
      "utf-8",
    );

    assert.strictEqual(
      hookSource.includes("const targetSummary = taskSummaries.find((summary) => summary.id === id);"),
      true,
    );
    assert.strictEqual(hookSource.includes('setStatus(targetSummary?.status ?? "idle");'), true);
    assert.strictEqual(hookSource.includes("setMessages([]);"), true);
    assert.strictEqual(hookSource.includes("setLogs([]);"), true);
    assert.strictEqual(hookSource.includes("currentTaskActive: activeTask,"), true);
    assert.strictEqual(workspaceSource.includes("currentTaskActive={workspace.currentTaskActive}"), true);
    assert.strictEqual(
      composerSource.includes(
        'placeholder={currentTaskActive ? "当前会话正在生成回复，请稍候..." : "尽管问..."}',
      ),
      true,
    );
    assert.strictEqual(composerSource.includes('aria-label="停止当前会话任务"'), true);
    assert.strictEqual(composerSource.includes("{currentTaskActive ? ("), true);
  });

  void it("should expose a clear-history action through the sidebar boundary", () => {
    const hookSource = readFileSync(
      new URL("../../hooks/use-task-workspace.ts", import.meta.url),
      "utf-8",
    );
    const workspaceSource = readFileSync(
      new URL("../../components/chat/TaskWorkspace.tsx", import.meta.url),
      "utf-8",
    );
    const sidebarSource = readFileSync(
      new URL("../../components/chat/ChatSidebar.tsx", import.meta.url),
      "utf-8",
    );

    assert.strictEqual(hookSource.includes("const handleClearConversations = useCallback"), true);
    assert.strictEqual(hookSource.includes("taskSummaries.some((summary) => isTaskActive(summary.status))"), true);
    assert.strictEqual(hookSource.includes("清空所有历史会话后无法恢复"), true);
    assert.strictEqual(hookSource.includes("for (const id of deletedIds)"), true);
    assert.strictEqual(workspaceSource.includes("onClearConversations={workspace.handleClearConversations}"), true);
    assert.strictEqual(sidebarSource.includes("onClearConversations: () => Promise<void> | void"), true);
    assert.strictEqual(sidebarSource.includes("clearHistoryButton"), true);
    assert.strictEqual(sidebarSource.includes("清空所有会话"), true);
  });

  void it("should expose run log download handling through the workspace boundary", () => {
    const hookSource = readFileSync(
      new URL("../../hooks/use-task-workspace.ts", import.meta.url),
      "utf-8",
    );
    const workspaceSource = readFileSync(
      new URL("../../components/chat/TaskWorkspace.tsx", import.meta.url),
      "utf-8",
    );

    assert.strictEqual(hookSource.includes("const handleDownloadLogs = useCallback"), true);
    assert.strictEqual(hookSource.includes('new Blob([payload], { type: "application/x-ndjson;charset=utf-8" })'), true);
    assert.strictEqual(hookSource.includes("anchor.download = buildRunLogDownloadName(runId);"), true);
    assert.strictEqual(workspaceSource.includes("onDownloadLogs={workspace.handleDownloadLogs}"), true);
  });

  void it("should render the slash skill picker and removable skill chips in ChatComposer", () => {
    const composerSource = readFileSync(
      new URL("../../components/chat/ChatComposer.tsx", import.meta.url),
      "utf-8",
    );

    assert.strictEqual(composerSource.includes("findActiveSkillSlashToken"), true);
    assert.strictEqual(composerSource.includes("replaceActiveSkillSlashToken"), true);
    assert.strictEqual(composerSource.includes("dismissedSkillSlashTokenRef"), true);
    assert.strictEqual(composerSource.includes("filterSkillOptions(skillOptions"), true);
    assert.strictEqual(composerSource.includes('data-testid="selected-skill-shelf"'), true);
    assert.strictEqual(composerSource.includes("skillPickerMenu"), true);
    assert.strictEqual(composerSource.includes("skillOption-active"), true);
    assert.strictEqual(composerSource.includes('role="listbox"'), true);
    assert.strictEqual(composerSource.includes("没有匹配的 skill"), true);
    assert.strictEqual(composerSource.includes("event.key === \"ArrowDown\""), true);
    assert.strictEqual(composerSource.includes("event.key === \"ArrowUp\""), true);
    assert.strictEqual(composerSource.includes("event.key === \"Escape\""), true);
    assert.strictEqual(composerSource.includes("handleSkillSelect(activeSkillOption)"), true);
  });

  void it("should not render dollar signs inside skill markers", () => {
    const composerSource = readFileSync(
      new URL("../../components/chat/ChatComposer.tsx", import.meta.url),
      "utf-8",
    );

    assert.doesNotMatch(
      composerSource,
      /<span className="skill(?:Chip|Option)Marker"[^>]*>\s*\$\s*<\/span>/,
    );
    assert.match(composerSource, /<span className="skillChipMarker" aria-hidden="true" \/>/);
    assert.match(composerSource, /<span className="skillOptionMarker" aria-hidden="true" \/>/);
  });
});
