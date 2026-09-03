import fs from "node:fs/promises";
import process from "node:process";

let payload;
try {
  payload = JSON.parse(await new Promise((resolve, reject) => {
    let input = "";
    process.stdin.setEncoding("utf8");
    process.stdin.on("data", (chunk) => { input += chunk; });
    process.stdin.on("end", () => resolve(input));
    process.stdin.on("error", reject);
  }));
} catch (error) {
  console.error(`Invalid renderer input: ${error.message}`);
  process.exit(2);
}

let chromium;
try {
  ({ chromium } = await import("playwright"));
} catch (error) {
  console.error("Playwright is not installed. Run: pnpm --dir apps/web install");
  process.exit(3);
}

const browser = await chromium.launch({ headless: true });
try {
  const page = await browser.newPage({ viewport: { width: Math.ceil(payload.width), height: Math.ceil(payload.height) } });
  await page.setContent(payload.html, { waitUntil: "load" });
  await page.emulateMedia({ media: "print" });
  await page.evaluate(() => document.fonts.ready);
  await page.evaluate(() => Promise.all([...document.images].map((image) => image.complete ? Promise.resolve() : new Promise((resolve) => { image.onload = resolve; image.onerror = resolve; }))));
  await page.pdf({
    path: payload.output,
    printBackground: true,
    preferCSSPageSize: true,
    displayHeaderFooter: Boolean(payload.page_numbers),
    footerTemplate: payload.page_numbers ? '<div style="width:100%;font:9pt serif;color:#777;text-align:center;"><span class="pageNumber"></span></div>' : undefined,
    margin: { top: "0", right: "0", bottom: "0", left: "0" },
  });
} finally {
  await browser.close();
}
