const fs = require("fs");
const path = require("path");
const { chromium } = require("D:/bsl/skills/web-test/scripts/node_modules/playwright");

const repoRoot = path.resolve(__dirname, "../..");
const articleDir = path.join(repoRoot, "docs/articles/product_0_9_0_skills");
const html = fs.readFileSync(path.join(articleDir, "is/article.html"), "utf8");
const mediaDir = path.join(articleDir, "media");

const meta = {
  title: "1C AI Agent 0.9.0: skills для агента 1С",
  shortTitle: "1C AI Agent 0.9.0: skills",
  preview: "Релиз 1C AI Agent 0.9.0: переносимые JSON skills, генерация сценариев по описанию, тестовый запуск и использование skills в обычной форме агента 1С.",
  keywords: "1С, 1C, ИИ агент, AI Agent, skills, JSON, LLM, автоматизация, DSL, управляемые формы",
  editReason: "Черновик статьи для релиза 1C AI Agent 0.9.0",
  cover: path.join(mediaDir, "cover_ai_agent_0_9_0_skills.png"),
  screenshots: [
    path.join(mediaDir, "cover_ai_agent_0_9_0_skills.png"),
    path.join(mediaDir, "skills_json_editor.png"),
    path.join(mediaDir, "skills_generated_json.png"),
    path.join(mediaDir, "skills_test_run.png"),
    path.join(mediaDir, "agent_skill_selected.png"),
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

    const openCode = document.querySelector('input[name="PROPERTIES[OPENCODE]"][value="Y"], input[name="PROPERTIES[OPENCODE]"]');
    if (openCode) {
      openCode.checked = true;
      openCode.dispatchEvent(new Event("change", { bubbles: true }));
    }
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
    if (!/image/i.test(accept) && i !== 0) {
      report.push({ index: i, name, id, accept, skipped: true });
      continue;
    }
    const isAnnouncement = /jpeg/i.test(accept) && !/gif/i.test(accept);
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

  await fillIfExists(page, 'input[name="FIELDS[NAME]"]', meta.title);
  await fillIfExists(page, 'input[name="PROPERTIES[SHORT_TITLE]"]', meta.shortTitle);
  await fillIfExists(page, 'textarea[name="FIELDS[PREVIEW_TEXT]"]', meta.preview);
  await fillIfExists(page, 'textarea[name="PROPERTIES[KEYWORDS]"]', meta.keywords);
  await fillIfExists(page, 'textarea[name="PROPERTIES[EDIT_REASON]"]', meta.editReason);
  await setDetailHtml(page, html);
  await setSelects(page);
  const uploads = await uploadImages(page);

  const buttons = await buttonsReport(page);
  fs.writeFileSync(path.join(artifactDir, "buttons_before_draft.json"), JSON.stringify(buttons, null, 2), "utf8");
  await page.screenshot({ path: path.join(artifactDir, "before_save_draft.png"), fullPage: true });

  const draftButton = page.locator("button.BtnToDraft, input.BtnToDraft, button:has-text('Сохранить в черновик'), input[value*='черновик']").first();
  if (!(await draftButton.count())) {
    throw new Error("Не найдена кнопка сохранения в черновик. Модерацию не нажимаю.");
  }

  await Promise.allSettled([
    page.waitForNavigation({ waitUntil: "domcontentloaded", timeout: 30000 }),
    draftButton.click(),
  ]);
  await page.waitForTimeout(5000);

  const bodyText = await page.locator("body").innerText({ timeout: 30000 }).catch(() => "");
  const result = {
    status: /Черновик|черновик|Публикация отправлена в Черновик/i.test(bodyText) ? "draft_saved" : "saved_check_manually",
    url: page.url(),
    uploads,
    title: meta.title,
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
