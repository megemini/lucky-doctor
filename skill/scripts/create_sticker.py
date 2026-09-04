#!/usr/bin/env python3
"""
create_sticker.py - Create the medicine-box QR sticker (PNG + A4 printable PDF).

The QR payload follows the Lucky Doctor sticker spec shared with the mobile app:

    LD|1|<record_id>|<medicine_name>

    LD            - fixed Lucky Doctor prefix (discriminates our QR codes)
    1             - payload version (bump only on breaking changes)
    record_id     - the same id embedded in the package metadata.json; the app
                    looks up its imported local record by this exact id
    medicine_name - human readable name shown when no local record exists yet

The sticker is produced from a data package ZIP (create_package.py output) so
the QR id and the imported record id can never drift apart.

Usage:
    python create_sticker.py --package medicine_package_阿莫西林.zip \
                             [--out-png medicine_sticker_阿莫西林.png] \
                             [--out-pdf medicine_sticker_sheet_阿莫西林.pdf] \
                             [--copies 6]

Outputs:
    PNG      - single high-resolution QR code (for digital use / 1:1 printing)
    PDF      - A4 sheet of trimmed labels (dashed border), each with the
               medicine name, the QR code and a scan hint
"""

import argparse
import json
import logging
import re
import zipfile
from pathlib import Path

import segno
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.pdfgen import canvas as pdf_canvas

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("lucky_doctor")

# ---------------------------------------------------------------------------
# Sticker payload spec (MUST stay in sync with mobile/lib/services/qr_service.dart)
# ---------------------------------------------------------------------------
PAYLOAD_PREFIX = "LD"
PAYLOAD_VERSION = "1"
PAYLOAD_SEPARATOR = "|"
FONT_NAME = "STSong-Light"  # reportlab built-in CID font with CJK support

# A4 label sheet layout (mm)
PAGE_W_MM, PAGE_H_MM = 210.0, 297.0
MARGIN_MM = 12.0
GAP_MM = 2.0
LABEL_COLS = 2
LABEL_ROWS = 3
LABEL_W_MM = (PAGE_W_MM - 2 * MARGIN_MM - (LABEL_COLS - 1) * GAP_MM) / LABEL_COLS
LABEL_H_MM = (PAGE_H_MM - 2 * MARGIN_MM - (LABEL_ROWS - 1) * GAP_MM) / LABEL_ROWS
LABELS_PER_PAGE = LABEL_COLS * LABEL_ROWS

MM_TO_PT = 72.0 / 25.4


def mm(v):
    """Convert millimetres to PDF points."""
    return v * MM_TO_PT


def build_payload(record_id, medicine_name):
    """Build the sticker payload; sanitize fields so parsing stays unambiguous."""
    if not record_id:
        raise ValueError("record_id is empty; cannot build a sticker payload")
    name = str(medicine_name or "").replace(PAYLOAD_SEPARATOR, "_")
    return f"{PAYLOAD_PREFIX}{PAYLOAD_SEPARATOR}{PAYLOAD_VERSION}{PAYLOAD_SEPARATOR}{record_id}{PAYLOAD_SEPARATOR}{name}"


def _sanitize_file_stem(name):
    stem = re.sub(r"[^\w\u4e00-\u9fff-]", "_", str(name)).strip("_")
    return stem[:40] or "medicine"


def load_package_meta(package_path):
    """Read metadata.json out of a data package ZIP and return (id, medicine_name)."""
    package_path = Path(package_path)
    if not package_path.exists():
        raise FileNotFoundError(f"Package not found: {package_path}")
    try:
        with zipfile.ZipFile(package_path) as zf:
            meta_raw = zf.read("metadata.json")
    except (zipfile.BadZipFile, KeyError) as exc:
        raise ValueError(f"Invalid medicine package (need metadata.json in ZIP): {package_path}") from exc
    meta = json.loads(meta_raw.decode("utf-8"))
    record_id = meta.get("id")
    medicine_name = meta.get("medicine_name", "")
    if not record_id:
        raise ValueError(f"Package metadata has no 'id': {package_path}")
    return record_id, medicine_name


def generate_png(payload, out_png, scale=20, error="q", border=4):
    """Render the QR code to a high-resolution PNG (quiet zone included)."""
    qr = segno.make(payload, error=error, encoding="utf-8")
    out_png = Path(out_png)
    qr.save(
        out_png,
        scale=scale,
        border=border,
        dark="black",
        light="white",
    )
    logger.info("QR PNG written: %s", out_png)
    logger.info("  - payload: %s", payload)
    return str(out_png.resolve())


def _register_font():
    if FONT_NAME not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont(FONT_NAME))


def _draw_centered_text(c, text, center_x_mm, baseline_y_mm, font, size):
    """Draw CJK text horizontally centered at center_x (all coords in mm)."""
    c.setFont(font, size)
    width_pt = pdfmetrics.stringWidth(text, font, size)
    c.drawString(mm(center_x_mm) - width_pt / 2, mm(baseline_y_mm), text)


def _draw_label(c, x_mm, y_bottom_mm, medicine_name, payload, qr_png):
    """Draw a single label box (local coordinates in mm), incl. dashed trim line."""
    w, h = LABEL_W_MM, LABEL_H_MM
    c.saveState()
    c.translate(mm(x_mm), mm(y_bottom_mm))
    c.setFillColorRGB(1, 1, 1)
    c.rect(0, 0, mm(w), mm(h), stroke=0, fill=1)

    # Dashed trim border
    c.setStrokeColorRGB(0.35, 0.35, 0.35)
    c.setDash(3, 3)
    c.setLineWidth(0.5)
    c.rect(mm(0.6), mm(0.6), mm(w - 1.2), mm(h - 1.2), stroke=1, fill=0)
    c.setDash()

    # --- Medicine name (top, centered) ---
    name = medicine_name or "药品"
    name_len = len(name)
    if name_len <= 8:
        name_font = 20
    elif name_len <= 13:
        name_font = 16
    else:
        name_font = 12
    c.setFillColorRGB(0, 0, 0)
    _draw_centered_text(c, name, w / 2, h - 10.0, FONT_NAME, name_font)

    # --- QR code (centered) ---
    qr_size = 54.0
    qr_x = (w - qr_size) / 2
    qr_y = 13.0  # leaves room for the footer hint at the bottom
    c.drawImage(qr_png, mm(qr_x), mm(qr_y), width=mm(qr_size), height=mm(qr_size))

    # --- Footer hint ---
    c.setFillColorRGB(0, 0, 0)
    hint = "扫码查看用药说明 · Lucky Doctor"
    _draw_centered_text(c, hint, w / 2, 6.5, FONT_NAME, 8.5)

    # --- Id trace (small, bottom-left) ---
    parts = payload.split(PAYLOAD_SEPARATOR)
    trace_id = parts[2][:8] if len(parts) > 2 else ""
    c.setFillColorRGB(0.45, 0.45, 0.45)
    c.setFont(FONT_NAME, 5.5)
    c.drawString(mm(2.5), mm(2.5), f"ID {trace_id}")
    c.restoreState()


def generate_pdf(payload, medicine_name, qr_png, out_pdf, copies=LABELS_PER_PAGE):
    """Render an A4 sheet of trimmed, printable labels (multi-page if needed)."""
    copies = max(1, copies)
    out_pdf = Path(out_pdf)
    _register_font()

    c = pdf_canvas.Canvas(str(out_pdf), pagesize=A4)
    c.setTitle("Lucky Doctor medicine sticker")

    total_drawn = 0
    while total_drawn < copies:
        page_remaining = min(copies - total_drawn, LABELS_PER_PAGE)
        for cell in range(page_remaining):
            row = cell // LABEL_COLS
            col = cell % LABEL_COLS
            x = MARGIN_MM + col * (LABEL_W_MM + GAP_MM)
            # Rows are laid out from the top of the page downward.
            y_top = PAGE_H_MM - MARGIN_MM - row * (LABEL_H_MM + GAP_MM)
            y_bottom = y_top - LABEL_H_MM
            _draw_label(c, x, y_bottom, medicine_name, payload, qr_png)
        total_drawn += page_remaining
        c.showPage()
    c.save()

    logger.info("A4 sticker sheet written: %s (%d label(s), label %s x %s mm)",
                out_pdf, total_drawn, round(LABEL_W_MM, 1), round(LABEL_H_MM, 1))
    return str(out_pdf.resolve())


def _main():
    parser = argparse.ArgumentParser(
        description="Create Lucky Doctor QR sticker (PNG + A4 printable PDF) from a data package ZIP"
    )
    parser.add_argument("--package", required=True,
                        help="Path to the data package ZIP created by create_package.py")
    parser.add_argument("--out-png", default=None,
                        help="Output PNG path (default: medicine_sticker_<name>.png)")
    parser.add_argument("--out-pdf", default=None,
                        help="Output A4 label-sheet PDF path (default: medicine_sticker_<name>.pdf)")
    parser.add_argument("--error", default="q",
                        help="QR error-correction level: l/m/q/h (default: q)")
    parser.add_argument("--scale", type=int, default=20,
                        help="QR pixel scale per module (default: 20, ~print friendly)")
    parser.add_argument("--copies", type=int, default=LABELS_PER_PAGE,
                        help="Number of identical labels per output (default: %d)" % LABELS_PER_PAGE)
    args = parser.parse_args()

    record_id, medicine_name = load_package_meta(args.package)
    payload = build_payload(record_id, medicine_name)
    stem = _sanitize_file_stem(medicine_name)

    if args.out_png is None:
        args.out_png = f"medicine_sticker_{stem}.png"
    if args.out_pdf is None:
        args.out_pdf = f"medicine_sticker_{stem}.pdf"

    png_path = generate_png(payload, args.out_png, scale=args.scale, error=args.error)
    pdf_path = generate_pdf(payload, medicine_name, png_path, args.out_pdf, copies=args.copies)

    print(json.dumps({
        "status": "success",
        "record_id": record_id,
        "medicine_name": medicine_name,
        "payload": payload,
        "qr_png": png_path,
        "sticker_pdf": pdf_path,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    _main()
