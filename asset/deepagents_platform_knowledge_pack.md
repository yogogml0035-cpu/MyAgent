# DeepAgents Platform Knowledge Pack

## Background And Scope

This package documents the DeepAgents-powered universal agent platform that replaced the original bid-analysis system. It covers the backend agent architecture, multi-model provider, tools, streaming, SubAgent system, skill loading, API routes, and test layout.

Use it when changing agent factory, middleware assembly, model provider, tool registration, streaming events, SubAgent definitions, SKILL.md loading, API routes, or test structure.

## Business Rules

- The platform uses `create_deep_agent()` from the `deepagents` SDK as the sole execution engine. It returns a `CompiledStateGraph` ready for `.invoke()` or `.stream()`.
- `build_agent()` (in `agent/factory.py`) is the default builder; it passes `checkpointer`, `store`, and `max_concurrent_subagents` directly to `create_deep_agent()`.
- `build_agent_with_middleware()` is an alternative builder that also assembles extra middleware (SkillsMiddleware, SubAgentMiddleware) via `agent/middleware.py` before calling `create_deep_agent()`. **Do NOT use `build_agent_with_middleware()` to add `SummarizationMiddleware`** — it is already auto-injected by `create_deep_agent()`.
- `create_deep_agent()` auto-injects `TodoListMiddleware`, `FilesystemMiddleware`, `SummarizationMiddleware`, and `PatchToolCallsMiddleware`. Do NOT pass these via the `middleware` parameter — it causes duplicate middleware assertion errors.
- Skills and SubAgents are passed via `create_deep_agent(skills=..., subagents=...)` keyword arguments, not via the middleware parameter.
- Multi-model support uses `langchain.chat_models.init_chat_model` with `provider:model-name` format (e.g., `deepseek:deepseek-chat`, `openai:gpt-4o`, `anthropic:claude-sonnet-4-20250514`).
- The model provider parses the provider prefix, validates the API key is configured, and creates the appropriate `BaseChatModel` instance.
- `MODEL_REGISTRY` in `config.py` lists all supported models. The `/api/models` endpoint returns models with an `available` flag based on whether the provider API key is configured.
- Default model is `deepseek:deepseek-chat` (configurable via `MYAGENT_DEFAULT_MODEL` env var).
- Tools are LangChain `@tool` decorated functions: `read_file`, `write_file`, `list_files` (filesystem) and `tavily_search` (conditional on `TAVILY_API_KEY`).
- Filesystem tools validate paths stay within `workspace_root` for security.
- SubAgents are `SubAgent` TypedDicts with `name`, `description`, `system_prompt`, and optional `model`/`tools`/`skills`. Three built-in: `researcher`, `coder`, `file-analyst`.
- Skills follow the DeepAgents SKILL.md convention: YAML frontmatter with `name` and `description`, plus Markdown instructions. Loaded from directories listed in `settings.skills_dirs`.
- Streaming uses `agent.astream(input, stream_mode=["messages", "updates"])` via the v2 adapter. Events are converted to `EventRecord` objects via `event_converter.py`.
- SSE endpoint at `GET /api/tasks/{task_id}/stream` provides real-time output. Frontend uses `EventSource` API with token as query parameter.
- `TaskRunner` manages agent lifecycle: build agent → stream events → convert → collect results. Supports background execution via `start_background()` and cancellation via `cancel()`. Enforces `settings.agent_timeout_seconds` via `asyncio.timeout()`.
- Task API routes follow REST conventions: `POST /api/tasks` (create), `GET /api/tasks` (list), `GET /api/tasks/{id}` (read), `POST /api/tasks/{id}/messages` (send message), `POST /api/tasks/{id}/cancel` (cancel).
- Auth middleware enforces loopback-only access by default; non-local access requires `MYAGENT_ACCESS_TOKEN`.

## Input And Output Examples

- Create task: `POST /api/tasks` → `{"task_id": "...", "status": "idle", "model": "deepseek:deepseek-chat", ...}`
- Send message: `POST /api/tasks/{id}/messages` body: `{"message": "搜索最新的AI新闻", "model": "deepseek:deepseek-chat"}`
- Build agent: `build_agent(settings, tools=get_platform_tools(settings), skills=["./skills"])`
- Model ID format: `"deepseek:deepseek-chat"`, `"openai:gpt-4o"`, `"anthropic:claude-sonnet-4-20250514"`
- SSE event: `event: message\ndata: {"type": "agent_message", "text": "..."}\n\n`

## Boundary Conditions

- `create_deep_agent()` does NOT accept duplicate middleware instances — assertion error if duplicates found.
- `storage.py` depends on compatibility shims in `app/contracts/__init__.py` and `app/reasoning_trace.py` that recreate deleted module types. These shims must not be removed until storage.py is rewritten.
- `schemas.py` inlines `TaskMode` and `InputScope` Literal types (previously from deleted `intent.py`).
- Missing API keys cause graceful errors in provider (not crashes). Tavily tool returns error string if key missing.
- `SKILL.md` files without valid YAML frontmatter are silently skipped during discovery.

## Known Pitfalls

- **Middleware duplication**: Never pass `TodoListMiddleware`, `FilesystemMiddleware`, `SummarizationMiddleware`, or `PatchToolCallsMiddleware` via the `middleware` param — `create_deep_agent` auto-injects them.
- **Provider prefix**: Model IDs must include provider prefix (`deepseek:`, `openai:`, `anthropic:`). Raw model names will fail.
- **EventSource auth**: Browser `EventSource` API doesn't support custom headers; token must be passed as query parameter for SSE.
- **storage.py coupling**: TaskStorage is deeply coupled to old contracts/reasoning_trace types via compatibility shims. A future storage rewrite should use native DeepAgents state management.
- **Single-process runtime**: The platform uses in-process runner and local JSON storage. Multi-worker deployment will break.
- **Timeout enforcement**: `TaskRunner.start()` enforces `settings.agent_timeout_seconds` via `asyncio.timeout()`. If the deepagents SDK or LLM call hangs, the run is terminated after the configured timeout and a warning is logged.
- **checkpointer/store passthrough**: `build_agent()` passes `checkpointer` and `store` to `create_deep_agent()`, but the current deployment uses no checkpointer (state is managed by TaskStorage in JSON files). To enable LangGraph-native persistence, pass an `InMemorySaver` or `PostgresSaver` instance when constructing the agent.

## Related Code Paths

- Backend config: `backend/app/config.py`
- Model provider: `backend/app/models/provider.py`, `backend/app/models/registry.py`
- Agent factory: `backend/app/agent/factory.py`, `backend/app/agent/middleware.py`
- Tools: `backend/app/tools/tavily_search.py`, `backend/app/tools/filesystem_bridge.py`, `backend/app/tools/registry.py`
- Streaming: `backend/app/streaming/v2_adapter.py`, `backend/app/streaming/event_converter.py`, `backend/app/streaming/sse.py`
- Runner: `backend/app/runner/core.py`
- SubAgents: `backend/app/subagents/definitions.py`, `backend/app/subagents/registry.py`
- Skills: `backend/app/skills/loader.py`, `backend/app/skills/registry.py`
- API routes: `backend/app/api/tasks.py`, `backend/app/api/files.py`, `backend/app/api/streaming.py`, `backend/app/api/models.py`
- Entry point: `backend/app/main.py`
- Skills directory: `backend/skills/web_research/SKILL.md`, `backend/skills/code_review/SKILL.md`
- Compatibility shims: `backend/app/contracts/__init__.py`, `backend/app/reasoning_trace.py`

## Related Test Paths

- Unit tests: `backend/tests/unit/models/`, `backend/tests/unit/tools/`, `backend/tests/unit/agent/`, `backend/tests/unit/skills/`, `backend/tests/unit/streaming/`
- Integration tests: `backend/tests/integration/`
- E2E tests: `backend/tests/e2e/` (empty, for future)
- Test fixture: `backend/tests/conftest.py` (provides `test_settings` fixture with tmp_path)

## Verification Commands

```bash
cd /mnt/d/AgentProject/MyAgent/backend
uv run ruff check app/
uv run pytest tests/ -v
uv run python -c "from app.main import create_app; create_app()"
```

```bash
cd /mnt/d/AgentProject/MyAgent/frontend
npm run typecheck
npm test
```

## Regression Risks

- Middleware duplication if future developer re-adds default middleware to the stack.
- storage.py breakage if compatibility shims are deleted without rewriting storage.
- Model format mismatch if frontend sends old-style `deepseek-reasoner` instead of `deepseek:deepseek-chat`.
- SSE auth bypass if EventSource query param is removed without alternative auth.
- Timeout breakage if `asyncio.timeout()` is removed without an alternative mechanism to prevent runaway agent runs.
- Concurrency risk if `max_concurrent_subagents` is changed without testing subagent parallel execution limits.
