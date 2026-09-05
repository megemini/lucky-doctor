#!/usr/bin/env python3
"""
convert_tts_base.py - Convert the Qwen3-TTS **Base** model to OpenVINO IR.

What this is / who runs it:
    This is a PROJECT-LEVEL, one-off tool for the model publisher. The
    converted result is meant to be uploaded to ModelScope (or any model hub)
    so that the Lucky Doctor skill - and any other user - can simply download
    the ready-made OpenVINO model like any other model. The skill itself does
    NOT run or reference any conversion logic.

    It intentionally does NOT depend on the skill codebase in any way. Only the
    public packages in model-convert/requirements.txt are needed.

Usage (inside a Python env created from model-convert/requirements.txt):

    # A) Convert an already-downloaded Qwen3-TTS Base checkpoint directory:
    python convert_tts_base.py --model-id <local_ckpt_dir>

    # B) Download + convert from HuggingFace:
    python convert_tts_base.py

    # C) Download + convert from ModelScope (recommended in mainland China):
    python convert_tts_base.py --source modelscope

    # Custom output location / force re-conversion:
    python convert_tts_base.py --output-dir <dir> [--force]

What it produces (<output-dir>, default ./Qwen3-TTS-12Hz-0.6B-Base-OpenVINO):
    config.json, processor files,
    openvino_talker_*.xml/.bin, openvino_speaker_encoder_model.xml/.bin,
    speech_tokenizer/openvino_speech_tokenizer_{encoder,decoder}_model.{xml,bin}

After conversion, upload every file of <output-dir> to the model repo root
(e.g. ModelScope repo "megemini/Qwen3-TTS-12Hz-0.6B-Base-OpenVINO"). Consumers
then download the repo as-is and point their model dir at it.
"""

import argparse
import shutil
import sys
from pathlib import Path

DEFAULT_MODEL_ID = "Qwen/Qwen3-TTS-12Hz-0.6B-Base"

# Artifacts produced for a Base model. The speaker encoder is Base-only and is
# what makes voice cloning possible.
BASE_REQUIRED_FILES = [
    "config.json",
    "openvino_talker_language_model.xml",
    "openvino_talker_embedding_model.xml",
    "openvino_talker_text_embedding_model.xml",
    "openvino_talker_text_projection_model.xml",
    "openvino_talker_code_predictor_model.xml",
    "openvino_talker_code_predictor_embedding_model.xml",
    "openvino_speaker_encoder_model.xml",
]

# The reference audio must be encoded by the speech tokenizer before it can be
# used as a cloning prompt.
TOKENIZER_FILES = [
    "openvino_speech_tokenizer_encoder_model.xml",
    "openvino_speech_tokenizer_decoder_model.xml",
]


def base_model_ready(dest):
    return all((dest / f).exists() for f in BASE_REQUIRED_FILES)


def tokenizer_ready(dest):
    tok = dest / "speech_tokenizer"
    return all((tok / f).exists() for f in TOKENIZER_FILES)


def download_checkpoint(model_id, ckpt_dir, source):
    """Download the raw checkpoint (HuggingFace or ModelScope) to ckpt_dir."""
    ckpt_dir = Path(ckpt_dir)
    if ckpt_dir.exists():
        shutil.rmtree(ckpt_dir)
    ckpt_dir.mkdir(parents=True, exist_ok=True)
    if source == "hf":
        print(f"⬇  Downloading {model_id} from HuggingFace Hub -> {ckpt_dir}")
        from huggingface_hub import snapshot_download

        snapshot_download(model_id=model_id, local_dir=ckpt_dir)
    else:
        print(f"⬇  Downloading {model_id} from ModelScope -> {ckpt_dir}")
        from modelscope import snapshot_download

        snapshot_download(model_id=model_id, local_dir=str(ckpt_dir))
    return ckpt_dir


def clean_converted(dest):
    removed = 0
    for pattern in ("openvino_*.xml", "openvino_*.bin"):
        for f in dest.glob(pattern):
            if f.is_file():
                f.unlink()
                removed += 1
    tok = dest / "speech_tokenizer"
    if tok.exists():
        shutil.rmtree(tok)
        removed += 1
    if removed:
        print(f"Removed {removed} previous OpenVINO artifact(s) (--force)")


def ensure_dependencies():
    missing = []
    for mod in ("openvino", "torch", "qwen_tts", "transformers"):
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    if missing:
        sys.exit(
            "Missing conversion dependencies: " + ", ".join(missing) + "\n"
            "Install them first, e.g.:\n"
            "    python -m pip install -r model-convert/requirements.txt"
        )


def main():
    parser = argparse.ArgumentParser(
        description="ONE-TIME conversion of the Qwen3-TTS Base model to OpenVINO IR "
                    "(for publishing; consumers download the ready model instead). "
                    "See README.md in this folder."
    )
    parser.add_argument(
        "--model-id",
        default=DEFAULT_MODEL_ID,
        help="HuggingFace/ModelScope model id or a local checkpoint directory "
             "(default: %(default)s). Local directories are used directly.",
    )
    parser.add_argument(
        "--source",
        choices=["hf", "modelscope"],
        default="hf",
        help="Where to fetch the raw checkpoint from when --model-id is not a "
             "local directory (default: hf). Use 'modelscope' for faster access "
             "in mainland China.",
    )
    parser.add_argument(
        "--output-dir",
        default="Qwen3-TTS-12Hz-0.6B-Base-OpenVINO",
        help="Output directory for the converted OpenVINO model "
             "(default: %(default)s under the current directory).",
    )
    parser.add_argument(
        "--ckpt-dir",
        default=None,
        help="Where to store the downloaded raw checkpoint "
             "(default: <output-dir>/../Qwen3-TTS-12Hz-0.6B-Base-src).",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-convert even if a converted model already exists in --output-dir.",
    )
    args = parser.parse_args()

    ensure_dependencies()

    import qwen3_tts_ov_converter as converter

    dest = Path(args.output_dir).expanduser().resolve()
    dest.mkdir(parents=True, exist_ok=True)

    def resolve_checkpoint():
        """Return the local raw checkpoint dir (download it when needed)."""
        ckpt = Path(args.model_id).expanduser()
        if ckpt.is_dir():
            print(f"Using local checkpoint: {ckpt.resolve()}")
            return ckpt.resolve()
        ckpt_dir = Path(args.ckpt_dir) if args.ckpt_dir else (
            dest.parent / "Qwen3-TTS-12Hz-0.6B-Base-src")
        return download_checkpoint(args.model_id, ckpt_dir, args.source)

    already_done = base_model_ready(dest) and not args.force

    if already_done and tokenizer_ready(dest):
        print(f"✅ Base model already converted at {dest}")
        print("   Speech tokenizer present. Nothing to do.")
        return

    if args.force:
        clean_converted(dest)

    local_ckpt = resolve_checkpoint()

    if already_done:
        # Core model is ready; only the speech tokenizer is missing.
        print("ℹ️  Base model already converted; finishing the speech tokenizer...")
    else:
        print(f"⌛ Converting {local_ckpt} -> {dest} (may take a while)...")
        converter.convert_qwen3_tts_model(
            model_id=str(local_ckpt),
            output_dir=str(dest),
            use_local_dir=False,
        )

    if not tokenizer_ready(dest):
        src_tokenizer = local_ckpt / "speech_tokenizer"
        if (src_tokenizer / TOKENIZER_FILES[0]).exists():
            print(f"⌛ Converting speech tokenizer ({src_tokenizer})...")
            converter.convert_speech_tokenizer(
                model_id=str(src_tokenizer),
                output_dir=str(dest / "speech_tokenizer"),
                use_local_dir=False,
            )
        else:
            print(f"⚠️  No speech_tokenizer/ found in {local_ckpt} either; skipping.")

    if base_model_ready(dest):
        tok_state = tokenizer_ready(dest)
        print("✅ Conversion finished. Base model ready at:", dest)
        print("   Speech tokenizer:", "present" if tok_state else "MISSING")
        if not tok_state:
            print("⚠️  The Base checkpoint had no speech_tokenizer/ directory.")
            print("   Voice cloning needs it - publish without it will still work for")
            print("   a cloned-voice pipeline only if consumers supply their own.")
    else:
        print("❌ Conversion finished but some expected files are missing in", dest)
        sys.exit(1)

    print()
    print("=" * 70)
    print("Next steps for the publisher (this is a ONE-TIME job):")
    print("  1. Upload every file under the output dir to the model repo root,")
    print("     e.g. ModelScope repo:  megemini/Qwen3-TTS-12Hz-0.6B-Base-OpenVINO")
    print("  2. Web upload is easiest (drag the folder contents into the repo).")
    print("     Programmatic upload (after 'modelscope login'):")
    print("         python -c 'from modelscope import HubApi; HubApi().push_model(")
    print(f"             model_id=\"megemini/Qwen3-TTS-12Hz-0.6B-Base-OpenVINO\", local_dir=\"{dest}\")'")
    print("  3. Consumers just download that repo (snapshot_download) and point")
    print("     their model dir at it - no conversion on their side at all.")
    print("=" * 70)


if __name__ == "__main__":
    main()
