import assert from "node:assert/strict";
import test from "node:test";

import {
  buildModelDisplayOptions,
  selectedModelDisplayOption,
} from "../../app/model-ui";

test("buildModelDisplayOptions adds compact model descriptions for the picker", () => {
  const options = buildModelDisplayOptions([
    { id: "deepseek-v4-flash-thinking", label: "DeepSeek V4 Flash Thinking" },
    { id: "k26-agent-cluster", label: "K2.6 Agent 集群" },
    { id: "k26-quick", label: "K2.6 快速" },
  ]);

  assert.deepEqual(
    options.map((option) => ({
      badge: option.badge,
      description: option.description,
      label: option.label,
    })),
    [
      {
        badge: undefined,
        description: "开启思考模式，适合复杂问题",
        label: "DeepSeek V4 Flash Thinking",
      },
      {
        badge: "测试",
        description: "海量搜索、长文写作、批量处理",
        label: "K2.6 Agent 集群",
      },
      {
        badge: undefined,
        description: "快速响应",
        label: "K2.6 快速",
      },
    ],
  );
});

test("selectedModelDisplayOption keeps a readable fallback for unknown selected ids", () => {
  const selected = selectedModelDisplayOption([], "custom-agent");

  assert.equal(selected.label, "custom-agent");
  assert.equal(selected.description, "调研、文档、表格与多步骤任务");
});

test("buildModelDisplayOptions annotates unavailable models with a disabled reason", () => {
  const [option] = buildModelDisplayOptions([
    { id: "deepseek-v4-flash-thinking", label: "DeepSeek V4 Flash Thinking", available: false },
  ]);

  assert.equal(option.available, false);
  assert.equal(option.disabledReason, "后端未配置对应 API Key");
});
