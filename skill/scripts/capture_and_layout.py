import argparse
import json
import re
from html import escape
from pathlib import Path
from typing import Any

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

EMPTY_TEXT = "暂无数据"
EMPTY_IMAGE_TEXT = "暂无图片"
DEFAULT_TITLE = "宠物竞品分析图谱"
DEFAULT_AUTHOR = "yangyanan"
DEFAULT_INDUSTRY = "宠物软件赛道"
ANALYSIS_HIGHLIGHT_KEYWORDS = [
    "硬件+订阅",
    "服务收费",
    "多SKU电商",
    "纯软件",
    "订阅",
    "流量",
    "转化",
    "复购",
    "闭环",
    "割裂",
]
EXPORT_FIELDS = [
    "官网链接",
    "App 完整功能",
    "App 亮点功能",
    "Android 下载量",
    "Android 评分和评论数",
    "iOS 评分和评论数",
    "硬件依赖度",
    "商业模式",
]
STATE_VERSION = 1
ANALYSIS_VERSION = 1
ANALYSIS_COLUMNS = ["服务预约", "在线问诊", "电商交易", "订阅体系", "硬件连接", "健康追踪"]
ANALYSIS_ENGINE = "market-function-v2"
PRODUCT_STRUCTURES = ["单品爆款", "多SKU电商", "订阅产品", "硬件+服务", "纯软件"]
BUSINESS_MODELS = ["一次性电商", "订阅", "硬件+订阅", "服务收费"]
FEATURE_SPECS = [
    {
        "name": "宠物档案管理",
        "keywords": ["档案", "profile", "pet profile", "记录", "病历"],
        "user_value": 5,
        "business_value": 3,
        "tech_feasibility": 5,
    },
    {
        "name": "健康记录与提醒",
        "keywords": ["提醒", "用药", "症状", "健康", "病历", "生命体征", "活动", "追踪"],
        "user_value": 5,
        "business_value": 4,
        "tech_feasibility": 5,
    },
    {
        "name": "服务预约",
        "keywords": ["预约", "寄养", "遛狗", "日托", "看护", "drop-in", "boarding", "walking"],
        "user_value": 4,
        "business_value": 4,
        "tech_feasibility": 2,
    },
    {
        "name": "在线问诊",
        "keywords": ["问诊", "兽医", "视频问诊", "处方", "vet", "telehealth"],
        "user_value": 4,
        "business_value": 4,
        "tech_feasibility": 2,
    },
    {
        "name": "电商交易",
        "keywords": ["购物", "商品", "药房", "订单", "发货", "shop", "pharmacy", "autoship"],
        "user_value": 4,
        "business_value": 5,
        "tech_feasibility": 4,
    },
    {
        "name": "订阅体系",
        "keywords": ["订阅", "会员", "premium", "续费", "autoship", "持续护理"],
        "user_value": 4,
        "business_value": 5,
        "tech_feasibility": 4,
    },
    {
        "name": "设备连接",
        "keywords": ["设备", "摄像头", "追踪器", "项圈", "投喂", "tracker", "camera", "feeder"],
        "user_value": 3,
        "business_value": 4,
        "tech_feasibility": 2,
    },
    {
        "name": "定位追踪",
        "keywords": ["gps", "定位", "围栏", "轨迹", "位置历史"],
        "user_value": 4,
        "business_value": 4,
        "tech_feasibility": 2,
    },
    {
        "name": "远程看宠",
        "keywords": ["双向语音", "实时查看", "回看", "摄像头", "视频", "激光", "投喂"],
        "user_value": 3,
        "business_value": 3,
        "tech_feasibility": 2,
    },
]


CAPTURE_LABEL_MAP = {
    "棣栧睆": "首屏",
    "鏁撮〉": "整页",
    "鏁撮頁": "整页",
}


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r"[^a-z0-9]+", "-", value)
    return value.strip("-") or "item"


def load_manifest(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if "items" not in data or not isinstance(data["items"], list) or not data["items"]:
        raise ValueError("Manifest must contain a non-empty 'items' list.")
    return data


def load_state(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("State file must be a JSON object.")
    items = data.get("items", {})
    if items is not None and not isinstance(items, dict):
        raise ValueError("State file 'items' must be an object.")
    return data


def load_analysis(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(data, dict):
        raise ValueError("Analysis file must be a JSON object.")
    return data


def ensure_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def resolve_state_path(manifest_path: Path, explicit_state: str | None) -> Path:
    if explicit_state:
        return Path(explicit_state).resolve()

    candidates = [manifest_path.with_suffix(".state.json")]
    if manifest_path.stem.endswith("_manifest"):
        short_name = manifest_path.stem[: -len("_manifest")] + ".state.json"
        candidates.append(manifest_path.with_name(short_name))

    for candidate in candidates:
        if candidate.exists():
            return candidate
    return candidates[0]


def get_item_id(item: dict[str, Any]) -> str:
    raw = clean_text(item.get("slug") or item.get("name"), "item")
    return slugify(raw)


def clean_text(value: Any, empty_text: str = EMPTY_TEXT) -> str:
    if value is None:
        return empty_text
    text = str(value).strip()
    if not text:
        return empty_text
    if re.fullmatch(r"[?？\s]+", text):
        return empty_text
    return CAPTURE_LABEL_MAP.get(text, text)


def format_analysis_text(value: Any) -> str:
    text = escape(clean_text(value, ""))
    if not text:
        return ""
    for keyword in sorted(ANALYSIS_HIGHLIGHT_KEYWORDS, key=len, reverse=True):
        text = text.replace(keyword, f'<span class="analysis-emphasis">{keyword}</span>')
    return text


def normalize_capture_label(value: Any) -> str:
    text = clean_text(value, "截图")
    return CAPTURE_LABEL_MAP.get(text, text)


def get_item_links(item: dict[str, Any]) -> list[dict[str, str]]:
    links: list[dict[str, str]] = []
    for entry in item.get("links", []):
        label = clean_text(entry.get("label"), "")
        url = clean_text(entry.get("url"), "")
        if label and url and url != EMPTY_TEXT:
            links.append({"label": label, "url": url})
    return links


def get_primary_website(item: dict[str, Any]) -> str:
    for entry in get_item_links(item):
        if entry["label"] == "官网":
            return entry["url"]
    return clean_text(item.get("url"))


def get_detail_map(item: dict[str, Any]) -> dict[str, str]:
    detail_map: dict[str, str] = {}
    for entry in item.get("details", []):
        label = clean_text(entry.get("label"), "")
        if not label:
            continue
        detail_map[label] = clean_text(entry.get("value"))
    return detail_map


def normalize_state_capture(entry: Any) -> dict[str, str] | None:
    if not isinstance(entry, dict):
        return None
    path = clean_text(entry.get("path"), "")
    if not path or path == EMPTY_TEXT:
        return None
    label = normalize_capture_label(entry.get("label"))
    kind = clean_text(entry.get("kind"), "")
    if not kind or kind == EMPTY_TEXT:
        kind = "uploaded" if path.startswith("data:image/") else "existing"
    return {"label": label, "path": path, "kind": kind}


def build_details_from_map(base_item: dict[str, Any], detail_map: dict[str, str]) -> list[dict[str, str]]:
    existing_labels: list[str] = []
    rows: list[dict[str, str]] = []
    for entry in base_item.get("details", []):
        label = clean_text(entry.get("label"), "")
        if not label:
            continue
        existing_labels.append(label)
        rows.append({"label": label, "value": detail_map.get(label, clean_text(entry.get("value")))})
    for label, value in detail_map.items():
        if label in existing_labels:
            continue
        rows.append({"label": label, "value": value})
    return rows


def apply_state_to_items(items: list[dict[str, Any]], state: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not state:
        return items

    state_items = state.get("items", {})
    if not isinstance(state_items, dict):
        return items

    merged_items: list[dict[str, Any]] = []
    for item in items:
        item_id = get_item_id(item)
        item_state = state_items.get(item_id) or state_items.get(clean_text(item.get("name"), ""))
        if not isinstance(item_state, dict):
            merged_items.append(item)
            continue

        merged = dict(item)
        merged["slug"] = item_id

        state_name = clean_text(item_state.get("name"), "")
        if state_name and state_name != EMPTY_TEXT:
            merged["name"] = state_name

        state_fields = item_state.get("fields", {})
        detail_map = get_detail_map(merged)
        if isinstance(state_fields, dict):
            for label, value in state_fields.items():
                normalized_label = clean_text(label, "")
                if not normalized_label:
                    continue
                detail_map[normalized_label] = clean_text(value)
            merged["details"] = build_details_from_map(merged, detail_map)

        if "captures" in item_state:
            captures = item_state.get("captures", [])
            if isinstance(captures, list):
                normalized_captures = []
                for capture in captures[:6]:
                    normalized = normalize_state_capture(capture)
                    if normalized:
                        normalized_captures.append(normalized)
                merged["captures"] = normalized_captures

        merged_items.append(merged)

    return merged_items


def build_report_state(items: list[dict[str, Any]], analysis: dict[str, Any] | None = None) -> dict[str, Any]:
    payload_items: dict[str, Any] = {}
    for item in items:
        item_id = get_item_id(item)
        detail_map = get_detail_map(item)
        payload_items[item_id] = {
            "name": clean_text(item.get("name"), "未命名"),
            "fields": detail_map,
            "captures": [
                {
                    "label": normalize_capture_label(cap.get("label")),
                    "path": clean_text(cap.get("path"), ""),
                    "kind": clean_text(cap.get("kind"), "uploaded" if clean_text(cap.get("path"), "").startswith("data:image/") else "existing"),
                }
                for cap in (item.get("captures", []) or [])[:6]
                if clean_text(cap.get("path"), "")
            ],
        }
    payload: dict[str, Any] = {"version": STATE_VERSION, "items": payload_items}
    if analysis:
        payload["analysis"] = analysis
    return payload


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
                label = clean_text(entry.get("name"), "截图")
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


def render_links(item: dict[str, Any]) -> str:
    links = get_item_links(item)
    if not links:
        return ""
    parts = []
    for entry in links:
        label = escape(entry["label"])
        url = escape(entry["url"])
        parts.append(f'<a class="pill-link" href="{url}" target="_blank" rel="noreferrer">{label}</a>')
    return f'<div class="link-grid">{"".join(parts)}</div>'


def render_detail_row(label: str, value: str, editable: bool = True) -> str:
    safe_label = escape(clean_text(label))
    normalized_value = clean_text(value)
    safe_value = escape(normalized_value)
    is_empty = "true" if normalized_value == EMPTY_TEXT else "false"
    editable_attr = ' contenteditable="true"' if editable else ""
    editable_class = " editable-field" if editable else " static-field"
    row_class = "detail-row is-editable" if editable else "detail-row detail-row--static"
    return f"""
            <div class="{row_class}" data-row-field="{safe_label}">
              <div class="detail-label">{safe_label}</div>
              <div class="detail-value{editable_class}"{editable_attr} data-field="{safe_label}" data-empty="{is_empty}">{safe_value}</div>
            </div>
            """


def render_details(item: dict[str, Any], manifest: dict[str, Any]) -> str:
    detail_map = get_detail_map(item)
    configured_fields = manifest.get("fields") if isinstance(manifest.get("fields"), list) else []
    ordered_fields: list[str] = []
    for field in EXPORT_FIELDS + [str(field) for field in configured_fields]:
        if field not in ordered_fields:
            ordered_fields.append(field)

    website_url = escape(get_primary_website(item))
    rows = [
        f"""
            <div class="detail-row detail-row--static website-row" data-row-field="官网链接">
              <div class="detail-label">官网链接</div>
              <a class="detail-link website-link" href="{website_url}" target="_blank" rel="noreferrer">{website_url}</a>
            </div>
        """
    ]
    for field in ordered_fields:
        if field == "官网链接":
            continue
        rows.append(render_detail_row(field, detail_map.get(field, EMPTY_TEXT)))

    for label, value in detail_map.items():
        if label not in ordered_fields:
            rows.append(render_detail_row(label, value))
    return "".join(rows)


def render_gallery(item: dict[str, Any]) -> str:
    captures = (item.get("captures", []) or [])[:6]
    if captures:
        cards = []
        for index, cap in enumerate(captures):
            image_path = escape(cap["path"])
            label = escape(normalize_capture_label(cap.get("label")))
            alt = escape(f'{clean_text(item.get("name"), "产品")} {label}')
            kind = escape(clean_text(cap.get("kind"), "uploaded" if cap.get("path", "").startswith("data:image/") else "existing"))
            cards.append(
                f"""
                <div class="gallery-item" data-kind="{kind}" data-label="{label}" data-index="{index}">
                  <button type="button" class="delete-btn" aria-label="删除图片">删除</button>
                  <img src="{image_path}" alt="{alt}" class="gallery-image" data-full-src="{image_path}">
                  <div class="gallery-caption">{label}</div>
                </div>
                """
            )
        count_text = f"当前展示 {len(captures)} 张图片，最多可保留 6 张。"
    else:
        cards = [
            f"""
            <div class="empty-state">
              <div>{EMPTY_IMAGE_TEXT}</div>
              <span>你可以手动上传补图，最多 6 张。</span>
            </div>
            """
        ]
        count_text = "当前没有图片，可上传最多 6 张。"

    return f"""
    <div class="gallery-shell" data-max-images="6">
      <div class="gallery-toolbar">
        <label class="upload-btn">
          上传截图
          <input type="file" accept=".png,.jpg,.jpeg,.webp,image/png,image/jpeg,image/webp" multiple class="upload-input">
        </label>
        <div class="gallery-hint">{count_text}</div>
      </div>
      <div class="gallery-grid count-{min(len(captures), 6) if captures else 0}">
        {''.join(cards)}
      </div>
    </div>
    """


def get_item_name_map(items: list[dict[str, Any]]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for item in items:
        item_id = get_item_id(item)
        name = clean_text(item.get("name"), item_id)
        mapping[item_id] = name
        mapping[name] = name
    return mapping


def resolve_analysis_label(raw: Any, item_name_map: dict[str, str]) -> str:
    key = clean_text(raw, "")
    if not key:
        return ""
    return item_name_map.get(key) or item_name_map.get(slugify(key)) or key


def analysis_level_weight(level: str) -> int:
    return {"无": 0, "弱": 1, "中": 2, "强": 3}.get(clean_text(level, "无"), 0)


def labels_for_capability(rows: list[dict[str, Any]], capability: str, minimum: int = 2) -> list[str]:
    return [
        clean_text(row.get("label"), "竞品")
        for row in rows
        if analysis_level_weight((row.get("values", {}) or {}).get(capability, "无")) >= minimum
    ]


def _contains_any(text: str, keywords: list[str]) -> bool:
    source = text.lower()
    return any(keyword.lower() in source for keyword in keywords)


def _count_matches(text: str, keywords: list[str]) -> int:
    source = text.lower()
    return sum(1 for keyword in keywords if keyword.lower() in source)


def _has_hardware_signal(text: str) -> bool:
    source = text.lower()
    explicit_terms = ["camera", "tracker", "collar", "feeder", "摄像头", "追踪器", "项圈", "投喂", "喂食器"]
    if any(term in source for term in explicit_terms):
        return True
    if "设备" in source and "不依赖设备" not in source:
        return True
    if "硬件" in source and "不依赖硬件" not in source and "不依赖专属硬件" not in source:
        return True
    return False


def _item_text_bundle(item: dict[str, Any]) -> tuple[str, dict[str, str]]:
    detail_map = get_detail_map(item)
    values = [clean_text(item.get("name"), ""), clean_text(item.get("url"), "")]
    values.extend(clean_text(entry.get("label"), "") for entry in item.get("links", []))
    values.extend(detail_map.values())
    full_text = " | ".join(value for value in values if value and value != EMPTY_TEXT).lower()
    return full_text, detail_map


def _derive_product_structure(text: str) -> str:
    if _has_hardware_signal(text):
        return "硬件+服务"
    if _contains_any(text, ["autoship", "pharmacy", "food", "用品", "药房", "购物", "商品", "shop", "store"]):
        return "多SKU电商"
    if _contains_any(text, ["订阅", "subscription", "member", "会员", "box", "premium", "持续护理"]):
        return "订阅产品"
    if _contains_any(text, ["single product", "hero product", "单品", "爆款"]) and not _contains_any(text, ["商品", "购物", "用品"]):
        return "单品爆款"
    return "纯软件"


def _derive_business_model(text: str, structure: str) -> str:
    if structure == "硬件+服务":
        return "硬件+订阅"
    if structure == "订阅产品" or _contains_any(text, ["subscription", "订阅", "会员", "premium", "autoship", "持续护理"]):
        return "订阅"
    if _contains_any(text, ["预约", "寄养", "遛狗", "看护", "训练", "问诊", "兽医", "咨询", "支付抽成", "佣金"]):
        return "服务收费"
    return "一次性电商"


def _derive_traffic_score(text: str, structure: str, business_model: str) -> int:
    if _contains_any(text, ["blog", "guide", "community", "learn", "academy", "tips", "content", "social", "youtube", "instagram", "tiktok", "攻略", "知识", "内容"]):
        return 5
    if structure in {"多SKU电商", "单品爆款", "硬件+服务", "订阅产品"}:
        return 3
    if business_model == "服务收费":
        return 2
    return 1


def _derive_conversion_score(text: str, structure: str, business_model: str) -> int:
    strong_signals = _count_matches(
        text,
        ["订阅", "会员", "premium", "autoship", "bundle", "套装", "组合", "评分", "评论", "guarantee", "发货", "支付", "下单"],
    )
    if strong_signals >= 3:
        return 5
    if structure in {"多SKU电商", "订阅产品", "硬件+服务"} or business_model in {"订阅", "硬件+订阅"}:
        return 3
    if business_model == "服务收费":
        return 2
    return 1


def _derive_repeat_score(text: str, structure: str, business_model: str) -> int:
    if business_model in {"订阅", "硬件+订阅"} or structure in {"订阅产品", "硬件+服务"}:
        return 5
    if _contains_any(text, ["autoship", "持续护理", "补货", "药房", "处方", "follow-up", "复购", "再次预约"]):
        return 4
    if business_model in {"服务收费", "一次性电商"} and _contains_any(text, ["订单", "训练", "日托", "提醒", "复诊"]):
        return 3
    return 1


def _derive_capability_values(text: str) -> dict[str, str]:
    return {
        "服务预约": "强" if _count_matches(text, ["预约", "寄养", "遛狗", "日托", "看护", "训练", "boarding", "walking", "drop-in"]) >= 2 else ("中" if _contains_any(text, ["预约", "寄养", "遛狗", "看护", "训练"]) else "无"),
        "在线问诊": "强" if _count_matches(text, ["问诊", "兽医", "视频问诊", "处方", "vet"]) >= 2 else ("中" if _contains_any(text, ["问诊", "兽医", "视频", "健康建议"]) else "无"),
        "电商交易": "强" if _count_matches(text, ["购物", "商品", "药房", "autoship", "订单", "发货"]) >= 2 else ("中" if _contains_any(text, ["购物", "商品", "药房", "订单"]) else "无"),
        "订阅体系": "强" if _count_matches(text, ["订阅", "会员", "premium", "autoship", "持续护理"]) >= 2 else ("中" if _contains_any(text, ["订阅", "会员", "premium"]) else "无"),
        "硬件连接": "强" if (_has_hardware_signal(text) and _count_matches(text, ["摄像头", "追踪器", "设备", "项圈", "投喂", "喂食器"]) >= 2) else ("中" if _has_hardware_signal(text) else "无"),
        "健康追踪": "强" if _count_matches(text, ["健康", "档案", "病历", "生命体征", "活动", "提醒"]) >= 2 else ("中" if _contains_any(text, ["健康", "档案", "提醒", "活动"]) else "无"),
    }


def _build_company_profiles(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    profiles: list[dict[str, Any]] = []
    for item in items:
        text, detail_map = _item_text_bundle(item)
        structure = _derive_product_structure(text)
        business_model = _derive_business_model(text, structure)
        profiles.append(
            {
                "id": get_item_id(item),
                "label": clean_text(item.get("name"), "未命名"),
                "text": text,
                "detail_map": detail_map,
                "traffic_score": _derive_traffic_score(text, structure, business_model),
                "conversion_score": _derive_conversion_score(text, structure, business_model),
                "repeat_score": _derive_repeat_score(text, structure, business_model),
                "product_structure": structure,
                "business_model": business_model,
                "capabilities": _derive_capability_values(text),
            }
        )
    return profiles


def _build_market_groups(profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {name: [] for name in PRODUCT_STRUCTURES}
    for profile in profiles:
        grouped[profile["product_structure"]].append(profile)

    groups: list[dict[str, Any]] = []
    for structure, members in grouped.items():
        if not members:
            continue
        business_mix = sorted({member["business_model"] for member in members})
        description = f"{len(members)} 个样本落在这一结构，当前主要对应 {'、'.join(business_mix)} 这类收入方式。"
        groups.append(
            {
                "title": structure,
                "description": description,
                "items": [{"id": member["id"], "label": member["label"]} for member in members],
            }
        )
    return groups


def _build_market_insights(profiles: list[dict[str, Any]]) -> tuple[str, list[str]]:
    if not profiles:
        return "", []

    structures = sorted({profile["product_structure"] for profile in profiles})
    business_counts: dict[str, int] = {}
    for profile in profiles:
        business_counts[profile["business_model"]] = business_counts.get(profile["business_model"], 0) + 1
    business_summary = "、".join(f"{name}{count}家" for name, count in sorted(business_counts.items(), key=lambda item: item[1], reverse=True))

    multi_model = len(structures) > 1
    all_rounder = [
        profile
        for profile in profiles
        if profile["traffic_score"] >= 4 and profile["conversion_score"] >= 4 and profile["repeat_score"] >= 4
    ]
    content_driven = [profile["label"] for profile in profiles if profile["traffic_score"] >= 5]
    brand_driven = [profile["label"] for profile in profiles if profile["traffic_score"] <= 3]
    pure_software = [profile for profile in profiles if profile["product_structure"] == "纯软件"]
    pure_software_avg = (
        sum(profile["conversion_score"] for profile in pure_software) / len(pure_software) if pure_software else 0
    )

    summary_parts = []
    if business_summary:
        summary_parts.append(f"样本当前主要靠{business_summary}赚钱")
    if multi_model:
        summary_parts.append(f"同时存在{'、'.join(structures)}，属于多模型竞争")
    if not all_rounder:
        summary_parts.append("没有产品同时把流量、转化和复购做成闭环，所以市场能力仍然割裂")
    core_summary = "；".join(summary_parts) + "。"

    insights = []
    if multi_model:
        insights.append(f"市场结构：样本同时出现{'、'.join(structures)}几种产品结构，所以这不是单一路径吃透市场，而是多模型竞争。")
    else:
        insights.append(f"市场结构：当前样本几乎都落在{structures[0]}这一种产品结构里，所以新进入者更容易被拖进同一种竞争方式。")
    if not all_rounder:
        insights.append("市场能力：没有任何一个样本同时具备强流量、强转化和强复购，因为流量入口、成交能力和复购机制分散在不同玩家手里，所以市场仍处于能力割裂状态。")
    if len(brand_driven) >= max(1, (len(profiles) // 2) + 1):
        insights.append(f"流量结构：大多数样本更依赖品牌站、商店页和现成渠道获客，例如{'、'.join(brand_driven[:4])}，所以当前缺少内容型或工具型高频流量入口。")
    elif content_driven:
        insights.append(f"流量结构：只有{'、'.join(content_driven)}具备明显内容/社区型流量特征，其余样本仍偏品牌流量，所以内容入口还没有形成规模壁垒。")
    if pure_software and pure_software_avg <= 2.5:
        names = "、".join(profile["label"] for profile in pure_software[:4])
        insights.append(f"转化结构：纯软件样本如{names}平均转化能力只有 {pure_software_avg:.1f}/5，因为它们缺少硬件、商品或订阅抓手，所以软件本身难以直接变现。")
    else:
        strong_converters = [profile["label"] for profile in profiles if profile["conversion_score"] >= 4]
        if strong_converters:
            insights.append(f"转化结构：高转化能力主要集中在{'、'.join(strong_converters)}，因为这些产品同时拥有评价、订阅或商品成交设计，所以转化优势更多来自商业机制而不是单一功能。")
    return core_summary, insights[:4]


def _build_opportunities(profiles: list[dict[str, Any]]) -> list[str]:
    if not profiles:
        return []

    opportunities: list[str] = []
    content_profiles = [profile["label"] for profile in profiles if profile["traffic_score"] >= 5]
    brand_profiles = [profile["label"] for profile in profiles if profile["traffic_score"] <= 3]
    hardware_profiles = [profile["label"] for profile in profiles if profile["product_structure"] == "硬件+服务"]
    service_profiles = [profile["label"] for profile in profiles if profile["business_model"] == "服务收费"]
    software_profiles = [profile["label"] for profile in profiles if profile["product_structure"] == "纯软件"]
    software_low_conversion = [
        profile["label"] for profile in profiles if profile["product_structure"] == "纯软件" and profile["conversion_score"] <= 2
    ]
    commerce_profiles = [profile["label"] for profile in profiles if profile["business_model"] in {"一次性电商", "订阅", "硬件+订阅"}]

    if not content_profiles and brand_profiles:
        opportunities.append(
            f"当前状态：{len(brand_profiles)} 个样本主要靠品牌站、商店页或既有渠道获客。缺口：市场里几乎没有内容型或工具型高频入口。机会方向：先做软件/工具流量入口，把档案、提醒、记录这类高频动作变成持续获客位。"
        )
    if hardware_profiles and service_profiles:
        opportunities.append(
            f"当前状态：硬件能力主要在{'、'.join(hardware_profiles)}，服务收费能力主要在{'、'.join(service_profiles[:4])}。缺口：数据、消费和服务没有被同一个产品打成闭环。机会方向：把设备数据、健康事件或提醒直接接到消费推荐和服务预约里，做数据驱动转化。"
        )
    if software_low_conversion:
        opportunities.append(
            f"当前状态：纯软件样本如{'、'.join(software_low_conversion[:4])}转化能力偏弱。缺口：软件侧缺少明确收入路径。机会方向：把软件入口和电商、订阅或会员服务绑在一起，让软件先拿流量，再承接成交。"
        )
    if len(opportunities) < 3 and software_profiles and commerce_profiles:
        opportunities.append(
            f"当前状态：软件入口更多在{'、'.join(software_profiles[:4])}，成交能力更多在{'、'.join(commerce_profiles[:4])}。缺口：流量和变现不在同一个产品里。机会方向：优先做“记录/提醒/档案 + 商品或订阅推荐”的中间层产品。"
        )
    return opportunities[:4]


def _build_feature_priorities(profiles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not profiles:
        return []

    rows: list[dict[str, Any]] = []
    sample_count = len(profiles)
    for spec in FEATURE_SPECS:
        matched = [profile["label"] for profile in profiles if _contains_any(profile["text"], spec["keywords"])]
        if not matched:
            continue
        if len(matched) >= max(1, (sample_count + 1) // 2):
            competition = 5
        elif len(matched) >= 3:
            competition = 3
        else:
            competition = 1
        opportunity_score = round(
            spec["user_value"] * spec["business_value"] * spec["tech_feasibility"] / max(competition, 1), 1
        )
        if opportunity_score >= 20:
            recommendation = "推荐"
        elif opportunity_score >= 10:
            recommendation = "中"
        else:
            recommendation = "不建议"
        rows.append(
            {
                "id": slugify(spec["name"]),
                "label": spec["name"],
                "values": {
                    "覆盖竞品": f"{len(matched)}/{sample_count}：{'、'.join(matched[:4])}",
                    "用户价值": str(spec["user_value"]),
                    "商业价值": str(spec["business_value"]),
                    "技术可行性": str(spec["tech_feasibility"]),
                    "竞争强度": str(competition),
                    "机会分": f"{opportunity_score:.1f}",
                    "判断": recommendation,
                },
            }
        )
    rows.sort(key=lambda row: float(row["values"]["机会分"]), reverse=True)
    return rows


def _build_strategy_points(profiles: list[dict[str, Any]], feature_rows: list[dict[str, Any]]) -> list[str]:
    if not profiles:
        return []

    top_features = [row["label"] for row in feature_rows if row["values"].get("判断") == "推荐"][:3]
    mid_features = [row["label"] for row in feature_rows if row["values"].get("判断") == "中"][:4]
    low_features = [row["label"] for row in feature_rows if row["values"].get("判断") == "不建议"][:4]
    hardware_heavy = [profile for profile in profiles if profile["product_structure"] == "硬件+服务"]
    service_heavy = [profile for profile in profiles if profile["business_model"] == "服务收费"]
    software_weak = [profile for profile in profiles if profile["product_structure"] == "纯软件" and profile["conversion_score"] <= 2]

    strategy: list[str] = []
    if service_heavy:
        strategy.append("不建议做什么：不要直接从重履约服务撮合切入，因为样本里服务收费玩家已经先占住供给网络和履约心智，新玩家很容易被拖进重运营。")
    if hardware_heavy and software_weak:
        strategy.append("推荐切入点：先做软件型高频入口，再把入口接到订阅、电商或设备数据，而不是一开始就自己做硬件或重服务。")
    else:
        strategy.append("推荐切入点：优先从高频记录、提醒、档案这类轻功能切入，用高频使用先拿流量，再承接商业动作。")
    if top_features:
        strategy.append(f"发展路径：第一阶段先把{'、'.join(top_features)}做成稳定高频入口，第二阶段接入订阅或电商转化，第三阶段再把服务或设备数据接成闭环。")
    else:
        strategy.append("发展路径：先用轻量功能验证流量入口，再补订阅或成交链路，最后再扩展到更重的服务与硬件协同。")
    priority_parts = []
    if top_features:
        priority_parts.append(f"高机会：{'、'.join(top_features)}")
    if mid_features:
        priority_parts.append(f"中机会：{'、'.join(mid_features)}")
    if low_features:
        priority_parts.append(f"低机会：{'、'.join(low_features)}")
    if priority_parts:
        strategy.append("功能优先级：" + "；".join(priority_parts) + "。")
    return strategy[:4]


def derive_analysis_payload(items: list[dict[str, Any]]) -> dict[str, Any]:
    profiles = _build_company_profiles(items)
    core_summary, insights = _build_market_insights(profiles)
    feature_rows = _build_feature_priorities(profiles)
    return {
        "version": str(ANALYSIS_VERSION + 1),
        "engine": ANALYSIS_ENGINE,
        "summary": core_summary,
        "groups": _build_market_groups(profiles),
        "feature_matrix": {
            "row_label": "功能",
            "columns": ["覆盖竞品", "用户价值", "商业价值", "技术可行性", "竞争强度", "机会分", "判断"],
            "rows": feature_rows,
        },
        "insights": insights,
        "opportunities": _build_opportunities(profiles),
        "strategy": _build_strategy_points(profiles, feature_rows),
    }


def normalize_analysis_payload(analysis: dict[str, Any] | None, items: list[dict[str, Any]]) -> dict[str, Any] | None:
    if isinstance(analysis, dict) and clean_text(analysis.get("engine"), "") == ANALYSIS_ENGINE:
        payload = dict(analysis)
        payload.setdefault("feature_matrix", {"row_label": "功能", "columns": [], "rows": []})
        payload.setdefault("summary", "")
        payload.setdefault("groups", [])
        payload.setdefault("insights", [])
        payload.setdefault("opportunities", [])
        payload.setdefault("strategy", [])
        return payload
    return derive_analysis_payload(items)


def render_analysis_section(analysis: dict[str, Any] | None, items: list[dict[str, Any]]) -> str:
    normalized = normalize_analysis_payload(analysis, items)
    if not normalized:
        return ""

    def split_insight_text(text: str) -> tuple[str, str]:
        for marker in ["，说明", "，而", "，这说明", "，但"]:
            if marker in text:
                left, right = text.split(marker, 1)
                return left, marker.lstrip("，") + right
        return text, ""

    def parse_opportunity_text(text: str) -> tuple[str, str, str]:
        current = gap = opportunity = ""
        if "当前状态：" in text and "缺口：" in text and "机会方向：" in text:
            _, rest = text.split("当前状态：", 1)
            current, rest = rest.split("缺口：", 1)
            gap, opportunity = rest.split("机会方向：", 1)
        return current.strip(), gap.strip(), opportunity.strip()

    def strategy_bucket(items_list: list[str], prefix: str) -> list[str]:
        return [item.replace(prefix, "", 1).strip() for item in items_list if item.startswith(prefix)]

    insights_list = [clean_text(item, "") for item in normalized.get("insights", []) if clean_text(item, "")]
    core_summary = clean_text(normalized.get("summary"), "") or (
        insights_list[0] if insights_list else "当前竞品呈现多中心竞争结构，各能力模块由不同类型玩家分别占据。"
    )

    groups_html = ""
    groups = normalized.get("groups", [])
    if isinstance(groups, list) and groups:
        group_cards = []
        for group in groups:
            if not isinstance(group, dict):
                continue
            title = escape(clean_text(group.get("title"), "未命名分组"))
            description = escape(clean_text(group.get("description"), EMPTY_TEXT))
            members = []
            for raw_item in group.get("items", []):
                label = clean_text((raw_item or {}).get("label"), "")
                if label:
                    members.append(f'<span class="analysis-chip">{escape(label)}</span>')
            if not members:
                continue
            description_html = f'<p class="analysis-note">{description}</p>' if description != EMPTY_TEXT else ""
            group_cards.append(
                f"""
                <article class="analysis-card">
                  <h3>{title}</h3>
                  {description_html}
                  <div class="analysis-chip-row">{''.join(members)}</div>
                </article>
                """
            )
        if group_cards:
            groups_html = f"""
            <section class="analysis-block" id="market-structure" data-nav-section data-nav-group="分析" data-nav-label="市场结构">
              <h3 class="analysis-block-title">市场结构</h3>
              <div class="analysis-card-grid">{''.join(group_cards)}</div>
            </section>
            """

    feature_html = ""
    feature_matrix = normalized.get("feature_matrix", {})
    if isinstance(feature_matrix, dict):
        columns = feature_matrix.get("columns", [])
        rows = feature_matrix.get("rows", [])
        if isinstance(columns, list) and columns and isinstance(rows, list) and rows:
            row_label = escape(clean_text(feature_matrix.get("row_label"), "竞品"))
            header = "".join(f"<th>{escape(clean_text(col, ''))}</th>" for col in columns if clean_text(col, ""))
            body_rows = []
            for row in rows:
                if not isinstance(row, dict):
                    continue
                item_label = clean_text(row.get("label"), "")
                if not item_label:
                    continue
                values = []
                for col in columns:
                    col_label = clean_text(col, "")
                    if not col_label:
                        continue
                    values.append(f"<td>{format_analysis_text((row.get('values') or {}).get(col_label, EMPTY_TEXT))}</td>")
                body_rows.append(f"<tr><th>{escape(item_label)}</th>{''.join(values)}</tr>")
            if body_rows:
                feature_html = f"""
                <section class="analysis-block" id="feature-priority" data-nav-section data-nav-group="分析" data-nav-label="功能优先级">
                  <h3 class="analysis-block-title">功能优先级建议</h3>
                  <div class="analysis-table-wrap">
                    <table class="analysis-table">
                      <thead><tr><th>{row_label}</th>{header}</tr></thead>
                      <tbody>{''.join(body_rows)}</tbody>
                    </table>
                  </div>
                </section>
                """

    opportunities_html = ""
    insights_html = ""
    if insights_list:
        blocks = []
        for item in insights_list:
            headline, detail = split_insight_text(item)
            blocks.append(
                f"""
                <li class="insight-item">
                  <span class="insight-dot"></span>
                    <div class="insight-copy">
                    <div class="insight-headline">{format_analysis_text(headline)}</div>
                    {f'<div class="insight-detail">{format_analysis_text(detail)}</div>' if detail else ''}
                  </div>
                </li>
                """
            )
        if blocks:
            insights_html = f"""
            <section class="analysis-block" id="market-analysis" data-nav-section data-nav-group="分析" data-nav-label="市场/商业分析">
              <h3 class="analysis-block-title">市场/商业分析</h3>
              <ul class="analysis-insight-list">{''.join(blocks)}</ul>
            </section>
            """

    opportunities = normalized.get("opportunities", [])
    if isinstance(opportunities, list) and opportunities:
        cards = []
        for item in opportunities:
            text = clean_text(item, "")
            if text:
                current, gap, opportunity = parse_opportunity_text(text)
                title = current[:20] + ("..." if len(current) > 20 else "") if current else "机会点"
                cards.append(
                    f"""
                    <article class="opportunity-card">
                      <h4>{format_analysis_text(title)}</h4>
                      <div class="opportunity-row"><span>当前</span><p>{format_analysis_text(current)}</p></div>
                      <div class="opportunity-row"><span>缺口</span><p>{format_analysis_text(gap)}</p></div>
                      <div class="opportunity-row"><span>机会</span><p>{format_analysis_text(opportunity)}</p></div>
                    </article>
                    """
                )
        if cards:
            opportunities_html = f"""
            <section class="analysis-block" id="opportunity" data-nav-section data-nav-group="分析" data-nav-label="核心机会">
              <h3 class="analysis-block-title">核心机会</h3>
              <div class="opportunity-grid">{''.join(cards)}</div>
            </section>
            """

    strategy_html = ""
    strategy = normalized.get("strategy", [])
    if isinstance(strategy, list) and strategy:
        strategy_texts = [clean_text(item, "") for item in strategy if clean_text(item, "")]
        avoid = strategy_bucket(strategy_texts, "不建议做什么：")
        entry = strategy_bucket(strategy_texts, "推荐切入点：")
        path = strategy_bucket(strategy_texts, "发展路径：")
        priority = strategy_bucket(strategy_texts, "功能优先级：")
        groups = []
        if avoid:
            groups.append(f'<div class="strategy-group strategy-group--warn"><div class="strategy-label">不建议做</div><ul class="analysis-summary">{"".join(f"<li>{format_analysis_text(item)}</li>" for item in avoid)}</ul></div>')
        if entry:
            groups.append(f'<div class="strategy-group strategy-group--focus"><div class="strategy-label">推荐切入点</div><ul class="analysis-summary">{"".join(f"<li>{format_analysis_text(item)}</li>" for item in entry)}</ul></div>')
        if path:
            groups.append(f'<div class="strategy-group strategy-group--path"><div class="strategy-label">发展路径</div><ul class="analysis-summary">{"".join(f"<li>{format_analysis_text(item)}</li>" for item in path)}</ul></div>')
        if priority:
            groups.append(f'<div class="strategy-group strategy-group--focus"><div class="strategy-label">功能优先级</div><ul class="analysis-summary">{"".join(f"<li>{format_analysis_text(item)}</li>" for item in priority)}</ul></div>')
        if groups:
            strategy_html = f"""
            <section class="analysis-block" id="strategy" data-nav-section data-nav-group="分析" data-nav-label="策略建议">
              <h3 class="analysis-block-title">策略建议</h3>
              <div class="strategy-grid">{''.join(groups)}</div>
            </section>
            """

    core_html = f"""
    <section class="analysis-core" id="summary" data-nav-section data-nav-group="总览" data-nav-label="核心结论">
      <div class="analysis-core-label">核心结论</div>
      <div class="analysis-core-text">{format_analysis_text(core_summary)}</div>
    </section>
    """
    blocks = "".join(part for part in [core_html, groups_html, feature_html, insights_html, opportunities_html, strategy_html] if part)
    if not blocks:
        return ""

    return f"""
    <section class="analysis-section analysis-section--hero" id="analysis-section" data-nav-section data-nav-group="分析" data-nav-label="竞品分析">
      <div class="analysis-header">
        <div>
          <div class="eyebrow">竞品分析</div>
          <h2>竞品分析</h2>
        </div>
        <button type="button" class="export-btn" id="regenerateAnalysisBtn">重新生成分析</button>
      </div>
      <div id="analysisContent">{blocks}</div>
    </section>
    """


def render_report(manifest: dict[str, Any], items: list[dict[str, Any]], output_dir: Path, state_filename: str, analysis: dict[str, Any] | None) -> Path:
    title = clean_text(manifest.get("title"), DEFAULT_TITLE)
    subtitle = clean_text(manifest.get("subtitle"), EMPTY_TEXT)
    author = clean_text(manifest.get("author"), DEFAULT_AUTHOR)
    industry = clean_text(manifest.get("industry"), DEFAULT_INDUSTRY)

    cards = []
    for item in items:
        media_html = render_gallery(item)
        if not item.get("captures") and item.get("capture_error"):
            media_html += f'<div class="capture-note">自动截图失败：{escape(clean_text(item.get("capture_error")))}</div>'

        item_id = escape(get_item_id(item))
        item_name = escape(clean_text(item.get("name"), "未命名"))

        cards.append(
            f"""
            <section class="card product-card" id="brand-{item_id}" data-nav-section data-nav-group="竞品" data-nav-label="{item_name}" data-brand="{item_name}" data-item-id="{item_id}">
              <div class="media-panel">
                {media_html}
              </div>
              <div class="content info-panel">
                <h2 class="brand-name editable-field brand-editable" contenteditable="true" data-field="品牌名" data-empty="false">{item_name}</h2>
                <div class="info-content">
                  {render_links(item)}
                  <div class="detail-grid">
                    {render_details(item, manifest)}
                  </div>
                </div>
              </div>
            </section>
            """
        )

    export_fields_json = json.dumps(EXPORT_FIELDS, ensure_ascii=False)
    normalized_analysis = normalize_analysis_payload(analysis, items)
    initial_state_json = json.dumps(build_report_state(items, normalized_analysis), ensure_ascii=False)
    initial_analysis_json = json.dumps(normalized_analysis, ensure_ascii=False)
    analysis_html = render_analysis_section(normalized_analysis, items)
    sidebar_html = f"""
    <button type="button" class="side-nav-toggle" id="sideNavToggle" aria-controls="sideNav" aria-expanded="true">目录</button>
    <aside class="side-nav" id="sideNav">
      <div class="side-nav-inner">
        <div class="side-nav-title">快速定位</div>
        <nav class="side-nav-groups" id="sideNavGroups"></nav>
      </div>
    </aside>
    """
    html = f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)}</title>
  <style>
    :root {{
      --bg: #161108;
      --bg-soft: #1c1409;
      --panel: rgba(63, 48, 27, 0.56);
      --panel-soft: rgba(82, 63, 37, 0.52);
      --panel-strong: rgba(94, 72, 42, 0.62);
      --ink: #ffffff;
      --muted: rgba(255,255,255,0.62);
      --line: rgba(255,255,255,0.10);
      --accent: #F6DB58;
      --accent-blue: #8AA8FF;
      --accent-strong: #FF9A54;
      --accent-soft: rgba(246, 219, 88, 0.16);
      --blue-soft: rgba(138, 168, 255, 0.14);
      --shadow: 0 22px 58px rgba(0,0,0,0.34);
      --shadow-soft: 0 14px 34px rgba(0,0,0,0.24);
      --overlay: rgba(10, 7, 3, 0.72);
      --glass-sheen: rgba(255,255,255,0.12);
      --glass-border: rgba(255,255,255,0.10);
      --glass-border-strong: rgba(255, 216, 77, 0.18);
    }}
    * {{ box-sizing: border-box; }}
    html {{
      scroll-behavior: smooth;
    }}
    body {{
      margin: 0;
      font-family: "Segoe UI", Arial, sans-serif;
      color: var(--ink);
      background:
        radial-gradient(circle at 18% 10%, rgba(246, 219, 88, 0.12), transparent 24%),
        radial-gradient(circle at 82% 12%, rgba(255, 154, 84, 0.12), transparent 22%),
        radial-gradient(circle at 50% 0%, rgba(255,255,255,0.05), transparent 28%),
        linear-gradient(180deg, #171108 0%, #191208 48%, #1c1409 100%);
      padding: 40px 32px 56px 324px;
      transition: padding-left 0.22s ease;
    }}
    body.side-nav-collapsed {{
      padding-left: 32px;
    }}
    [data-nav-section] {{
      scroll-margin-top: 24px;
    }}
    .side-nav-toggle {{
      position: fixed;
      top: 24px;
      left: 24px;
      z-index: 120;
      border: 0;
      border-radius: 14px;
      min-width: 52px;
      height: 46px;
      padding: 0 14px;
      background: rgba(83, 62, 35, 0.62);
      color: #fff;
      font-size: 14px;
      font-weight: 700;
      cursor: pointer;
      box-shadow: 0 14px 28px rgba(0,0,0,0.24), inset 0 0 0 1px var(--glass-border);
      backdrop-filter: blur(16px);
      transition: transform 0.2s ease, background 0.2s ease, left 0.22s ease;
    }}
    .side-nav-toggle:hover {{
      transform: translateY(-1px);
      background: rgba(101, 76, 43, 0.74);
    }}
    body.side-nav-collapsed .side-nav-toggle {{
      left: 18px;
    }}
    .side-nav {{
      position: fixed;
      top: 82px;
      left: 20px;
      bottom: 24px;
      width: 276px;
      z-index: 110;
      border-radius: 22px;
      background: linear-gradient(180deg, rgba(70, 54, 32, 0.80) 0%, rgba(56, 42, 24, 0.76) 100%);
      box-shadow: 0 18px 42px rgba(0,0,0,0.28), inset 0 0 0 1px var(--glass-border);
      backdrop-filter: blur(18px);
      overflow: hidden;
      transition: width 0.22s ease, background 0.22s ease, box-shadow 0.22s ease, transform 0.22s ease, opacity 0.22s ease;
    }}
    .side-nav-inner {{
      height: 100%;
      padding: 18px 12px;
      overflow-y: auto;
      display: grid;
      align-content: start;
      gap: 18px;
    }}
    .side-nav-title,
    .side-nav-group-label,
    .side-nav-text,
    .side-nav-group-toggle-text {{
      transition: opacity 0.18s ease, transform 0.18s ease;
    }}
    .side-nav-title {{
      font-size: 14px;
      font-weight: 700;
      color: #fff;
      white-space: nowrap;
    }}
    .side-nav-group {{
      display: grid;
      gap: 8px;
      padding-top: 8px;
      border-top: 1px solid rgba(255,255,255,0.07);
    }}
    .side-nav-group-label {{
      font-size: 11px;
      letter-spacing: 0.08em;
      color: rgba(255,255,255,0.46);
      text-transform: uppercase;
      padding: 0 8px;
      white-space: nowrap;
    }}
    .side-nav-group-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 8px;
    }}
    .side-nav-group-toggle {{
      display: inline-flex;
      align-items: center;
      gap: 8px;
      width: 100%;
      border: 0;
      background: transparent;
      color: rgba(255,255,255,0.88);
      padding: 8px 10px;
      border-radius: 12px;
      cursor: pointer;
      text-align: left;
      transition: background 0.2s ease, color 0.2s ease;
    }}
    .side-nav-group-toggle:hover {{
      background: linear-gradient(180deg, rgba(69, 53, 31, 0.74) 0%, rgba(56, 42, 24, 0.72) 100%);
      color: #fff;
    }}
    .side-nav-group-toggle-text {{
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.04em;
    }}
    .side-nav-chevron {{
      margin-left: auto;
      width: 8px;
      height: 8px;
      border-right: 2px solid currentColor;
      border-bottom: 2px solid currentColor;
      transform: rotate(45deg);
      transition: transform 0.2s ease;
      flex: 0 0 auto;
    }}
    .side-nav-group.is-collapsed .side-nav-chevron {{
      transform: rotate(-45deg);
    }}
    .side-nav-group-body {{
      display: grid;
      gap: 8px;
      min-height: 0;
    }}
    .side-nav-group.is-collapsed .side-nav-group-body {{
      display: none;
    }}
    .side-nav-link {{
      display: flex;
      align-items: center;
      gap: 10px;
      min-width: 0;
      padding: 11px 14px 11px 18px;
      border-radius: 14px;
      color: rgba(255,255,255,0.72);
      text-decoration: none;
      background: rgba(255,255,255,0.025);
      box-shadow: inset 0 0 0 1px transparent;
      transition: background 0.2s ease, color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;
      position: relative;
    }}
    .side-nav-link:hover {{
      transform: translateX(2px);
      color: #fff;
      background: rgba(255,255,255,0.07);
      box-shadow: inset 0 0 0 1px rgba(255,255,255,0.10), 0 0 20px rgba(246,219,88,0.08);
    }}
    .side-nav-link::before {{
      content: "";
      position: absolute;
      left: 6px;
      top: 8px;
      bottom: 8px;
      width: 3px;
      border-radius: 999px;
      background: transparent;
      transition: background 0.2s ease, box-shadow 0.2s ease;
    }}
    .side-nav-link.is-active {{
      color: #111;
      background: linear-gradient(180deg, rgba(246,219,88,0.94) 0%, rgba(240,205,74,0.94) 100%);
      box-shadow: 0 14px 28px rgba(246,219,88,0.20);
    }}
    .side-nav-link.is-active::before {{
      background: #111;
      box-shadow: 0 0 10px rgba(17,17,17,0.18);
    }}
    .side-nav-dot {{
      width: 8px;
      height: 8px;
      border-radius: 999px;
      background: currentColor;
      flex: 0 0 auto;
    }}
    .side-nav-text {{
      min-width: 0;
      flex: 1 1 auto;
      overflow: visible;
      white-space: normal;
      font-size: 13px;
      line-height: 1.35;
    }}
    body.side-nav-collapsed .side-nav {{
      width: 276px;
      transform: translateX(calc(-100% - 12px));
      opacity: 0.92;
    }}
    body.side-nav-collapsed .side-nav-title,
    body.side-nav-collapsed .side-nav-group-label,
    body.side-nav-collapsed .side-nav-text,
    body.side-nav-collapsed .side-nav-group-toggle-text {{
      opacity: 0;
      transform: translateX(-8px);
      pointer-events: none;
    }}
    body.side-nav-collapsed .side-nav-link {{
      justify-content: center;
      padding: 11px 0;
    }}
    body.side-nav-collapsed .side-nav-inner {{
      pointer-events: none;
    }}
    body.side-nav-collapsed .side-nav-link::before {{
      left: 4px;
    }}
    body.side-nav-collapsed .side-nav-chevron {{
      display: none;
    }}
    header {{
      max-width: 1520px;
      margin: 0 auto 24px;
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 20px;
    }}
    .hero-copy {{ min-width: 0; }}
    .eyebrow {{
      display: inline-flex;
      align-items: center;
      padding: 7px 14px;
      border-radius: 999px;
      background: rgba(255,255,255,0.05);
      color: var(--accent);
      font-size: 13px;
      font-weight: 600;
      margin-bottom: 14px;
      box-shadow: inset 0 0 0 1px rgba(255,255,255,0.08), 0 12px 28px rgba(0,0,0,0.24);
      backdrop-filter: blur(14px);
    }}
    h1 {{
      margin: 0 0 10px;
      font-size: 44px;
      line-height: 1.08;
      letter-spacing: -0.02em;
    }}
    .subtitle {{
      margin: 0;
      color: var(--muted);
      font-size: 15px;
      line-height: 1.9;
      max-width: 980px;
    }}
    .author {{
      margin-top: 12px;
      color: rgba(255,255,255,0.58);
      font-size: 14px;
    }}
    .toolbar {{
      display: flex;
      align-items: center;
      flex-wrap: wrap;
      gap: 14px;
      flex-shrink: 0;
      justify-content: flex-end;
    }}
    .export-btn {{
      appearance: none;
      border: 0;
      border-radius: 16px;
      background: var(--accent);
      box-shadow: 0 16px 36px rgba(0,0,0,0.28);
      color: #111;
      backdrop-filter: blur(18px);
      padding: 13px 20px;
      font-size: 14px;
      font-weight: 600;
      cursor: pointer;
      transition: transform 0.2s ease, box-shadow 0.2s ease, opacity 0.2s ease;
    }}
    #exportCsvBtn,
    #regenerateAnalysisBtn {{
      background: var(--accent);
      color: #111;
      box-shadow: 0 16px 36px rgba(255, 216, 77, 0.18), 0 10px 28px rgba(0,0,0,0.24);
    }}
    #exportStateBtn,
    #resetStateBtn,
    .import-label {{
      background: linear-gradient(180deg, rgba(84, 64, 37, 0.64) 0%, rgba(71, 54, 31, 0.60) 100%);
      color: rgba(255,255,255,0.85);
      box-shadow: 0 12px 24px rgba(0,0,0,0.22), inset 0 0 0 1px rgba(255,255,255,0.10);
    }}
    .export-btn:hover {{
      transform: translateY(-1px);
      box-shadow: 0 20px 42px rgba(0,0,0,0.34);
    }}
    .export-btn:active {{
      transform: translateY(0);
      opacity: 0.95;
    }}
    .toolbar .import-label {{
      position: relative;
      overflow: hidden;
    }}
    .state-input {{
      position: absolute;
      inset: 0;
      opacity: 0;
      cursor: pointer;
    }}
    .report {{
      max-width: 1520px;
      margin: 0 auto;
      display: grid;
      gap: 28px;
    }}
    .analysis-section {{
      max-width: 1520px;
      margin: 36px auto 0;
      background: rgba(255,255,255,0.068);
      border-radius: 24px;
      padding: 28px;
      box-shadow: 0 18px 50px rgba(0,0,0,0.45);
      border: 1px solid rgba(255,255,255,0.10);
      backdrop-filter: blur(16px);
      display: grid;
      gap: 24px;
    }}
    .analysis-section--hero {{
      background:
        radial-gradient(circle at top right, rgba(255, 216, 77, 0.08), transparent 30%),
        linear-gradient(180deg, rgba(255,255,255,0.082) 0%, rgba(255,255,255,0.072) 100%);
      border: 1px solid rgba(255, 216, 77, 0.18);
      box-shadow: 0 22px 60px rgba(0,0,0,0.46), 0 0 0 1px rgba(255, 216, 77, 0.06), 0 0 26px rgba(255, 216, 77, 0.08);
    }}
    .analysis-header {{
      display: flex;
      align-items: flex-start;
      justify-content: space-between;
      gap: 16px;
    }}
    .analysis-core {{
      display: grid;
      gap: 12px;
      padding: 28px 30px;
      border-radius: 20px;
      background:
        radial-gradient(circle at top right, rgba(255, 216, 77, 0.16), transparent 34%),
        linear-gradient(135deg, rgba(255,255,255,0.092) 0%, rgba(255,255,255,0.048) 100%);
      box-shadow: 0 20px 54px rgba(0,0,0,0.40), 0 0 0 1px rgba(255, 216, 77, 0.06);
      border: 1px solid rgba(255, 216, 77, 0.16);
      position: relative;
      overflow: hidden;
    }}
    .analysis-core::after {{
      content: "";
      position: absolute;
      inset: 0;
      background: linear-gradient(180deg, rgba(255,255,255,0.13) 0%, rgba(255,255,255,0.03) 28%, rgba(255,255,255,0.00) 54%);
      pointer-events: none;
    }}
    .analysis-core-label {{
      font-size: 13px;
      letter-spacing: 0.12em;
      color: rgba(255,255,255,0.72);
      text-transform: uppercase;
    }}
    .analysis-core-text {{
      font-size: 31px;
      line-height: 1.5;
      font-weight: 700;
      color: #fff;
    }}
    .analysis-emphasis {{
      color: #FFD84D;
      font-weight: 800;
      text-shadow: 0 0 14px rgba(255, 216, 77, 0.16);
    }}
    .analysis-emphasis:nth-of-type(2n) {{
      color: #FF8A3D;
      text-shadow: 0 0 14px rgba(255, 138, 61, 0.14);
    }}
    .analysis-header h2 {{
      margin: 8px 0 0;
      font-size: 38px;
      letter-spacing: 0.01em;
    }}
    .analysis-block {{
      display: grid;
      gap: 16px;
    }}
    .analysis-block-title {{
      margin: 0;
      font-size: 22px;
    }}
    .analysis-card-grid {{
      display: grid;
      gap: 14px;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    }}
    .analysis-card {{
      border-radius: 18px;
      background: linear-gradient(180deg, rgba(255,255,255,0.075) 0%, rgba(255,255,255,0.058) 100%);
      padding: 18px;
      display: grid;
      gap: 12px;
      box-shadow: 0 18px 50px rgba(0,0,0,0.45);
      border: 1px solid rgba(255,255,255,0.10);
      backdrop-filter: blur(14px);
      position: relative;
      overflow: hidden;
      transition: transform 0.22s ease, box-shadow 0.22s ease, border-color 0.22s ease, background 0.22s ease;
    }}
    .analysis-card::before {{
      content: "";
      position: absolute;
      inset: 0;
      background: linear-gradient(180deg, var(--glass-sheen) 0%, rgba(255,255,255,0.03) 24%, rgba(255,255,255,0.00) 50%);
      pointer-events: none;
    }}
    .analysis-card:hover {{
      transform: translateY(-2px);
      border-color: rgba(255,255,255,0.14);
      box-shadow: 0 20px 52px rgba(0,0,0,0.48);
      background: linear-gradient(180deg, rgba(255,255,255,0.082) 0%, rgba(255,255,255,0.066) 100%);
    }}
    .analysis-card h3 {{
      margin: 0;
      font-size: 18px;
    }}
    .analysis-note {{
      margin: 0;
      color: var(--muted);
      font-size: 14px;
      line-height: 1.82;
    }}
    .analysis-chip-row {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
    }}
    .analysis-chip {{
      display: inline-flex;
      align-items: center;
      padding: 7px 10px;
      border-radius: 999px;
      color: var(--accent);
      font-size: 13px;
      font-weight: 600;
      box-shadow: inset 0 0 0 1px rgba(255,255,255,0.10);
      background: rgba(255,255,255,0.045);
    }}
    .analysis-table-wrap {{
      overflow-x: auto;
      border-radius: 18px;
      background: linear-gradient(180deg, rgba(255,255,255,0.074) 0%, rgba(255,255,255,0.058) 100%);
      box-shadow: 0 18px 50px rgba(0,0,0,0.45);
      border: 1px solid rgba(255,255,255,0.10);
    }}
    .analysis-table {{
      width: 100%;
      border-collapse: collapse;
      min-width: 760px;
    }}
    .analysis-table th,
    .analysis-table td {{
      padding: 12px 14px;
      border-bottom: 1px solid rgba(255,255,255,0.08);
      text-align: left;
      vertical-align: top;
      font-size: 14px;
      line-height: 1.6;
    }}
    .analysis-table thead th {{
      background: rgba(255,255,255,0.05);
      color: rgba(255,255,255,0.72);
      font-weight: 700;
    }}
    .analysis-tag-list {{
      display: grid;
      gap: 12px;
    }}
    .analysis-tag-row {{
      display: grid;
      gap: 8px;
      padding: 14px 16px;
      border: 1px solid rgba(255,255,255,0.10);
      border-radius: 16px;
      background: linear-gradient(180deg, rgba(255,255,255,0.072) 0%, rgba(255,255,255,0.056) 100%);
      backdrop-filter: blur(14px);
      transition: transform 0.22s ease, box-shadow 0.22s ease, border-color 0.22s ease, background 0.22s ease;
    }}
    .analysis-tag-row:hover {{
      transform: translateY(-1px);
      border-color: rgba(255,255,255,0.14);
      background: linear-gradient(180deg, rgba(255,255,255,0.078) 0%, rgba(255,255,255,0.062) 100%);
      box-shadow: 0 18px 50px rgba(0,0,0,0.46);
    }}
    .analysis-tag-label {{
      font-size: 15px;
      font-weight: 700;
    }}
    .analysis-summary {{
      margin: 0;
      padding-left: 20px;
      display: grid;
      gap: 12px;
      line-height: 1.9;
    }}
    .analysis-insight-list {{
      list-style: none;
      margin: 0;
      padding: 0;
      display: grid;
      gap: 12px;
    }}
    .insight-item {{
      display: grid;
      grid-template-columns: 12px minmax(0, 1fr);
      gap: 14px;
      align-items: flex-start;
      padding: 18px 18px;
      border-radius: 18px;
      background: linear-gradient(180deg, rgba(255,255,255,0.074) 0%, rgba(255,255,255,0.058) 100%);
      box-shadow: 0 18px 50px rgba(0,0,0,0.45);
      border: 1px solid rgba(255,255,255,0.10);
      backdrop-filter: blur(14px);
      transition: transform 0.22s ease, box-shadow 0.22s ease, border-color 0.22s ease, background 0.22s ease;
    }}
    .insight-item:hover {{
      transform: translateY(-1px);
      border-color: rgba(255,255,255,0.14);
      background: linear-gradient(180deg, rgba(255,255,255,0.082) 0%, rgba(255,255,255,0.064) 100%);
      box-shadow: 0 20px 54px rgba(0,0,0,0.48);
    }}
    .insight-dot {{
      width: 10px;
      height: 10px;
      border-radius: 999px;
      margin-top: 8px;
      background: linear-gradient(135deg, var(--accent) 0%, var(--accent-strong) 100%);
      box-shadow: 0 0 0 5px rgba(255, 216, 77, 0.12);
    }}
    .insight-copy {{
      display: grid;
      gap: 6px;
    }}
    .insight-headline {{
      font-size: 15px;
      line-height: 1.9;
      font-weight: 700;
    }}
    .insight-detail {{
      font-size: 14px;
      line-height: 1.95;
      color: var(--muted);
    }}
    .opportunity-grid {{
      display: grid;
      gap: 18px;
      grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
    }}
    .opportunity-card {{
      display: grid;
      gap: 14px;
      padding: 20px;
      border-radius: 18px;
      background: linear-gradient(180deg, rgba(255,255,255,0.074) 0%, rgba(255,255,255,0.058) 100%);
      box-shadow: 0 18px 50px rgba(0,0,0,0.45);
      border: 1px solid rgba(255,255,255,0.10);
      backdrop-filter: blur(14px);
      transition: border-color 0.2s ease, background 0.2s ease, transform 0.2s ease;
      position: relative;
      overflow: hidden;
    }}
    .opportunity-card::before {{
      content: "";
      position: absolute;
      inset: 0;
      background: linear-gradient(180deg, var(--glass-sheen) 0%, rgba(255,255,255,0.03) 20%, rgba(255,255,255,0.00) 46%);
      pointer-events: none;
    }}
    .opportunity-card:hover {{
      background: linear-gradient(180deg, rgba(255,255,255,0.082) 0%, rgba(255,255,255,0.064) 100%);
      border-color: rgba(255,255,255,0.14);
      transform: translateY(-2px);
      box-shadow: 0 20px 54px rgba(0,0,0,0.48);
    }}
    .opportunity-card h4 {{
      margin: 0;
      font-size: 17px;
    }}
    .opportunity-row {{
      display: grid;
      gap: 8px;
      padding-top: 8px;
      border-top: 1px solid rgba(255,255,255,0.09);
    }}
    .opportunity-row:first-of-type {{
      padding-top: 0;
      border-top: 0;
    }}
    .opportunity-row span {{
      font-size: 12px;
      letter-spacing: 0.06em;
      color: var(--accent);
      font-weight: 700;
    }}
    .opportunity-row p {{
      margin: 0;
      font-size: 14px;
      line-height: 1.86;
    }}
    .strategy-grid {{
      display: grid;
      gap: 18px;
      grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
    }}
    .strategy-group {{
      display: grid;
      gap: 12px;
      padding: 20px;
      border-radius: 18px;
      box-shadow: 0 18px 50px rgba(0,0,0,0.45);
      background: linear-gradient(180deg, rgba(255,255,255,0.074) 0%, rgba(255,255,255,0.058) 100%);
      border: 1px solid rgba(255,255,255,0.10);
      backdrop-filter: blur(14px);
      transition: transform 0.22s ease, box-shadow 0.22s ease, border-color 0.22s ease, background 0.22s ease;
    }}
    .strategy-group:hover {{
      transform: translateY(-2px);
      border-color: rgba(255,255,255,0.14);
      background: linear-gradient(180deg, rgba(255,255,255,0.082) 0%, rgba(255,255,255,0.064) 100%);
      box-shadow: 0 20px 54px rgba(0,0,0,0.48);
    }}
    .strategy-group--warn {{
      background: linear-gradient(180deg, rgba(90, 67, 38, 0.48) 0%, rgba(75, 52, 28, 0.42) 100%);
      box-shadow:
        inset 3px 0 0 rgba(255,138,61,0.7),
        0 12px 30px rgba(0,0,0,0.32);
    }}
    .strategy-group--focus {{
      background: linear-gradient(180deg, rgba(86, 69, 36, 0.48) 0%, rgba(72, 56, 28, 0.42) 100%);
      box-shadow:
        inset 3px 0 0 rgba(255,216,77,0.78),
        0 12px 30px rgba(0,0,0,0.32);
    }}
    .strategy-group--path {{
      background: linear-gradient(180deg, rgba(66, 58, 43, 0.48) 0%, rgba(55, 48, 35, 0.42) 100%);
      box-shadow:
        inset 3px 0 0 rgba(124,154,255,0.7),
        0 12px 30px rgba(0,0,0,0.32);
    }}
    .strategy-label {{
      display: inline-flex;
      align-items: center;
      width: fit-content;
      padding: 6px 10px;
      border-radius: 999px;
      font-size: 12px;
      font-weight: 700;
      letter-spacing: 0.04em;
      color: rgba(255,255,255,0.82);
      background: rgba(255,255,255,0.05);
      box-shadow: inset 0 0 0 1px rgba(255,255,255,0.10);
    }}
    .card {{
      display: grid;
      grid-template-columns: minmax(0, 56%) minmax(0, 44%);
      height: 760px;
      min-height: 760px;
      max-height: 760px;
      gap: 32px;
      align-items: stretch;
      background: linear-gradient(180deg, rgba(255,255,255,0.074) 0%, rgba(255,255,255,0.058) 100%);
      border-radius: 24px;
      padding: 28px;
      box-shadow: 0 18px 50px rgba(0,0,0,0.45);
      border: 1px solid rgba(255,255,255,0.10);
      backdrop-filter: blur(14px);
      overflow: hidden;
      box-sizing: border-box;
      position: relative;
      transition: transform 0.24s ease, box-shadow 0.24s ease, border-color 0.24s ease, background 0.24s ease;
    }}
    .card::before {{
      content: "";
      position: absolute;
      inset: 0;
      background:
        linear-gradient(180deg, var(--glass-sheen) 0%, rgba(255,255,255,0.03) 18%, rgba(255,255,255,0.00) 42%),
        radial-gradient(circle at top left, rgba(255,255,255,0.05), transparent 26%);
      pointer-events: none;
    }}
    .card:hover {{
      transform: translateY(-3px);
      border-color: rgba(255,255,255,0.14);
      box-shadow: 0 22px 56px rgba(0,0,0,0.48);
      background: linear-gradient(180deg, rgba(255,255,255,0.082) 0%, rgba(255,255,255,0.064) 100%);
    }}
    .media-panel {{
      min-width: 0;
      height: 100%;
      max-height: 100%;
      display: flex;
      flex-direction: column;
      box-sizing: border-box;
      overflow: hidden;
    }}
    .content {{
      min-width: 0;
      height: 100%;
      max-height: 100%;
      align-self: stretch;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }}
    .gallery-shell {{
      border-radius: 20px;
      background: transparent;
      padding: 0;
      height: 100%;
      max-height: 100%;
      width: 100%;
      box-sizing: border-box;
      display: flex;
      flex-direction: column;
      overflow: hidden;
      box-shadow: none;
      backdrop-filter: none;
      position: relative;
    }}
    .gallery-shell::before {{
      display: none;
    }}
    .gallery-toolbar {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 14px;
      flex-wrap: wrap;
    }}
    .upload-btn {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      padding: 10px 14px;
      border-radius: 12px;
      background: rgba(255,255,255,0.07);
      color: rgba(255,255,255,0.85);
      font-weight: 600;
      cursor: pointer;
      box-shadow: 0 12px 24px rgba(0,0,0,0.24), inset 0 0 0 1px rgba(255,255,255,0.10);
      backdrop-filter: blur(14px);
      transition: transform 0.2s ease, box-shadow 0.2s ease, background 0.2s ease;
    }}
    .upload-btn:hover {{
      transform: translateY(-1px);
      background: linear-gradient(180deg, rgba(95, 72, 42, 0.74) 0%, rgba(82, 63, 37, 0.70) 100%);
      box-shadow: 0 16px 28px rgba(0,0,0,0.24), inset 0 0 0 1px rgba(246, 219, 88, 0.16);
    }}
    .upload-input {{ display: none; }}
    .gallery-hint {{
      color: var(--muted);
      font-size: 13px;
    }}
    .gallery-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(0, 1fr));
      grid-template-rows: repeat(2, minmax(0, 1fr));
      gap: 12px;
      flex: 1 1 0;
      height: 100%;
      max-height: 100%;
      min-height: 0;
      overflow: hidden;
      padding: 16px;
      border-radius: 18px;
      border: 1px dashed rgba(255,255,255,0.18);
      background: rgba(255,255,255,0.022);
    }}
    .gallery-grid.count-0,
    .gallery-grid.count-1 {{
      grid-template-columns: 1fr;
      grid-template-rows: 1fr;
    }}
    .gallery-grid.count-2 {{
      grid-template-columns: repeat(2, minmax(0, 1fr));
      grid-template-rows: 1fr;
    }}
    .gallery-grid.count-3 {{
      grid-template-columns: repeat(3, minmax(0, 1fr));
      grid-template-rows: 1fr;
    }}
    .gallery-grid.count-4 {{
      grid-template-columns: repeat(2, minmax(0, 1fr));
      grid-template-rows: repeat(2, minmax(0, 1fr));
    }}
    .gallery-grid.count-5,
    .gallery-grid.count-6 {{
      grid-template-columns: repeat(3, minmax(0, 1fr));
      grid-template-rows: repeat(2, minmax(0, 1fr));
    }}
    .gallery-item {{
      position: relative;
      overflow: hidden;
      border-radius: 14px;
      background: rgba(255,255,255,0.03);
      min-height: 0;
      height: 100%;
      width: 100%;
      display: flex;
      align-items: stretch;
      justify-content: stretch;
      box-shadow: inset 0 0 0 1px rgba(255,255,255,0.06);
    }}
    .gallery-image {{
      width: 100%;
      height: 100%;
      object-fit: contain;
      display: block;
      cursor: zoom-in;
      background: rgba(255,255,255,0.025);
      padding: 6px;
    }}
    .gallery-caption {{
      position: absolute;
      left: 10px;
      bottom: 10px;
      background: rgba(22, 16, 8, 0.72);
      color: #fff;
      font-size: 12px;
      padding: 6px 10px;
      border-radius: 999px;
    }}
    .delete-btn {{
      position: absolute;
      top: 10px;
      right: 10px;
      z-index: 1;
      border: 0;
      background: rgba(31, 22, 11, 0.82);
      color: #fff;
      border-radius: 999px;
      min-width: 54px;
      height: 32px;
      padding: 0 12px;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      cursor: pointer;
      font-size: 12px;
      font-weight: 600;
    }}
    .delete-btn:hover {{ background: rgba(182, 101, 49, 0.92); }}
    .empty-state {{
      grid-column: 1 / -1;
      grid-row: 1 / -1;
      min-height: 100%;
      border-radius: 16px;
      border: 1px dashed rgba(255,255,255,0.12);
      display: grid;
      place-items: center;
      text-align: center;
      color: var(--muted);
      gap: 8px;
      background: rgba(255,255,255,0.018);
      padding: 24px;
    }}
    .empty-state span {{ font-size: 13px; }}
    .content h2 {{
      margin: 0 0 16px;
      font-size: 30px;
      outline: none;
      border-radius: 10px;
      padding: 2px 4px;
      transition: background 0.2s ease, box-shadow 0.2s ease;
    }}
    .brand-editable:hover {{
      background: rgba(255,255,255,0.035);
      cursor: text;
    }}
    .brand-editable:focus {{
      background: rgba(255,255,255,0.05);
      box-shadow: 0 0 0 2px rgba(255,216,77,0.18);
    }}
    .link-grid {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-bottom: 16px;
    }}
    .info-content {{
      flex: 1 1 auto;
      min-height: 0;
      overflow-y: auto;
      overflow-x: hidden;
      padding-right: 6px;
    }}
    .pill-link {{
      display: inline-flex;
      align-items: center;
      padding: 10px 14px;
      border-radius: 999px;
      background: linear-gradient(180deg, rgba(84, 64, 37, 0.64) 0%, rgba(71, 54, 31, 0.60) 100%);
      color: rgba(255,255,255,0.85);
      font-size: 13px;
      font-weight: 600;
      text-decoration: none;
      box-shadow: 0 12px 24px rgba(0,0,0,0.22), inset 0 0 0 1px rgba(255,255,255,0.10);
      backdrop-filter: blur(14px);
      transition: transform 0.2s ease, box-shadow 0.2s ease, background 0.2s ease, border-color 0.2s ease;
    }}
    .pill-link:hover {{
      background: linear-gradient(180deg, rgba(95, 72, 42, 0.74) 0%, rgba(82, 63, 37, 0.70) 100%);
      transform: translateY(-1px);
      box-shadow: 0 16px 28px rgba(0,0,0,0.24), inset 0 0 0 1px rgba(246, 219, 88, 0.16);
    }}
    .detail-grid {{
      display: grid;
      gap: 12px;
    }}
    .detail-row {{
      display: grid;
      gap: 9px;
      padding: 14px 16px;
      border-radius: 16px;
      background: linear-gradient(180deg, rgba(255,255,255,0.072) 0%, rgba(255,255,255,0.056) 100%);
      transition: background 0.2s ease, border-color 0.2s ease, transform 0.2s ease;
      position: relative;
      min-height: 72px;
      max-height: 96px;
      overflow: hidden;
      box-shadow: 0 18px 50px rgba(0,0,0,0.45), inset 0 0 0 1px rgba(255,255,255,0.10);
      backdrop-filter: blur(14px);
    }}
    .detail-row:hover {{
      background: linear-gradient(180deg, rgba(255,255,255,0.080) 0%, rgba(255,255,255,0.064) 100%);
      border-color: rgba(255,255,255,0.14);
      transform: translateY(-2px);
      box-shadow: 0 16px 36px rgba(0,0,0,0.28), inset 0 0 0 1px rgba(255,255,255,0.12);
    }}
    .detail-row.is-editable::after {{
      content: "点击编辑";
      position: absolute;
      top: 12px;
      right: 14px;
      font-size: 11px;
      color: rgba(127, 116, 107, 0.72);
      opacity: 0;
      transition: opacity 0.2s ease;
      pointer-events: none;
    }}
    .detail-row.is-editable:hover::after {{
      opacity: 1;
    }}
    .detail-row--static {{
      background: linear-gradient(180deg, rgba(255,255,255,0.074) 0%, rgba(255,255,255,0.058) 100%);
    }}
    .detail-label {{
      font-size: 12px;
      color: rgba(255,255,255,0.48);
      letter-spacing: 0.04em;
    }}
    .detail-link {{
      color: var(--accent);
      text-decoration: none;
      word-break: break-all;
      font-size: 15px;
      line-height: 1.7;
      font-weight: 600;
    }}
    .detail-link:hover {{
      text-decoration: underline;
    }}
    .detail-value {{
      font-size: 15px;
      line-height: 1.72;
      white-space: pre-wrap;
      word-break: break-word;
      outline: none;
      border-radius: 8px;
      padding: 2px 4px;
      transition: background 0.2s ease;
    }}
    .detail-row[data-row-field="App 完整功能"] .detail-value,
    .detail-row[data-row-field="App 亮点功能"] .detail-value,
    .detail-row[data-row-field="商业模式"] .detail-value {{
      max-height: 100px;
      overflow-y: auto;
      padding-right: 4px;
    }}
    .detail-value:hover {{ background: rgba(255,255,255,0.035); }}
    .detail-value:focus {{
      background: rgba(255,255,255,0.06);
      box-shadow: 0 0 0 2px rgba(246,219,88,0.18);
    }}
    .detail-value[data-empty="true"] {{ color: rgba(255,255,255,0.34); }}
    .capture-note {{
      margin-top: 12px;
      color: var(--accent);
      font-size: 13px;
      line-height: 1.6;
    }}
    .lightbox {{
      position: fixed;
      inset: 0;
      background: var(--overlay);
      display: none;
      align-items: center;
      justify-content: center;
      padding: 24px;
      z-index: 99;
    }}
    .lightbox.is-open {{ display: flex; }}
    .lightbox-image {{
      max-width: min(94vw, 1440px);
      max-height: 88vh;
      border-radius: 18px;
      box-shadow: 0 22px 60px rgba(0,0,0,0.4);
    }}
    .lightbox-close {{
      position: absolute;
      top: 24px;
      right: 24px;
      border-radius: 999px;
      border: 0;
      background: rgba(82, 63, 37, 0.72);
      color: #fff;
      min-width: 68px;
      height: 42px;
      padding: 0 14px;
      cursor: pointer;
      font-size: 14px;
      font-weight: 600;
    }}
    @media (max-width: 1080px) {{
      body,
      body.side-nav-collapsed {{
        padding-left: 32px;
      }}
      .side-nav {{
        display: none;
      }}
      .side-nav-groups {{
        display: none;
      }}
      .side-nav-toggle {{
        left: 24px;
      }}
      header {{ flex-direction: column; }}
      .toolbar {{ width: 100%; }}
      .export-btn {{ width: 100%; }}
      .card {{
        grid-template-columns: 1fr;
        height: auto;
        min-height: 0;
        max-height: none;
      }}
      .media-panel,
      .gallery-shell {{
        height: 520px;
        max-height: 520px;
      }}
      .content {{
        height: auto;
        max-height: none;
      }}
      .info-content {{
        overflow: visible;
        padding-right: 0;
      }}
    }}
</style>
</head>
<body>
  {sidebar_html}
  <header id="page-top" data-nav-section data-nav-group="总览" data-nav-label="报告顶部">
    <div class="hero-copy">
      <div class="eyebrow">{escape(industry)}</div>
      <h1>{escape(title)}</h1>
      <p class="subtitle">{escape(subtitle)}</p>
      <div class="author">作者：{escape(author)}</div>
    </div>
    <div class="toolbar">
      <button type="button" class="export-btn" id="exportStateBtn">导出状态 JSON</button>
      <label class="export-btn import-label">
        导入状态 JSON
        <input type="file" accept=".json,application/json" class="state-input" id="importStateInput">
      </label>
      <button type="button" class="export-btn" id="resetStateBtn">重置当前状态</button>
      <button type="button" class="export-btn" id="exportCsvBtn">导出表格</button>
    </div>
  </header>
  <main class="report">
    {''.join(cards)}
  </main>
  {analysis_html}
  <div class="lightbox" id="lightbox">
    <button type="button" class="lightbox-close" id="lightboxClose" aria-label="关闭大图">关闭</button>
    <img class="lightbox-image" id="lightboxImage" src="" alt="">
  </div>
  <script>
    (() => {{
      const exportFields = {export_fields_json};
      const initialReportState = {initial_state_json};
      const initialAnalysisData = {initial_analysis_json};
      const defaultStateFilename = {json.dumps(state_filename, ensure_ascii=False)};
      const lightbox = document.getElementById('lightbox');
      const lightboxImage = document.getElementById('lightboxImage');
      const lightboxClose = document.getElementById('lightboxClose');
      const exportBtn = document.getElementById('exportCsvBtn');
      const exportStateBtn = document.getElementById('exportStateBtn');
      const importStateInput = document.getElementById('importStateInput');
      const resetStateBtn = document.getElementById('resetStateBtn');
      const regenerateAnalysisBtn = document.getElementById('regenerateAnalysisBtn');
      const analysisContent = document.getElementById('analysisContent');
      const sideNavGroups = document.getElementById('sideNavGroups');
      const sideNavToggle = document.getElementById('sideNavToggle');
      let currentAnalysisData = initialAnalysisData;
      let sectionObserver = null;
      let sideNavLinks = [];

      function openLightbox(src, alt) {{
        lightboxImage.src = src;
        lightboxImage.alt = alt || '放大查看';
        lightbox.classList.add('is-open');
      }}

      function closeLightbox() {{
        lightbox.classList.remove('is-open');
        lightboxImage.src = '';
      }}

      function normalizeEditable(field) {{
        const text = (field.textContent || '').trim();
        if (!text) {{
          field.textContent = '{EMPTY_TEXT}';
          field.dataset.empty = 'true';
        }} else {{
          field.dataset.empty = text === '{EMPTY_TEXT}' ? 'true' : 'false';
        }}
      }}

      function escapeCsv(value) {{
        const text = String(value || '').replace(/"/g, '""');
        return '"' + text + '"';
      }}

      function exportCsv() {{
        const rows = [['品牌名'].concat(exportFields)];
        document.querySelectorAll('.card').forEach((card) => {{
          const brandNode = card.querySelector('.brand-name');
          const brand = brandNode ? ((brandNode.textContent || '').trim() || '{EMPTY_TEXT}') : (card.dataset.brand || '{EMPTY_TEXT}');
          const row = [brand];
          exportFields.forEach((field) => {{
            if (field === '官网链接') {{
              const websiteNode = card.querySelector('.website-link');
              const value = websiteNode ? (websiteNode.getAttribute('href') || websiteNode.textContent || '').trim() || '{EMPTY_TEXT}' : '{EMPTY_TEXT}';
              row.push(value);
              return;
            }}
            const node = card.querySelector('.detail-value[data-field="' + field + '"]');
            const value = node ? ((node.textContent || '').trim() || '{EMPTY_TEXT}') : '{EMPTY_TEXT}';
            row.push(value);
          }});
          rows.push(row);
        }});

        const csv = '\\ufeff' + rows.map((row) => row.map(escapeCsv).join(',')).join('\\r\\n');
        window.__reportCsvPreview = csv;
        window.__reportCsvFilename = '宠物竞品分析图谱.csv';
        const blob = new Blob([csv], {{ type: 'text/csv;charset=utf-8;' }});
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = '宠物竞品分析图谱.csv';
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
      }}

      function syncMediaHeight(card) {{
        return;
      }}

      function syncAllMediaHeights() {{
        return;
      }}

      function triggerDownload(filename, content, type) {{
        const blob = new Blob([content], {{ type }});
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
      }}

      function fileToDataUrl(file) {{
        return new Promise((resolve, reject) => {{
          const reader = new FileReader();
          reader.onload = () => resolve(String(reader.result || ''));
          reader.onerror = () => reject(reader.error || new Error('读取文件失败'));
          reader.readAsDataURL(file);
        }});
      }}

      function createGalleryItemMarkup(capture) {{
        const label = capture.label || '手动上传';
        const path = capture.path || '';
        const kind = capture.kind || (path.startsWith('data:image/') ? 'uploaded' : 'existing');
        return (
          '<button type="button" class="delete-btn" aria-label="删除图片">删除</button>' +
          '<img src="' + path + '" alt="' + label + '" class="gallery-image" data-full-src="' + path + '">' +
          '<div class="gallery-caption">' + label + '</div>'
        );
      }}

      function buildGalleryItemElement(capture) {{
        const item = document.createElement('div');
        item.className = 'gallery-item';
        item.dataset.kind = capture.kind || (String(capture.path || '').startsWith('data:image/') ? 'uploaded' : 'existing');
        item.dataset.label = capture.label || '手动上传';
        item.innerHTML = createGalleryItemMarkup(capture);
        return item;
      }}

      function collectCardState(card) {{
        const itemId = card.dataset.itemId || card.dataset.brand || 'item';
        const brandNode = card.querySelector('.brand-name');
        const fields = {{}};
        card.querySelectorAll('.detail-value[data-field]').forEach((node) => {{
          fields[node.dataset.field] = ((node.textContent || '').trim() || '{EMPTY_TEXT}');
        }});
        const captures = [];
        const shell = card.querySelector('.gallery-shell');
        if (shell && shell._helpers) {{
          shell._helpers.activeItems().slice(0, 6).forEach((item) => {{
            const img = item.querySelector('.gallery-image');
            const caption = item.querySelector('.gallery-caption');
            if (!img) return;
            const path = img.dataset.fullSrc || img.getAttribute('src') || '';
            if (!path) return;
            captures.push({{
              label: ((caption && caption.textContent) || item.dataset.label || '截图').trim() || '截图',
              path,
              kind: item.dataset.kind || (path.startsWith('data:image/') ? 'uploaded' : 'existing'),
            }});
          }});
        }}
        return {{
          id: itemId,
          name: brandNode ? ((brandNode.textContent || '').trim() || '未命名') : '未命名',
          fields,
          captures,
        }};
      }}

      function collectReportState() {{
        const items = {{}};
        document.querySelectorAll('.card').forEach((card) => {{
          const snapshot = collectCardState(card);
          items[snapshot.id] = {{
            name: snapshot.name,
            fields: snapshot.fields,
            captures: snapshot.captures,
          }};
        }});
        return {{
          version: {STATE_VERSION},
          items,
          analysis: currentAnalysisData,
        }};
      }}

      function escapeHtml(value) {{
        return String(value || '')
          .replace(/&/g, '&amp;')
          .replace(/</g, '&lt;')
          .replace(/>/g, '&gt;')
          .replace(/"/g, '&quot;')
          .replace(/'/g, '&#39;');
      }}

      function updateActiveNav(targetId) {{
        sideNavLinks.forEach((link) => {{
          link.classList.toggle('is-active', link.dataset.navTarget === targetId);
        }});
      }}

      function getNavSections() {{
        return Array.from(document.querySelectorAll('[data-nav-section][id]'))
          .filter((node) => node.id && node.dataset.navLabel)
          .map((node) => ({{
            id: node.id,
            label: node.dataset.navLabel,
            group: node.dataset.navGroup || '其他',
          }}));
      }}

      function renderSideNav() {{
        if (!sideNavGroups) return;
        const sections = getNavSections();
        const groupOrder = ['总览', '竞品', '分析'];
        const grouped = new Map();
        sections.forEach((section) => {{
          if (!grouped.has(section.group)) {{
            grouped.set(section.group, []);
          }}
          grouped.get(section.group).push(section);
        }});
        const groups = [];
        groupOrder.concat(Array.from(grouped.keys()).filter((key) => !groupOrder.includes(key))).forEach((groupName) => {{
          const items = grouped.get(groupName);
          if (!items || !items.length) return;
          const isCollapsible = groupName === '竞品';
          const links = items.map((item) => {{
            return '<a class="side-nav-link' + (groupName === '竞品' ? ' side-nav-link--product' : '') + '" href="#' + escapeHtml(item.id) + '" data-nav-target="' + escapeHtml(item.id) + '"><span class="side-nav-dot"></span><span class="side-nav-text">' + escapeHtml(item.label) + '</span></a>';
          }}).join('');
          const header = isCollapsible
            ? '<button type="button" class="side-nav-group-toggle" data-nav-group-toggle><span class="side-nav-group-toggle-text">' + escapeHtml(groupName) + '</span><span class="side-nav-chevron"></span></button>'
            : '<div class="side-nav-group-label">' + escapeHtml(groupName) + '</div>';
          groups.push('<section class="side-nav-group' + (isCollapsible ? '' : ' side-nav-group--static') + '" data-nav-group-name="' + escapeHtml(groupName) + '">' + header + '<div class="side-nav-group-body">' + links + '</div></section>');
        }});
        sideNavGroups.innerHTML = groups.join('');
        sideNavLinks = Array.from(document.querySelectorAll('.side-nav-link[data-nav-target]'));
        bindSideNavInteractions();
      }}

      function bindSideNavInteractions() {{
        document.querySelectorAll('[data-nav-group-toggle]').forEach((button) => {{
          button.onclick = () => {{
            const group = button.closest('.side-nav-group');
            if (!group) return;
            group.classList.toggle('is-collapsed');
          }};
        }});
        sideNavLinks.forEach((link) => {{
          link.onclick = (event) => {{
            const targetId = link.dataset.navTarget;
            const target = targetId ? document.getElementById(targetId) : null;
            if (!target) return;
            event.preventDefault();
            updateActiveNav(targetId);
            target.scrollIntoView({{ behavior: 'smooth', block: 'start' }});
          }};
        }});
      }}

      function containsAny(text, keywords) {{
        const source = String(text || '').toLowerCase();
        return keywords.some((keyword) => source.includes(String(keyword).toLowerCase()));
      }}

      function countMatches(text, keywords) {{
        const source = String(text || '').toLowerCase();
        return keywords.filter((keyword) => source.includes(String(keyword).toLowerCase())).length;
      }}

      function hasHardwareSignal(text) {{
        const source = String(text || '').toLowerCase();
        const explicitTerms = ['camera', 'tracker', 'collar', 'feeder', '摄像头', '追踪器', '项圈', '投喂', '喂食器'];
        if (explicitTerms.some((term) => source.includes(term))) return true;
        if (source.includes('设备') && !source.includes('不依赖设备')) return true;
        if (source.includes('硬件') && !source.includes('不依赖硬件') && !source.includes('不依赖专属硬件')) return true;
        return false;
      }}

      function buildSnapshotText(snapshot) {{
        return [
          snapshot.name,
          snapshot.fields['App 完整功能'],
          snapshot.fields['App 亮点功能'],
          snapshot.fields['商业模式'],
          snapshot.fields['硬件依赖度'],
          snapshot.fields['Android 评分和评论数'],
          snapshot.fields['iOS 评分和评论数'],
          snapshot.fields['Android 下载量'],
        ].join(' | ').toLowerCase();
      }}

      function deriveProductStructure(text) {{
        if (hasHardwareSignal(text)) return '硬件+服务';
        if (containsAny(text, ['autoship', 'pharmacy', 'food', '用品', '药房', '购物', '商品', 'shop', 'store'])) return '多SKU电商';
        if (containsAny(text, ['订阅', 'subscription', 'member', '会员', 'box', 'premium', '持续护理'])) return '订阅产品';
        if (containsAny(text, ['single product', 'hero product', '单品', '爆款']) && !containsAny(text, ['商品', '购物', '用品'])) return '单品爆款';
        return '纯软件';
      }}

      function deriveBusinessModel(text, structure) {{
        if (structure === '硬件+服务') return '硬件+订阅';
        if (structure === '订阅产品' || containsAny(text, ['subscription', '订阅', '会员', 'premium', 'autoship', '持续护理'])) return '订阅';
        if (containsAny(text, ['预约', '寄养', '遛狗', '看护', '训练', '问诊', '兽医', '咨询', '支付抽成', '佣金'])) return '服务收费';
        return '一次性电商';
      }}

      function deriveTrafficScore(text, structure, businessModel) {{
        if (containsAny(text, ['blog', 'guide', 'community', 'learn', 'academy', 'tips', 'content', 'social', 'youtube', 'instagram', 'tiktok', '攻略', '知识', '内容'])) return 5;
        if (['多SKU电商', '单品爆款', '硬件+服务', '订阅产品'].includes(structure)) return 3;
        if (businessModel === '服务收费') return 2;
        return 1;
      }}

      function deriveConversionScore(text, structure, businessModel) {{
        const strongSignals = countMatches(text, ['订阅', '会员', 'premium', 'autoship', 'bundle', '套装', '组合', '评分', '评论', 'guarantee', '发货', '支付', '下单']);
        if (strongSignals >= 3) return 5;
        if (['多SKU电商', '订阅产品', '硬件+服务'].includes(structure) || ['订阅', '硬件+订阅'].includes(businessModel)) return 3;
        if (businessModel === '服务收费') return 2;
        return 1;
      }}

      function deriveRepeatScore(text, structure, businessModel) {{
        if (['订阅', '硬件+订阅'].includes(businessModel) || ['订阅产品', '硬件+服务'].includes(structure)) return 5;
        if (containsAny(text, ['autoship', '持续护理', '补货', '药房', '处方', 'follow-up', '复购', '再次预约'])) return 4;
        if (['服务收费', '一次性电商'].includes(businessModel) && containsAny(text, ['订单', '训练', '日托', '提醒', '复诊'])) return 3;
        return 1;
      }}

      function deriveCapabilityValues(text) {{
        return {{
          '服务预约': countMatches(text, ['预约', '寄养', '遛狗', '日托', '看护', '训练', 'boarding', 'walking', 'drop-in']) >= 2 ? '强' : (containsAny(text, ['预约', '寄养', '遛狗', '看护', '训练']) ? '中' : '无'),
          '在线问诊': countMatches(text, ['问诊', '兽医', '视频问诊', '处方', 'vet']) >= 2 ? '强' : (containsAny(text, ['问诊', '兽医', '视频', '健康建议']) ? '中' : '无'),
          '电商交易': countMatches(text, ['购物', '商品', '药房', 'autoship', '订单', '发货']) >= 2 ? '强' : (containsAny(text, ['购物', '商品', '药房', '订单']) ? '中' : '无'),
          '订阅体系': countMatches(text, ['订阅', '会员', 'premium', 'autoship', '持续护理']) >= 2 ? '强' : (containsAny(text, ['订阅', '会员', 'premium']) ? '中' : '无'),
          '硬件连接': (hasHardwareSignal(text) && countMatches(text, ['摄像头', '追踪器', '设备', '项圈', '投喂', '喂食器']) >= 2) ? '强' : (hasHardwareSignal(text) ? '中' : '无'),
          '健康追踪': countMatches(text, ['健康', '档案', '病历', '生命体征', '活动', '提醒']) >= 2 ? '强' : (containsAny(text, ['健康', '档案', '提醒', '活动']) ? '中' : '无'),
        }};
      }}

      function buildCompanyProfilesFromPage() {{
        const profiles = [];
        document.querySelectorAll('.card').forEach((card) => {{
          const snapshot = collectCardState(card);
          const text = buildSnapshotText(snapshot);
          const structure = deriveProductStructure(text);
          const businessModel = deriveBusinessModel(text, structure);
          profiles.push({{
            id: snapshot.id,
            label: snapshot.name,
            text,
            traffic_score: deriveTrafficScore(text, structure, businessModel),
            conversion_score: deriveConversionScore(text, structure, businessModel),
            repeat_score: deriveRepeatScore(text, structure, businessModel),
            product_structure: structure,
            business_model: businessModel,
            capabilities: deriveCapabilityValues(text),
          }});
        }});
        return profiles;
      }}

      function buildMarketGroups(profiles) {{
        const structures = ['单品爆款', '多SKU电商', '订阅产品', '硬件+服务', '纯软件'];
        return structures
          .map((structure) => {{
            const members = profiles.filter((profile) => profile.product_structure === structure);
            if (!members.length) return null;
            const businessMix = Array.from(new Set(members.map((member) => member.business_model)));
            return {{
              title: structure,
              description: members.length + ' 个样本落在这一结构，当前主要对应 ' + businessMix.join('、') + ' 这类收入方式。',
              items: members.map((member) => ({{ id: member.id, label: member.label }})),
            }};
          }})
          .filter(Boolean);
      }}

      function buildMarketInsights(profiles) {{
        if (!profiles.length) return {{ summary: '', insights: [] }};
        const structures = Array.from(new Set(profiles.map((profile) => profile.product_structure))).sort();
        const businessCounts = {{}};
        profiles.forEach((profile) => {{
          businessCounts[profile.business_model] = (businessCounts[profile.business_model] || 0) + 1;
        }});
        const businessSummary = Object.entries(businessCounts)
          .sort((a, b) => b[1] - a[1])
          .map(([name, count]) => name + count + '家')
          .join('、');
        const allRounder = profiles.filter((profile) => profile.traffic_score >= 4 && profile.conversion_score >= 4 && profile.repeat_score >= 4);
        const contentDriven = profiles.filter((profile) => profile.traffic_score >= 5).map((profile) => profile.label);
        const brandDriven = profiles.filter((profile) => profile.traffic_score <= 3).map((profile) => profile.label);
        const pureSoftware = profiles.filter((profile) => profile.product_structure === '纯软件');
        const pureSoftwareAvg = pureSoftware.length
          ? pureSoftware.reduce((sum, profile) => sum + profile.conversion_score, 0) / pureSoftware.length
          : 0;

        const summaryParts = [];
        if (businessSummary) summaryParts.push('样本当前主要靠' + businessSummary + '赚钱');
        if (structures.length > 1) summaryParts.push('同时存在' + structures.join('、') + '，属于多模型竞争');
        if (!allRounder.length) summaryParts.push('没有产品同时把流量、转化和复购做成闭环，所以市场能力仍然割裂');

        const insights = [];
        if (structures.length > 1) {{
          insights.push('市场结构：样本同时出现' + structures.join('、') + '几种产品结构，所以这不是单一路径吃透市场，而是多模型竞争。');
        }} else {{
          insights.push('市场结构：当前样本几乎都落在' + structures[0] + '这一种产品结构里，所以新进入者更容易被拖进同一种竞争方式。');
        }}
        if (!allRounder.length) {{
          insights.push('市场能力：没有任何一个样本同时具备强流量、强转化和强复购，因为流量入口、成交能力和复购机制分散在不同玩家手里，所以市场仍处于能力割裂状态。');
        }}
        if (brandDriven.length >= Math.max(1, Math.floor(profiles.length / 2) + 1)) {{
          insights.push('流量结构：大多数样本更依赖品牌站、商店页和现成渠道获客，例如' + brandDriven.slice(0, 4).join('、') + '，所以当前缺少内容型或工具型高频流量入口。');
        }} else if (contentDriven.length) {{
          insights.push('流量结构：只有' + contentDriven.join('、') + '具备明显内容/社区型流量特征，其余样本仍偏品牌流量，所以内容入口还没有形成规模壁垒。');
        }}
        if (pureSoftware.length && pureSoftwareAvg <= 2.5) {{
          insights.push('转化结构：纯软件样本如' + pureSoftware.slice(0, 4).map((profile) => profile.label).join('、') + '平均转化能力只有 ' + pureSoftwareAvg.toFixed(1) + '/5，因为它们缺少硬件、商品或订阅抓手，所以软件本身难以直接变现。');
        }} else {{
          const strongConverters = profiles.filter((profile) => profile.conversion_score >= 4).map((profile) => profile.label);
          if (strongConverters.length) {{
            insights.push('转化结构：高转化能力主要集中在' + strongConverters.join('、') + '，因为这些产品同时拥有评价、订阅或商品成交设计，所以转化优势更多来自商业机制而不是单一功能。');
          }}
        }}
        return {{ summary: summaryParts.join('；') + '。', insights: insights.slice(0, 4) }};
      }}

      function buildOpportunitySummary(profiles) {{
        const result = [];
        const contentProfiles = profiles.filter((profile) => profile.traffic_score >= 5).map((profile) => profile.label);
        const brandProfiles = profiles.filter((profile) => profile.traffic_score <= 3).map((profile) => profile.label);
        const hardwareProfiles = profiles.filter((profile) => profile.product_structure === '硬件+服务').map((profile) => profile.label);
        const serviceProfiles = profiles.filter((profile) => profile.business_model === '服务收费').map((profile) => profile.label);
        const softwareLowConversion = profiles.filter((profile) => profile.product_structure === '纯软件' && profile.conversion_score <= 2).map((profile) => profile.label);
        const softwareProfiles = profiles.filter((profile) => profile.product_structure === '纯软件').map((profile) => profile.label);
        const commerceProfiles = profiles.filter((profile) => ['一次性电商', '订阅', '硬件+订阅'].includes(profile.business_model)).map((profile) => profile.label);
        if (!contentProfiles.length && brandProfiles.length) result.push('当前状态：' + brandProfiles.length + ' 个样本主要靠品牌站、商店页或既有渠道获客。缺口：市场里几乎没有内容型或工具型高频入口。机会方向：先做软件/工具流量入口，把档案、提醒、记录这类高频动作变成持续获客位。');
        if (hardwareProfiles.length && serviceProfiles.length) result.push('当前状态：硬件能力主要在' + hardwareProfiles.join('、') + '，服务收费能力主要在' + serviceProfiles.slice(0, 4).join('、') + '。缺口：数据、消费和服务没有被同一个产品打成闭环。机会方向：把设备数据、健康事件或提醒直接接到消费推荐和服务预约里，做数据驱动转化。');
        if (softwareLowConversion.length) result.push('当前状态：纯软件样本如' + softwareLowConversion.slice(0, 4).join('、') + '转化能力偏弱。缺口：软件侧缺少明确收入路径。机会方向：把软件入口和电商、订阅或会员服务绑在一起，让软件先拿流量，再承接成交。');
        if (result.length < 3 && softwareProfiles.length && commerceProfiles.length) result.push('当前状态：软件入口更多在' + softwareProfiles.slice(0, 4).join('、') + '，成交能力更多在' + commerceProfiles.slice(0, 4).join('、') + '。缺口：流量和变现不在同一个产品里。机会方向：优先做“记录/提醒/档案 + 商品或订阅推荐”的中间层产品。');
        return result.slice(0, 4);
      }}

      function buildFeaturePriorities(profiles) {{
        const featureSpecs = [
          {{ name: '宠物档案管理', keywords: ['档案', 'profile', 'pet profile', '记录', '病历'], userValue: 5, businessValue: 3, techFeasibility: 5 }},
          {{ name: '健康记录与提醒', keywords: ['提醒', '用药', '症状', '健康', '病历', '生命体征', '活动', '追踪'], userValue: 5, businessValue: 4, techFeasibility: 5 }},
          {{ name: '服务预约', keywords: ['预约', '寄养', '遛狗', '日托', '看护', 'drop-in', 'boarding', 'walking'], userValue: 4, businessValue: 4, techFeasibility: 2 }},
          {{ name: '在线问诊', keywords: ['问诊', '兽医', '视频问诊', '处方', 'vet', 'telehealth'], userValue: 4, businessValue: 4, techFeasibility: 2 }},
          {{ name: '电商交易', keywords: ['购物', '商品', '药房', '订单', '发货', 'shop', 'pharmacy', 'autoship'], userValue: 4, businessValue: 5, techFeasibility: 4 }},
          {{ name: '订阅体系', keywords: ['订阅', '会员', 'premium', '续费', 'autoship', '持续护理'], userValue: 4, businessValue: 5, techFeasibility: 4 }},
          {{ name: '设备连接', keywords: ['设备', '摄像头', '追踪器', '项圈', '投喂', 'tracker', 'camera', 'feeder'], userValue: 3, businessValue: 4, techFeasibility: 2 }},
          {{ name: '定位追踪', keywords: ['gps', '定位', '围栏', '轨迹', '位置历史'], userValue: 4, businessValue: 4, techFeasibility: 2 }},
          {{ name: '远程看宠', keywords: ['双向语音', '实时查看', '回看', '摄像头', '视频', '激光', '投喂'], userValue: 3, businessValue: 3, techFeasibility: 2 }},
        ];
        const sampleCount = profiles.length || 1;
        const rows = [];
        featureSpecs.forEach((spec) => {{
          const matched = profiles.filter((profile) => containsAny(profile.text, spec.keywords)).map((profile) => profile.label);
          if (!matched.length) return;
          let competition = 1;
          if (matched.length >= Math.max(1, Math.ceil(sampleCount / 2))) {{
            competition = 5;
          }} else if (matched.length >= 3) {{
            competition = 3;
          }}
          const opportunityScore = Number((spec.userValue * spec.businessValue * spec.techFeasibility / Math.max(competition, 1)).toFixed(1));
          const recommendation = opportunityScore >= 20 ? '推荐' : (opportunityScore >= 10 ? '中' : '不建议');
          rows.push({{
            id: spec.name,
            label: spec.name,
            values: {{
              '覆盖竞品': matched.length + '/' + sampleCount + '：' + matched.slice(0, 4).join('、'),
              '用户价值': String(spec.userValue),
              '商业价值': String(spec.businessValue),
              '技术可行性': String(spec.techFeasibility),
              '竞争强度': String(competition),
              '机会分': opportunityScore.toFixed(1),
              '判断': recommendation,
            }},
          }});
        }});
        rows.sort((a, b) => Number(b.values['机会分']) - Number(a.values['机会分']));
        return rows;
      }}

      function buildStrategySummary(profiles, featureRows) {{
        const topFeatures = featureRows.filter((row) => row.values['判断'] === '推荐').slice(0, 3).map((row) => row.label);
        const hardwareHeavy = profiles.filter((profile) => profile.product_structure === '硬件+服务');
        const serviceHeavy = profiles.filter((profile) => profile.business_model === '服务收费');
        const softwareWeak = profiles.filter((profile) => profile.product_structure === '纯软件' && profile.conversion_score <= 2);
        const result = [];
        if (serviceHeavy.length) result.push('不建议做什么：不要直接从重履约服务撮合切入，因为样本里服务收费玩家已经先占住供给网络和履约心智，新玩家很容易被拖进重运营。');
        if (hardwareHeavy.length && softwareWeak.length) {{
          result.push('推荐切入点：先做软件型高频入口，再把入口接到订阅、电商或设备数据，而不是一开始就自己做硬件或重服务。');
        }} else {{
          result.push('推荐切入点：优先从高频记录、提醒、档案这类轻功能切入，用高频使用先拿流量，再承接商业动作。');
        }}
        if (topFeatures.length) {{
          result.push('发展路径：第一阶段先把' + topFeatures.join('、') + '做成稳定高频入口，第二阶段接入订阅或电商转化，第三阶段再把服务或设备数据接成闭环。');
        }} else {{
          result.push('发展路径：先用轻量功能验证流量入口，再补订阅或成交链路，最后再扩展到更重的服务与硬件协同。');
        }}
        const midFeatures = featureRows.filter((row) => row.values['判断'] === '中').slice(0, 4).map((row) => row.label);
        const lowFeatures = featureRows.filter((row) => row.values['判断'] === '不建议').slice(0, 4).map((row) => row.label);
        const priorityParts = [];
        if (topFeatures.length) priorityParts.push('高机会：' + topFeatures.join('、'));
        if (midFeatures.length) priorityParts.push('中机会：' + midFeatures.join('、'));
        if (lowFeatures.length) priorityParts.push('低机会：' + lowFeatures.join('、'));
        if (priorityParts.length) result.push('功能优先级：' + priorityParts.join('；') + '。');
        return result.slice(0, 4);
      }}

      function deriveAnalysisFromPage() {{
        const profiles = buildCompanyProfilesFromPage();
        const market = buildMarketInsights(profiles);
        const featureRows = buildFeaturePriorities(profiles);
        return {{
          version: '2',
          engine: '{ANALYSIS_ENGINE}',
          summary: market.summary,
          groups: buildMarketGroups(profiles),
          feature_matrix: {{
            row_label: '功能',
            columns: ['覆盖竞品', '用户价值', '商业价值', '技术可行性', '竞争强度', '机会分', '判断'],
            rows: featureRows,
          }},
          insights: market.insights,
          opportunities: buildOpportunitySummary(profiles),
          strategy: buildStrategySummary(profiles, featureRows),
        }};
      }}

      function renderAnalysisHtml(data) {{
        if (!data) return '';
        const emphasizeKeywords = (text) => {{
          let html = escapeHtml(String(text || ''));
          const keywords = {json.dumps(ANALYSIS_HIGHLIGHT_KEYWORDS, ensure_ascii=False)};
          keywords
            .slice()
            .sort((a, b) => b.length - a.length)
            .forEach((keyword) => {{
              html = html.split(keyword).join('<span class="analysis-emphasis">' + keyword + '</span>');
            }});
          return html;
        }};
        const splitInsightText = (text) => {{
          const markers = ['，说明', '，而', '，这说明', '，但'];
          for (const marker of markers) {{
            if (String(text || '').includes(marker)) {{
              const parts = String(text).split(marker);
              return {{
                headline: parts.shift() || '',
                detail: marker.replace('，', '') + parts.join(marker),
              }};
            }}
          }}
          return {{ headline: String(text || ''), detail: '' }};
        }};
        const parseOpportunityText = (text) => {{
          const source = String(text || '');
          if (source.includes('当前状态：') && source.includes('缺口：') && source.includes('机会方向：')) {{
            const afterCurrent = source.split('当前状态：')[1];
            const [current, afterGap] = afterCurrent.split('缺口：');
            const [gap, opportunity] = afterGap.split('机会方向：');
            return {{ current: current.trim(), gap: gap.trim(), opportunity: opportunity.trim() }};
          }}
          return {{ current: source, gap: '', opportunity: '' }};
        }};
        const stripPrefix = (text, prefix) => String(text || '').startsWith(prefix) ? String(text).slice(prefix.length).trim() : '';
        const coreSummary = data.summary || ((data.insights && data.insights[0]) || '当前竞品呈现多中心竞争结构，各能力模块由不同类型玩家分别占据。');
        const groupHtml = (data.groups || []).map((group) => {{
          const chips = (group.items || []).map((item) => '<span class="analysis-chip">' + escapeHtml(item.label) + '</span>').join('');
          const note = group.description ? '<p class="analysis-note">' + emphasizeKeywords(group.description) + '</p>' : '';
          return '<article class="analysis-card"><h3>' + escapeHtml(group.title) + '</h3>' + note + '<div class="analysis-chip-row">' + chips + '</div></article>';
        }}).join('');

        const feature = data.feature_matrix || {{ columns: [], rows: [] }};
        const rowLabel = feature.row_label || '竞品';
        const featureHeader = (feature.columns || []).map((col) => '<th>' + escapeHtml(col) + '</th>').join('');
        const featureRows = (feature.rows || []).map((row) => {{
          const tds = (feature.columns || []).map((col) => '<td>' + emphasizeKeywords((row.values || {{}})[col] || '{EMPTY_TEXT}') + '</td>').join('');
          return '<tr><th>' + escapeHtml(row.label) + '</th>' + tds + '</tr>';
        }}).join('');
        const featureHtml = feature.rows && feature.rows.length
          ? '<section class="analysis-block"><h3 class="analysis-block-title">功能优先级建议</h3><div class="analysis-table-wrap"><table class="analysis-table"><thead><tr><th>' + escapeHtml(rowLabel) + '</th>' + featureHeader + '</tr></thead><tbody>' + featureRows + '</tbody></table></div></section>'
          : '';

        const insightItems = (data.insights || []).map((item) => {{
          const parsed = splitInsightText(item);
          return '<li class="insight-item"><span class="insight-dot"></span><div class="insight-copy"><div class="insight-headline">' + emphasizeKeywords(parsed.headline) + '</div>' + (parsed.detail ? '<div class="insight-detail">' + emphasizeKeywords(parsed.detail) + '</div>' : '') + '</div></li>';
        }}).join('');
        const insightHtml = insightItems
          ? '<section class="analysis-block"><h3 class="analysis-block-title">市场/商业分析</h3><ul class="analysis-insight-list">' + insightItems + '</ul></section>'
          : '';

        const opportunityItems = (data.opportunities || []).map((item) => {{
          const parsed = parseOpportunityText(item);
          const title = parsed.current ? (parsed.current.length > 20 ? parsed.current.slice(0, 20) + '...' : parsed.current) : '机会点';
          return '<article class="opportunity-card"><h4>' + emphasizeKeywords(title) + '</h4><div class="opportunity-row"><span>当前</span><p>' + emphasizeKeywords(parsed.current) + '</p></div><div class="opportunity-row"><span>缺口</span><p>' + emphasizeKeywords(parsed.gap) + '</p></div><div class="opportunity-row"><span>机会</span><p>' + emphasizeKeywords(parsed.opportunity) + '</p></div></article>';
        }}).join('');
        const opportunityHtml = opportunityItems
          ? '<section class="analysis-block"><h3 class="analysis-block-title">核心机会</h3><div class="opportunity-grid">' + opportunityItems + '</div></section>'
          : '';

        const avoidItems = (data.strategy || []).map((item) => stripPrefix(item, '不建议做什么：')).filter(Boolean).map((item) => '<li>' + emphasizeKeywords(item) + '</li>').join('');
        const entryItems = (data.strategy || []).map((item) => stripPrefix(item, '推荐切入点：')).filter(Boolean).map((item) => '<li>' + emphasizeKeywords(item) + '</li>').join('');
        const pathItems = (data.strategy || []).map((item) => stripPrefix(item, '发展路径：')).filter(Boolean).map((item) => '<li>' + emphasizeKeywords(item) + '</li>').join('');
        const priorityItems = (data.strategy || []).map((item) => stripPrefix(item, '功能优先级：')).filter(Boolean).map((item) => '<li>' + emphasizeKeywords(item) + '</li>').join('');
        const strategyBlocks = [
          avoidItems ? '<div class="strategy-group strategy-group--warn"><div class="strategy-label">不建议做</div><ul class="analysis-summary">' + avoidItems + '</ul></div>' : '',
          entryItems ? '<div class="strategy-group strategy-group--focus"><div class="strategy-label">推荐切入点</div><ul class="analysis-summary">' + entryItems + '</ul></div>' : '',
          pathItems ? '<div class="strategy-group strategy-group--path"><div class="strategy-label">发展路径</div><ul class="analysis-summary">' + pathItems + '</ul></div>' : '',
          priorityItems ? '<div class="strategy-group strategy-group--focus"><div class="strategy-label">功能优先级</div><ul class="analysis-summary">' + priorityItems + '</ul></div>' : '',
        ].join('');
        const strategyHtml = strategyBlocks
          ? '<section class="analysis-block"><h3 class="analysis-block-title">策略建议</h3><div class="strategy-grid">' + strategyBlocks + '</div></section>'
          : '';

        const groupsBlock = groupHtml
          ? '<section class="analysis-block"><h3 class="analysis-block-title">市场结构</h3><div class="analysis-card-grid">' + groupHtml + '</div></section>'
          : '';

        return '<section class="analysis-core"><div class="analysis-core-label">核心结论</div><div class="analysis-core-text">' + emphasizeKeywords(coreSummary) + '</div></section>' + groupsBlock + featureHtml + insightHtml + opportunityHtml + strategyHtml;
      }}

      function renderAnalysis(data) {{
        if (!analysisContent) return;
        currentAnalysisData = data || null;
        analysisContent.innerHTML = renderAnalysisHtml(currentAnalysisData);
        renderSideNav();
        initializeSectionObserver();
      }}

      function initializeSectionObserver() {{
        if (sectionObserver) {{
          sectionObserver.disconnect();
        }}
        const sections = Array.from(document.querySelectorAll('[data-nav-section][id]'));
        if (!sections.length) return;
        sectionObserver = new IntersectionObserver((entries) => {{
          const visible = entries
            .filter((entry) => entry.isIntersecting)
            .sort((a, b) => b.intersectionRatio - a.intersectionRatio);
          if (visible.length) {{
            updateActiveNav(visible[0].target.id);
          }}
        }}, {{
          rootMargin: '-10% 0px -55% 0px',
          threshold: [0.15, 0.3, 0.55],
        }});
        sections.forEach((section) => sectionObserver.observe(section));
      }}

      function applyCardState(card, itemState) {{
        if (!card || !itemState || typeof itemState !== 'object') return;
        const brandNode = card.querySelector('.brand-name');
        if (brandNode && itemState.name) {{
          brandNode.textContent = itemState.name;
          normalizeEditable(brandNode);
        }}
        if (itemState.fields && typeof itemState.fields === 'object') {{
          card.querySelectorAll('.detail-value[data-field]').forEach((node) => {{
            const field = node.dataset.field;
            if (Object.prototype.hasOwnProperty.call(itemState.fields, field)) {{
              node.textContent = itemState.fields[field];
              normalizeEditable(node);
            }}
          }});
        }}
        const shell = card.querySelector('.gallery-shell');
        if (shell && shell._helpers && Array.isArray(itemState.captures)) {{
          shell._helpers.setCaptures(itemState.captures);
        }}
      }}

      function applyReportState(payload) {{
        if (!payload || typeof payload !== 'object' || !payload.items || typeof payload.items !== 'object') return;
        document.querySelectorAll('.card').forEach((card) => {{
          const itemId = card.dataset.itemId || card.dataset.brand;
          if (!itemId) return;
          const itemState = payload.items[itemId];
          if (itemState) {{
            applyCardState(card, itemState);
          }}
        }});
        renderAnalysis(deriveAnalysisFromPage());
      }}

      if (sideNavToggle) {{
        sideNavToggle.addEventListener('click', () => {{
          const collapsed = document.body.classList.toggle('side-nav-collapsed');
          sideNavToggle.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
        }});
      }}

      lightboxClose.addEventListener('click', closeLightbox);
      lightbox.addEventListener('click', (event) => {{
        if (event.target === lightbox) {{
          closeLightbox();
        }}
      }});
      document.addEventListener('keydown', (event) => {{
        if (event.key === 'Escape' && lightbox.classList.contains('is-open')) {{
          closeLightbox();
        }}
      }});

      if (exportBtn) {{
        exportBtn.addEventListener('click', exportCsv);
      }}
      if (exportStateBtn) {{
        exportStateBtn.addEventListener('click', () => {{
          const payload = JSON.stringify(collectReportState(), null, 2);
          triggerDownload(defaultStateFilename, payload, 'application/json;charset=utf-8;');
        }});
      }}
      if (resetStateBtn) {{
        resetStateBtn.addEventListener('click', () => applyReportState(initialReportState));
      }}
      if (importStateInput) {{
        importStateInput.addEventListener('change', async (event) => {{
          const file = event.target.files && event.target.files[0];
          if (!file) return;
          try {{
            const text = await file.text();
            const payload = JSON.parse(text);
            applyReportState(payload);
          }} catch (error) {{
            console.error('导入状态失败', error);
          }} finally {{
            event.target.value = '';
          }}
        }});
      }}
      if (regenerateAnalysisBtn) {{
        regenerateAnalysisBtn.addEventListener('click', () => {{
          renderAnalysis(deriveAnalysisFromPage());
        }});
      }}

      document.querySelectorAll('.editable-field').forEach((field) => {{
        normalizeEditable(field);
        field.addEventListener('focus', () => {{
          if (field.dataset.empty === 'true') {{
            field.textContent = '';
          }}
        }});
        field.addEventListener('blur', () => normalizeEditable(field));
        field.addEventListener('keydown', (event) => {{
          if (event.key === 'Enter' && !event.shiftKey) {{
            event.preventDefault();
            field.blur();
          }}
        }});
        field.addEventListener('blur', () => {{
          const card = field.closest('.card');
          syncMediaHeight(card);
        }});
      }});

      document.querySelectorAll('.gallery-shell').forEach((shell) => {{
        const maxImages = Number(shell.dataset.maxImages || 6);
        const grid = shell.querySelector('.gallery-grid');
        const uploadInput = shell.querySelector('.upload-input');
        const hint = shell.querySelector('.gallery-hint');

        function updateGridClass() {{
          const current = activeItems().length;
          grid.classList.remove('count-0', 'count-1', 'count-2', 'count-3', 'count-4', 'count-5', 'count-6');
          grid.classList.add('count-' + Math.min(current, 6));
        }}

        function activeItems() {{
          return Array.from(grid.querySelectorAll('.gallery-item'));
        }}

        function refreshHint() {{
          const current = activeItems().length;
          updateGridClass();
          hint.textContent = '当前展示 ' + current + ' 张图片，最多可保留 ' + maxImages + ' 张。';
          syncMediaHeight(shell.closest('.card'));
        }}

        function bindItem(item) {{
          const img = item.querySelector('.gallery-image');
          const del = item.querySelector('.delete-btn');
          if (img) {{
            img.addEventListener('click', () => openLightbox(img.dataset.fullSrc || img.src, img.alt));
          }}
          if (del) {{
            del.addEventListener('click', () => {{
              item.remove();
              if (!activeItems().length) {{
                grid.innerHTML = '<div class="empty-state"><div>{EMPTY_IMAGE_TEXT}</div><span>你可以上传最多 6 张图片。</span></div>';
              }}
              refreshHint();
            }});
          }}
        }}

        function setCaptures(captures) {{
          grid.innerHTML = '';
          const validCaptures = Array.isArray(captures) ? captures.slice(0, maxImages) : [];
          validCaptures.forEach((capture) => {{
            if (!capture || !capture.path) return;
            const item = buildGalleryItemElement(capture);
            grid.appendChild(item);
            bindItem(item);
          }});
          if (!activeItems().length) {{
            grid.innerHTML = '<div class="empty-state"><div>{EMPTY_IMAGE_TEXT}</div><span>你可以上传最多 6 张图片。</span></div>';
          }}
          refreshHint();
        }}

        shell._helpers = {{
          activeItems,
          refreshHint,
          bindItem,
          setCaptures,
        }};

        activeItems().forEach(bindItem);
        refreshHint();

        uploadInput.addEventListener('change', async (event) => {{
          const files = Array.from(event.target.files || []);
          if (!files.length) return;

          const existingEmpty = grid.querySelector('.empty-state');
          if (existingEmpty) existingEmpty.remove();

          let current = activeItems().length;
          for (const file of files) {{
            if (current >= maxImages) break;
            const validType = ['image/png', 'image/jpeg', 'image/webp'].includes(file.type) || /\\.(png|jpe?g|webp)$/i.test(file.name);
            if (!validType) continue;
            const url = await fileToDataUrl(file);
            const item = buildGalleryItemElement({{
              label: '手动上传',
              path: url,
              kind: 'uploaded',
            }});
            grid.appendChild(item);
            bindItem(item);
            current += 1;
          }}
          refreshHint();
          event.target.value = '';
        }});
      }});

      window.addEventListener('load', syncAllMediaHeights);
      window.addEventListener('resize', syncAllMediaHeights);
      requestAnimationFrame(syncAllMediaHeights);
      renderSideNav();
      if (analysisContent) {{
        renderAnalysis(deriveAnalysisFromPage());
      }}
      initializeSectionObserver();
      updateActiveNav('page-top');
    }})();
  </script>
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
    parser.add_argument("--state", help="可选的状态 JSON 文件路径。")
    parser.add_argument("--analysis", help="可选的分析 JSON 文件路径。")
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve()
    output_dir = Path(args.output_dir).resolve()
    image_dir = output_dir / "images"
    ensure_dir(output_dir)
    ensure_dir(image_dir)

    manifest = load_manifest(manifest_path)
    state_path = resolve_state_path(manifest_path, args.state)
    state_data: dict[str, Any] | None = None
    if state_path.exists():
        state_data = load_state(state_path)
    analysis_path: Path | None = None
    analysis_data: dict[str, Any] | None = None
    if args.analysis:
        analysis_path = Path(args.analysis).resolve()
        if analysis_path.exists():
            analysis_data = load_analysis(analysis_path)
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

    captured_items = apply_state_to_items(captured_items, state_data)

    normalized_path = output_dir / "manifest.normalized.json"
    normalized_path.write_text(
        json.dumps(
            {
                "title": clean_text(manifest.get("title"), DEFAULT_TITLE),
                "subtitle": clean_text(manifest.get("subtitle"), EMPTY_TEXT),
                "author": clean_text(manifest.get("author"), DEFAULT_AUTHOR),
                "industry": clean_text(manifest.get("industry"), DEFAULT_INDUSTRY),
                "fields": manifest.get("fields", []),
                "state_path": str(state_path) if state_data else "",
                "analysis_path": str(analysis_path) if analysis_data else "",
                "items": captured_items,
            },
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    report_path = render_report(manifest, captured_items, output_dir, state_path.name, analysis_data)
    print(f"报告已生成: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
