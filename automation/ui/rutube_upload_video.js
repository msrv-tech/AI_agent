const fs = require("fs");
const path = require("path");
const { chromium } = require("D:/bsl/skills/web-test/scripts/node_modules/playwright");

const repoRoot = path.resolve(__dirname, "../..");
const videoPath = path.join(
  repoRoot,
  "docs/articles/product_0_9_0_skills/media/supplier_invoice_recognition_demo.mp4",
);
const artifactDir = path.join(repoRoot, "automation/logs/rutube_upload");

async function pageSnapshot(page, name) {
  const snapshot = await page.evaluate(() => ({
    url: location.href,
    title: document.title,
    buttons: Array.from(document.querySelectorAll("button, a"))
      .map((element) => ({
        tag: element.tagName,
        text: (element.textContent || "").trim().replace(/\s+/g, " "),
        href: element.href || "",
        ariaLabel: element.getAttribute("aria-label") || "",
      }))
      .filter((item) => item.text || item.ariaLabel),
    inputs: Array.from(document.querySelectorAll("input, textarea")).map((element) => ({
      tag: element.tagName,
      type: element.type || "",
      name: element.name || "",
      placeholder: element.placeholder || "",
      accept: element.accept || "",
    })),
    options: Array.from(document.querySelectorAll('[role="option"], [role="menuitem"]'))
      .map((element) => (element.textContent || "").trim().replace(/\s+/g, " "))
      .filter(Boolean),
  }));
  fs.writeFileSync(
    path.join(artifactDir, `${name}.json`),
    JSON.stringify(snapshot, null, 2),
    "utf8",
  );
  await page.screenshot({ path: path.join(artifactDir, `${name}.png`), fullPage: true });
  return snapshot;
}

async function main() {
  fs.mkdirSync(artifactDir, { recursive: true });
  if (!fs.existsSync(videoPath)) throw new Error(`Video not found: ${videoPath}`);

  const browser = await chromium.connectOverCDP("http://127.0.0.1:9333");
  const context = browser.contexts()[0];
  const pages = context.pages();
  let page = pages.find((candidate) => candidate.url().includes("studio.rutube.ru"));
  if (!page) page = await context.newPage();
  await page.bringToFront();
  if (!page.url().includes("studio.rutube.ru")) {
    await page.goto("https://studio.rutube.ru/", { waitUntil: "domcontentloaded", timeout: 60000 });
  }
  await page.waitForTimeout(2000);

  if (process.env.RUTUBE_INSPECT === "1") {
    const snapshot = await pageSnapshot(page, "current_state");
    console.log(JSON.stringify(snapshot, null, 2));
    await browser.close();
    return;
  }

  if (process.env.RUTUBE_FIND === "1") {
    await page.goto("https://studio.rutube.ru/videos", {
      waitUntil: "domcontentloaded",
      timeout: 60000,
    });
    await page.waitForTimeout(3000);
    const targetTitle = "1C AI Agent: распознавание счета поставщика из PDF";
    const titleLocator = page.getByText(targetTitle, { exact: true }).first();
    await titleLocator.waitFor({ state: "visible", timeout: 60000 });
    const result = await titleLocator.evaluate((element) => {
      const container = element.closest("a, article, li, tr, [role=row]") || element.parentElement;
      const links = Array.from((container || document).querySelectorAll("a[href]"))
        .map((link) => link.href)
        .filter(Boolean);
      return { title: element.textContent.trim(), links };
    });
    const snapshot = await pageSnapshot(page, "published_video");
    console.log(JSON.stringify({ result, snapshot }, null, 2));
    await browser.close();
    return;
  }

  const titleInput = page.locator('input[name="title"]').first();
  if (!(await titleInput.isVisible().catch(() => false))) {
    let uploadMenuItem = page.locator("button", { hasText: "Загрузить видео или Shorts" }).first();
    if (!(await uploadMenuItem.isVisible().catch(() => false))) {
      const addButton = page.locator("button", { hasText: "Добавить" }).first();
      await addButton.evaluate((element) => element.click());
      await page.waitForTimeout(500);
      uploadMenuItem = page.locator("button", { hasText: "Загрузить видео или Shorts" }).first();
    }
    await uploadMenuItem.evaluate((element) => element.click());
    await page.waitForTimeout(1000);
    const fileInput = page.locator('input[type="file"][accept*=".mp4"]').first();
    await fileInput.setInputFiles(videoPath);
    await titleInput.waitFor({ state: "visible", timeout: 30000 });
  }

  await titleInput.fill("1C AI Agent: распознавание счета поставщика из PDF");
  await page.locator('textarea[name="description"]').fill(
    "ИИ-агент распознает счет поставщика из PDF, выбирает переносимый JSON skill, находит стороны и номенклатуру, создает заполненный черновик документа в 1С:Бухгалтерии и показывает ссылку на результат.\n\nПроект: https://github.com/msrv-tech/AI_agent",
  );
  const categoryTrigger = page.getByText("Выберите категорию", { exact: true }).first();
  if (await categoryTrigger.isVisible().catch(() => false)) {
    await categoryTrigger.click();
    await page.waitForTimeout(500);
  }
  const technologyOption = page.getByRole("option", { name: "Технологии и интернет", exact: true });
  if (await technologyOption.isVisible().catch(() => false)) {
    await technologyOption.click();
  }

  if (process.env.RUTUBE_PUBLISH === "1") {
    const publishButton = page.getByRole("button", { name: "Опубликовать", exact: true });
    await publishButton.waitFor({ state: "visible", timeout: 30000 });
    await publishButton.waitFor({ state: "attached", timeout: 30000 });
    await page.waitForFunction(
      () => {
        const button = Array.from(document.querySelectorAll("button"))
          .find((element) => (element.textContent || "").trim() === "Опубликовать");
        return button && !button.disabled && button.getAttribute("aria-disabled") !== "true";
      },
      null,
      { timeout: 180000 },
    );
    await pageSnapshot(page, "before_publish");
    await publishButton.click();
    await page.waitForTimeout(5000);
  }
  const snapshot = await pageSnapshot(page, "category_options");
  console.log(JSON.stringify(snapshot, null, 2));
  await browser.close();
}

main().catch((error) => {
  console.error(error);
  process.exit(1);
});
