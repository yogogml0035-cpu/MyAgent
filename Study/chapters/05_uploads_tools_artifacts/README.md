# 05 上传资源、工具与产物

## 学习目标

你要理解文件相关的三类对象：

- Upload：用户上传的源文件。
- Resource：Agent 可通过工具按需读取的任务内资源。
- Artifact：运行后生成的结果文件。

## 前置知识

- 文件扩展名校验：只允许平台支持的格式进入工作区。
- 路径穿越：例如 `../other-task/secret.md` 试图越过当前目录。
- 产物预览：下载和打开报告必须经过受控 API。

## 必读代码

- `backend/app/api/files.py`
- `backend/app/execution/resources.py`
- `backend/app/api/artifacts.py`
- `backend/app/storage.py`
- `frontend/app/file-upload.ts`
- `frontend/lib/task-api.ts`

## 本章主线

先看上传 API 如何把文件保存到当前 task 的 `uploads/`，再看资源工具如何只读取这个目录，最后看 artifact API 如何让前端安全下载结果。

## 核心概念

### 上传文件不是自动上下文

上传文件可能很大，也可能包含敏感内容。系统只把 manifest 给模型：文件名、格式、大小、digest 等。真正内容要由资源工具按页、按范围读取。

资源工具包括：

- `list_uploaded_resources`
- `inspect_resource`
- `read_resource_text`
- `read_resource_table`

这些是“上传资源工具”，只处理当前 task 的 uploads。联网搜索是另一类平台工具：`searxng_search`，由 `backend/app/tools/searxng_search.py` 调用本地 SearXNG 引擎，不读取上传文件，也不扩大 resource tool 的文件系统权限。

### Resource 工具必须 task-scoped

资源工具只能读：

```text
settings.workspace_root / task_id / uploads
```

不能读任意本地路径，不能跨 task 读文件。

### Artifact 下载要走 API

前端不能相信任意 artifact URL。它必须通过当前 API origin 和当前 task 的 artifact 路由下载；HTML 产物预览还要放进禁用脚本的 sandbox iframe。

对应路由：

```text
GET /api/tasks/{task_id}/artifacts/{artifact_name}
GET /api/tasks/{task_id}/runs/{run_id}/artifacts/{artifact_name}
```

## 你可能卡住的问题

### 为什么支持 `.docx`、`.xlsx`，但不直接支持任意本地路径？

因为本地路径会扩大权限边界。v1 的安全模型是：先上传到当前 task，再由 resource tool 读取当前 task 的资源。

### 为什么 JSON 上传要提前校验？

JSON 格式轻量，上传时就能判断是否合法；Word/Excel 解析更重，放到工具执行阶段按需处理。

## 动手练习

运行：

```bash
python3 Study/chapters/05_uploads_tools_artifacts/mini_unit.py
```

尝试把 `resolve_task_upload_path` 里的越界检查删掉，再运行。你会看到路径穿越测试无法被拦住。

练习还会读取前后端源码，确认支持格式、资源工具名、artifact 路由和前端 URL allowlist 边界。

## 自测题

1. Upload、Resource、Artifact 各自是什么？
2. 为什么资源读取要分页或限制范围？
3. 为什么 HTML artifact 不能直接 top-level 导航到 blob URL？
4. 前端和后端为什么都要做上传格式校验？

## 常见误区

- 误区：文件上传后模型已经看过全文。纠正：模型只看到 manifest，正文要工具按需读取。
- 误区：resource tool 可以读任意本地路径。纠正：只能读当前 task 的 uploads。
- 误区：artifact.url 是后端给的就一定可信。纠正：前端仍要校验 origin、task id、run id、artifact name。
