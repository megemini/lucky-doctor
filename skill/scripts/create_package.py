#!/usr/bin/env python3
"""
create_package.py - Create a medicine data package (ZIP) for mobile app import.

Usage:
    python create_package.py --info recognition_result.json --audio audio.wav
                             [--output medicine_package.zip]

Package contents:
    metadata.json   - medicine info + keywords
    audio.wav       - TTS generated audio
"""

import argparse
import json
import logging
import sys
import uuid
import zipfile
from datetime import datetime
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("lucky_doctor")


def create_package(info_dict, audio_path, output_path):
    """Create a ZIP package with metadata.json and audio.wav."""
    audio_path = Path(audio_path)
    if not audio_path.exists():
        raise FileNotFoundError(f"Audio file not found: {audio_path}")

    metadata = {
        "id": str(uuid.uuid4()),
        "medicine_name": info_dict.get("medicine_name", ""),
        "generic_name": info_dict.get("generic_name", ""),
        "ingredients": info_dict.get("ingredients", []),
        "category": info_dict.get("category", ""),
        "function": info_dict.get("function", []),
        "manufacturer": info_dict.get("manufacturer", ""),
        "keywords": info_dict.get("keywords", []),
        "indications": info_dict.get("indications", ""),
        "contraindications": info_dict.get("contraindications", ""),
        "usage_summary": info_dict.get("usage_summary", ""),
        "created_at": datetime.now().strftime("%Y-%m-%d"),
        "speaker": info_dict.get("speaker", "vivian"),
        "language": info_dict.get("language", "chinese"),
        "version": 1,
    }

    # Create ZIP
    output_path = Path(output_path)
    with zipfile.ZipFile(output_path, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("metadata.json", json.dumps(metadata, ensure_ascii=False, indent=2))
        zf.write(audio_path, "audio.wav")

    logger.info("Package created: %s", output_path)
    logger.info("  - metadata.json (medicine: %s)", metadata["medicine_name"])
    logger.info("  - audio.wav (%s bytes)", audio_path.stat().st_size)
    return str(output_path.resolve())


def main():
    parser = argparse.ArgumentParser(description="Create medicine data package")
    parser.add_argument("--info", required=True,
                        help="Path to recognition result JSON file (or inline JSON)")
    parser.add_argument("--audio", required=True, help="Path to audio WAV file")
    parser.add_argument("--output", default=None,
                        help="Output ZIP path (default: medicine_package_<name>.zip)")
    args = parser.parse_args()

    # Load info
    info_path = Path(args.info)
    if info_path.exists():
        with open(info_path, "r", encoding="utf-8") as f:
            info_dict = json.load(f)
    else:
        # Try inline JSON
        info_dict = json.loads(args.info)

    # Default output name
    if args.output is None:
        name = info_dict.get("medicine_name", "unknown")
        name = name.replace(" ", "_").replace("/", "_")[:30]
        args.output = f"medicine_package_{name}.zip"

    result = create_package(info_dict, args.audio, args.output)
    print(json.dumps({"status": "success", "package_path": result}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
