import assert from "node:assert/strict";
import test from "node:test";

import {
  FILE_INPUT_ACCEPT,
  isSupportedUploadFile,
  partitionSupportedUploadFiles,
  type UploadFileCandidate,
} from "../../app/file-upload";

function candidate(name: string, type = ""): UploadFileCandidate {
  return { name, type };
}

test("native file picker does not hide adjacent downloaded files", () => {
  assert.equal(FILE_INPUT_ACCEPT, undefined);
});

test("isSupportedUploadFile accepts markdown and json filenames that match backend validation", () => {
  assert.equal(isSupportedUploadFile(candidate("bid.md")), true);
  assert.equal(isSupportedUploadFile(candidate("BID.MD")), true);
  assert.equal(isSupportedUploadFile(candidate("content.json", "application/json")), true);
  assert.equal(isSupportedUploadFile(candidate("CONTENT.JSON")), true);
  assert.equal(isSupportedUploadFile(candidate("export", "text/markdown")), false);
  assert.equal(isSupportedUploadFile(candidate("export", "application/json")), false);
});

test("partitionSupportedUploadFiles separates supported files from other visible files", () => {
  const bid = candidate("bid.md");
  const contentList = candidate("1102665_content_list.json", "application/json");
  const notes = candidate("notes.txt", "text/plain");

  const result = partitionSupportedUploadFiles([bid, contentList, notes]);

  assert.deepEqual(result.supportedFiles, [bid, contentList]);
  assert.deepEqual(result.rejectedFiles, [notes]);
});
