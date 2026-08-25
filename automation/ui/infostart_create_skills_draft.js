const fs = require("fs");
const path = require("path");
const { chromium } = require("D:/bsl/skills/web-test/scripts/node_modules/playwright");

const repoRoot = path.resolve(__dirname, "../..");
const articleDir = path.join(repoRoot, "docs/articles/product_0_9_0_skills");
const html = fs.readFileSync(path.join(articleDir, "is/article.html"), "utf8");
const mediaDir = path.join(articleDir, "media");

const meta = {
  title: "1C AI Agent 0.9.3: skills и распознавание документов в 1С",
  shortTitle: "1C AI Agent 0.9.3: skills и документы",
  preview: "Переносимые JSON skills и прикладной сценарий: агент распознает счет, УПД, акт или счет-фактуру из PDF и создает заполненный черновик в 1С.",
  keywords: "1С, 1C, ИИ агент, AI Agent, skills, JSON, LLM, распознавание документов, OCR, первичные документы, БП, УНФ, DSL",
  editReason: "Добавлены распознавание документов, реальные скриншоты и видео для релиза 0.9.3",
  rutubeUrl: "https://rutube.ru/video/0322dc38ed4162ceae220fe00dc5a5d8/",
  cover: path.join(mediaDir, "supplier_invoice_02_result.png"),
  screenshots: [
    path.join(mediaDir, "skills_dsl_workflow.png"),
    path.join(mediaDir, "supplier_invoice_02_result.png"),
    path.join(mediaDir, "supplier_invoice_03_document.png"),
  ],
};

async function fillIfExists(page, selector, value) {
  const locator = page.locator(selector).first();
  if (await locator.count()) {
    await locator.fill(value);
    return true;
  }
  return false;
}

async function setSelects(page) {
  await page.evaluate(() => {
    function setSelect(name, values) {
      const select = document.querySelector(`select[name="${name}"]`);
      if (!select) return false;
      const vals = Array.isArray(values) ? values : [values];
      Array.from(select.options).forEach((option) => {
        option.selected = vals.includes(option.value);
      });
      select.value = vals[0] || "";
      select.dispatchEvent(new Event("change", { bubbles: true }));
      if (window.jQuery) window.jQuery(select).trigger("change");
      return true;
    }

    setSelect("PROPERTIES[OBJECT_VIEW][]", "22582");
    setSelect("PROPERTIES[CONFIG][]", ["6760", "26540", "71711"]);
    setSelect("PROPERTIES[OPENCODE]", "Y");
    setSelect("FIELDS[IBLOCK_SECTION_ID][]", ["1646"]);
    setSelect("FIELDS[IBLOCK_SECTION_ID_MAIN]", "1646");
    setSelect("PROPERTIES[CLASS_TYPE][]", "6669");
    setSelect("PROPERTIES[CLASS_PLATFORMS][]", "1960");
    setSelect("PROPERTIES[CLASS_OS][]", "6878");
    setSelect("PROPERTIES[CLASS_COUNTRY][]", "6759");
    setSelect("PROPERTIES[CLASS_WHO][]", "6659");
    setSelect("PROPERTIES[CLASS_INDUSTRY][]", "6769");
    setSelect("PROPERTIES[CLASS_TAX][]", "6876");
    setSelect("PROPERTIES[CLASS_ACCOUNT][]", "6767");

  });
}

async function setDetailHtml(page, bodyHtml) {
  await page.evaluate((value) => {
    const detail = document.querySelector('textarea[name="FIELDS[DETAIL_TEXT]"], textarea#DETAIL_TEXT');
    if (detail) {
      detail.value = value;
      detail.dispatchEvent(new Event("input", { bubbles: true }));
      detail.dispatchEvent(new Event("change", { bubbles: true }));
    }
    if (window.CKEDITOR?.instances?.DETAIL_TEXT) {
      window.CKEDITOR.instances.DETAIL_TEXT.setData(value);
      window.CKEDITOR.instances.DETAIL_TEXT.updateElement();
    }
  }, bodyHtml);
}

async function uploadImages(page) {
  const inputs = await page.locator('input[type="file"]').elementHandles();
  const report = [];
  for (let i = 0; i < inputs.length; i += 1) {
    const input = inputs[i];
    const accept = (await input.getAttribute("accept")) || "";
    const name = (await input.getAttribute("name")) || "";
    const id = (await input.getAttribute("id")) || "";
    const multiple = await input.getAttribute("multiple");
    if (!/image/i.test(accept)) {
      report.push({ index: i, name, id, accept, skipped: true });
      continue;
    }
    const isAnnouncement = multiple === null;
    const files = isAnnouncement ? [meta.cover] : meta.screenshots;
    try {
      if (multiple !== null || files.length === 1) {
        await input.setInputFiles(files);
      } else {
        for (const file of files) {
          await input.setInputFiles(file);
          await page.waitForTimeout(1500);
        }
      }
      report.push({ index: i, name, id, accept, multiple: multiple !== null, files: files.map((file) => path.basename(file)), ok: true });
      await page.waitForTimeout(2500);
    } catch (error) {
      report.push({ index: i, name, id, accept, ok: false, error: String(error.message || error) });
    }
  }
  return report;
}

async function clearScreenshots(page) {
  const removeButtons = page.locator('#dropzone [data-dz-remove]');
  let removed = 0;
  while (await removeButtons.count()) {
    await removeButtons.first().click();
    const confirmation = page.locator('#MsgBoxBack:has-text("Файл будет удален, продолжить?")');
    if (await confirmation.count()) {
      await confirmation.locator('button:has-text("Да")').click();
      await confirmation.waitFor({ state: "hidden", timeout: 10000 }).catch(() => {});
    }
    removed += 1;
    await page.waitForTimeout(300);
  }
  return removed;
}

async function resolveUploadedImageUrls(page) {
  return await page.locator('#dropzone .dz-preview').evaluateAll((previews) => Object.fromEntries(
    previews.map((preview) => {
      const name = preview.querySelector('[data-dz-name]')?.textContent?.trim() || "";
      const url = preview.querySelector('.fname-wrap a[href*="/upload/"]')?.href || "";
      return [name, url];
    }).filter(([name, url]) => name && url)
  ));
}

function useInfostartImageUrls(bodyHtml, uploadedImageUrls) {
  let result = bodyHtml;
  for (const [name, url] of Object.entries(uploadedImageUrls)) {
    const source = `https://raw.githubusercontent.com/msrv-tech/AI_agent/main/docs/articles/product_0_9_0_skills/media/${name}`;
    result = result.split(source).join(url);
  }
  return result.replace(
    /<p>\s*<img\b[^>]*src="https:\/\/raw\.githubusercontent\.com\/[^>]+>\s*<\/p>/gi,
    ""
  );
}

async function buttonsReport(page) {
  return await page.evaluate(() =>
    Array.from(document.querySelectorAll("button, input[type=submit], input[type=button]")).map((button) => ({
      text: (button.innerText || button.value || "").trim(),
      value: button.value || "",
      cls: button.className || "",
      name: button.name || "",
    }))
  );
}

async function main() {
  const profileDir = path.join(repoRoot, "temp", "infostart-chrome-profile");
  const artifactDir = path.join(repoRoot, "automation", "logs", "infostart_draft");
  fs.mkdirSync(profileDir, { recursive: true });
  fs.mkdirSync(artifactDir, { recursive: true });

  const context = await chromium.launchPersistentContext(profileDir, {
    headless: false,
    executablePath: "C:/Program Files/Google/Chrome/Application/chrome.exe",
    viewport: { width: 1366, height: 900 },
    args: ["--no-first-run", "--no-default-browser-check"],
  });
  const page = context.pages()[0] || await context.newPage();
  page.setDefaultTimeout(30000);

  const editUrl = process.env.INFOSTART_EDIT_URL || "https://infostart.ru/public/edit/";
  await page.goto(editUrl, { waitUntil: "domcontentloaded", timeout: 60000 });

  const editorSelector = 'input[name="FIELDS[NAME]"]';
  try {
    await page.waitForSelector(editorSelector, { timeout: 20000 });
  } catch (_) {
    console.log(JSON.stringify({ status: "needs_login", url: page.url() }, null, 2));
    await page.screenshot({ path: path.join(artifactDir, "needs_login.png"), fullPage: true });
    await page.waitForSelector(editorSelector, { timeout: 900000 });
  }

  if (process.env.INFOSTART_INSPECT_RUTUBE === "1") {
    const report = await page.evaluate(() => ({
      labels: Array.from(document.querySelectorAll("label, legend, summary"))
        .map((element) => ({
          text: (element.textContent || "").trim().replace(/\s+/g, " "),
          htmlFor: element.getAttribute("for") || "",
        }))
        .filter((item) => /rutube|видео/i.test(item.text)),
      fields: Array.from(document.querySelectorAll("input, textarea"))
        .map((element) => ({
          tag: element.tagName,
          type: element.type || "",
          id: element.id || "",
          name: element.name || "",
          value: element.value || "",
          placeholder: element.placeholder || "",
          outerHTML: element.outerHTML,
        }))
        .filter((item) => /rutube|видео|video/i.test(JSON.stringify(item))),
    }));
    console.log(JSON.stringify(report, null, 2));
    await context.close();
    return;
  }

  await fillIfExists(page, 'input[name="FIELDS[NAME]"]', meta.title);
  await fillIfExists(page, 'input[name="PROPERTIES[SHORT_TITLE]"]', meta.shortTitle);
  await fillIfExists(page, 'textarea[name="FIELDS[PREVIEW_TEXT]"]', meta.preview);
  await fillIfExists(page, 'textarea[name="PROPERTIES[KEYWORDS]"]', meta.keywords);
  await fillIfExists(page, 'textarea[name="PROPERTIES[EDIT_REASON]"]', meta.editReason);
  await fillIfExists(page, 'input[name="PROPERTIES[VIDEO_PRESENTATION_RUTUBE]"]', meta.rutubeUrl);
  await setDetailHtml(page, html);
  await setSelects(page);
  const removedScreenshots = process.env.INFOSTART_REPLACE_SCREENSHOTS === "1"
    ? await clearScreenshots(page)
    : 0;
  const uploads = process.env.INFOSTART_SKIP_UPLOAD === "1"
    ? [{ skipped: true, reason: "INFOSTART_SKIP_UPLOAD" }]
    : await uploadImages(page);
  const uploadedImageUrls = await resolveUploadedImageUrls(page);
  await setDetailHtml(page, useInfostartImageUrls(html, uploadedImageUrls));

  const buttons = await buttonsReport(page);
  fs.writeFileSync(path.join(artifactDir, "buttons_before_draft.json"), JSON.stringify(buttons, null, 2), "utf8");
  await page.screenshot({ path: path.join(artifactDir, "before_save_draft.png"), fullPage: true });

  const draftButton = page.locator([
    'button.BtnToDraft',
    'input.BtnToDraft',
    'button:has-text("Сохранить в черновик")',
    'input[value*="черновик"]',
    'button[name="ACTION"][value="SAVE"]',
    'input[name="ACTION"][value="SAVE"]',
  ].join(", ")).first();
  if (!(await draftButton.count())) {
    throw new Error("Не найдена кнопка сохранения в черновик. Модерацию не нажимаю.");
  }

  const navigation = page.waitForNavigation({ waitUntil: "domcontentloaded", timeout: 30000 }).catch(() => null);
  await draftButton.click();
  await navigation;
  await page.waitForTimeout(5000);

  const afterClick = await page.evaluate(() => ({
    url: location.href,
    messages: Array.from(document.querySelectorAll('#MsgBoxBack, .alert, .text-danger'))
      .map((element) => (element.textContent || "").trim())
      .filter(Boolean),
    invalid: Array.from(document.querySelectorAll(':invalid')).map((element) => ({
      name: element.getAttribute('name') || "",
      value: element.value || "",
    })),
  }));
  fs.writeFileSync(path.join(artifactDir, "after_click.json"), JSON.stringify(afterClick, null, 2), "utf8");
  await page.screenshot({ path: path.join(artifactDir, "after_click_before_reload.png"), fullPage: true });

  await page.goto(editUrl, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForSelector(editorSelector, { timeout: 30000 });
  const persistedTitle = await page.locator(editorSelector).inputValue();
  const persistedRutubeUrl = await page.locator('input[name="PROPERTIES[VIDEO_PRESENTATION_RUTUBE]"]').inputValue();
  const persistedScreenshots = await page.locator('#dropzone .dz-filename [data-dz-name]').allTextContents();
  const expectedScreenshots = meta.screenshots.map((file) => path.basename(file));
  const screenshotsMatch = persistedScreenshots.length === expectedScreenshots.length
    && expectedScreenshots.every((name) => persistedScreenshots.includes(name));
  const result = {
    status: persistedTitle === meta.title && persistedRutubeUrl === meta.rutubeUrl && screenshotsMatch
      ? "draft_saved"
      : "save_not_persisted",
    url: page.url(),
    uploads,
    uploadedImageUrls,
    removedScreenshots,
    title: meta.title,
    persistedTitle,
    persistedRutubeUrl,
    persistedScreenshots,
    afterClick,
  };
  fs.writeFileSync(path.join(artifactDir, "result.json"), JSON.stringify(result, null, 2), "utf8");
  await page.screenshot({ path: path.join(artifactDir, "after_save_draft.png"), fullPage: true });
  console.log(JSON.stringify(result, null, 2));
  await context.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
