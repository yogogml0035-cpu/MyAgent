# 06 标准答案

## 自测题答案

1. Runner 状态变为非 running 和最后一批事件写入之间可能有很小时间差。drain remaining events 可以避免漏掉终态事件。
2. `assistant_answer_delta` 是流式中间片段；`final_answer` 是从完成后的图状态提取的权威最终回答事件。
3. 网络异常时无限重连会浪费资源、制造噪音。最大重试次数能让用户得到明确错误提示。
4. `mergeExecutionLogs` 负责按事件 id 去重并追加新日志；`workspace-view.ts` 的 `byLogOrder` 负责展示排序，优先按 `seq`，再按时间。

## 练习观察点

同一秒内的多个事件按时间字符串排序不可靠。`seq` 是后端为同一 task 维护的自然顺序。学习时要把“合并”和“展示排序”分开看。
