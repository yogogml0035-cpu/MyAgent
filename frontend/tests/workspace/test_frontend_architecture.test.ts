import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import test from "node:test";

test("home route delegates task workspace implementation to chat components", () => {
  const pageSource = readFileSync(new URL("../../app/page.tsx", import.meta.url), "utf-8");

  assert.match(pageSource, /import \{ TaskWorkspace \} from "\.\.\/components\/chat\/TaskWorkspace";/);
  assert.match(pageSource, /return <TaskWorkspace \/>;/);
  assert.equal(pageSource.includes("requestTaskJson"), false);
  assert.equal(pageSource.includes("renderChatMessage"), false);
});

test("task workspace follows components, hook, and api-client boundaries", () => {
  const expectedPaths = [
    "../../components/chat/TaskWorkspace.tsx",
    "../../components/chat/TaskConversation.tsx",
    "../../components/chat/ChatComposer.tsx",
    "../../components/chat/ChatSidebar.tsx",
    "../../hooks/use-task-workspace.ts",
    "../../lib/task-api.ts",
  ];

  expectedPaths.forEach((path) => {
    assert.equal(existsSync(new URL(path, import.meta.url)), true, path);
  });
});

test("history sidebar exposes compact rename and delete actions", () => {
  const sidebarSource = readFileSync(
    new URL("../../components/chat/ChatSidebar.tsx", import.meta.url),
    "utf-8",
  );
  const workspaceSource = readFileSync(
    new URL("../../components/chat/TaskWorkspace.tsx", import.meta.url),
    "utf-8",
  );
  const cssSource = readFileSync(new URL("../../app/globals.css", import.meta.url), "utf-8");

  assert.equal(sidebarSource.includes("historyMenuButton"), true);
  assert.equal(sidebarSource.includes("重命名"), true);
  assert.equal(sidebarSource.includes("删除"), true);
  assert.equal(sidebarSource.includes("historyRenameForm"), true);
  assert.equal(workspaceSource.includes("onRenameConversation"), true);
  assert.equal(workspaceSource.includes("onDeleteConversation"), true);
  assert.match(cssSource, /\.historyActionMenu\s*\{[\s\S]*?position: absolute;[\s\S]*?box-shadow:/);
  assert.match(cssSource, /\.historyActionMenu\s*\{[\s\S]*?background:[\s\S]*?var\(--surface\);/);
  assert.match(
    cssSource,
    /\.historyMenuButton:hover,\s*\n\.historyMenuButton\[aria-expanded="true"\]\s*\{[\s\S]*?color: var\(--primary-active\);/,
  );
  assert.match(cssSource, /\.historyMenuButton\s*\{[\s\S]*?border: 0;/);
  assert.match(cssSource, /\.historyMenuButton:focus-visible\s*\{[\s\S]*?outline: none;/);
  assert.match(cssSource, /\.historyMenuItem-danger\s*\{[\s\S]*?color: var\(--text-strong\);/);
  assert.match(
    cssSource,
    /\.historyMenuItem-danger:hover,\s*\n\.historyMenuItem-danger:focus-visible\s*\{[\s\S]*?background: rgba\(204, 120, 92, 0\.1\);[\s\S]*?color: var\(--primary-active\);/,
  );
  assert.equal(cssSource.includes("#dbe5f3"), false);
  assert.equal(cssSource.includes("#31415c"), false);
  assert.equal(cssSource.includes("#e11d48"), false);
  assert.equal(cssSource.includes("#fff1f2"), false);
});

test("frontend dev server uses the default Next dist directory", () => {
  const nextConfigSource = readFileSync(
    new URL("../../next.config.mjs", import.meta.url),
    "utf-8",
  );
  const packageSource = readFileSync(
    new URL("../../package.json", import.meta.url),
    "utf-8",
  );
  const devRunnerSource = readFileSync(
    new URL("../../../scripts/dev-terminal-runner.sh", import.meta.url),
    "utf-8",
  );
  const eslintConfigSource = readFileSync(
    new URL("../../eslint.config.mjs", import.meta.url),
    "utf-8",
  );
  const tsconfigSource = readFileSync(
    new URL("../../tsconfig.json", import.meta.url),
    "utf-8",
  );
  const gitignoreSource = readFileSync(
    new URL("../../.gitignore", import.meta.url),
    "utf-8",
  );

  assert.doesNotMatch(nextConfigSource, /NEXT_DIST_DIR/);
  assert.match(
    nextConfigSource,
    /watchOptions:\s*\{[\s\S]*?pollIntervalMs: Number\(process\.env\.NEXT_WATCH_POLL_INTERVAL_MS \|\| "300"\),/,
  );
  assert.match(nextConfigSource, /distDir:\s*isDevServer \? "\.next-dev" : "\.next"/);
  assert.match(
    packageSource,
    /"dev": "WATCHPACK_POLLING=true CHOKIDAR_USEPOLLING=true CHOKIDAR_INTERVAL=300 next dev -p 3001"/,
  );
  assert.match(packageSource, /"typecheck": "next typegen && tsc --noEmit"/);
  assert.doesNotMatch(devRunnerSource, /NEXT_DIST_DIR/);
  assert.match(devRunnerSource, /WATCHFILES_FORCE_POLLING="\$\{WATCHFILES_FORCE_POLLING:-true\}"/);
  assert.match(devRunnerSource, /WATCHPACK_POLLING="\$\{WATCHPACK_POLLING:-true\}"/);
  assert.match(eslintConfigSource, /"\.next\/\*\*"/);
  assert.match(tsconfigSource, /"\.next\/types\/\*\*\/\*\.ts"/);
  assert.match(tsconfigSource, /"\.next-dev\/types\/\*\*\/\*\.ts"/);
  assert.match(gitignoreSource, /^next-env\.d\.ts$/m);
});

test("robot avatar uses the same lucide Bot geometry as the reference frontend", () => {
  const avatarSource = readFileSync(
    new URL("../../components/chat/RobotAvatar.tsx", import.meta.url),
    "utf-8",
  );

  ["M12 8V4H8", "M2 14h2", "M20 14h2", "M15 13v2", "M9 13v2"].forEach((path) => {
    assert.equal(avatarSource.includes(path), true, path);
  });
  assert.match(avatarSource, /<rect height="12" rx="2" width="16" x="4" y="8" \/>/);
});
