# Task Workspace Runtime Knowledge Pack

## Background And Scope

This package is the single durable knowledge source for the MyAgent task workspace. It absorbs the previous backend runtime, frontend workspace, and model-provider/security packages.

Use it when changing task APIs, task state transitions, runner behavior, event logs, artifact downloads, uploads, local JSON storage, frontend task creation, file selection, message submission, polling, artifact opening, model routing, environment variables, access tokens, CORS, or test layout.

## Business Rules

- A task is the durable conversation container. `POST /api/tasks` creates only an empty task shell; accepted user messages must go through `POST /api/tasks/{task_id}/messages` and start a run.
- `GET /api/tasks` is the backend source of truth for chat history. It returns only tasks with at least one non-empty user message, sorted by newest activity.
- A completed, failed, cancelled, interrupted, or needs-input task may accept a follow-up message. A running task must reject another message or upload with conflict semantics.
- Follow-up messages append to the same task conversation. Existing uploads are available task context, not implicit prompt content or guaranteed inputs for every later run.
- `POST /api/tasks/{task_id}/messages` accepts optional `mode` values `auto`, `chat`, `search`, `document_analysis`, and `deep_agent`; legacy `bid_analysis` is accepted as a document-analysis alias. It still accepts optional `input_scope` values `auto`, `none`, and `task_uploads`, plus legacy `uploads`, for API compatibility only. The first-party frontend no longer sends or exposes `input_scope`, and legacy `input_scope` does not override `mode=auto` routing.
- In `auto`, weather/search/new casual questions resolve to `search` or `chat` and do not expose old uploads. Clear continuation or document-analysis requests such as "继续根据刚才这些文件分析" resolve to `deep_agent` when uploads exist; uploads are copied as available read-only snapshots, and actual file use is determined by model tool calls recorded in `file_tool_audit`.
- If an `auto` file-aware request resolves to `deep_agent` but the optional DeepAgent runtime is unavailable, the backend emits a Chinese warning and falls back to the deterministic document-analysis compatibility path. Explicit `mode=deep_agent` does not fallback; it completes with a Chinese warning if the adapter is unavailable.
- Uploads support `.md` and `.json` files through `POST /api/tasks/{task_id}/files`. Backend filename checks and JSON parsing are authoritative; MIME type alone is not trusted.
- Upload validation is atomic. Invalid file type, invalid JSON, duplicate names, file-count limits, file-size limits, request-size limits, or overlong filenames must reject the batch without partial persistence.
- Every new run has a non-empty `run_id`. New user messages, assistant messages, events, run records, and run-scoped artifacts should carry that `run_id`.
- Successful terminal transitions must not expose a `complete` task state before the corresponding success event (`chat_completed`, `search_completed`, `deep_agent_completed`, or `task_completed`) is persisted for the same `run_id`.
- Search/weather runs must synthesize a final answer after tool use. Search result formatting may be used only as a bounded source-summary helper or fallback, not as the normal successful assistant answer.
- Search synthesis uses the `TaskRunner`'s injected model provider. It should not instantiate a separate provider router inside the runner unless ownership is intentionally refactored.
- Search synthesis output is represented internally as `answer`, up to five bounded `sources` with `title`, `url`, and short `snippet`, `used_model`, optional `warning_code`, and safe `event_payload`. The event payload must not include raw Tavily JSON or raw provider content. Successful model synthesis must not append a hard-coded `参考来源` block; if the model includes references in its own Markdown answer, render that answer as-is.
- Search/weather events are ordered as `search_tool_call`, `search_tool_result`, optional answer-generation status events, `search_synthesis_completed`, then terminal `search_completed` in the same completion transition when sources are available. If `TAVILY_API_KEY` is missing, the final answer is a Chinese warning that search is not enabled. If provider synthesis is unavailable, the final answer is a Chinese warning plus a bounded deterministic source summary.
- User-visible backend messages, assistant warnings, needs-input text, report copy, and HTTP `detail` strings should be Chinese. Machine contracts stay stable: do not translate `event.type`, `TaskStatus`, `level`, payload keys, artifact names, model IDs, or environment variable names.
- Request validation failures should return a stable Chinese `detail` string instead of raw framework or parser messages.
- Report-like outputs are versioned under `artifacts/runs/{run_id}/`. Top-level artifact paths remain latest/legacy compatibility aliases.
- Run-scoped artifact access is allowlisted by the run's recorded artifact names and must reject traversal or unlisted files.
- DeepAgent integration is an optional backend adapter, not a required runtime dependency. Importing backend code and running tests must work when the third-party `deepagents` package is absent; tests may inject a mock agent factory.
- DeepAgent-backed execution must be constructed through MyAgent's adapter and `create_deep_agent(...)` with audited tools and `AuditedDeepAgentBackend`; local reference-project code, unrestricted filesystem backends, shell backends, raw `Path` handles, and project-root backends are not runtime dependencies.
- DeepAgent streaming, when supported by the agent object, must call `stream(..., subgraphs=True, version="v2", stream_mode=["updates", "messages"])` with `config.configurable.thread_id` derived from `{task_id}:{run_id}`. DeepAgents raw stream chunks are backend inputs only; they are projected into MyAgent events before persistence or UI rendering.
- `custom` is not enabled for raw DeepAgents execution. It is reserved for future MyAgent-authored progress events emitted by MyAgent code after those events have passed the same sanitizer and schema rules as other user-visible logs.
- A successful DeepAgent run should produce one user message, one AI-side execution-log card rendered from run events, and one AI-side final-answer card rendered from the single persisted assistant message. Process logs, intermediate assistant-like stream text, and tool progress must not be appended as extra assistant messages.
- A successful DeepAgent run should emit at least one safe execution event, preferably `deep_agent_activity`; if streaming is unavailable and the runtime falls back to `invoke()`, a synthesized safe activity/warning event keeps the execution-log card visible without persisting raw fallback payloads.
- `deep_agent_activity` is the minimal DeepAgents lifecycle/progress event contract. Payloads use `schema_version: 1`, `source: deepagents`, optional `source_event_id`, `activity_kind` (`lifecycle` or `progress`), `phase` (`planning`, `reasoning`, `tool_use`, `file_operation`, `finalizing`), `status` (`started`, `running`, `completed`, `failed`, `skipped`), safe `title`/`summary`, optional safe `tool_name`, `parameter_summary`, `result_summary`, optional `subgraph_path`, optional `related_event_id`, and `truncated`.
- User-facing live logs use optional `payload.live` metadata with `schema_version: 1`, `kind` (`think`, `tool_call`, `tool_result`, `answer_status`, or `status`), optional public `stage`, `agent_name`, `tool_name`, `tool_call_id`, bounded primitive `parameter_items`, optional `result_status`, and optional `result_count`. Backend events keep technical fields for debugging, but the frontend default view and copied log text should use this live projection instead of raw technical payloads. New task-run entry, orchestration, tool, answer-generation, needs-input, failure, cancellation, and terminal completion events should carry live metadata when they are meant to affect the user-facing progress card.
- `payload.live.parameter_items` must stay generic and safe: preserve only a few primitive parameters, keep explicit safe keys such as `max_results`, redact unsafe paths, drop keys matching secrets/tokens/auth/password/credential/content/prompt/body/result unless explicitly allowlisted, and replace long strings with `"..."`. Tool result cards must summarize status/count generically and must not render source links, raw Tavily JSON, uploaded body text, or tool response bodies.
- DeepAgent loop observability is event-derived. Safe activity may describe planning, observation, decision, next-step, and final-summary summaries, but must not store or display provider raw reasoning, hidden chain-of-thought, raw prompts, uploaded bodies, raw Tavily JSON, raw tool response bodies, DeepAgent internal traces, or raw subagent conversations.
- Optional `deep_agent_activity` metadata such as `iteration_index`, `agent_id`, `parent_agent_id`, or `task_label` may remain `schema_version: 1` only when backward-compatible and individually bounded. A breaking schema change requires a new schema version plus synchronized backend sanitizer, frontend normalizer, copy-text, and tests.
- DeepAgent system prompts must require final synthesis after tool use, task plan/todo recording for complex file work, deliverable files under `outputs/`, and subagent use only when parallel or isolated analysis is justified.
- DeepAgent subagent roles should be explicit and bounded for document classification, requirement matching, bidder-pair comparison, evidence normalization, and report writing. The main agent may still complete a file-aware task without reading uploads when tool use is not justified.
- Single-agent versus multi-agent orchestration is a separate decision record, not `execution_mode`. `execution_mode` remains `stream` versus `invoke`; orchestration records describe strategy selection.
- DeepAgent multi-agent routing is owned by backend static Agent Profiles in `backend/app/agent_profiles.py`. V1 profiles are `default_file_agent` for ordinary file-aware DeepAgent work and `bid_multi_agent` for complex bid-collusion workflows. The frontend and external API do not accept raw subagent specs, backends, callables, shell tools, or filesystem paths.
- Agent Profiles contain bounded `SubAgentSpec` records with `name`, `description`, `system_prompt`, safe tool aliases, and optional model overrides. V1 disables `compiled_factory`; future `CompiledSubAgent` support must remain backend-owned and pass the same validation, auditing, and optional-dependency tests.
- Runtime compilation of dictionary-style DeepAgents subagents must map safe tool aliases such as `list_dir`, `read_file`, and `write_file` to the same audited callable tools passed to the main agent. Custom subagents must not receive empty tool lists for file-analysis roles, raw filesystem handles, shell tools, or user-supplied callables.
- Profile selection is deterministic. Chat/search routes do not create DeepAgent profiles. Explicit `mode=deep_agent` uses `default_file_agent` unless a future backend-owned rule says otherwise. Auto bid/document prompts with uploads select `bid_multi_agent` only when at least two bidder-like uploads are available, including upload-reference phrasing such as "继续根据刚才这些文件检查串标"; otherwise they use `default_file_agent` or the existing needs-input/fallback path.
- Each run records the safe event `orchestration_decision` with `schema_version: 1`, `strategy` (`single_agent` or `multi_agent`), `reason_code`, `input_count`, `bidder_count`, `planned_subagents`, `decision_summary`, `chosen_profile_id`, optional `chosen_profile_label`, route, route reason, and message class. Complex file runs may also mirror safe summaries into `reasoning_trace` or `deep_agent_activity`. Subagent outputs are evidence inputs to the final answer, never assistant chat messages.
- `run.json`, `orchestration_decision`, and the DeepAgents factory arguments must agree on the selected profile and subagent tool set for a run. A mismatch means the UI can claim multi-agent planning while the runtime executes a different subagent set or leaves custom subagents unable to access audited workspace files.
- DeepAgent file access must go through audited workspace tools only. The agent receives callable tools such as `list_dir`, `read_file`, and `write_file`, never raw `Path` objects, workspace roots, or unrestricted filesystem handles. The `create_deep_agent` call must pass an `AuditedDeepAgentBackend` implementing the DeepAgents backend file-operation protocol so the framework's built-in filesystem surface also routes through audited `ls/read/write/edit/glob/grep` behavior, including file-name enumeration.
- DeepAgent runs use `agent_workspace/runs/{run_id}/` as their private workspace. Current task uploads are copied into read-only `uploads/` snapshots as optional available context; writable agent files are restricted to `records/` and `outputs/`; promoted user-facing files are copied to run-scoped artifacts.
- DeepAgent output files promoted from `outputs/` are stored as artifact-safe names with a `deep-agent-` prefix. Unsafe filename characters are normalized with the storage filename rules, useful extensions are preserved where possible, and collisions after normalization are disambiguated with a stable numeric prefix.
- Recognized bid-analysis DeepAgent outputs are promoted to the canonical names `report.html`, `final-summary.md`, `evidence.json`, and `task-plan.md` after validation. Other DeepAgent outputs keep the `deep-agent-` prefix.
- Bid-collusion analysis requires at least two bidder documents; a tender document is strongly preferred and should be classified when present. Durable analysis dimensions are quotation similarity, technical text similarity, template traces, shared entities, requirement deviations, metadata clues, and common deviations.
- Bidder-pair comparison coverage is complete: three bidders require A/B, A/C, and B/C records, and larger sets generalize to N choose 2. Each pair must have one or more evidence records or an explicit safe no-finding comparison record in `evidence.json`.
- Canonical bid evidence fields are `category`, `severity`, `title`, `description`, `bidders`, `pair`, `locations`, `requirement_reference`, `confidence`, `source_agent`, and `rationale_summary`. Missing optional values are normalized to explicit safe empty values such as `null`, `[]`, or `"unknown"`.
- `evidence.json` must be schema-validated before report artifact promotion. Invalid DeepAgent evidence fails the DeepAgent bid path or falls back to deterministic normalization; malformed evidence must not be promoted into canonical report artifacts.
- Bid HTML reports should include comparison tables, severity grouping, bidder-pair filters or sections, and evidence locations. `final-summary.md` is the concise final-answer source when available, while artifacts remain run-scoped downloads.
- File-tool audit events use event type `file_tool_audit` and payload keys including `run_id`, `tool_name`, `op`, `virtual_path`, `resolved_workspace_path`, `bytes`, `sha256`, `source`, `timestamp`, `promoted_artifact_id`, plus compatibility keys `tool`, `operation`, `requested_path`, `relative_path`, `status`, `reason`, and `partial`. Paths exposed through events must be virtual or task/run-relative, never raw local filesystem roots. DeepAgents internal paths must be folded to a neutral placeholder such as `<deepagents-internal>` before persistence. When a DeepAgent activity row describes the same operation, `deep_agent_activity.related_event_id` should point at the `file_tool_audit` event id.
- Agent thinking shown in frontend logs uses only safe public summaries such as `payload.live` stages or event type `reasoning_trace`. It is a safe, user-facing reasoning summary contract, not raw hidden chain-of-thought. Payloads contain `agent_id`, `phase` (`plan`, `observe`, `decide`, `next_step`, `final_summary`, `risk`), `summary`, optional `confidence`, optional safe `evidence_refs`, and optional `source_event_id`.
- Every run successfully created by the runner must have at least one safe `reasoning_trace` before its settled state is observable. This invariant applies to successful, warning/fallback, `needs_input`, failed, and cancelled runs; it does not apply to request validation rejects, empty task creation, uploads, running-task conflicts, or cancel requests with no active run.
- Run-level terminal reasoning uses phase guidance rather than a full phase matrix: `final_summary` for successful runs, `next_step` for `needs_input`, and `risk` for failed, cancelled, fallback, or warning-limited runs. DeepAgent/document routes can emit richer route-specific traces; generic run-level traces must be idempotent per run/phase and avoid duplicating an existing phase.
- `reasoning_trace` summaries may be synthesized only from structured evidence metadata, finding counts, category labels, filenames, virtual paths, audited file metadata, safe route/status facts, warning codes, artifact names, and bounded search source counts/titles. They must not quote raw provider output, provider `reasoning_content`, raw internal prompts, uploaded document bodies, DeepAgent message history, `/conversation_history/` contents, raw tool result content, raw Tavily JSON, provider key values, authorization headers, unsanitized exception strings, or absolute local paths.
- DeepAgent file-observation reasoning must be emitted only after `file_tool_audit` persistence succeeds, using the audit event id as `source_event_id` when available. The reasoning summary references virtual paths such as `uploads/a.md` or `outputs/summary.md`, not raw workspace paths or file contents.
- The frontend is a chat-first task workspace, not a marketing page. The sidebar history comes from `GET /api/tasks`, not from the current in-memory message list.
- Frontend route ownership is intentionally thin: `frontend/app/page.tsx` mounts the task workspace, `frontend/hooks/use-task-workspace.ts` owns task state, polling, copy feedback, uploads, and artifact actions, `frontend/lib/task-api.ts` owns token-aware API calls, and `frontend/components/chat/` owns sidebar, composer, conversation, and robot avatar rendering.
- The frontend visual system follows the durable warm editorial contract captured in this package: tinted cream canvas, warm coral primary actions, dark product surfaces for run/log chrome, light cream cards with hairline borders, a text-only serif display empty-state wordmark, and sans UI text for operational controls.
- Frontend style tokens are centralized in `frontend/app/globals.css`. Sidebar/history, composer, upload chips, menus, assistant messages, and artifact cards use cream surfaces; send/download/user-message actions use coral; grouped run progress and execution logs use dark product surfaces.
- Robot-authored assistant messages, execution-log rows, and artifact rows use the reference TenderWord robot avatar treatment: a 32px square blue-100 marker with a blue-600 lucide Bot glyph (`M12 8V4H8` geometry) rendered by `frontend/components/chat/RobotAvatar.tsx`, not the previous `/agent-robot.svg` background marker.
- In active conversations, the composer panel should align to the same column and width as assistant message cards by sharing the conversation stream width and left message-marker gutter. The empty-state composer remains visually centered.
- New Chat opens an unpersisted local draft, clears local workspace state, and must not create a backend history item until the first send succeeds and summaries refresh.
- Frontend file selection remains client-side until submit. Submit creates or reuses a task, uploads selected `.md`/`.json` files, posts the message, clears local input, and refreshes task state.
- The native file picker intentionally has no restrictive `accept` filter; the visible upload workflow queues only `.md` and `.json` filenames.
- Execution logs render as run-grouped cards inside the conversation stream. For a run with an assistant reply, activity appears after the user prompt and before the assistant reply.
- Successful AI-side conversation order is user message -> execution-log card -> final-answer card -> run-scoped artifact cards when logs and a final answer exist. The execution-log card projects search events, `deep_agent_activity`, `reasoning_trace`, `file_tool_audit`, and warning/error events through safe live summaries for that run; it is not a persisted chat message and must not be fed back as assistant conversation history.
- User message cards expose a copy action after the timestamp whose clipboard text is exactly `message.content`, without timestamps, labels, metadata, or logs. The user-message copy control is visually hidden until hover, keyboard focus, or its copied feedback state so the default user footer remains quiet. Assistant copy support remains on the final-answer card only. Execution-log copy/export uses the full safe run log set, including rows hidden by compact default rendering.
- User-message, final-answer, and execution-log copy controls show a short checkmark feedback state only after a successful clipboard write. The checkmark should stay within the warm cream/coral/dark visual-token system instead of using a separate green success block. Copy failures stay as assistant-style workspace notices and must not fake a success state.
- Frontend final-answer wording should distinguish assistant final content from execution logs with an `AI回复` card title. It must not create extra assistant messages or move tool/log summaries into the final-answer card.
- Assistant final content renders as Markdown using `react-markdown` with `remark-gfm` and no raw-HTML plugin. Paragraphs, lists, tables, code blocks, links, and blockquotes should use the warm editorial visual system while preserving raw answer text for copy.
- Frontend handling of new optional activity or orchestration fields must be explicit. Unknown optional fields are ignored by default and must not appear in the DOM or copied logs; displayed/copied fields must be individually normalized with enum and length bounds.
- Frontend orchestration rendering may show the selected profile label, strategy, reason code, bidder count, and planned subagents. It must not expose raw prompts or arbitrary payload fields. Copied logs include only normalized safe orchestration labels.
- Reasoning summaries render inside the same run-grouped progress card as operation logs, with a distinct `思考摘要` label. The frontend does not create a separate reasoning/history card.
- Backend task errors, needs-input notices, missing provider-key warnings, local upload warnings, copy failures, and artifact-open failures should stay in the conversation stream as robot-authored assistant notices, not detached banners.
- Generated run artifacts render as independent result/download cards for runs without an assistant reply. When a run has an `AI回复` card, run-scoped artifacts are attached to that card's footer as per-artifact open/download actions and are not duplicated as standalone cards. All artifact actions must open/download through token-aware blob fetching. Prefer run-scoped artifact URLs when a `run_id` is available.
- The frontend may map known fixed English backend legacy strings to Chinese through an explicit whitelist. Do not add broad automatic translation for user text, filenames, URLs, uploaded content, or model replies.
- Provider keys such as `DEEPSEEK_API_KEY` and `TAVILY_API_KEY` are backend-only. Browser-visible `NEXT_PUBLIC_*` values must not contain provider keys, customer text, or private credentials.
- Missing `DEEPSEEK_API_KEY` for simple chat is a provider-configuration warning, not a hard frontend error. Document-analysis fallback behavior should remain available.
- `NEXT_PUBLIC_MYAGENT_API_BASE_URL=auto` derives `http://<current page hostname>:8001`. Non-default backend ports require an explicit URL or a resolver/test change.
- Task APIs are local-first. Non-loopback access requires `MYAGENT_ACCESS_TOKEN`; browser calls send `NEXT_PUBLIC_MYAGENT_TOKEN` as `X-MyAgent-Token`.
- Backend CORS uses exact origins from `MYAGENT_CORS_ORIGINS`; scheme, host, and port must match the browser origin.
- The backend is single-process oriented because task runners and JSON task storage are in-process/local. Multi-worker deployment is blocked until ownership and storage are redesigned.
- The default local JSON storage root is `backend/storage/sessions/`. `MYAGENT_TASK_ROOT` remains the override for custom or persistent roots.
- Test files must be named with a `test_` prefix and live under the module/type directory that owns the behavior.

## Input And Output Examples

Create a visible conversation:

```text
Input: POST /api/tasks without a message, then POST /api/tasks/{task_id}/messages with "你好".
Output: the task stores a user message with run_id, starts a run, and GET /api/tasks includes the conversation title.
```

Upload a mixed source batch:

```text
Input: POST /api/tasks/{task_id}/files with tender.md, alpha.json, and beta.json.
Output: all valid files are stored under uploads/, upload_count includes them, and the next run manifest records source_format for each file.
```

Continue an old conversation:

```text
Input: POST /api/tasks/{task_id}/messages after the previous run is complete.
Output: the same task gains a new run and prior messages remain. Previous uploads are reused only when the resolved input scope is task_uploads.
```

Ask an unrelated follow-up after uploads:

```text
Input: POST /api/tasks/{task_id}/messages with "请告诉今天的天气" after earlier uploads.
Output: the run manifest records intent search or chat, selected_uploads [], no DeepAgent workspace upload snapshots, and no document-analysis plan/subagent events.
```

Synthesize search results:

```text
Input: POST /api/tasks/{task_id}/messages with "上海今天的天气怎么样" and search is configured.
Output: events include search_tool_call, search_tool_result, answer-generation live status, search_synthesis_completed, and search_completed for the run; the assistant message is a synthesized Chinese answer without a backend-appended reference block, while bounded source metadata remains in events.
```

Continue document work:

```text
Input: POST /api/tasks/{task_id}/messages with "继续根据刚才这些文件分析".
Output: with DeepAgent available, the run manifest records route deep_agent and available upload snapshots; file reads occur only if the model calls audited file tools. If DeepAgent is unavailable, the run records a warning and falls back to deterministic document analysis.
```

Render a DeepAgent run:

```text
Input: DeepAgents stream emits safe lifecycle, tool-call, file-audit, and final assistant-answer data for run-1.
Output: task events include sanitized deep_agent_activity/file_tool_audit/reasoning_trace rows for run-1 plus optional live metadata, task messages include exactly one assistant final answer for run-1, and the frontend renders user message -> execution-log card -> AI回复 card with artifact footer when artifacts exist.
```

Record orchestration strategy:

```text
Input: a complex bid-comparison task with one tender and three bidder files.
Output: the main agent records a safe `orchestration_decision` with strategy multi_agent, bidder_count 3, chosen_profile_id bid_multi_agent, and planned_subagents matching the runtime factory subagent list; the decision is separate from stream/invoke execution_mode.
```

Promote canonical bid outputs:

```text
Input: DeepAgent writes outputs/report.html, outputs/final-summary.md, outputs/evidence.json, and outputs/task-plan.md for a recognized bid workflow.
Output: validated outputs are promoted as report.html, final-summary.md, evidence.json, and task-plan.md; evidence.json contains every bidder pair with findings or explicit no-finding records.
```

Copy a user message:

```text
Input: frontend user message content is "继续根据刚才这些文件分析".
Output: the footer shows time before a hover/focus-revealed copy control; clicking copy writes exactly "继续根据刚才这些文件分析" to the clipboard and briefly changes the copy icon into a warm checkmark state, without labels, timestamps, run logs, or hidden metadata.
```

Open a run report:

```text
Input: frontend opens report.html for run-2.
Output: it fetches /api/tasks/{task_id}/runs/run-2/artifacts/report.html with the configured access-token header before creating a blob URL.
```

Configure LAN access:

```text
Input: frontend is opened at http://<LAN_IP>:3001.
Output: backend MYAGENT_CORS_ORIGINS includes http://<LAN_IP>:3001, backend access token is set, and frontend NEXT_PUBLIC_MYAGENT_TOKEN matches that token.
```

## Boundary Conditions

- `idle`, `needs_input`, `complete`, `failed`, `cancelled`, and `interrupted` are startable states.
- `running` is not startable. Orphaned running tasks are marked interrupted before recovery actions proceed.
- Empty tasks may exist on disk, but they must not appear in `GET /api/tasks` until they have a user message.
- A create-task request containing `message` should return 400 and must not create a task directory.
- Missing required document uploads move the active run and task to `needs_input` with `required_file_type: markdown_or_json`.
- Needs-input payload keys such as `required_file_type`, `minimum_bidder_documents`, and `current_bidder_documents` remain machine-readable and stable.
- Runtime JSON parse failures after a previously valid upload indicate local storage drift or corruption and should fail the run with a filename-specific error.
- JSON upload and runtime parse failures should keep filenames visible but must not expose raw parser text such as Python or Pydantic English messages.
- `TaskStorage.get_task()` may derive `events`, `artifacts`, `upload_count`, and `run_count`, but derived fields are not persisted back as authoritative data.
- Top-level artifact URLs resolve to the latest completed run containing that artifact name, then fall back to legacy top-level files.
- Frontend message submission sends `mode` only for normal first-party runs. The composer intentionally does not expose Auto/Do not use files/Use files choices; file relevance is decided by backend routing and, for DeepAgent runs, by the model's audited file-tool calls.
- Frontend run activity grouping suppresses setup-only `task_created` and `file_uploaded` fallback history when real run cards exist, while preserving unmatched warning/error logs.
- Frontend run activity grouping must include every backend-provided run artifact name or artifact record; filtering to report-like or HTML-only names hides valid generated files.
- Frontend normalizes `deep_agent_activity` into `ExecutionLog.agentActivity` only when `schema_version`, enum fields, and required safe text fields are valid. Malformed activity payloads fall back to normal log rendering and must not expose arbitrary payload JSON in DOM or copied logs.
- Frontend normalizes `reasoning_trace` into `ExecutionLog.reasoning` only when the payload is valid. Malformed reasoning payloads fall back to normal log rendering and must not expose arbitrary payload JSON in DOM or copied logs.
- Frontend normalizes optional `payload.live` into `ExecutionLog.live` only when `schema_version`, kind, stage/status enums, bounded IDs, primitive parameter items, and result counts are valid. Malformed live metadata is ignored and must not expose arbitrary payload fields in DOM or copied logs.
- Frontend live-log projection pairs tool call/result events by `tool_call_id`, then uses chronological same-tool FIFO fallback only for legacy data that lacks ids. Tool cards are collapsed by default; their title shows agent, tool, and bounded parameters, while the expanded body shows only a generic result summary.
- Frontend run cards default to user-facing live summaries rather than historical technical reasoning dumps. Running tasks show one active animated status row such as `正在生成回答...`; completed history keeps terminal summaries and tool cards without exposing raw reasoning traces by default. Non-live info/success events should not fall back to raw technical titles in the live log; warning/error fallbacks use generic user-facing status text.
- `deep_agent_activity` field limits are strict user-visible bounds: `title` 120 characters, `summary` 1,000, `tool_name` 80, `parameter_summary` 240, `result_summary` 360, `source_event_id` and `related_event_id` 160 each, `subgraph_path` up to 8 items of 80 characters each, and serialized payload target max 8 KB. Over-limit values are truncated, `truncated: true` is set, and raw overflow text is not stored elsewhere.
- `deep_agent_activity` sanitization must redact API keys, access tokens, bearer tokens, authorization headers, known canary patterns, Windows drive-letter paths, UNC paths, and Posix absolute private paths. It must never include uploaded file body text, raw prompts, raw provider chunks, raw model/tool result bodies, raw DeepAgents `/conversation_history/`, raw `/large_tool_results/`, provider keys, authorization headers, or local absolute paths.
- DeepAgents `updates` chunks may create lifecycle/progress `deep_agent_activity` rows for subgraph boundaries, phase changes, and task/tool lifecycle boundaries. DeepAgents `messages` chunks are used only to accumulate the final answer candidate, emit safe `answer_status` live progress, and derive safe tool lifecycle summaries; intermediate assistant-like text is not persisted as `ChatMessage`.
- Malicious or accidental tool output that resembles a final answer must not become the final assistant message. The final answer is selected only from safe assistant content after stream completion or the explicit `invoke()` fallback result.
- High-frequency DeepAgents progress must not create per-token/per-chunk storage noise. Coalesce identical `task_id + run_id + subgraph_path + phase + status` running/progress activity within a 1-2 second storage window and avoid appending more than one activity event per 250-500 ms burst, while always preserving `started`, major phase change, `completed`, and `failed` boundaries.
- DeepAgent audited file tools normalize absolute paths inside the run workspace to workspace-relative paths. Traversal or outside-workspace paths are denied and audited without writing raw absolute paths into payloads.
- Windows drive-letter and UNC paths supplied to DeepAgent audited tools must be treated as absolute outside-workspace paths and redacted to `<outside-workspace>/<basename>` in audit payloads.
- DeepAgent audited writes are atomic: content is written to a temporary sibling file and published with replace only after completion. Cancellation during a write removes the temporary file, keeps the target unpublished, and records `status: cancelled` with `partial: true` only when bytes were written before cancellation.
- DeepAgent audited writes outside `records/` and `outputs/` are denied. Writes must not mutate upload snapshots or original task uploads.
- DeepAgents internal virtual paths `/large_tool_results/` and `/conversation_history/` are mapped into audited `records/deepagents/` storage, while the backend returns the original virtual paths to DeepAgents. User-visible and persisted logs must not expose those internal virtual paths or `records/deepagents/...`; audit/activity/reasoning payloads use the neutral internal placeholder instead.
- Cancellation before or during DeepAgent file operations must raise through the existing cancellation controller and emit an audit record with `status: cancelled`.
- Search synthesis fallback must not persist raw Tavily response bodies, raw provider messages, or arbitrary tool result JSON as assistant content, event detail, DOM text, copied logs, or knowledge-pack examples.
- Live-log copied text uses the same safe frontend projection as the rendered log card. It must not include raw hidden reasoning, source URLs from tool results, provider raw chunks, uploaded body text, raw tool result bodies, or arbitrary malformed payload fields.
- Bid artifact promotion must be all-or-safe: malformed canonical evidence blocks promotion of the malformed canonical report path or routes through deterministic normalization, rather than publishing a report that disagrees with `evidence.json`.
- Upload request limits and JSON body limits are enforced before task mutation. Uploaded `.json` files use upload file/request limits, not the API JSON body limit.
- Invalid uploaded JSON rejects the upload request with no partial batch persistence.
- Task APIs are loopback-only when no access token is configured. Non-loopback task access without a configured token returns `403`; missing or wrong token returns `401` when a token is configured.
- CORS entries are origins, not URLs with paths. Use exact origins such as `http://<LAN_IP>:3001`.
- Frontend polling runs only while `isTaskActive(status)` is true, and incremental event refresh appends only unseen log IDs.
- Long messages, log details, filenames, model labels, file cards, and composer controls must wrap or ellipsize without overlapping at mobile widths.
- Malformed `orchestration_decision` payloads fall back to normal log rendering without exposing arbitrary payload JSON in DOM or copied logs.
- Agent Profile validation must reject duplicate subagent names, empty or overlong descriptions/prompts, unknown tool aliases, missing runtime implementations for selected safe tool aliases, unsafe model overrides, and any enabled compiled factory in V1.
- Composer/message-card alignment must preserve the assistant marker gutter on desktop and mobile widths, while empty-state composer centering stays independent of conversation-card alignment.
- Frontend component refactors must keep API/token handling in `frontend/lib/task-api.ts` and task orchestration in `frontend/hooks/use-task-workspace.ts`; presentational chat components should receive normalized data and callbacks instead of creating parallel fetch or polling flows.
- Copy feedback must be per button/keyed target and time out automatically; copying one message or log card must not permanently mark unrelated copy controls as successful.
- Visual-only restyling must preserve existing task creation, upload, message submission, model selection, polling, artifact opening/downloading, log copying, and notice rendering behavior.
- Frontend development uses `NEXT_DIST_DIR=.next-dev`; production builds use `.next`. Do not let `next dev` and `next build` write the same dist directory, and run only one Next.js dev server against a single dev dist directory at a time.

## Known Pitfalls

- Do not reintroduce a create-task path that persists user messages outside `TaskRunner.start()`.
- Do not list blank draft tasks in history summaries.
- Do not overwrite old run artifacts when adding follow-up support.
- Do not create path-taking artifact APIs for run outputs; use `{run_id}` plus a normalized artifact name.
- Do not drop token checks from list, detail, event, upload, message, cancel, or artifact routes.
- Do not assume all old task states already contain `runs`; legacy synthesis must stay readable.
- Do not accept JSON uploads by MIME type alone or add a separate JSON upload endpoint unless JSON becomes a distinct workflow.
- Do not translate stored machine fields to satisfy UI copy requirements.
- Do not rebuild sidebar history from local messages; that loses persisted conversations on refresh and backend restart.
- Do not render backend task errors, needs-input notices, or frontend workspace warnings as full-width detached banners.
- Do not turn the workspace into a marketing landing page when applying the warm editorial visual system; keep the first screen usable as the task composer and history workspace.
- Do not reintroduce the old cool-blue/slate visual theme for primary actions, selected states, or run chrome unless the frontend visual-token contract is intentionally replaced.
- Do not flatten multi-run logs and artifacts into one undifferentiated result area.
- Do not place artifact actions only inside a log card footer.
- Do not let the sticky composer obscure the newest assistant output after logs or artifacts are inserted.
- Do not pass `AuditedWorkspaceTools` instances, task directories, or absolute paths directly into DeepAgent code; pass only the callables returned by the adapter.
- Do not pass raw DeepAgent output filenames directly into artifact storage; promote them through the artifact-safe naming boundary so ordinary model-created names with spaces or punctuation cannot fail an otherwise successful run.
- Do not import or depend on local DeepAgents reference-project code; MyAgent runtime should use its adapter around the installed DeepAgents package and keep the optional-dependency fallback intact.
- Do not persist raw DeepAgents stream chunks, raw LangGraph event payloads, raw provider messages, raw tool results, or raw hidden reasoning in `events.jsonl`, task messages, frontend state, DOM, or clipboard text.
- Do not enable DeepAgents raw `custom` stream mode as a shortcut for UI logs. `custom` is reserved for MyAgent-authored progress events with stable schemas.
- Do not use `FilesystemBackend`, `LocalShellBackend`, shell execution, or a project-root DeepAgents backend in place of `AuditedDeepAgentBackend`.
- Do not create extra assistant messages for execution progress. DeepAgent execution details belong in run events and the execution-log card; only the final answer belongs in the assistant message history.
- Do not let the UI or API submit arbitrary subagent specs, compiled agents, raw backends, shell tools, callables, or local paths. Multi-agent profiles are backend-owned until a future security design explicitly changes that boundary.
- Do not record `multi_agent` in `orchestration_decision` while passing the default subagent set to the DeepAgents factory.
- Do not let malformed `deep_agent_activity` payloads leak arbitrary JSON through the frontend fallback log detail or copied execution-log text.
- Do not reintroduce a first-party composer file-use segmented control. Actual DeepAgent file use should be inferred from `file_tool_audit`, not from a user-selected scope.
- Do not reintroduce `/agent-robot.svg` or hand-drawn CSS robot backgrounds for assistant sender markers unless the reference avatar contract is intentionally replaced.
- Do not move token-aware fetch, polling, or artifact blob handling back into `frontend/app/page.tsx` or individual presentational message components.
- Do not add `deepagents` as a hard dependency unless the test strategy and fallback behavior are updated in the same change.
- Do not implement `reasoning_trace` aliases such as `agent_thinking` or `reasoning_step`, and do not reuse `model_result` as the frontend thinking-summary contract.
- Do not display raw hidden chain-of-thought or provider/model raw reasoning output. Product copy may say `思考摘要`, but the stored/displayed content must remain a safe summary.
- Do not hard-code `参考来源` into successful search answers; source metadata belongs in bounded events, and model-generated Markdown references should pass through naturally.
- Do not make tool-card UI specific to Tavily or any other single tool. Tool cards should use generic live metadata and should not display source links or raw result bodies in expanded content.
- Do not enable raw HTML rendering in assistant Markdown; keep `react-markdown` plus GFM without `rehype-raw` unless a separate sanitizer design is added.
- Do not expose provider credentials through `NEXT_PUBLIC_*` values.
- Do not document fixed private LAN IPs, customer documents, local absolute private paths, secrets, tokens, deleted filenames, temporary script paths, or dated patch timelines in knowledge packs.

## Related Code Paths

- `backend/app/main.py`
- `backend/app/agent_profiles.py`
- `backend/app/runner.py`
- `backend/app/intent.py`
- `backend/app/deep_agent_runtime.py`
- `backend/app/orchestrator.py`
- `backend/app/storage.py`
- `backend/app/analysis.py`
- `backend/app/model_provider.py`
- `backend/app/settings.py`
- `backend/app/schemas.py`
- `backend/app/tools.py`
- `backend/storage/sessions/`
- `frontend/app/page.tsx`
- `frontend/components/chat/TaskWorkspace.tsx`
- `frontend/components/chat/TaskConversation.tsx`
- `frontend/components/chat/ChatComposer.tsx`
- `frontend/components/chat/ChatSidebar.tsx`
- `frontend/components/chat/RobotAvatar.tsx`
- `frontend/hooks/use-task-workspace.ts`
- `frontend/lib/task-api.ts`
- `frontend/app/file-upload.ts`
- `frontend/app/model-ui.ts`
- `frontend/app/task-state.ts`
- `frontend/app/workspace-view.ts`
- `frontend/app/globals.css`
- `frontend/app/layout.tsx`
- `frontend/next.config.mjs`
- `frontend/package.json`
- `frontend/tsconfig.json`
- `frontend/eslint.config.mjs`
- `scripts/dev-terminal-runner.sh`
- `backend/.env.example`
- `frontend/.env.example`

## Related Test Paths

- `backend/tests/workflow/test_workflow.py`
- `backend/tests/runtime/test_intent_router.py`
- `backend/tests/runtime/test_deep_agent_runtime.py`
- `backend/tests/runtime/test_reasoning_trace.py`
- `frontend/tests/state/test_task_state.test.ts`
- `frontend/tests/workspace/test_frontend_architecture.test.ts`
- `frontend/tests/workspace/test_workspace_view.test.ts`
- `frontend/tests/upload/test_file_upload.test.ts`
- `frontend/tests/model/test_model_ui.test.ts`

DeepAgent two-card/activity coverage should live in the existing paths above:

- `backend/tests/runtime/test_deep_agent_runtime.py`: Agent Profile registry validation, selected-profile factory arguments, subagent audited tool mapping, stream call kwargs (`subgraphs=True`, `version="v2"`, `stream_mode=["updates", "messages"]`), `deep_agent_activity` schema/sanitization, safe answer-status live events, safe final-answer selection, `invoke()` fallback, optional dependency behavior, high-frequency activity coalescing, and DeepAgent bid-output promotion rules including canonical-output evidence validation.
- `backend/tests/workflow/test_workflow.py`: API-level successful/failing DeepAgent runs, profile selection consistency between run manifest/orchestration event/runtime factory, upload-reference bid prompt routing, search synthesis event order, exactly one user and one assistant message per run, `deep_agent_activity` plus `file_tool_audit` plus `reasoning_trace`, every created run's terminal safe reasoning coverage, generic reasoning idempotency on DeepAgent/document routes, incremental `/events` polling, orchestration decision records, bounded search source summaries, missing-provider fallback summaries, no raw Tavily JSON or provider content in final assistant content/event payloads, canonical bid artifacts, evidence pair coverage, and final task status.
- `backend/tests/runtime/test_intent_router.py`: search/weather after uploads route without selected uploads; multi-document bid markers with uploads route to the DeepAgent/document-analysis path.
- `backend/tests/runtime/test_reasoning_trace.py`: shared redaction/truncation canaries when activity sanitization reuses reasoning sanitizers, including prompt/upload/private-path/provider-key leakage guards for `reasoning_trace` payloads and provider `reasoning_content` non-disclosure.
- `frontend/tests/state/test_task_state.test.ts`: valid activity normalization to `ExecutionLog.agentActivity`, terminal `task-run` reasoning normalization, optional orchestration/profile/activity field normalization, invalid enum/missing-field rejection, malformed payload non-disclosure, unknown optional field ignore behavior, long/truncated field safety, exact user-message copy wiring, copy feedback state, and user footer time-before-copy order.
- `frontend/tests/workspace/test_workspace_view.test.ts`: user -> execution-log card -> `AI回复` card order, assistant artifact footer dedupe, live-log projection and clipboard text, legacy same-tool FIFO pairing without ids, non-live technical-title suppression, Markdown renderer usage, composer-to-message-card alignment CSS, live-log width/copy checkmark CSS, user-copy hover/focus reveal CSS, text-only empty-state wordmark CSS, and reference robot-avatar CSS.
- `frontend/tests/workspace/test_frontend_architecture.test.ts`: route-shell delegation, chat component/hook/API-client file boundaries, and lucide Bot avatar geometry.

## Verification Commands

```bash
cd backend && uv run pytest tests/runtime/test_deep_agent_runtime.py
cd backend && uv run pytest tests/runtime/test_reasoning_trace.py
cd backend && uv run pytest tests/workflow/test_workflow.py
cd backend && uv run pytest
cd backend && uv run ruff check .
cd backend && uv run mypy app tests
cd frontend && npm run typecheck
cd frontend && npm test
cd frontend && npm run lint
cd frontend && npm run build
git diff --check
```

For documentation-only edits, `git diff --check` is the minimum check. For test-layout changes, run the affected backend and frontend test commands.

## Regression Risks

- Follow-up messages accidentally starting a separate task instead of a new run in the existing task.
- A later run replacing an earlier run's report, evidence, summary, or artifact metadata.
- Restart recovery losing run metadata, artifact URLs, or message `run_id` values.
- Artifact traversal through encoded separators or unlisted names.
- History ordering drifting from newest activity.
- New backend event sources emitting English user-visible text that bypasses the frontend legacy whitelist.
- Reasoning summaries accidentally leaking uploaded document bodies, raw prompts, raw provider output, DeepAgent internal history, provider key values, authorization headers, or absolute local paths.
- Frontend reasoning rendering expanding malformed payload JSON or hiding warning/error logs when collapsed.
- DeepAgent stream projection leaking raw stream chunks, raw tool result bodies, `/conversation_history/`, `/large_tool_results/`, provider chunks, or hidden reasoning into storage, DOM, or clipboard output.
- DeepAgent progress accidentally becoming extra assistant messages, which pollutes chat history and breaks the two-card AI-side contract.
- Search/weather completing with only tool result formatting, raw JSON, or a numbered source list instead of a synthesized final answer.
- Search completion writing `complete` before `search_synthesis_completed` and `search_completed` are persisted for the same `run_id`.
- Inferring single-agent versus multi-agent orchestration from `execution_mode`, causing stream/invoke transport details to masquerade as product decisions.
- Agent Profile selection or compilation drift causing `run.json`, `orchestration_decision`, runtime factory subagents, and subagent audited tools to disagree.
- User-configurable subagent specs enabling prompt injection, tool alias escalation, unsafe model overrides, raw backend use, or unbounded event payloads.
- Canonical bid reports being promoted while `evidence.json` lacks required fields, omits no-finding pair coverage, or uses prefixed DeepAgent names for recognized bid outputs.
- Frontend rendering the final answer before the execution-log card, omitting the execution-log card for successful logged runs, or copying labels/metadata instead of exact user-message content from user bubbles.
- Composer width drifting away from assistant message-card width after responsive-token edits, especially when the left marker gutter or empty-state composer is changed.
- Assistant sender markers drifting from the reference TenderWord blue lucide Bot avatar after CSS or component rewrites.
- Reintroducing decorative generated glyphs around the empty-state `MYAGENT` wordmark after it has been made text-only.
- Task API calls splitting across route, hook, and presentational components, causing duplicated polling, stale token handling, or artifact-open regressions.
- Copy success styling appearing before clipboard writes complete, sticking forever after navigation, or marking all copy controls when only one button was used.
- Activity coalescing dropping `started`, major phase change, `completed`, or `failed` boundary events, or failing to bound high-frequency `running` events.
- Malformed `deep_agent_activity` payloads exposing arbitrary JSON because frontend fallback rendering treats unknown payload fields as safe detail.
- Breaking create-task, upload, and message-send order so analysis runs without selected files.
- Dropping access-token headers when opening or downloading artifacts.
- Regressing upload support back to Markdown-only behavior.
- Moving tests without updating runner globs, imports, AGENTS.md, README.md, and this package index.
