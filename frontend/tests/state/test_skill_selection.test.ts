import assert from "node:assert/strict";
import test from "node:test";

import {
  filterSkillOptions,
  findActiveSkillSlashToken,
  normalizeSkillOption,
  normalizeSkillOptions,
  replaceActiveSkillSlashToken,
  type SkillOption,
} from "../../app/skill-selection";

const SKILL_OPTIONS: SkillOption[] = [
  {
    name: "code-review",
    description: "Review code changes for regressions",
  },
  {
    name: "web-research",
    description: "Search the web and cite sources",
  },
];

test("normalizeSkillOption keeps only browser-safe string fields", () => {
  const option = normalizeSkillOption({
    name: " web-research ",
    description: " Search current web sources ",
    path: "/private/backend/skills/web_research/SKILL.md",
    body: "SHOULD_NOT_RENDER",
  });

  assert.deepEqual(option, {
    name: "web-research",
    description: "Search current web sources",
  });
  assert.deepEqual(Object.keys(option ?? {}), ["name", "description"]);
  assert.equal(normalizeSkillOption({ name: 42, description: "bad" }), null);
  assert.deepEqual(normalizeSkillOption({ name: "code-review", description: 42 }), {
    name: "code-review",
    description: "",
  });
});

test("normalizeSkillOptions ignores non-array and invalid skill entries", () => {
  assert.deepEqual(normalizeSkillOptions({ name: "web-research" }), []);
  assert.deepEqual(
    normalizeSkillOptions([
      { name: "web-research", description: "Search" },
      { name: "", description: "bad" },
      { description: "missing name" },
    ]),
    [{ name: "web-research", description: "Search" }],
  );
});

test("filterSkillOptions matches names and descriptions with slash queries", () => {
  assert.deepEqual(filterSkillOptions(SKILL_OPTIONS, "/web").map((option) => option.name), [
    "web-research",
  ]);
  assert.deepEqual(filterSkillOptions(SKILL_OPTIONS, "/CODE").map((option) => option.name), [
    "code-review",
  ]);
  assert.deepEqual(filterSkillOptions(SKILL_OPTIONS, "cite").map((option) => option.name), [
    "web-research",
  ]);
  assert.deepEqual(filterSkillOptions(SKILL_OPTIONS, "/missing"), []);
  assert.deepEqual(filterSkillOptions(SKILL_OPTIONS, "/").map((option) => option.name), [
    "code-review",
    "web-research",
  ]);
});

test("findActiveSkillSlashToken identifies the slash query around the cursor", () => {
  const value = "请使用 /web 分析";
  const token = findActiveSkillSlashToken(value, "请使用 /web".length);

  assert.deepEqual(token, {
    start: "请使用 ".length,
    end: "请使用 /web".length,
    query: "web",
  });

  assert.deepEqual(findActiveSkillSlashToken("/", 1), {
    start: 0,
    end: 1,
    query: "",
  });
});

test("findActiveSkillSlashToken ignores ordinary message body slashes", () => {
  assert.equal(findActiveSkillSlashToken("打开 src/app/page.tsx", "打开 src/app".length), null);
  assert.equal(findActiveSkillSlashToken("访问 https://example.test/api", 18), null);
  assert.equal(findActiveSkillSlashToken("请使用 /web 分析", "请使用 /web 分析".length), null);
});

test("replaceActiveSkillSlashToken removes the active slash token instead of appending trigger text", () => {
  const value = "请使用 /web 分析";
  const token = findActiveSkillSlashToken(value, "请使用 /web".length);

  assert.deepEqual(replaceActiveSkillSlashToken(value, token), {
    value: "请使用 分析",
    cursor: "请使用 ".length,
  });
  assert.deepEqual(replaceActiveSkillSlashToken("/web 继续输入", findActiveSkillSlashToken("/web 继续输入", 4)), {
    value: "继续输入",
    cursor: 0,
  });
  assert.deepEqual(replaceActiveSkillSlashToken("普通消息", null), {
    value: "普通消息",
    cursor: "普通消息".length,
  });
});
