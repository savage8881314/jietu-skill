---
name: web-capture-layout
description: Use when the user wants competitor or product analysis with direct webpage screenshots instead of links, especially for hardware products, app landing pages, App Store pages, or ecommerce product pages. This skill captures public webpages, optionally crops key sections like hero or price blocks, and generates a side-by-side HTML report with images and structured notes.
---

# Web Capture Layout

Use this skill when the deliverable needs screenshots embedded into the output, not just source links.

## What this skill does

- Captures public webpages with Playwright.
- Supports full-page, viewport, and selector-based screenshots.
- Generates a local HTML report with image-and-text side-by-side cards.
- Keeps a machine-readable manifest so reports are repeatable.
- All user-facing outputs from this skill should default to Simplified Chinese unless the user explicitly requests another language.

## Workflow

1. Gather the target pages and the text that should appear beside each image.
2. Create a manifest JSON based on `references/manifest.example.json`.
3. Run:

```powershell
python scripts/capture_and_layout.py --manifest "<path-to-manifest>" --output-dir "<output-dir>"
```

4. Open the generated `report.html` in the output directory and verify the crops look right.
5. If a key section is missing, add or adjust selectors in the manifest and rerun.

## Capture guidance

- For product analysis pages, prefer selector captures for:
  - `hero`
  - `price`
  - `highlights`
- For App Store or marketing pages, include one clean viewport screenshot and one feature-section crop.
- Use public pages only. If the page requires login or aggressively blocks automation, stop and tell the user.

## Manifest notes

- `items[].image_strategy` can be `viewport`, `full_page`, or `selectors`.
- `items[].selectors` is only used when `image_strategy` is `selectors`.
- `items[].facts` should be short strings such as price, series, model, or key selling points. These render next to the image.
- `items[].wait_for` is optional and useful when a page needs a stable selector before capture.

## Output

The script writes:

- `report.html` - side-by-side report
- `manifest.normalized.json` - resolved run config
- `images/` - captured screenshots

## Language rule

- Default all report titles, subtitles, labels, section names, and explanatory text to Simplified Chinese.
- Preserve product model names, brand names, and official English feature phrases only when they are source identifiers or materially clearer than translation.
- If the source facts are collected in English, translate them into concise Chinese before final delivery whenever practical.

## Recommended use

- Hardware competitor teardown pages
- Product line summaries with price and key specs
- App landing page comparisons
- Store listing screenshot boards
