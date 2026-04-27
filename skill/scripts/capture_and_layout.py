import argparse
import json
import re
from html import escape
from pathlib import Path
from typing import Any

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "item"


def load_manifest(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if "items" not in data or not isinstance(data["items"], list) or not data["items"]:
        raise ValueError("Manifest must contain a non-empty 'items' list.")
    return data


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def capture_item(page, item: dict[str, Any], image_dir: Path) -> dict[str, Any]:
    slug = item.get("slug") or slugify(item["name"])
    strategy = item.get("image_strategy", "viewport")
    url = item["url"]
    wait_for = item.get("wait_for")
    outputs: list[dict[str, str]] = []
    error = ""

    try:
        page.goto(url, wait_until="domcontentloaded", timeout=90000)
        if wait_for:
            try:
                page.wait_for_selector(wait_for, timeout=12000)
            except PlaywrightTimeoutError:
                pass

        if strategy == "full_page":
            filename = f"{slug}-full.png"
            target = image_dir / filename
            page.screenshot(path=str(target), full_page=True)
            outputs.append({"label": "整页", "path": f"images/{filename}"})
        elif strategy == "selectors":
            selectors = item.get("selectors") or []
            for entry in selectors:
                label = entry["name"]
                selector = entry["selector"]
                locator = page.locator(selector).first
                if locator.count() == 0:
                    continue
                filename = f"{slug}-{slugify(label)}.png"
                target = image_dir / filename
                locator.screenshot(path=str(target))
                outputs.append({"label": label, "path": f"images/{filename}"})
            if not outputs:
                filename = f"{slug}-viewport.png"
                target = image_dir / filename
                page.screenshot(path=str(target), full_page=False)
                outputs.append({"label": "首屏", "path": f"images/{filename}"})
        else:
            filename = f"{slug}-viewport.png"
            target = image_dir / filename
            page.screenshot(path=str(target), full_page=False)
            outputs.append({"label": "首屏", "path": f"images/{filename}"})
    except Exception as exc:  # noqa: BLE001
        error = str(exc)

    result = dict(item)
    result["slug"] = slug
    result["captures"] = outputs
    result["capture_error"] = error
    return result


def render_report(manifest: dict[str, Any], items: list[dict[str, Any]], output_dir: Path) -> Path:
    title = manifest.get("title", "网页截图报告")
    subtitle = manifest.get("subtitle", "")
    cards = []
    for item in items:
        images_html = "".join(
            f'<figure><img src="{escape(cap["path"])}" alt="{escape(item["name"])} {escape(cap["label"])}"><figcaption>{escape(cap["label"])}</figcaption></figure>'
            for cap in item["captures"]
        )
        if not images_html:
            images_html = f'<div class="empty">截图不可用<br><span>{escape(item.get("capture_error", ""))}</span></div>'
        facts_html = "".join(f"<li>{escape(fact)}</li>" for fact in item.get("facts", []))
        cards.append(
            f"""
            <section class="card">
              <div class="media">{images_html}</div>
              <div class="content">
                <h2>{escape(item["name"])}</h2>
                <p class="url">{escape(item["url"])}</p>
                <ul>{facts_html}</ul>
              </div>
            </section>
            """
        )

    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>
    :root {{
      --bg: #f4f1ea;
      --panel: #fffdf8;
      --ink: #1e1a16;
      --muted: #6f665f;
      --line: #ddd3c7;
      --accent: #a54c1e;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "Segoe UI", Arial, sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at top left, rgba(165, 76, 30, 0.08), transparent 30%),
        linear-gradient(180deg, #fbf8f3 0%, var(--bg) 100%);
      padding: 32px;
    }}
    header {{
      max-width: 1200px;
      margin: 0 auto 24px;
    }}
    h1 {{
      margin: 0 0 8px;
      font-size: 34px;
      line-height: 1.1;
    }}
    .subtitle {{
      margin: 0;
      color: var(--muted);
      font-size: 16px;
    }}
    .report {{
      max-width: 1200px;
      margin: 0 auto;
      display: grid;
      gap: 20px;
    }}
    .card {{
      display: grid;
      grid-template-columns: minmax(0, 1.2fr) minmax(280px, 0.8fr);
      gap: 20px;
      background: var(--panel);
      border: 1px solid var(--line);
      border-radius: 22px;
      padding: 20px;
      box-shadow: 0 16px 40px rgba(26, 18, 10, 0.08);
    }}
    .media {{
      display: grid;
      gap: 14px;
    }}
    .empty {{
      min-height: 260px;
      border: 1px dashed var(--line);
      border-radius: 16px;
      display: grid;
      place-items: center;
      text-align: center;
      padding: 24px;
      color: var(--muted);
      background: rgba(255,255,255,0.72);
      line-height: 1.5;
    }}
    .empty span {{
      display: block;
      margin-top: 8px;
      font-size: 12px;
      word-break: break-word;
    }}
    figure {{
      margin: 0;
    }}
    img {{
      width: 100%;
      border-radius: 16px;
      border: 1px solid var(--line);
      display: block;
      background: white;
    }}
    figcaption {{
      margin-top: 8px;
      color: var(--muted);
      font-size: 13px;
    }}
    .content h2 {{
      margin: 0 0 8px;
      font-size: 26px;
    }}
    .url {{
      margin: 0 0 16px;
      color: var(--accent);
      font-size: 14px;
      word-break: break-all;
    }}
    ul {{
      margin: 0;
      padding-left: 18px;
      display: grid;
      gap: 10px;
    }}
    li {{
      line-height: 1.5;
    }}
    @media (max-width: 900px) {{
      body {{ padding: 18px; }}
      .card {{ grid-template-columns: 1fr; }}
    }}
  </style>
</head>
<body>
  <header>
    <h1>{escape(title)}</h1>
    <p class="subtitle">{escape(subtitle)}</p>
  </header>
  <main class="report">
    {''.join(cards)}
  </main>
</body>
</html>
"""
    report_path = output_dir / "report.html"
    report_path.write_text(html, encoding="utf-8")
    return report_path


def main() -> int:
    parser = argparse.ArgumentParser(description="抓取公开网页并生成图文并排的 HTML 报告。")
    parser.add_argument("--manifest", required=True, help="Manifest JSON 文件路径。")
    parser.add_argument("--output-dir", required=True, help="报告和图片输出目录。")
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve()
    output_dir = Path(args.output_dir).resolve()
    image_dir = output_dir / "images"
    ensure_dir(output_dir)
    ensure_dir(image_dir)

    manifest = load_manifest(manifest_path)
    browser_config = manifest.get("browser", {})
    viewport = browser_config.get("viewport", {"width": 1440, "height": 1200})
    channel = browser_config.get("channel")
    headless = browser_config.get("headless", True)

    captured_items = []
    with sync_playwright() as playwright:
      launch_kwargs: dict[str, Any] = {"headless": headless}
      if channel:
          launch_kwargs["channel"] = channel
      browser = playwright.chromium.launch(**launch_kwargs)
      context = browser.new_context(viewport=viewport)
      page = context.new_page()

      for item in manifest["items"]:
          captured_items.append(capture_item(page, item, image_dir))

      context.close()
      browser.close()

    normalized_path = output_dir / "manifest.normalized.json"
    normalized_path.write_text(
        json.dumps({"title": manifest.get("title"), "subtitle": manifest.get("subtitle"), "items": captured_items}, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    report_path = render_report(manifest, captured_items, output_dir)
    print(f"报告已生成: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
