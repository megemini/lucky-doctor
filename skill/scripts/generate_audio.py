#!/usr/bin/env python3
"""
generate_audio.py - TTS speech synthesis for medicine instructions.

Usage:
    python generate_audio.py --text "药品说明文字" [--speaker vivian] [--language chinese]
                             [--output audio.wav] [--device AUTO] [--do-sample] [--float32]
    python generate_audio.py --text-file broadcast.txt --output audio.wav

Voice cloning (uses the Qwen3-TTS Base model). The Base model is the community
INT8 OpenVINO release `aurora2035/Qwen3-TTS-12Hz-0.6B-Base-OpenVINO-INT8` on
Hugging Face, fetched through the hf-mirror.com endpoint - a ready-made model
with the same layout as the CustomVoice one, so no conversion is involved. If it
is missing, `scripts/setup.py install` fetches it:
    python generate_audio.py --text-file broadcast.txt \
        --ref-audio ref.wav --ref-text "参考音频说的话" --output audio.wav

Notes:
    - `--text` and `--text-file` are mutually exclusive; exactly one is required.
    - `--ref-audio` switches to voice cloning: --speaker/--instruct are ignored.
      With --ref-text the audio is cloned in ICL mode (closer match); without it
      the clone falls back to speaker-embedding only (same as --x-vector-only).
    - Decoding is **greedy** by default (`do_sample=False`). Sampling on fp16
      OpenVINO models can emit nan/inf and produce silent or broken audio;
      pass `--do-sample` only when the more varied (less stable) output is wanted.
    - Output is 16-bit PCM WAV by default for maximum player compatibility
      (use `--float32` for the previous IEEE-float format).
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
                     max_new_tokens=2048, device="AUTO", do_sample=False,
                     ref_audio=None, ref_text=None, x_vector_only=False,
                     tts_base_dir=None):
    """Run TTS synthesis and return wav data + sample rate.

    do_sample=False (default) uses greedy decoding for both the talker and the
    sub-talker: deterministic output that avoids the nan/inf failures seen with
    fp16 OpenVINO models on CPU.

    Voice cloning: when ref_audio is given, the Qwen3-TTS **Base** model is used
    (--speaker/--instruct are ignored). ref_text enables ICL mode for a closer
    voice match; without it cloning uses speaker-embedding only.
    """
    from model_manager import ModelManager

    cfg = pyenv.config_or_default()
    if not cfg.get("configured"):
        raise SystemExit(
            "Environment not configured. Run setup first:\n"
            "  <python> scripts/setup.py check   # inspect status\n"
            "  <python> scripts/setup.py install  # auto-configure\n"
            "  <python> scripts/setup.py --guided # step-by-step"
        )

    cloning = bool(ref_audio)
    if cloning:
        base_dir = (Path(tts_base_dir).expanduser() if tts_base_dir
                    else pyenv.resolve_model_dir(cfg, "tts_base"))
        if not base_dir.exists():
            raise SystemExit(
                "Voice cloning needs the Qwen3-TTS **Base** model (the default "
                f"CustomVoice model cannot clone voices). Not found at:\n  {base_dir}\n"
                "It is downloaded from Hugging Face (via hf-mirror) as a ready-made "
                "INT8 OpenVINO release - run:\n"
                "  <python> scripts/setup.py install\n"
                "Or drop --ref-audio to use a built-in speaker."
            )
    else:
        base_dir = pyenv.resolve_model_dir(cfg, "tts")
        if not pyenv.is_model_ready(cfg, "tts"):
            raise SystemExit(
                "TTS model not found at:\n"
                f"  {base_dir}\n"
                "Download it with:  <python> scripts/setup.py install"
            )

    model_manager = ModelManager(
        ocr_model_dir=str(pyenv.resolve_model_dir(cfg, "ocr")),
        tts_model_dir=str(base_dir),
        device=device,
    )

    cleaned = clean_for_tts(text)
    logger.info("TTS input length: %d chars", len(cleaned))

    tts_model = model_manager.get_tts_model()
    if cloning:
        xvec_only = bool(x_vector_only or not (ref_text or "").strip())
        if xvec_only and not x_vector_only:
            logger.warning(
                "No --ref-text provided: falling back to speaker-embedding-only "
                "cloning (x_vector_only_mode=True). For a closer match, pass the "
                "transcript of the reference audio with --ref-text."
            )
        logger.info("Voice cloning from %s (%s mode)",
                    ref_audio, "x-vector" if xvec_only else "ICL")
        wavs, sr = tts_model.generate_voice_clone(
            text=cleaned,
            language=language,
            ref_audio=ref_audio,
            ref_text=None if xvec_only else ref_text,
            x_vector_only_mode=xvec_only,
            non_streaming_mode=True,
            max_new_tokens=max_new_tokens,
            do_sample=do_sample,
            subtalker_dosample=do_sample,
        )
    else:
        wavs, sr = tts_model.generate_custom_voice(
            text=cleaned,
            speaker=speaker,
            language=language,
            instruct=instruct,
            non_streaming_mode=True,
            max_new_tokens=max_new_tokens,
            do_sample=do_sample,
            subtalker_dosample=do_sample,
        )

    model_manager.release_tts()

    if wavs is not None:
        logger.info("TTS done, duration: %.2fs, sample rate: %d Hz", len(wavs[0]) / sr, sr)
        return wavs[0], sr

    logger.error("TTS synthesis failed")
    return None, None


def sanitize_audio(wav_data):
    """Drop non-finite samples, guard clipping, and warn about silent output.

    Returns a float32 1-D array, or None if the waveform is unusable.
    """
    import numpy as np

    wav = np.asarray(wav_data, dtype=np.float32).reshape(-1)
    if wav.size == 0:
        logger.error("TTS returned an empty waveform")
        return None

    if not np.isfinite(wav).all():
        bad = int(np.count_nonzero(~np.isfinite(wav)))
        logger.warning(
            "TTS output contains %d non-finite sample(s) (nan/inf) - replaced with 0. "
            "If audio is still broken, keep the default greedy decoding or try --device CPU.",
            bad,
        )
        wav = np.nan_to_num(wav, nan=0.0, posinf=0.0, neginf=0.0)

    peak = float(np.max(np.abs(wav)))
    if peak == 0.0:
        logger.warning(
            "TTS produced digital silence (peak=0). This usually means decoding collapsed "
            "(e.g. nan/inf with an fp16 model); try --device CPU or another --speaker."
        )
    elif peak > 0.99:
        wav = wav * (0.99 / peak)
        logger.info("Scaled output down to avoid clipping (peak was %.3f).", peak)
    elif peak < 0.05:
        wav = wav * (0.9 / peak)
        logger.warning(
            "TTS output was very quiet (peak=%.4f) - amplified to 0.9. "
            "If it sounds wrong, try --device CPU.",
            peak,
        )
    return wav


def write_wav(path, sample_rate, wav, as_float32=False):
    """Write WAV: 16-bit PCM by default (widest support), IEEE float on request."""
    import numpy as np
    from scipy.io.wavfile import write as wav_write

    if as_float32:
        wav_write(path, sample_rate, wav.astype(np.float32))
    else:
        wav_write(path, sample_rate, (np.clip(wav, -1.0, 1.0) * 32767.0).astype(np.int16))


def main():
    parser = argparse.ArgumentParser(description="Medicine TTS synthesis")
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--text", help="Text to synthesize")
    source.add_argument("--text-file", help="Read text from a UTF-8 file instead of --text")
    parser.add_argument("--speaker", default="vivian", help="Speaker name (default: vivian)")
    parser.add_argument("--language", default="chinese", help="Language (default: chinese)")
    parser.add_argument("--instruct", default="用友好亲切的语气说话。",
                        help="Style instruction for TTS")
    parser.add_argument("--output", default="audio.wav", help="Output WAV file path")
    parser.add_argument("--device", default="AUTO", help="OpenVINO device")
    parser.add_argument("--do-sample", dest="do_sample", action="store_true",
                        help="Enable sampling (temperature/top-p). Default is greedy decoding, "
                             "which avoids nan/inf failures of fp16 models on CPU")
    parser.add_argument("--float32", action="store_true",
                        help="Write 32-bit float WAV instead of the default 16-bit PCM")
    parser.add_argument("--max-tokens", type=int, default=2048,
                        help="TTS max new tokens (default: 2048)")
    parser.add_argument("--ref-audio",
                        help="Reference audio for voice cloning (wav/mp3/etc). Needs the "
                             "Qwen3-TTS Base model - a ready-made INT8 OpenVINO release "
                             "downloaded from Hugging Face via hf-mirror "
                             "(missing models are fetched by scripts/setup.py install)")
    parser.add_argument("--ref-text",
                        help="Transcript of the reference audio (ICL mode; closer voice match)")
    parser.add_argument("--x-vector-only", action="store_true",
                        help="Clone the timbre only, ignoring --ref-text "
                             "(this is the default when --ref-text is omitted)")
    parser.add_argument("--tts-base-dir",
                        help="Override the Qwen3-TTS Base model directory used for voice cloning")
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
        do_sample=args.do_sample,
        ref_audio=args.ref_audio,
        ref_text=args.ref_text,
        x_vector_only=args.x_vector_only,
        tts_base_dir=args.tts_base_dir,
    )

    if wav_data is not None:
        wav_data = sanitize_audio(wav_data)

    if wav_data is not None:
        write_wav(args.output, sr, wav_data, as_float32=args.float32)
        print(json.dumps({
            "status": "success",
            "audio_path": str(Path(args.output).resolve()),
            "sample_rate": sr,
            "duration_seconds": len(wav_data) / sr,
            "sample_format": "float32" if args.float32 else "int16",
        }, ensure_ascii=False, indent=2))
    else:
        print(json.dumps({"status": "error", "message": "TTS synthesis failed"}))
        sys.exit(1)


if __name__ == "__main__":
    main()
