import assert from "node:assert/strict";
import test from "node:test";

import {
  buildModelDisplayOptions,
  selectedModelDisplayOption,
} from "../../app/model-ui";

test("buildModelDisplayOptions adds compact model descriptions for the picker", () => {
  const options = buildModelDisplayOptions([
    { id: "deepseek-reasoner", label: "DeepSeek Reasoner" },
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
        description: "多轮推理，回答复杂问题",
        label: "Deepseek",
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
