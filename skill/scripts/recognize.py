#!/usr/bin/env python3
"""
recognize.py - Medicine box / instruction leaflet OCR.

Usage:
    python recognize.py --image <path> [--device AUTO] [--output json|text]

Steps:
    1. OCR (PaddleOCR-VL) - extract text from the FULL image directly
    2. Output OCR text for the agent to summarize

Note:
    The image is NOT split into tiles: the whole image is sent to the model
    as-is for a single pass. Structured medicine info extraction, summary
    writing, and keyword generation are done by the AGENT (not by a VLM
    model). This script only produces the raw OCR text plus the image path.
"""

import argparse
import json
import logging
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


def run_ocr(image_path, device="AUTO", ocr_max_new_tokens=5120):
    """Run OCR-only recognition on the full image.

    Returns dict with ocr_text and image_path.
    """
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

    ocr_model = model_manager.get_ocr_model()
    logger.info("Running OCR on the full image (single pass)...")
    ocr_text = ocr_image(ocr_model, image, max_new_tokens=ocr_max_new_tokens)

    result["ocr_text"] = ocr_text
    result["image_path"] = str(Path(image_path).resolve())
    logger.info("OCR done, text length: %d", len(ocr_text))

    model_manager.release_ocr()
    return result


def main():
    parser = argparse.ArgumentParser(description="Medicine box OCR")
    parser.add_argument("--image", required=True, help="Path to medicine box image")
    parser.add_argument("--device", default="AUTO", help="OpenVINO device (CPU/GPU/AUTO)")
    parser.add_argument("--output", choices=["json", "text"], default="json",
                        help="Output format (default: json)")
    parser.add_argument("--ocr-max-tokens", type=int, default=5120,
                        help="OCR max new tokens (default: 5120)")
    args = parser.parse_args()

    result = run_ocr(
        image_path=args.image,
        device=args.device,
        ocr_max_new_tokens=args.ocr_max_tokens,
    )

    if args.output == "text":
        print(result["ocr_text"])
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
