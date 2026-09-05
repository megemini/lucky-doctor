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
                             [--copies 6] \
                             [--sticker-size 70x50] \
                             [--qr-size-mm 20]

Layout / pill-box adaptation:
    The A4 sheet is filled with one sticker per medicine box.  By default each
    sticker is a 70x50 mm label -- large enough to carry a comfortably
    scannable QR code while still leaving most of an 11x6 cm pill-box face
    visible.  The QR code is auto-sized to fit the label; pass --qr-size-mm to
    force a size or --sticker-size to match other box faces.

Outputs:
    PNG      - single high-resolution QR code (for digital use / 1:1 printing)
    PDF      - A4 sheet of trimmed labels (dashed border), each showing the
               medicine name, the QR code and the record id at the bottom
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

# A4 sheet layout (mm)
PAGE_W_MM, PAGE_H_MM = 210.0, 297.0
MARGIN_MM = 12.0
MIN_GUTTER_MM = 3.0   # minimum white space kept between two stickers

# Default single-sticker size: a roomy label that keeps the QR comfortably
# scannable while still leaving space for other info on the pill-box face.
# Auto-fit keeps the QR around 20 mm on this size.
DEFAULT_STICKER_W_MM = 70.0
DEFAULT_STICKER_H_MM = 50.0
PAD_MM = 2.0          # inner padding inside the dashed trim line

# Auto QR: at most this share of the sticker height, so the code never crowds
# the whole label on small boxes.
AUTO_QR_MAX_HEIGHT_RATIO = 0.62

PT_TO_MM = 25.4 / 72.0
MM_TO_PT = 72.0 / 25.4

# The bottom band prints the record id embedded in the QR payload, so a printed
# sticker can be matched back to the record it belongs to.  FOOTER_FALLBACK is
# shown only if a payload somehow carries no id.  Keep the fallback plain CJK:
# STSong-Light lacks a glyph for some Latin punctuation (e.g. U+00B7 middle
# dot), which used to render as mojibake.
FOOTER_FALLBACK = "扫码查看用药说明"

TITLE_SIZES = [22, 20, 18, 16, 14, 12, 11, 10, 9, 8, 7, 6]
HINT_SIZES = [13, 12, 11, 10, 9, 8.5, 8, 7.5, 7, 6.5, 6, 5.5, 5, 4.5]


def mm(v):
    """Convert millimetres to PDF points."""
    return v * MM_TO_PT


def parse_size_pair(text):
    """Parse 'WxH' (mm) into (float, float); supports x/X/× separators."""
    m = re.fullmatch(r"\s*([\d.]+)\s*[xX×]\s*([\d.]+)\s*", text or "")
    if not m:
        raise argparse.ArgumentTypeError(
            f"invalid size '{text}' (expected '<width>x<height>' in mm, e.g. 70x50)"
        )
    return float(m.group(1)), float(m.group(2))


def build_payload(record_id, medicine_name):
    """Build the sticker payload; sanitize fields so parsing stays unambiguous."""
    if not record_id:
        raise ValueError("record_id is empty; cannot build a sticker payload")
    name = str(medicine_name or "").replace(PAYLOAD_SEPARATOR, "_")
    return f"{PAYLOAD_PREFIX}{PAYLOAD_SEPARATOR}{PAYLOAD_VERSION}{PAYLOAD_SEPARATOR}{record_id}{PAYLOAD_SEPARATOR}{name}"


def _record_id(payload):
    """Extract the record id (payload field 3) from a sticker payload."""
    parts = payload.split(PAYLOAD_SEPARATOR)
    return parts[2] if len(parts) > 2 else ""


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


def _fit_font_size(font, text, candidates, max_width_mm):
    """Pick the largest font size whose text width fits max_width_mm."""
    for size in candidates:
        if pdfmetrics.stringWidth(text, font, size) * PT_TO_MM <= max_width_mm:
            return size
    return candidates[-1]


def _label_geometry(sw_mm, sh_mm, medicine_name, qr_override_mm, footer_text=None):
    """
    Compute per-sticker text/image sizes from the sticker box size.
    All dimensions in mm. Returns a dict consumed by _draw_label.
    footer_text is the bottom band text (normally the record id); it falls back
    to FOOTER_FALLBACK when omitted or empty.
    """
    name = medicine_name or "药品"
    usable_w = sw_mm - 2 * PAD_MM
    footer_text = footer_text or FOOTER_FALLBACK

    # On short labels a big title eats the space the QR needs for scanning, so
    # cap the title size on compact stickers.
    title_cap = 14.0 if sh_mm < 36 else TITLE_SIZES[0]
    title_candidates = [s for s in TITLE_SIZES if s <= title_cap]
    title_fs = _fit_font_size(FONT_NAME, name, title_candidates, usable_w - 1.0)
    hint_fs = _fit_font_size(FONT_NAME, footer_text, HINT_SIZES, usable_w - 1.0)

    title_mm = title_fs * PT_TO_MM
    hint_mm = hint_fs * PT_TO_MM

    # Title sits in the top band.  CJK glyphs rise ~0.88 em above the baseline
    # and ~0.1 em below it, so the baseline is lowered to keep the glyph box
    # inside the padded area (baseline_y is the text's bottom anchor).
    title_baseline = sh_mm - PAD_MM - title_mm * 0.9
    mid_top = sh_mm - PAD_MM - title_mm - 1.0

    # Hint + trace id share the bottom band.
    hint_baseline = PAD_MM + hint_mm * 0.35
    mid_bottom = hint_baseline + hint_mm + 1.0

    mid_h = max(0.0, mid_top - mid_bottom)

    if qr_override_mm and qr_override_mm > 0:
        qr_size = qr_override_mm
    else:
        qr_size = min(
            usable_w - 1.5,
            mid_h - 1.5,
            sh_mm * AUTO_QR_MAX_HEIGHT_RATIO,
        )
    # Never let the QR escape the trimmed area (padded box).
    qr_size = max(0.0, min(qr_size, usable_w, sh_mm - 2 * PAD_MM))

    if mid_h >= qr_size + 1.0:
        qr_y = mid_bottom + (mid_h - qr_size) / 2.0
    else:
        qr_y = PAD_MM  # degenerate tiny label: keep it at the bottom
    qr_y = min(max(qr_y, PAD_MM), max(PAD_MM, sh_mm - PAD_MM - qr_size))

    return {
        "title_fs": title_fs,
        "title_baseline": title_baseline,
        "hint_fs": hint_fs,
        "hint_baseline": hint_baseline,
        "qr_size": qr_size,
        "qr_x": (sw_mm - qr_size) / 2.0,
        "qr_y": qr_y,
        "mid_top": mid_top,
    }


def _draw_label_full(c, x_mm, y_bottom_mm, medicine_name, payload, qr_png,
                     sw_mm, sh_mm, qr_override_mm):
    """Draw one trimmed label (dashed border + name + QR + record id)."""
    footer = _record_id(payload) or FOOTER_FALLBACK
    geo = _label_geometry(sw_mm, sh_mm, medicine_name, qr_override_mm, footer)
    w, h = sw_mm, sh_mm

    c.saveState()
    c.translate(mm(x_mm), mm(y_bottom_mm))
    c.setFillColorRGB(1, 1, 1)
    c.rect(0, 0, mm(w), mm(h), stroke=0, fill=1)

    # Dashed trim border (a few mm inside the edge for scissors)
    c.setStrokeColorRGB(0.35, 0.35, 0.35)
    c.setDash(3, 3)
    c.setLineWidth(0.5)
    c.rect(mm(0.7), mm(0.7), mm(w - 1.4), mm(h - 1.4), stroke=1, fill=0)
    c.setDash()

    # --- Medicine name (top, centered) ---
    name = medicine_name or "药品"
    c.setFillColorRGB(0, 0, 0)
    _draw_centered_text(c, name, w / 2, geo["title_baseline"], FONT_NAME, geo["title_fs"])

    # --- QR code (auto-sized, centred in the middle band) ---
    qr_size = geo["qr_size"]
    if qr_size >= 6.0:
        c.drawImage(qr_png, mm(geo["qr_x"]), mm(geo["qr_y"]),
                    width=mm(qr_size), height=mm(qr_size))

    # --- Footer: record id (centered, bottom) ---
    c.setFillColorRGB(0, 0, 0)
    _draw_centered_text(c, footer, w / 2, geo["hint_baseline"], FONT_NAME, geo["hint_fs"])

    c.restoreState()


def generate_pdf(payload, medicine_name, qr_png, out_pdf, copies=6,
                 sticker_w=DEFAULT_STICKER_W_MM, sticker_h=DEFAULT_STICKER_H_MM,
                 qr_size_mm=0):
    """
    Render an A4 sheet of trimmed, printable labels.

    Stickers of one page are packed with a fixed MIN_GUTTER_MM spacing and the
    whole block is centred on the page; if the number of copies cannot fit one
    page, extra pages are added automatically.
    """
    copies = max(1, int(copies))
    sticker_w = min(sticker_w, PAGE_W_MM - 2 * MARGIN_MM)
    sticker_h = min(sticker_h, PAGE_H_MM - 2 * MARGIN_MM)
    if sticker_w < 20 or sticker_h < 20:
        raise ValueError("sticker size too small to print (>= 20 mm each side)")
    out_pdf = Path(out_pdf)
    _register_font()

    usable_w = PAGE_W_MM - 2 * MARGIN_MM
    usable_h = PAGE_H_MM - 2 * MARGIN_MM

    # Max stickers that fit per row/column with >= MIN_GUTTER_MM spacing.
    cols = max(1, int((usable_w + MIN_GUTTER_MM) // (sticker_w + MIN_GUTTER_MM)))
    rows = max(1, int((usable_h + MIN_GUTTER_MM) // (sticker_h + MIN_GUTTER_MM)))
    capacity = cols * rows

    # Warn once when the auto-sized QR comes out very small (hard to scan).
    if not qr_size_mm:
        footer = _record_id(payload) or FOOTER_FALLBACK
        qr_est = _label_geometry(sticker_w, sticker_h, medicine_name, 0, footer)["qr_size"]
        if 0 < qr_est < 13.0:
            logger.warning(
                "Auto QR on %.0fx%.0f mm labels is only ~%.1f mm — scan the code "
                "up close. If it is hard to read, enlarge --sticker-size / "
                "--qr-size-mm or lower --error (e.g. m) and regenerate.",
                sticker_w, sticker_h, qr_est,
            )

    c = pdf_canvas.Canvas(str(out_pdf), pagesize=A4)
    c.setTitle("Lucky Doctor medicine sticker")

    total_drawn = 0
    while total_drawn < copies:
        per_page = min(copies - total_drawn, capacity)
        rows_used = (per_page + cols - 1) // cols  # <= rows by construction
        # Pack the stickers with MIN_GUTTER_MM spacing and centre the whole
        # block on the page (the rest of the sheet stays blank for trimming).
        block_w = cols * sticker_w + (cols - 1) * MIN_GUTTER_MM
        block_h = rows_used * sticker_h + (rows_used - 1) * MIN_GUTTER_MM
        x0 = MARGIN_MM + (usable_w - block_w) / 2.0
        y0 = MARGIN_MM + (usable_h - block_h) / 2.0
        for cell in range(per_page):
            row = cell // cols
            col = cell % cols
            x = x0 + col * (sticker_w + MIN_GUTTER_MM)
            y_bottom = y0 + row * (sticker_h + MIN_GUTTER_MM)
            _draw_label_full(c, x, y_bottom, medicine_name, payload, qr_png,
                             sticker_w, sticker_h, qr_size_mm)
        total_drawn += per_page
        c.showPage()
    c.save()

    logger.info(
        "A4 sticker sheet written: %s (%d label(s), each %.0f x %.0f mm, QR %s)",
        out_pdf, total_drawn, sticker_w, sticker_h,
        f"{qr_size_mm:g} mm" if qr_size_mm else "auto",
    )
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
    parser.add_argument("--copies", type=int, default=6,
                        help="Number of identical stickers to print (default: 6)")
    parser.add_argument(
        "--sticker-size", type=parse_size_pair, default=(DEFAULT_STICKER_W_MM, DEFAULT_STICKER_H_MM),
        metavar="WxH",
        help="Single sticker size in mm, e.g. 70x50 (default: 70x50); use a "
             "larger size (or more copies) and pages auto-split",
    )
    parser.add_argument("--qr-size-mm", type=float, default=0.0,
                        help="QR code edge in mm (default: auto — fit to the label; "
                             "on the default 70x50 mm sticker auto size lands "
                             "around 20 mm)")
    args = parser.parse_args()

    record_id, medicine_name = load_package_meta(args.package)
    payload = build_payload(record_id, medicine_name)
    stem = _sanitize_file_stem(medicine_name)

    if args.out_png is None:
        args.out_png = f"medicine_sticker_{stem}.png"
    if args.out_pdf is None:
        args.out_pdf = f"medicine_sticker_{stem}.pdf"

    sticker_w, sticker_h = args.sticker_size

    png_path = generate_png(payload, args.out_png, scale=args.scale, error=args.error)
    pdf_path = generate_pdf(payload, medicine_name, png_path, args.out_pdf,
                            copies=args.copies, sticker_w=sticker_w,
                            sticker_h=sticker_h, qr_size_mm=args.qr_size_mm)

    print(json.dumps({
        "status": "success",
        "record_id": record_id,
        "medicine_name": medicine_name,
        "payload": payload,
        "qr_png": png_path,
        "sticker_pdf": pdf_path,
        "sticker_size_mm": [sticker_w, sticker_h],
        "qr_size_mm": args.qr_size_mm or "auto",
        "copies": args.copies,
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    _main()
