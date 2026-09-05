"""
setup.py - Environment detection, check, and configuration for the Lucky Doctor skill.

Cross-platform: works on Windows / macOS / Linux.

By default, all dependencies are installed into a dedicated, project-local
virtualenv (skill/.venv) created here -- nothing is installed into the user's
default/system Python environments. Use --no-venv to reuse an existing env, or
--venv <dir> to choose a different venv location.

Usage:
  <python> scripts/setup.py check
      Read-only status report (JSON) for the Agent to decide next steps.

  <python> scripts/setup.py install [--auto-python] [--no-deps] [--no-models]
                                   [--venv <dir>] [--no-venv]
      Non-interactive setup. Creates/uses a dedicated project venv, installs
      dependencies, downloads missing models, writes skill/data/skill_config.json.

  <python> scripts/setup.py --guided
      Interactive guided setup. Walks through each step, asking the user to
      confirm before acting. Output is designed to be relayed by the Agent.
"""

import argparse
import datetime
import json
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pyenv

# model_key -> (source, remote repo id, local directory name).
#   source "modelscope"  -> modelscope.cn
#   source "huggingface" -> huggingface.co, fetched through the hf-mirror.com
#                           endpoint (set inside the download snippet).
# ocr / tts are ready-made OpenVINO models published on ModelScope. tts_base
# (voice cloning) uses the community INT8 OpenVINO release `aurora2035/...`,
# whose file layout is identical to the snake7gun CustomVoice model the helper
# was written against - no local conversion is ever needed.
MODEL_SPECS = {
    "ocr": ("modelscope", "megemini/PaddleOCR-VL-1.5-OpenVINO",
            "PaddleOCR-VL-1.5-OpenVINO"),
    "tts": ("modelscope", "snake7gun/Qwen3-TTS-CustomVoice-0.6B-fp16-ov",
            "Qwen3-TTS-CustomVoice-0.6B-fp16-ov"),
    "tts_base": ("huggingface",
                 "aurora2035/Qwen3-TTS-12Hz-0.6B-Base-OpenVINO-INT8",
                 "Qwen3-TTS-Base-0.6B-OpenVINO-INT8"),
}

CONDA_ENV_PATTERNS = ["~/.venvs", "~/.virtualenvs", ".venv"]

# Parameters are passed as JSON to stay quoting-safe on every platform.
# modelscope >= 1.30 no longer ships a `python -m modelscope` entry point,
# so models are fetched through the Python API (works on old and new releases).
MODEL_DOWNLOAD_SNIPPETS = {
    "modelscope": (
        "import json, sys\n"
        "spec = json.loads(sys.argv[1])\n"
        "try:\n"
        "    from modelscope import snapshot_download\n"
        "except ImportError:  # older modelscope releases\n"
        "    from modelscope.hub.snapshot_download import snapshot_download\n"
        "snapshot_download(model_id=spec['repo'], local_dir=spec['local_dir'])\n"
    ),
    # Hugging Face downloads go through the hf-mirror.com endpoint, which is
    # reachable in mainland China without extra proxy configuration.
    "huggingface": (
        "import json, os, sys\n"
        "spec = json.loads(sys.argv[1])\n"
        "os.environ.setdefault('HF_ENDPOINT', 'https://hf-mirror.com')\n"
        "from huggingface_hub import snapshot_download\n"
        "snapshot_download(repo_id=spec['repo'], local_dir=spec['local_dir'])\n"
    ),
}


def run(cmd, cwd=None, env=None):
    """Run a command, return (returncode, stdout_text)."""
    try:
        proc = subprocess.run(
            cmd, cwd=cwd, env=env, capture_output=True, text=True,
            timeout=1800,
        )
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except FileNotFoundError:
        return 127, f"command not found: {cmd}"
    except subprocess.TimeoutExpired:
        return 124, "command timed out"


def detect_conda_bases():
    """Return list of (name, python_path, 'conda') by parsing `conda env list`."""
    conda = shutil.which("conda") or shutil.which("conda.bat")
    if not conda:
        return []
    code, out = run([conda, "env", "list", "--json"])
    if code != 0:
        return []
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return []
    results = []
    for env_info in data.get("envs", []):
        base = Path(env_info)
        if pyenv.is_windows():
            py = base / "python.exe"
        else:
            py = base / "bin" / "python"
        if py.exists():
            results.append((base.name if base.name != "base" else "conda-base",
                            str(py), "conda"))
    return results


def detect_venv_bases():
    """Scan common venv locations for python interpreters."""
    results = []
    candidates = []
    home = Path.home()
    for pat in CONDA_ENV_PATTERNS:
        expanded = pat.replace("~", str(home))
        p = Path(expanded).expanduser()
        if p.exists():
            candidates.append(p)
    for base_dir in candidates:
        if not base_dir.is_dir():
            continue
        for sub in base_dir.iterdir():
            if pyenv.is_windows():
                py = sub / "Scripts" / "python.exe"
            else:
                py = sub / "bin" / "python"
            if py.exists():
                results.append((sub.name, str(py), "venv"))
    return results


def detect_system_python():
    """Return (name, python_path, 'system') for a system python if present."""
    for exe in pyenv.python_exe_names():
        found = shutil.which(exe)
        if found:
            return (f"system-{exe}", found, "system")
    return None


def build_environment_candidates():
    """Return ordered list of (name, py_path, kind)."""
    candidates = []
    candidates.extend(detect_conda_bases())
    candidates.extend(detect_venv_bases())
    sys_py = detect_system_python()
    if sys_py:
        candidates.append(sys_py)
    return candidates


def pick_best(candidates):
    """
    Choose the best candidate: prefer one already having most deps,
    then conda, then venv, then system.
    """
    if not candidates:
        return None
    scored = []
    for name, py, kind in candidates:
        missing = pyenv.deps_installed(py)
        score = len(pyenv.REQUIRED_DEPS) - len(missing)
        order = {"conda": 3, "venv": 2, "system": 1}.get(kind, 0)
        scored.append((score, order, name, py, kind))
    scored.sort(key=lambda x: (-x[0], -x[1], x[2]))
    return scored[0][2:]


def make_activate_cmd(py_path, kind):
    """Build a shell activation command for the interpreter (None on Windows)."""
    if pyenv.is_windows():
        return None
    base = Path(py_path).parent
    if kind != "system":
        # py at <venv>/bin/python -> venv root is parent.parent
        venv_root = base.parent
        return f"source {venv_root / 'bin' / 'activate'}"
    return None


def create_project_venv(venv_dir, guided=False):
    """
    Create a dedicated, project-local virtualenv using the running interpreter
    as base. Returns (interpreter_path, kind) or (None, None) on failure/cancel.
    """
    venv_dir = Path(venv_dir)
    base_py = sys.executable or shutil.which("python")
    if not base_py:
        print("cannot find a base Python to create the venv")
        return None, None
    print(f"creating dedicated project venv:\n    {venv_dir}\n"
          f"  (base python: {base_py})")
    if guided:
        if input("  Confirm create this venv? [Y/n] ").strip().lower() not in ("", "y", "yes"):
            print("  cancelled by user")
            return None, None
    code, out = run([base_py, "-m", "venv", str(venv_dir)])
    if code != 0:
        print(f"  venv creation FAILED (exit {code}):\n{out[-2000:]}")
        return None, None
    vpy = pyenv.venv_python(venv_dir)
    if not vpy.exists():
        print(f"  venv created but no interpreter found at {vpy}")
        return None, None
    print(f"  venv ready: {vpy}")
    return str(vpy), "venv(project)"


def select_environment(args, guided=False):
    """
    Decide which Python interpreter to use.

    Default: a dedicated project-local venv at skill/.venv (created on first
    run, reused afterwards) -- so nothing is installed into the user's default
    or system Python. Pass --no-venv to fall back to detected existing envs,
    or --venv <dir> to choose a different venv location.
    """
    cfg = pyenv.config_or_default()

    # 1) Non-guided, config already exists, not forcing re-detect -> keep it.
    if not guided and not args.auto_python and cfg.get("python", {}).get("interpreter"):
        interp = cfg["python"]["interpreter"]
        kind = cfg["python"].get("kind", "unknown")
        if Path(interp).exists():
            print(f"reusing configured interpreter: {interp}")
            return interp, kind
        print(f"configured interpreter missing ({interp}); re-detecting...")

    candidates = build_environment_candidates()

    # 2) Default path: dedicated project venv.
    if not args.no_venv:
        venv_dir = Path(args.venv) if args.venv else pyenv.VENV_DIR
        vpy = pyenv.venv_python(venv_dir)
        if vpy.exists():
            print(f"reusing dedicated project venv: {venv_dir}")
            return str(vpy), "venv(project)"
        if guided:
            # Present venv creation + existing envs as a numbered list.
            print("Select a Python environment:")
            print(f"  [0] create dedicated project venv ({venv_dir}) [recommended]")
            for i, (name, py, kind) in enumerate(candidates, start=1):
                missing = len(pyenv.deps_installed(py))
                print(f"  [{i}] use existing {name} ({kind}) -> {py} "
                      f"[missing {missing} dep(s)]")
            choice = input("Pick index, or press Enter for [0]: ").strip()
            if not choice or choice == "0":
                interp, kind = create_project_venv(venv_dir, guided=True)
                if interp:
                    return interp, kind
                print("  venv skipped; falling back to existing envs...")
            elif choice.isdigit() and 0 < int(choice) <= len(candidates):
                _, interp, kind = candidates[int(choice) - 1]
                return interp, kind
            else:
                best = pick_best(candidates)
                if best:
                    _, interp, kind = best
                    print(f"auto-selected: {interp} ({kind})")
                    return interp, kind
            print("No environment selected; nothing to configure.")
            return None, None
        interp, kind = create_project_venv(venv_dir, guided=False)
        if interp:
            return interp, kind
        print("venv creation failed; falling back to detected environments...")

    # 3) Fallback: reuse an existing environment.
    if not candidates:
        print("No Python environment found. Install Python first.")
        return None, None
    picked = pick_best(candidates)
    if not picked:
        print("No usable Python environment found.")
        return None, None
    _, interp, kind = picked
    print(f"selected existing interpreter: {interp} ({kind})")
    return interp, kind


def install_dependencies(interpreter, guided=False):
    """Install requirements for the target interpreter. Returns bool."""
    req = pyenv.SKILL_DIR / "requirements.txt"
    cmd = [interpreter, "-m", "pip", "install", "-r", str(req)]
    if guided:
        print(f"  [step] will run:\n    {' '.join(cmd)}")
        if input("  Confirm install dependencies? [y/N] ").strip().lower() != "y":
            print("  skipped by user")
            return False
    print(f"  installing dependencies with {interpreter} ...")
    code, out = run(cmd)
    if code != 0:
        print(f"  dependency install FAILED (exit {code}):\n{out[-2000:]}")
        return False
    print("  dependencies installed.")
    return True


def download_model(interpreter, model_key, guided=False):
    """Download a single model via ModelScope or HuggingFace. Returns bool."""
    source, repo, local_name = MODEL_SPECS[model_key]
    dest = pyenv.resolve_model_dir(pyenv.config_or_default(), model_key)
    cmd = [interpreter, "-c", MODEL_DOWNLOAD_SNIPPETS[source],
           json.dumps({"repo": repo, "local_dir": str(dest)})]
    source_label = "HuggingFace (hf-mirror)" if source == "huggingface" else "ModelScope"
    if guided:
        print(f"  [step] downloading {model_key} model from {source_label}: {repo}\n"
              f"    to {dest}")
        if input("  Confirm download? [y/N] ").strip().lower() != "y":
            print("  skipped by user")
            return False
    print(f"  downloading {model_key} model ({source_label}) ...")
    code, out = run(cmd)
    if code != 0:
        print(f"  {model_key} download FAILED (exit {code}):\n{out[-2000:]}")
        return False
    print(f"  {model_key} model ready.")
    return True


def cmd_check():
    status = pyenv.summary()
    print(json.dumps(status, ensure_ascii=False, indent=2))


def cmd_install(args, guided=False):
    cfg = pyenv.config_or_default()
    interpreter, kind = select_environment(args, guided=guided)
    if interpreter is None:
        return 1

    activate_cmd = make_activate_cmd(interpreter, kind)

    deps_ok = len(pyenv.deps_installed(interpreter)) == 0
    if not deps_ok and not args.no_deps:
        deps_ok = install_dependencies(interpreter, guided=guided)
    elif deps_ok:
        print("dependencies already satisfied.")

    models_ok = {"ocr": False, "tts": False, "tts_base": False}
    if not args.no_models:
        for key in models_ok:
            if pyenv.is_model_ready(cfg, key):
                models_ok[key] = True
                print(f"{key} model already present.")
            else:
                models_ok[key] = download_model(interpreter, key, guided=guided)
    else:
        print("model download skipped per flag.")

    new_cfg = {
        "configured": True,
        "config_version": 1,
        "platform": pyenv.platform_name(),
        "python": {
            "interpreter": interpreter,
            "kind": kind,
            "activate_cmd": activate_cmd,
        },
        "dependencies_installed": deps_ok,
        "models": {
            "ocr_model_dir": str(pyenv.resolve_model_dir(cfg, "ocr")),
            "tts_model_dir": str(pyenv.resolve_model_dir(cfg, "tts")),
            "tts_base_model_dir": str(pyenv.resolve_model_dir(cfg, "tts_base")),
            "ocr_ready": models_ok["ocr"],
            "tts_ready": models_ok["tts"],
            "tts_base_ready": models_ok["tts_base"],
        },
        "configured_at": datetime.datetime.now().strftime("%Y-%m-%d"),
    }
    pyenv.write_config(new_cfg)
    print("configuration saved to " + str(pyenv.CONFIG_FILE))
    return 0


def cmd_guided():
    print("=== Lucky Doctor guided setup ===")
    print("I will walk through each step. You confirm each one.")
    print("Detecting Python environments...\n")
    return cmd_install(args, guided=True)


def main():
    parser = argparse.ArgumentParser(description="Lucky Doctor environment setup")
    parser.add_argument("--guided", action="store_true",
                        help="interactive guided setup")
    sub = parser.add_subparsers(dest="command")
    sub.add_parser("check", help="report environment status (JSON)")
    inst = sub.add_parser("install", help="configure environment non-interactively")
    inst.add_argument("--auto-python", action="store_true",
                      help="re-detect python even if a config exists")
    inst.add_argument("--no-deps", action="store_true",
                      help="skip dependency installation")
    inst.add_argument("--no-models", action="store_true",
                      help="skip model downloads")
    inst.add_argument("--venv", help="path for the dedicated venv (default: skill/.venv)")
    inst.add_argument("--no-venv", action="store_true",
                      help="do not create a venv; reuse a detected existing env")
    # Allow the same flags globally so --guided --no-deps works.
    parser.add_argument("--auto-python", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--no-deps", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--no-models", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--venv", help=argparse.SUPPRESS)
    parser.add_argument("--no-venv", action="store_true", help=argparse.SUPPRESS)
    global args
    args = parser.parse_args()

    if args.guided:
        sys.exit(cmd_guided())
    if args.command == "check":
        cmd_check()
    elif args.command == "install":
        sys.exit(cmd_install(args))
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()