import type { ModelOption } from "./task-state";

export type ModelDisplayOption = ModelOption & {
  badge?: string;
  description: string;
};

type ModelPresentation = {
  label?: string;
  badge?: string;
  description: string;
};

const MODEL_PRESENTATION: Record<string, ModelPresentation> = {
  "deepseek-reasoner": {
    label: "Deepseek",
    description: "多轮推理，回答复杂问题",
  },
};

export function describeModelOption(option: ModelOption): ModelPresentation {
  const knownPresentation = MODEL_PRESENTATION[option.id];
  if (knownPresentation) {
    return knownPresentation;
  }

  const marker = `${option.id} ${option.label}`.toLowerCase();

  if (marker.includes("agent") && (marker.includes("cluster") || marker.includes("集群"))) {
    return {
      badge: "Beta",
      description: "海量搜索、长文写作、批量处理",
    };
  }

  if (marker.includes("agent")) {
    return {
      description: "调研、文档、表格与多步骤任务",
    };
  }

  if (marker.includes("reason") || marker.includes("think") || marker.includes("思考")) {
    return {
      description: "多轮推理，回答复杂问题",
    };
  }

  if (marker.includes("quick") || marker.includes("fast") || marker.includes("chat") || marker.includes("快速")) {
    return {
      description: "快速响应",
    };
  }

  return {
    description: "通用对话与任务处理",
  };
}

export function buildModelDisplayOptions(options: ModelOption[]): ModelDisplayOption[] {
  return options.map((option) => ({
    ...option,
    ...describeModelOption(option),
  }));
}

export function selectedModelDisplayOption(
  options: ModelDisplayOption[],
  selectedModelId: string,
): ModelDisplayOption {
  const selectedOption = options.find((option) => option.id === selectedModelId);
  if (selectedOption) {
    return selectedOption;
  }

  const fallbackOption = {
    id: selectedModelId,
    label: selectedModelId,
  };

  return {
    ...fallbackOption,
    ...describeModelOption(fallbackOption),
  };
}
