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

test("frontend dev server uses an isolated Next dist directory", () => {
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

  assert.match(nextConfigSource, /distDir: process\.env\.NEXT_DIST_DIR \|\| "\.next"/);
  assert.match(packageSource, /"dev": "NEXT_DIST_DIR=\.next-dev next dev -p 3001"/);
  assert.match(devRunnerSource, /export NEXT_DIST_DIR="\$\{NEXT_DIST_DIR:-\.next-dev\}"/);
  assert.match(eslintConfigSource, /"\.next-dev\/\*\*"/);
  assert.match(tsconfigSource, /"\.next-dev\/types\/\*\*\/\*\.ts"/);
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
