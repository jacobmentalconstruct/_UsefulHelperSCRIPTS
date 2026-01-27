#!/usr/bin/env python3
"""
_HelperScriptExeMAKER.py

Monolithic CLI tool to build a Windows .exe for one of your UsefulHelper projects.

Design goals:
- Point at a project root folder (contains src/app.py or src/app.pyw).
- Produce a shareable executable bundle into a destination folder.
- Be deterministic: emits a build report and logs.

Default behavior:
- Build mode: onedir (more reliable with assets/data).
- Uses per-project build venv: <project_root>/.build_venv
- Installs dependencies from requirements.txt if present.
- Includes assets/ folder if present via --add-data.

Later evolution:
- Wrap this into your microservice pattern.
- Add a Tkinter UI that shells out to this CLI (thin wrapper).
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, List, Tuple


# ----------------------------
# Utilities
# ----------------------------

def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime())

def eprint(*args):
    print(*args, file=sys.stderr)

def run(cmd: List[str], cwd: Optional[Path] = None, env: Optional[dict] = None) -> str:
    """Run a command, streaming combined stdout/stderr, and return full combined output.

    Why:
      - PyInstaller (and pip) often fail with the *real* reason only in stdout/stderr.
      - UI mode needs the text captured so it can be displayed.

    On failure:
      - Raises subprocess.CalledProcessError with .output containing the combined output.
    """
    print(f"\n[RUN] {' '.join(cmd)}")

    proc = subprocess.Popen(
        cmd,
        cwd=str(cwd) if cwd else None,
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    assert proc.stdout is not None
    buf: List[str] = []

    # Stream live output (helps in CLI usage) while also capturing for UI/reporting.
    for line in proc.stdout:
        buf.append(line)
        print(line, end="")

    rc = proc.wait()
    out = "".join(buf)

    if rc != 0:
        raise subprocess.CalledProcessError(rc, cmd, output=out)

    return out

def safe_mkdir(p: Path) -> None:
    p.mkdir(parents=True, exist_ok=True)

def is_windows() -> bool:
    return os.name == "nt"


# ----------------------------
# Configuration / Detection
# ----------------------------

@dataclass
class ProjectInfo:
    project_root: Path
    name: str
    entrypoint: Path
    gui: bool
    requirements: Optional[Path]
    assets_dir: Optional[Path]


def detect_project(project_root: Path) -> ProjectInfo:
    if not project_root.exists() or not project_root.is_dir():
        raise FileNotFoundError(f"Project root not found or not a directory: {project_root}")

    src_dir = project_root / "src"
    if not src_dir.exists():
        raise FileNotFoundError(f"Expected 'src' folder not found in: {project_root}")

    entry_pyW = src_dir / "app.pyw"
    entry_py  = src_dir / "app.py"

    if entry_pyW.exists():
        entrypoint = entry_pyW
        gui = True
    elif entry_py.exists():
        entrypoint = entry_py
        # Many of your tools are GUI even if app.py not app.pyw;
        # we default to GUI packaging unless user forces console.
        gui = True
    else:
        raise FileNotFoundError(f"No entrypoint found. Expected src/app.pyw or src/app.py in: {project_root}")

    requirements = (project_root / "requirements.txt") if (project_root / "requirements.txt").exists() else None
    assets_dir = (project_root / "assets") if (project_root / "assets").exists() else None

    # Name: use folder name by default
    name = project_root.name.strip()

    return ProjectInfo(
        project_root=project_root,
        name=name,
        entrypoint=entrypoint,
        gui=gui,
        requirements=requirements,
        assets_dir=assets_dir
    )


def venv_paths(venv_dir: Path) -> Tuple[Path, Path]:
    """
    Return (python_exe, pip_exe) for the venv.
    Windows: Scripts/python.exe, Scripts/pip.exe
    """
    if is_windows():
        py = venv_dir / "Scripts" / "python.exe"
        pip = venv_dir / "Scripts" / "pip.exe"
    else:
        py = venv_dir / "bin" / "python"
        pip = venv_dir / "bin" / "pip"
    return py, pip


def ensure_venv(venv_dir: Path) -> Tuple[Path, Path]:
    safe_mkdir(venv_dir.parent)
    py, pip = venv_paths(venv_dir)
    if py.exists() and pip.exists():
        return py, pip

    print(f"[INFO] Creating venv: {venv_dir}")
    run([sys.executable, "-m", "venv", str(venv_dir)])
    py, pip = venv_paths(venv_dir)

    # Upgrade pip tooling
    run([str(py), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"])
    return py, pip


def ensure_pyinstaller(python_exe: Path) -> None:
    """
    Ensure PyInstaller is installed in the build venv.
    """
    # Install or upgrade PyInstaller in the venv
    run([str(python_exe), "-m", "pip", "install", "--upgrade", "pyinstaller"])


def install_requirements(python_exe: Path, requirements: Optional[Path]) -> None:
    if requirements is None:
        print("[INFO] No requirements.txt found; skipping dependency install.")
        return
    print(f"[INFO] Installing requirements from: {requirements}")
    run([str(python_exe), "-m", "pip", "install", "-r", str(requirements)])


def build_pyinstaller_cmd(
    python_exe: Path,
    proj: ProjectInfo,
    build_mode: str,
    clean: bool,
    console: bool,
    icon_path: Optional[Path],
    extra_data_dirs: List[Path],
) -> List[str]:
    """
    Build a PyInstaller command suitable for running inside the project root.
    """
    cmd = [str(python_exe), "-m", "PyInstaller"]

    # Ensure the *project root* is on the analysis path.
    # Many of your tools are run as: python -m src.app
    # That relies on <project_root> being on sys.path so 'import src.*' works.
    cmd += ["--paths", str(proj.project_root)]

    # Clean build artifacts (PyInstaller build cache)
    if clean:
        cmd.append("--clean")

    # Name of the output exe/bundle
    cmd += ["--name", proj.name]

    # Mode
    if build_mode == "onefile":
        cmd.append("--onefile")
    else:
        cmd.append("--onedir")

    # Console behavior
    if not console:
        cmd.append("--noconsole")

    # Icon
    if icon_path and icon_path.exists():
        cmd += ["--icon", str(icon_path)]

    # Data directories (assets, configs, etc.)
    # On Windows, --add-data uses "SRC;DEST" separator.
    # DEST is relative inside the bundle.
    sep = ";" if is_windows() else ":"
    for data_dir in extra_data_dirs:
        # Put in same folder name inside bundle
        dest_name = data_dir.name
        cmd += ["--add-data", f"{str(data_dir)}{sep}{dest_name}"]

    # Entrypoint script
    cmd.append(str(proj.entrypoint))

    return cmd


def clean_project_build_artifacts(project_root: Path) -> None:
    """
    Remove build/ dist/ *.spec to avoid mixing outputs between builds.
    """
    for folder in ["build", "dist"]:
        p = project_root / folder
        if p.exists() and p.is_dir():
            shutil.rmtree(p, ignore_errors=True)

    # Spec file typically lands in project root: <name>.spec
    # We'll remove any spec files created by this build later as well.
    for spec in project_root.glob("*.spec"):
        try:
            spec.unlink()
        except Exception:
            pass


def copy_dist_to_destination(project_root: Path, proj_name: str, dest_dir: Path, build_mode: str) -> Path:
    """
    Copy the PyInstaller output into destination folder.
    Returns the output path created in destination.
    """
    dist_root = project_root / "dist"
    if not dist_root.exists():
        raise FileNotFoundError("PyInstaller dist folder not found. Build likely failed.")

    safe_mkdir(dest_dir)

    if build_mode == "onefile":
        exe_path = dist_root / f"{proj_name}.exe"
        if not exe_path.exists():
            # Sometimes exe is nested; attempt fallback
            candidates = list(dist_root.glob("*.exe"))
            if not candidates:
                raise FileNotFoundError(f"Expected exe not found in dist: {dist_root}")
            exe_path = candidates[0]

        out_path = dest_dir / exe_path.name
        shutil.copy2(exe_path, out_path)
        return out_path

    # onedir: dist/<name>/...
    bundle_dir = dist_root / proj_name
    if not bundle_dir.exists():
        # fallback: pick first dir in dist
        dirs = [p for p in dist_root.iterdir() if p.is_dir()]
        if not dirs:
            raise FileNotFoundError(f"Expected bundle folder not found in dist: {dist_root}")
        bundle_dir = dirs[0]

    out_bundle = dest_dir / bundle_dir.name
    if out_bundle.exists():
        shutil.rmtree(out_bundle, ignore_errors=True)

    shutil.copytree(bundle_dir, out_bundle)
    return out_bundle


def write_build_report(dest_dir: Path, proj: ProjectInfo, output_path: Path, args: argparse.Namespace) -> Path:
    report = {
        "timestamp": now_iso(),
        "project_root": str(proj.project_root),
        "project_name": proj.name,
        "entrypoint": str(proj.entrypoint),
        "gui": proj.gui,
        "requirements": str(proj.requirements) if proj.requirements else None,
        "assets_dir": str(proj.assets_dir) if proj.assets_dir else None,
        "build_mode": args.mode,
        "console": args.console,
        "clean": args.clean,
        "icon": str(args.icon) if args.icon else None,
        "extra_data": [str(p) for p in args.include_data] if args.include_data else [],
        "output_path": str(output_path),
        "python": sys.version,
        "platform": sys.platform,
    }
    report_path = dest_dir / f"{proj.name}_build_report.json"
    report_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report_path


# ----------------------------
# Main
# ----------------------------

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="Build a shareable .exe bundle for a UsefulHelper project (PyInstaller)."
    )
    p.add_argument("--project", required=True, help="Path to the target project root folder.")
    p.add_argument("--dest", required=True, help="Destination folder to place built output.")
    p.add_argument("--mode", choices=["onedir", "onefile"], default="onedir", help="PyInstaller build mode (default: onedir).")
    p.add_argument("--clean", action="store_true", help="Clean prior build artifacts before building.")
    p.add_argument("--console", action="store_true", help="Force console window (default: no console).")
    p.add_argument("--icon", default=None, help="Optional .ico path.")
    p.add_argument(
        "--include-data",
        nargs="*",
        default=[],
        help="Extra data directories to include (paths). Example: --include-data assets _roles"
    )
    p.add_argument(
        "--venv",
        default=None,
        help="Optional venv path. Default is <project_root>/.build_venv"
    )
    return p.parse_args()


def build_exe(
    project: Path | str,
    dest: Path | str,
    mode: str = "onedir",
    clean: bool = False,
    console: bool = False,
    icon: Optional[Path | str] = None,
    include_data: Optional[List[str]] = None,
    venv: Optional[Path | str] = None,
) -> Tuple[Path, Path]:
    """Build a shareable .exe bundle for a target project and stage it into dest.

    This is the stable façade API that both CLI and Tkinter UI will call.

    Returns:
        (output_path, report_path)
    """
    project_root = Path(project).resolve()
    dest_dir = Path(dest).resolve()

    proj = detect_project(project_root)

    # Compute venv location
    venv_dir = Path(venv).resolve() if venv else (proj.project_root / ".build_venv")

    # Extra data dirs: include assets automatically if present, plus user-specified
    extra_data_dirs: List[Path] = []
    if proj.assets_dir:
        extra_data_dirs.append(proj.assets_dir)

    for p in (include_data or []):
        candidate = (proj.project_root / p).resolve() if not Path(p).is_absolute() else Path(p).resolve()
        if candidate.exists() and candidate.is_dir():
            extra_data_dirs.append(candidate)
        else:
            eprint(f"[WARN] include-data path not found or not a directory, skipping: {candidate}")

    icon_path = Path(icon).resolve() if icon else None

    print(f"[INFO] Project: {proj.name}")
    print(f"[INFO] Root:    {proj.project_root}")
    print(f"[INFO] Entry:   {proj.entrypoint}")
    print(f"[INFO] Dest:    {dest_dir}")
    print(f"[INFO] Mode:    {mode}")

    if clean:
        print("[INFO] Cleaning prior build artifacts...")
        clean_project_build_artifacts(proj.project_root)

    # Build environment
    py, _pip = ensure_venv(venv_dir)
    ensure_pyinstaller(py)
    install_requirements(py, proj.requirements)

    # Build
    cmd = build_pyinstaller_cmd(
        python_exe=py,
        proj=proj,
        build_mode=mode,
        clean=clean,
        console=console,
        icon_path=icon_path,
        extra_data_dirs=extra_data_dirs,
    )

    # Run PyInstaller in the project root
    run(cmd, cwd=proj.project_root)

    # Copy to destination
    output_path = copy_dist_to_destination(proj.project_root, proj.name, dest_dir, mode)

    # Build a lightweight args-like object for the existing report function
    report_args = argparse.Namespace(
        mode=mode,
        console=console,
        clean=clean,
        icon=str(icon_path) if icon_path else None,
        include_data=include_data or [],
    )
    report_path = write_build_report(dest_dir, proj, output_path, report_args)

    print(f"\n[SUCCESS] Output: {output_path}")
    print(f"[SUCCESS] Report: {report_path}")
    return output_path, report_path


def main() -> int:
    args = parse_args()

    build_exe(
        project=args.project,
        dest=args.dest,
        mode=args.mode,
        clean=args.clean,
        console=args.console,
        icon=args.icon,
        include_data=args.include_data,
        venv=args.venv,
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except subprocess.CalledProcessError as e:
        eprint("\n[ERROR] Build command failed.")
        eprint(f"Command: {e.cmd}")
        eprint(f"Exit code: {e.returncode}")
        raise
    except Exception as e:
        eprint("\n[ERROR] Unexpected failure:", str(e))
        raise



