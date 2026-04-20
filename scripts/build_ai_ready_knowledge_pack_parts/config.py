
from __future__ import annotations

import argparse
import base64
import csv
import hashlib
import json
import math
import mimetypes
import re
import shutil
import statistics
import unicodedata
import zipfile
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable

import fitz
import pandas as pd
from bs4 import BeautifulSoup
from docx import Document
from rapidocr_onnxruntime import RapidOCR


IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff", ".bmp"}
TEXT_SUFFIXES = {".md", ".txt"}
HTML_SUFFIXES = {".html", ".htm"}
EXCEL_SUFFIXES = {".xlsx", ".xls"}
WORD_SUFFIXES = {".docx"}
PDF_SUFFIXES = {".pdf"}


def clean_text(value: Any) -> str:
    text = str(value or "")
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = text.replace("\xa0", " ").replace("\u3000", " ")
    text = text.replace("\ufeff", "").replace("\u200b", "")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def clean_inline_text(value: Any) -> str:
    return clean_text(value).replace("\n", " ")


def ensure_dir(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def write_text(path: Path, text: str) -> None:
    ensure_dir(path.parent)
    path.write_text(text.rstrip() + "\n", encoding="utf-8")


def write_json(path: Path, payload: Any) -> None:
    ensure_dir(path.parent)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, ensure_ascii=False) + "\n")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    ensure_dir(path.parent)
    with path.open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def slugify_ascii(value: str, fallback: str) -> str:
    normalized = unicodedata.normalize("NFKD", value or "")
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    ascii_text = re.sub(r"[^A-Za-z0-9]+", "_", ascii_text).strip("_").lower()
    return ascii_text or fallback


def semantic_name(path: Path, fallback: str) -> str:
    stem = path.stem
    if "1-2vs3-4" in stem:
        return "sc_basis_vs_cont0_price"
    if "各月份差" in stem:
        return "sc_multileg_spreads_vs_cont1_price"
    if "统计" in stem:
        return "sc_spread_statistics"
    if "sprd" in stem.lower():
        return "sc_spread_timeseries"
    if "策略" in stem:
        return "sc_spread_data_notes"
    if "原油" in stem:
        return "crude_oil_strategy_memo"
    if "价差图" in stem:
        return "sc_spread_notebook"
    return slugify_ascii(stem, fallback)


def sheet_slug(sheet_name: str, fallback: str) -> str:
    mapping = {
        "全部": "all",
        "all_daily": "all_daily",
        "all": "all",
    }
    if sheet_name in mapping:
        return mapping[sheet_name]
    if re.fullmatch(r"\d+-\d+", sheet_name):
        return sheet_name.replace("-", "_")
    return slugify_ascii(sheet_name, fallback)


def sha_uid(*parts: Any, length: int = 16) -> str:
    raw = "|".join(str(part or "") for part in parts)
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:length]


def approx_token_count(text: str) -> int:
    if not text:
        return 0
    cjk_count = len(re.findall(r"[\u4e00-\u9fff]", text))
    word_count = len(re.findall(r"[A-Za-z0-9_]+", text))
    punctuation_count = len(re.findall(r"[，。；：,.!?()\-\[\]/]", text))
    return max(1, cjk_count + word_count + math.ceil(punctuation_count / 2))


def make_markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    if not headers:
        return ""
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    for row in rows:
        cells = [clean_inline_text(item) for item in row]
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines)


def normalize_markdown(text: str) -> str:
    text = clean_text(text)
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def coerce_iso_date(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, pd.Timestamp):
        if pd.isna(value):
            return None
        return value.date().isoformat()
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    text = clean_inline_text(value)
    if not text:
        return None
    for parser in (
        lambda item: date.fromisoformat(item[:10]),
        lambda item: datetime.fromisoformat(item.replace("Z", "+00:00")).date(),
    ):
        try:
            return parser(text).isoformat()
        except Exception:
            continue
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) >= 8:
        try:
            return date.fromisoformat(f"{digits[:4]}-{digits[4:6]}-{digits[6:8]}").isoformat()
        except Exception:
            return None
    return None


def normalize_delivery_month(value: Any) -> str | None:
    text = clean_inline_text(value)
    if not text:
        return None
    if text.upper() == "ALL":
        return "ALL"
    digits = "".join(ch for ch in text if ch.isdigit())
    if len(digits) == 4:
        return digits
    return text


def normalize_percentile_label(value: Any) -> str | None:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        pct = float(value) * 100
        return f"pct_{int(round(pct)):02d}"
    text = clean_inline_text(value)
    if text in {"0.01", "0.05", "0.1", "0.25", "0.5", "0.75", "0.9", "0.95", "0.99"}:
        return normalize_percentile_label(float(text))
    return None


def normalize_column_name(name: Any) -> str:
    direct = {
        "月份": "delivery_month",
        "合约": "contract_leg",
        "count": "sample_count",
        "mean": "mean",
        "std": "std_dev",
        "min": "min_value",
        "max": "max_value",
        "date_std": "start_date",
        "date_end": "end_date",
        "trading_date_x": "trading_date",
        "Mid": "spread_mid",
        "Conts": "contracts",
        "01": "price_01",
        "Cont0": "front_contract",
        "Cont01": "contract_01",
        "Price01": "price_01",
        "Leg": "contract_leg",
    }
    if name in direct:
        return direct[name]
    if isinstance(name, str) and re.fullmatch(r"\d+-\d+", name):
        return f"spread_{name.replace('-', '_')}"
    percentile = normalize_percentile_label(name)
    if percentile:
        return percentile
    text = clean_inline_text(name)
    return slugify_ascii(text, "column")


def dataframe_to_records(df: pd.DataFrame) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for row in df.to_dict(orient="records"):
        normalized: dict[str, Any] = {}
        for key, value in row.items():
            if isinstance(value, float) and pd.isna(value):
                normalized[key] = None
                continue
            if isinstance(value, pd.Timestamp):
                normalized[key] = value.isoformat()
                continue
            normalized[key] = value
        records.append(normalized)
    return records


def chunk_markdown(text: str, max_chars: int = 900) -> list[str]:
    paragraphs = [part.strip() for part in normalize_markdown(text).split("\n\n") if part.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = paragraph if not current else f"{current}\n\n{paragraph}"
        if len(candidate) <= max_chars:
            current = candidate
            continue
        if current:
            chunks.append(current.strip())
            current = ""
        if len(paragraph) <= max_chars:
            current = paragraph
            continue
        sentences = re.split(r"(?<=[。！？.!?])\s+", paragraph)
        temp = ""
        for sentence in sentences:
            sentence = sentence.strip()
            if not sentence:
                continue
            candidate = sentence if not temp else f"{temp} {sentence}"
            if len(candidate) <= max_chars:
                temp = candidate
            else:
                if temp:
                    chunks.append(temp.strip())
                temp = sentence
        if temp:
            current = temp
    if current:
        chunks.append(current.strip())
    return chunks or [normalize_markdown(text)]


def rows_to_markdown_list(rows: list[str], prefix: str = "- ") -> str:
    return "\n".join(f"{prefix}{clean_inline_text(row)}" for row in rows if clean_inline_text(row))


def extract_docx_media(docx_path: Path, assets_dir: Path) -> list[Path]:
    extracted: list[Path] = []
    ensure_dir(assets_dir)
    with zipfile.ZipFile(docx_path) as archive:
        media_names = sorted(name for name in archive.namelist() if name.startswith("word/media/"))
        for idx, name in enumerate(media_names, start=1):
            ext = Path(name).suffix.lower() or ""
            payload = archive.read(name)
            if not payload or ext not in IMAGE_SUFFIXES:
                continue
            out_path = assets_dir / f"figure_{idx:02d}{ext}"
            out_path.write_bytes(payload)
            extracted.append(out_path)
    return extracted


def extract_pdf_text(doc_path: Path, page_assets_dir: Path, ocr: RapidOCR) -> tuple[str, list[Path]]:
    ensure_dir(page_assets_dir)
    doc = fitz.open(doc_path)
    pages: list[str] = []
    rendered_pages: list[Path] = []
    for page_index, page in enumerate(doc, start=1):
        page_text = clean_text(page.get_text("text"))
        if len(page_text) < 80:
            page_asset = page_assets_dir / f"page_{page_index:02d}.png"
            pixmap = page.get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
            pixmap.save(str(page_asset))
            rendered_pages.append(page_asset)
            ocr_lines = run_ocr_lines(ocr, page_asset)
            page_text = "\n".join(line["text"] for line in ocr_lines)
        pages.append(f"## Page {page_index}\n\n{page_text.strip()}")
    return "\n\n".join(pages).strip(), rendered_pages


def run_ocr_lines(ocr: RapidOCR, image_path: Path) -> list[dict[str, Any]]:
    results, _ = ocr(str(image_path))
    lines: list[dict[str, Any]] = []
    for item in results or []:
        box, text, score = item
        xs = [pt[0] for pt in box]
        ys = [pt[1] for pt in box]
        lines.append(
            {
                "text": clean_inline_text(text),
                "score": round(float(score), 6),
                "x": round(statistics.mean(xs), 2),
                "y": round(statistics.mean(ys), 2),
            }
        )
    lines.sort(key=lambda row: (round(row["y"] / 18), row["x"]))
    return [line for line in lines if line["text"]]


def summarize_ocr_chart(file_name: str, ocr_lines: list[dict[str, Any]]) -> str:
    texts = [line["text"] for line in ocr_lines]
    text_blob = " ".join(texts)
    if "1-2vs3-4" in file_name:
        return (
            "图像显示 SC 主力价格与两组跨月价差的叠加走势：蓝线对应 cont1-cont2，橙线对应 cont3-cont4。"
            " OCR 识别到横轴大致覆盖 2023-01 至 2025-01，左轴价差约 -60 到 60，右轴价格约 500 到 750。"
        )
    if "各月份差" in file_name:
        return (
            "图像将 1-2、2-3、3-4、4-5 四组价差与 ContNo1 价格放在双轴图中共同展示，"
            "横轴覆盖约 2022-11 至 2024-12，可用于观察近端价差与主力价格共振。"
        )
    title = next((item for item in texts if len(item) >= 8), file_name)
    dates = re.findall(r"\d{4}-\d{2}", text_blob)
    range_hint = ""
    if dates:
        range_hint = f" OCR 可见时间刻度大致为 {dates[0]} 至 {dates[-1]}。"
    return f"图像 OCR 标题为“{title}”。{range_hint}"


def summarize_html_figures(figures: list[dict[str, Any]]) -> str:
    if not figures:
        return "HTML 文件未发现嵌入图像。"
    count = len(figures)
    titles = [figure.get("title") for figure in figures if figure.get("title")]
    title_hint = f" 主要 OCR 标题包括：{'; '.join(titles[:3])}。" if titles else ""
    return (
        f"HTML 文件中提取出 {count} 张嵌入图像。结合 `sc_sprd` 工作簿包含 11 组月差数据这一事实，"
        f"这里推断这些图像大概率对应单腿价差或其派生可视化。{title_hint}"
    )


def guess_keywords(title: str, group: str, extra: list[str] | None = None) -> list[str]:
    base = {
        "strategy_notes": ["原油", "SC", "策略", "跨月价差"],
        "price_trend": ["原油", "SC", "价格走势", "价差图"],
        "spread_statistics": ["原油", "SC", "统计", "时间序列"],
    }.get(group, ["原油", "SC"])
    merged = base + list(extra or [])
    seen: list[str] = []
    for item in merged + re.findall(r"[A-Za-z0-9\-\u4e00-\u9fff]+", title):
        item = clean_inline_text(item)
        if item and item not in seen:
            seen.append(item)
    return seen[:12]


@dataclass
class ProcessedDocument:
    doc_uid: str
    title: str
    doc_type: str
    content_group: str
    source_file: str
    output_markdown: str
    summary: str
    body: str
    keywords: list[str]
    dataset_refs: list[str] = field(default_factory=list)
    published_at: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class DatasetArtifact:
    dataset_id: str
    title: str
    source_file: str
    output_csv: str
    group: str
    row_count: int
    column_count: int
    columns: list[str]
    date_columns: list[str]
    date_range: dict[str, str | None]
    summary: str
    metadata: dict[str, Any] = field(default_factory=dict)
