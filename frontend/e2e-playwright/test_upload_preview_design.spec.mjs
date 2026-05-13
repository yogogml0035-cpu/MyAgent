import fs from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

const BASE_URL = process.env.MYAGENT_E2E_BASE_URL || "http://127.0.0.1:3001";
const EVIDENCE_DIR = process.env.MYAGENT_E2E_EVIDENCE_DIR;

function requirePath(value, name) {
  if (!value) {
    throw new Error(`${name} is required for upload-preview-design E2E`);
  }
  return value;
}

function writeFixtureFiles(evidenceDir) {
  const fixtureDir = path.join(evidenceDir, "fixtures");
  fs.mkdirSync(fixtureDir, { recursive: true });
  fs.writeFileSync(
    path.join(fixtureDir, "0811-DSITC261127-tender-params.docx"),
    "browser upload preview fixture\n",
    "utf8",
  );
  fs.writeFileSync(
    path.join(fixtureDir, "bid-resource-notes.txt"),
    "notes for selected upload preview\n",
    "utf8",
  );
  return fixtureDir;
}

test.use({ baseURL: BASE_URL });

test("selected upload preview matches the warm-canvas design", async ({ page }) => {
  test.setTimeout(60_000);

  const evidenceDir = requirePath(EVIDENCE_DIR, "MYAGENT_E2E_EVIDENCE_DIR");
  fs.mkdirSync(evidenceDir, { recursive: true });
  const fixtureDir = writeFixtureFiles(evidenceDir);

  await page.goto("/");
  await expect(page.getByPlaceholder("尽管问...")).toBeVisible();
  await page.screenshot({
    fullPage: true,
    path: path.join(evidenceDir, "01-empty-composer.png"),
  });

  await page.locator("#document-files").setInputFiles([
    path.join(fixtureDir, "0811-DSITC261127-tender-params.docx"),
    path.join(fixtureDir, "bid-resource-notes.txt"),
  ]);

  const fileCard = page.getByTestId("selected-file-card");
  await expect(fileCard).toBeVisible();
  await expect(fileCard.getByText("0811-DSITC261127-tender-params.docx")).toBeVisible();
  await expect(fileCard.getByText("bid-resource-notes.txt")).toBeVisible();
  await expect(page.getByTestId("selected-file-item")).toHaveCount(2);
  await expect(fileCard.locator("small")).toHaveCount(0);
  await expect(fileCard.getByLabel("更换已选文件")).toBeVisible();

  const firstFile = page.getByTestId("selected-file-item").first();
  await expect(firstFile).toHaveCSS("border-top-color", "rgb(230, 223, 216)");
  await expect(firstFile).toHaveCSS("border-top-left-radius", "8px");
  const firstRemoveButton = firstFile.getByRole("button", {
    name: "移除 0811-DSITC261127-tender-params.docx",
  });
  await expect(firstRemoveButton).toHaveCSS("opacity", "0");
  await fileCard.screenshot({ path: path.join(evidenceDir, "02-file-card-default.png") });

  await firstFile.hover();
  await expect(firstRemoveButton).toHaveCSS("opacity", "1");
  await fileCard.screenshot({ path: path.join(evidenceDir, "03-file-card-hover-remove.png") });
  await page.screenshot({
    fullPage: true,
    path: path.join(evidenceDir, "04-files-selected-full-page.png"),
  });

  await firstRemoveButton.click();
  await page.mouse.move(24, 24);
  await expect(page.getByTestId("selected-file-item")).toHaveCount(1);
  await expect(fileCard.getByText("0811-DSITC261127-tender-params.docx")).toBeHidden();
  await expect(fileCard.getByText("bid-resource-notes.txt")).toBeVisible();
  await expect(
    fileCard.getByRole("button", { name: "移除 bid-resource-notes.txt" }),
  ).toHaveCSS("opacity", "0");
  await fileCard.screenshot({ path: path.join(evidenceDir, "05-after-single-file-remove.png") });

  await page.setViewportSize({ width: 390, height: 760 });
  await page.mouse.move(24, 24);
  await expect(fileCard).toBeVisible();
  await expect(fileCard.getByText("bid-resource-notes.txt")).toBeVisible();
  await fileCard.screenshot({ path: path.join(evidenceDir, "06-file-card-mobile-detail.png") });
});
