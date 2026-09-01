"""
pyenv.py - Shared environment/configuration helpers for the Lucky Doctor skill.

This module centralizes:
  - Locating the skill directory
  - Loading / saving skill_config.json (persisted environment config)
  - Resolving model directories (config override or default relative path)
  - Ensuring the skill is configured before running heavy scripts

It is platform-aware and designed to be imported by the other scripts
(recognize.py, generate_audio.py, setup.py, ...). Requires no third-party
dependencies beyond the Python standard library.
"""

import json
import platform
import sys
from pathlib import Path

# Where this file lives: <skill>/scripts/pyenv.py
_SCRIPTS_DIR = Path(__file__).resolve().parent
SKILL_DIR = _SCRIPTS_DIR.parent

CONFIG_FILE = SKILL_DIR / "data" / "skill_config.json"
DEFAULT_MODEL_DIR = SKILL_DIR / "models"

# Dedicated, project-local virtualenv. All heavy deps/models go here so nothing
# is installed into the user's default/system Python environments.
VENV_DIR = SKILL_DIR / ".venv"

DEFAULT_MODELS = {
    "ocr": "PaddleOCR-VL-1.5-OpenVINO",
    "tts": "Qwen3-TTS-CustomVoice-0.6B-fp16-ov",
}

REQUIRED_DEPS = [
    "openvino",
    "transformers",
    "torch",
    "scipy",
    "PIL",
]

PLATFORM = sys.platform


def is_windows():
    return PLATFORM.startswith("win")


def platform_name():
    """Return a stable, lower-case platform string for the config."""
    if is_windows():
        return "windows"
    if PLATFORM == "darwin":
        return "macos"
    return "linux"


def python_exe_names():
    """Candidate executable names for a Python interpreter on this platform."""
    if is_windows():
        return ["python.exe", "python"]
    return ["python3", "python"]


def venv_python(venv_dir=None):
    """Return the Python interpreter path inside a virtualenv, per platform."""
    vd = Path(venv_dir) if venv_dir else VENV_DIR
    if is_windows():
        return vd / "Scripts" / "python.exe"
    return vd / "bin" / "python"


def read_config():
    """Load skill_config.json. Returns None if not present or invalid."""
    if not CONFIG_FILE.exists():
        return None
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        if not isinstance(data, dict):
            return None
        return data
    except (json.JSONDecodeError, OSError):
        return None


def write_config(config):
    """Persist skill_config.json (atomic-ish: write temp then rename)."""
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = CONFIG_FILE.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    tmp.replace(CONFIG_FILE)


def config_or_default():
    """Return the loaded config or a fresh 'not configured' dict."""
    cfg = read_config()
    if cfg is None:
        return {"configured": False, "platform": platform_name()}
    return cfg


def get_interpreter(cfg=None):
    """Return the configured Python interpreter path to run scripts with."""
    cfg = cfg if cfg is not None else config_or_default()
    python = cfg.get("python", {})
    return python.get("interpreter")


def resolve_model_dir(cfg, model_key):
    """
    Resolve the absolute directory for a model (ocr/tts).
    Prefers config override, falls back to default <skill>/models/<name>.
    """
    if cfg is None:
        cfg = config_or_default()
    override = cfg.get("models", {}).get(f"{model_key}_model_dir")
    if override:
        return Path(override)
    name = DEFAULT_MODELS.get(model_key, model_key)
    return DEFAULT_MODEL_DIR / name


def is_model_ready(cfg, model_key):
    """Return True if the model directory exists and looks non-empty."""
    if cfg is None:
        cfg = config_or_default()
    # In config we may cache readiness; but always verify on disk.
    model_dir = resolve_model_dir(cfg, model_key)
    if not model_dir.exists():
        return False
    # A model dir must contain at least the config + some binaries/xml.
    has_config = (model_dir / "config.json").exists()
    has_bin = any(model_dir.glob("*.bin")) if model_dir.exists() else False
    return has_config and has_bin


def deps_installed(interpreter=None):
    """
    Check whether the required Python dependencies are importable.
    If interpreter given, try importing via that interpreter; else current.
    Returns list of missing deps (empty == all good).
    """
    if interpreter is not None:
        # Probe using the target interpreter in a subprocess.
        import subprocess
        probe = (
            "import importlib.util,json;"
            "mods=['openvino','transformers','torch','scipy','PIL'];"
            "missing=[m for m in mods if importlib.util.find_spec(m) is None];"
            "print(json.dumps(missing))"
        )
        try:
            out = subprocess.run(
                [interpreter, "-c", probe],
                capture_output=True, text=True, timeout=60,
            )
            if out.returncode == 0 and out.stdout.strip():
                return json.loads(out.stdout.strip())
            # If probe failed to even run, treat all as missing.
            return list(REQUIRED_DEPS)
        except Exception:
            return list(REQUIRED_DEPS)

    missing = []
    for mod in REQUIRED_DEPS:
        try:
            __import__(mod)
        except ImportError:
            missing.append(mod)
    return missing


def summary():
    """Return a human-readable status dict for the Agent to inspect."""
    cfg = config_or_default()
    interp = get_interpreter(cfg)
    missing_deps = deps_installed(interp) if interp else deps_installed()
    return {
        "configured": bool(cfg.get("configured")),
        "platform": platform_name(),
        "venv": {
            "dir": str(VENV_DIR),
            "exists": VENV_DIR.exists(),
            "interpreter": str(venv_python()),
        },
        "python": {
            "interpreter": interp,
            "kind": cfg.get("python", {}).get("kind"),
            "activate_cmd": cfg.get("python", {}).get("activate_cmd"),
        },
        "deps_installed": len(missing_deps) == 0,
        "missing_deps": missing_deps,
        "models": {
            "ocr_ready": is_model_ready(cfg, "ocr"),
            "tts_ready": is_model_ready(cfg, "tts"),
            "ocr_model_dir": str(resolve_model_dir(cfg, "ocr")),
            "tts_model_dir": str(resolve_model_dir(cfg, "tts")),
        },
    }
