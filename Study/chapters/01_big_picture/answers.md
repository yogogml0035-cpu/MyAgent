# 01 标准答案

## 自测题答案

1. `frontend/app/page.tsx` 只挂载 `TaskWorkspace`，因为页面入口保持很薄，具体状态和交互下沉到组件和 hook。
2. `backend/app/main.py` 注册了 tasks、files、artifacts、streaming、models 等 API 路由，并配置请求体限制、鉴权、CORS、健康检查和 lifespan。
3. 用户消息会成为会话消息；同时触发一次 Run；Run 执行过程中又会不断追加 Event，因此三者都会变化。
4. 空 task 只是草稿，不启动模型运行；带消息 task 会立刻 `start_run()` 并调度 `runner.start_background()`。

## 练习观察点

如果你把 `runner.start_background` 放到 `storage.start_run` 前，断言失败是正确的。真实项目里 Runner 需要 API 层从 `storage.start_run()` 拿到的 `run_id`，这样 events、messages、artifacts 才能归到同一次运行。

如果源码锚点检查失败，优先确认是不是项目结构改了；学习资料应跟着真实入口一起更新。
