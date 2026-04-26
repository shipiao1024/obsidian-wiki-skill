#!/usr/bin/env node

const fs = require("fs");
const path = require("path");
const { spawnSync } = require("child_process");

function parseArgs(argv) {
  const args = {};
  for (let i = 2; i < argv.length; i += 1) {
    const value = argv[i];
    if (value === "--url") args.url = argv[++i];
    else if (value === "--output-dir") args.outputDir = argv[++i];
    else if (value === "--cookies") args.cookies = argv[++i];
    else if (value === "--headed") args.headed = true;
  }
  return args;
}

function fail(status, reason) {
  process.stdout.write(JSON.stringify({ status, reason }, null, 2));
  process.exit(status === "ok" ? 0 : 1);
}

function parseNetscapeCookies(filePath) {
  if (!filePath || !fs.existsSync(filePath)) return [];
  const text = fs.readFileSync(filePath, "utf8");
  const cookies = [];
  for (const line of text.split(/\r?\n/)) {
    if (!line.trim() || line.startsWith("#")) continue;
    const parts = line.split("\t");
    if (parts.length < 7) continue;
    const [domain, , rawPath, secure, expires, name, value] = parts;
    cookies.push({
      name,
      value,
      domain,
      path: rawPath || "/",
      expires: Number(expires) || -1,
      httpOnly: false,
      secure: secure.toUpperCase() === "TRUE",
      sameSite: "Lax",
    });
  }
  return cookies;
}

function isVideoUrl(url) {
  return /douyinvod\.com|mime_type=video|\.mp4(?:\?|$)|\.m3u8(?:\?|$)/i.test(url);
}

function rankCandidate(item) {
  let score = 0;
  if (/douyinvod\.com/i.test(item.url)) score += 100;
  if (/mime_type=video/i.test(item.url)) score += 50;
  if (/\.mp4(?:\?|$)/i.test(item.url)) score += 40;
  if (/\.m3u8(?:\?|$)/i.test(item.url)) score += 20;
  if ((item.contentType || "").startsWith("video/")) score += 40;
  if (Number(item.contentLength) > 1024 * 1024) score += 30;
  return score;
}

async function main() {
  const args = parseArgs(process.argv);
  if (!args.url || !args.outputDir) {
    fail("invalid_input", "Usage: douyin_browser_capture.js --url <url> --output-dir <dir> [--cookies file]");
  }

  let chromium;
  try {
    ({ chromium } = require("playwright"));
  } catch (error) {
    fail("dependency_missing", "Node package 'playwright' is required for Douyin browser capture fallback.");
  }

  fs.mkdirSync(args.outputDir, { recursive: true });
  const userAgent =
    process.env.KWIKI_DOUYIN_USER_AGENT ||
    process.env.WECHAT_WIKI_DOUYIN_USER_AGENT ||
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36";
  const browser = await chromium.launch({
    headless: args.headed ? false : (process.env.KWIKI_DOUYIN_HEADLESS || process.env.WECHAT_WIKI_DOUYIN_HEADLESS) !== "0",
  });
  const context = await browser.newContext({
    userAgent,
    locale: "zh-CN",
    viewport: { width: 1365, height: 768 },
  });
  const cookies = parseNetscapeCookies(args.cookies);
  if (cookies.length) await context.addCookies(cookies);
  const page = await context.newPage();

  const candidates = [];
  page.on("response", async (response) => {
    const url = response.url();
    const headers = response.headers();
    const contentType = headers["content-type"] || "";
    const contentLength = Number(headers["content-length"] || "0");
    if (isVideoUrl(url) || contentType.startsWith("video/") || contentType.includes("mpegurl")) {
      candidates.push({ url, contentType, contentLength, status: response.status() });
    }
  });

  await page.goto(args.url, { waitUntil: "domcontentloaded", timeout: 45000 });
  try {
    await page.waitForLoadState("networkidle", { timeout: 15000 });
  } catch (_) {
    // Douyin pages often keep long polling open; captured responses are enough.
  }
  await page.waitForTimeout(8000);

  const title = (await page.title().catch(() => "")) || "Douyin video";
  const debugPath = path.join(args.outputDir, "douyin-browser-candidates.json");
  fs.writeFileSync(debugPath, JSON.stringify(candidates, null, 2), "utf8");
  const candidate = candidates
    .filter((item) => item.status >= 200 && item.status < 400 && isVideoUrl(item.url))
    .sort((a, b) => rankCandidate(b) - rankCandidate(a))[0];
  if (!candidate) {
    await browser.close();
    fail("empty_result", "Douyin browser capture found no playable video response.");
  }

  const outputPath = path.join(args.outputDir, "douyin-browser-capture.mp4");
  const curl = spawnSync(
    "curl",
    [
      "-L",
      "--fail",
      "--retry",
      "2",
      "-A",
      userAgent,
      "-H",
      `Referer: ${args.url}`,
      "-H",
      "Origin: https://www.douyin.com",
      "-o",
      outputPath,
      candidate.url,
    ],
    { encoding: "utf8" }
  );
  await browser.close();

  if (curl.status !== 0) {
    fail("runtime_failed", `curl failed: ${curl.stderr || curl.stdout || curl.status}`);
  }
  const stat = fs.statSync(outputPath);
  if (stat.size < 1024 * 1024) {
    fail("empty_result", `downloaded file is suspiciously small: ${stat.size} bytes`);
  }

  process.stdout.write(
    JSON.stringify(
      {
        status: "ok",
        title,
        video_path: outputPath,
        video_url: candidate.url,
      },
      null,
      2
    )
  );
}

main().catch((error) => {
  fail("runtime_failed", error && error.stack ? error.stack : String(error));
});
