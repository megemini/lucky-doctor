#!/usr/bin/env python3
"""
generate_audio.py - TTS speech synthesis for medicine instructions.

Usage:
    python generate_audio.py --text "药品说明文字" [--speaker vivian] [--language chinese]
                             [--output audio.wav] [--device AUTO]
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


def clean_for_tts(text):
    import re
    text = re.sub(
        r"[\U0001F600-\U0001F64F"
        r"\U0001F300-\U0001F5FF"
        r"\U0001F680-\U0001F6FF"
        r"\U0001F1E0-\U0001F1FF"
        r"\U00002702-\U000027B0"
        r"\U000024C2-\U0000324F"
        r"\U0001F200-\U0001F251"
        r"\U0001F900-\U0001F9FF"
        r"\U0001FA00-\U0001FA6F"
        r"\U0001FA70-\U0001FAFF"
        r"\U00002600-\U000026FF"
        r"\U0000FE00-\U0000FE0F"
        r"\U0000200D]+", "", text)
    text = re.sub(r"```.*?```", "", text, flags=re.DOTALL)
    text = re.sub(r"`([^`\n]+)`", r"\1", text)
    text = re.sub(r"^#{1,6}\s+", "", text, flags=re.MULTILINE)
    text = re.sub(r"\*\*([^*\n]+?)\*\*", r"\1", text)
    text = re.sub(r"__([^_\n]+?)__", r"\1", text)
    text = re.sub(r"\*([^*\n]+?)\*", r"\1", text)
    text = re.sub(r"(?<!\w)_([^_\n]+?)_(?!\w)", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", text)
    text = re.sub(r"^[-*_]{3,}\s*$", "", text, flags=re.MULTILINE)
    text = re.sub(r"^(\s*)[-*+]\s+", r"\1", text, flags=re.MULTILINE)
    text = re.sub(r"^(\s*)\d+\.\s+", r"\1", text, flags=re.MULTILINE)
    text = re.sub(r"\|", " ", text)
    text = re.sub(r"^[-: ]+$", "", text, flags=re.MULTILINE)
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(lines).strip()


def synthesize_audio(text, speaker="vivian", language="chinese",
                     instruct="用友好亲切的语气说话。",
                     max_new_tokens=2048, device="AUTO"):
    """Run TTS synthesis and return wav data + sample rate."""
    from model_manager import ModelManager

    cfg = pyenv.config_or_default()
    if not cfg.get("configured"):
        raise SystemExit(
            "Environment not configured. Run setup first:\n"
            "  <python> scripts/setup.py check   # inspect status\n"
            "  <python> scripts/setup.py install  # auto-configure\n"
            "  <python> scripts/setup.py --guided # step-by-step"
        )
    if not pyenv.is_model_ready(cfg, "tts"):
        raise SystemExit(
            "TTS model not found at:\n"
            f"  {pyenv.resolve_model_dir(cfg, 'tts')}\n"
            "Download it with:  <python> scripts/setup.py install"
        )
    model_manager = ModelManager(
        ocr_model_dir=str(pyenv.resolve_model_dir(cfg, "ocr")),
        tts_model_dir=str(pyenv.resolve_model_dir(cfg, "tts")),
        device=device,
    )

    cleaned = clean_for_tts(text)
    logger.info("TTS input length: %d chars", len(cleaned))

    tts_model = model_manager.get_tts_model()
    wavs, sr = tts_model.generate_custom_voice(
        text=cleaned,
        speaker=speaker,
        language=language,
        instruct=instruct,
        non_streaming_mode=True,
        max_new_tokens=max_new_tokens,
    )

    model_manager.release_tts()

    if wavs is not None:
        logger.info("TTS done, duration: %.2fs, sample rate: %d Hz", len(wavs[0]) / sr, sr)
        return wavs[0], sr

    logger.error("TTS synthesis failed")
    return None, None


def main():
    parser = argparse.ArgumentParser(description="Medicine TTS synthesis")
    parser.add_argument("--text", required=True, help="Text to synthesize")
    parser.add_argument("--text-file", help="Read text from file instead of --text")
    parser.add_argument("--speaker", default="vivian", help="Speaker name (default: vivian)")
    parser.add_argument("--language", default="chinese", help="Language (default: chinese)")
    parser.add_argument("--instruct", default="用友好亲切的语气说话。",
                        help="Style instruction for TTS")
    parser.add_argument("--output", default="audio.wav", help="Output WAV file path")
    parser.add_argument("--device", default="AUTO", help="OpenVINO device")
    parser.add_argument("--max-tokens", type=int, default=2048,
                        help="TTS max new tokens (default: 2048)")
    args = parser.parse_args()

    if args.text_file:
        with open(args.text_file, "r", encoding="utf-8") as f:
            text = f.read()
    else:
        text = args.text

    wav_data, sr = synthesize_audio(
        text=text,
        speaker=args.speaker,
        language=args.language,
        instruct=args.instruct,
        max_new_tokens=args.max_tokens,
        device=args.device,
    )

    if wav_data is not None:
        import numpy as np
        from scipy.io.wavfile import write as wav_write
        wav_write(args.output, sr, wav_data.astype(np.float32))
        print(json.dumps({
            "status": "success",
            "audio_path": str(Path(args.output).resolve()),
            "sample_rate": sr,
            "duration_seconds": len(wav_data) / sr,
        }, ensure_ascii=False, indent=2))
    else:
        print(json.dumps({"status": "error", "message": "TTS synthesis failed"}))
        sys.exit(1)


if __name__ == "__main__":
    main()
