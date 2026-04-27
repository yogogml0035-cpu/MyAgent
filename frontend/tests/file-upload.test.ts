import assert from "node:assert/strict";
import test from "node:test";

import {
  FILE_INPUT_ACCEPT,
  isMarkdownUploadFile,
  partitionMarkdownUploadFiles,
  type UploadFileCandidate,
} from "../app/file-upload";

function candidate(name: string, type = ""): UploadFileCandidate {
  return { name, type };
}

test("native file picker does not hide non-markdown downloads", () => {
  assert.equal(FILE_INPUT_ACCEPT, undefined);
});

test("isMarkdownUploadFile accepts markdown filenames that match backend validation", () => {
  assert.equal(isMarkdownUploadFile(candidate("bid.md")), true);
  assert.equal(isMarkdownUploadFile(candidate("BID.MD")), true);
  assert.equal(isMarkdownUploadFile(candidate("export", "text/markdown")), false);
});

test("partitionMarkdownUploadFiles separates markdown files from other visible files", () => {
  const bid = candidate("bid.md");
  const contentList = candidate("1102665_content_list.json", "application/json");
  const notes = candidate("notes.txt", "text/plain");

  const result = partitionMarkdownUploadFiles([bid, contentList, notes]);

  assert.deepEqual(result.markdownFiles, [bid]);
  assert.deepEqual(result.rejectedFiles, [contentList, notes]);
});
