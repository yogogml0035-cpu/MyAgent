import assert from "node:assert/strict";
import test from "node:test";

import {
  FILE_INPUT_ACCEPT,
  SUPPORTED_UPLOAD_LABEL,
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

test("isSupportedUploadFile accepts all backend-supported resource filenames", () => {
  assert.equal(isSupportedUploadFile(candidate("bid.md")), true);
  assert.equal(isSupportedUploadFile(candidate("BID.MD")), true);
  assert.equal(isSupportedUploadFile(candidate("content.json", "application/json")), true);
  assert.equal(isSupportedUploadFile(candidate("CONTENT.JSON")), true);
  assert.equal(isSupportedUploadFile(candidate("notes.txt", "text/plain")), true);
  assert.equal(isSupportedUploadFile(candidate("brief.docx")), true);
  assert.equal(isSupportedUploadFile(candidate("sheet.xlsx")), true);
  assert.equal(isSupportedUploadFile(candidate("macro.XLSM")), true);
  assert.equal(isSupportedUploadFile(candidate("export", "text/markdown")), false);
  assert.equal(isSupportedUploadFile(candidate("export", "application/json")), false);
  assert.equal(isSupportedUploadFile(candidate("legacy.doc")), false);
  assert.equal(isSupportedUploadFile(candidate("legacy.xls")), false);
  assert.equal(isSupportedUploadFile(candidate("data.csv")), false);
});

test("partitionSupportedUploadFiles separates supported files from other visible files", () => {
  const bid = candidate("bid.md");
  const contentList = candidate("1102665_content_list.json", "application/json");
  const notes = candidate("notes.txt", "text/plain");
  const workbook = candidate("analysis.xlsx");
  const csv = candidate("data.csv", "text/csv");

  const result = partitionSupportedUploadFiles([bid, contentList, notes, workbook, csv]);

  assert.deepEqual(result.supportedFiles, [bid, contentList, notes, workbook]);
  assert.deepEqual(result.rejectedFiles, [csv]);
});

test("supported upload label stays aligned with backend error copy", () => {
  assert.equal(SUPPORTED_UPLOAD_LABEL, "Markdown、JSON、TXT、DOCX、XLSX 或 XLSM 文件");
});
