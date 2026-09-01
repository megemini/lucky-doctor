#!/usr/bin/env python3
"""
recognize.py - Medicine box / instruction leaflet OCR.

Usage:
    python recognize.py --image <path> [--device AUTO] [--output json|text]

Steps:
    1. OCR (PaddleOCR-VL) - extract text from image
    2. Output OCR text for the agent to summarize

Note:
    Structured medicine info extraction, summary writing, and keyword
    generation are done by the AGENT (not by a VLM model). This script
    only produces the raw OCR text plus the image path.
"""

import argparse
import json
import logging
import math
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "lib"))
sys.path.insert(0, str(PROJECT_ROOT / "scripts"))

import pyenv  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("lucky_doctor")


def split_image(image, num_splits=4, overlap_ratio=0.1):
    grid_size = int(math.sqrt(num_splits))
    if grid_size * grid_size != num_splits:
        raise ValueError(f"num_splits must be a perfect square, got: {num_splits}")
    w, h = image.size
    cell_w = w / grid_size
    cell_h = h / grid_size
    overlap_w = cell_w * overlap_ratio
    overlap_h = cell_h * overlap_ratio
    sub_images = []
    for row in range(grid_size):
        for col in range(grid_size):
            left = max(0, col * cell_w - overlap_w)
            upper = max(0, row * cell_h - overlap_h)
            right = min(w, (col + 1) * cell_w + overlap_w)
            lower = min(h, (row + 1) * cell_h + overlap_h)
            sub_images.append(image.crop((int(left), int(upper), int(right), int(lower))))
    return sub_images


def ocr_image(ocr_model, image, max_new_tokens=5120):
    messages = [
        {
            "role": "user",
            "content": [
                {"type": "image", "image": image},
                {"type": "text", "text": "OCR:"},
            ],
        }
    ]
    generation_config = {
        "bos_token_id": ocr_model.tokenizer.bos_token_id,
        "eos_token_id": ocr_model.tokenizer.eos_token_id,
        "pad_token_id": ocr_model.tokenizer.pad_token_id,
        "max_new_tokens": max_new_tokens,
        "do_sample": False,
    }
    response, _ = ocr_model.chat(messages=messages, generation_config=generation_config)
    return response


def run_ocr(image_path, device="AUTO", enable_split=True,
            num_splits=4, overlap_ratio=0.1, ocr_max_new_tokens=5120):
    """Run OCR-only recognition. Returns dict with ocr_text and image_path."""
    from PIL import Image
    from model_manager import ModelManager

    cfg = pyenv.config_or_default()
    if not cfg.get("configured"):
        raise SystemExit(
            "Environment not configured. Run setup first:\n"
            "  <python> scripts/setup.py check   # inspect status\n"
            "  <python> scripts/setup.py install  # auto-configure\n"
            "  <python> scripts/setup.py --guided # step-by-step"
        )
    if not pyenv.is_model_ready(cfg, "ocr"):
        raise SystemExit(
            "OCR model not found at:\n"
            f"  {pyenv.resolve_model_dir(cfg, 'ocr')}\n"
            "Download it with:  <python> scripts/setup.py install"
        )
    model_manager = ModelManager(
        ocr_model_dir=str(pyenv.resolve_model_dir(cfg, "ocr")),
        device=device,
    )

    result = {}

    logger.info("Loading image: %s", image_path)
    image = Image.open(image_path).convert("RGB")
    logger.info("Image size: %s", image.size)

    if enable_split:
        sub_images = split_image(image, num_splits=num_splits, overlap_ratio=overlap_ratio)
        ocr_images = [image] + sub_images
    else:
        ocr_images = [image]

    logger.info("Running OCR on %d image(s)...", len(ocr_images))
    ocr_model = model_manager.get_ocr_model()
    all_ocr_texts = []
    for i, img in enumerate(ocr_images):
        all_ocr_texts.append(ocr_image(ocr_model, img, max_new_tokens=ocr_max_new_tokens))

    combined_ocr_text = "\n\n".join(all_ocr_texts)
    result["ocr_text"] = combined_ocr_text
    result["image_path"] = str(Path(image_path).resolve())
    logger.info("OCR done, text length: %d", len(combined_ocr_text))

    model_manager.release_ocr()
    return result


def main():
    parser = argparse.ArgumentParser(description="Medicine box OCR")
    parser.add_argument("--image", required=True, help="Path to medicine box image")
    parser.add_argument("--device", default="AUTO", help="OpenVINO device (CPU/GPU/AUTO)")
    parser.add_argument("--output", choices=["json", "text"], default="json",
                        help="Output format (default: json)")
    parser.add_argument("--enable-split", action="store_true", default=True,
                        help="Enable image splitting for OCR (default: True)")
    parser.add_argument("--no-split", dest="enable_split", action="store_false",
                        help="Disable image splitting")
    parser.add_argument("--num-splits", type=int, default=4,
                        help="Number of image splits (default: 4)")
    parser.add_argument("--ocr-max-tokens", type=int, default=5120,
                        help="OCR max new tokens (default: 5120)")
    args = parser.parse_args()

    result = run_ocr(
        image_path=args.image,
        device=args.device,
        enable_split=args.enable_split,
        num_splits=args.num_splits,
        ocr_max_new_tokens=args.ocr_max_tokens,
    )

    if args.output == "text":
        print(result["ocr_text"])
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
