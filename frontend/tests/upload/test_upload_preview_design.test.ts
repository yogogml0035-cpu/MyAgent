import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";

test("selected upload preview follows the warm-canvas design system", () => {
  const composerSource = readFileSync(
    new URL("../../components/chat/ChatComposer.tsx", import.meta.url),
    "utf-8",
  );
  const cssSource = readFileSync(new URL("../../app/globals.css", import.meta.url), "utf-8");

  assert.equal(composerSource.includes('data-testid="selected-file-card"'), true);
  assert.equal(composerSource.includes('data-testid="selected-file-item"'), true);
  assert.equal(composerSource.includes("fileIcon"), false);
  assert.equal(composerSource.includes("fileChipCopy"), false);
  assert.equal(composerSource.includes("formatFileSize"), false);
  assert.equal(composerSource.includes("removeFileGlyph"), true);
  assert.equal(composerSource.includes("更换已选文件"), true);
  assert.equal(composerSource.includes(">×<"), false);

  assert.match(cssSource, /\.filePreviewList\s*\{[\s\S]*?flex-wrap: wrap;/);
  assert.match(cssSource, /\.fileChip\s*\{[\s\S]*?border: 1px solid var\(--hairline\);/);
  assert.match(cssSource, /\.fileChip\s*\{[\s\S]*?background:[\s\S]*?rgba\(245, 240, 232, 0\.86\);/);
  assert.match(cssSource, /\.fileChip::before\s*\{[\s\S]*?background: rgba\(204, 120, 92, 0\.72\);/);
  assert.match(cssSource, /\.fileChip strong\s*\{[\s\S]*?text-overflow: ellipsis;/);
  assert.match(cssSource, /\.fileChip:hover \.removeFileButton,\s*\n\.fileChip:focus-within \.removeFileButton\s*\{[\s\S]*?opacity: 1;/);
  assert.equal(cssSource.includes(".fileIcon"), false);
});
