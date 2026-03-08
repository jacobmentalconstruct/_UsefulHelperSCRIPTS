import os
import platform
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from microservice_std_lib import service_endpoint, service_metadata


def _platform_name(system_override: Optional[str] = None) -> str:
    if system_override:
        return str(system_override).strip().lower()
    return platform.system().strip().lower()


def _safe_path(path: str) -> Path:
    return Path(path).expanduser()


def _is_windows(system_name: str) -> bool:
    return system_name.startswith("win")


def _is_macos(system_name: str) -> bool:
    return system_name in {"darwin", "mac", "macos"}


@service_metadata(
    name="ReferenceShellActionsMS",
    version="1.0.0",
    description="Pilfered from utils/shell.py. Plans and optionally launches cross-platform file/explorer/terminal shell actions.",
    tags=["shell", "filesystem", "desktop", "tools"],
    capabilities=["filesystem:read", "process:spawn"],
    side_effects=["filesystem:read", "process:spawn"],
    internal_dependencies=["microservice_std_lib"],
    external_dependencies=[],
)
class ReferenceShellActionsMS:
    def __init__(self):
        self.start_time = time.time()

    @service_endpoint(
        inputs={"path": "str"},
        outputs={"status": "dict"},
        description="Resolve a path and return existence/parent fallback metadata.",
        tags=["shell", "filesystem", "planning"],
        side_effects=["filesystem:read"],
    )
    def resolve_path(self, path: str) -> Dict[str, Any]:
        candidate = _safe_path(path)
        existing = candidate if candidate.exists() else candidate.parent
        return {
            "input_path": str(candidate),
            "exists": candidate.exists(),
            "resolved_path": str(existing),
            "resolved_exists": existing.exists(),
            "is_dir": existing.is_dir() if existing.exists() else False,
        }

    @service_endpoint(
        inputs={"path": "str", "system_override": "str|None"},
        outputs={"plan": "dict"},
        description="Plan platform-specific open-file action without launching it.",
        tags=["shell", "open", "planning"],
        side_effects=["filesystem:read"],
    )
    def plan_open_file(self, path: str, system_override: Optional[str] = None) -> Dict[str, Any]:
        target = _safe_path(path)
        if not target.exists():
            return {"ok": False, "error": "file_not_found", "path": str(target)}

        system_name = _platform_name(system_override)
        if _is_windows(system_name):
            return {"ok": True, "action": "startfile", "path": str(target), "command": []}
        if _is_macos(system_name):
            return {"ok": True, "action": "subprocess", "path": str(target), "command": ["open", str(target)]}
        return {"ok": True, "action": "subprocess", "path": str(target), "command": ["xdg-open", str(target)]}

    @service_endpoint(
        inputs={"path": "str", "line": "int|None", "system_override": "str|None"},
        outputs={"plan": "dict"},
        description="Plan open-file-at-line action, preferring VS Code goto command with fallback open action.",
        tags=["shell", "editor", "planning"],
        side_effects=["filesystem:read"],
    )
    def plan_open_file_at_line(self, path: str, line: Optional[int] = None, system_override: Optional[str] = None) -> Dict[str, Any]:
        target = _safe_path(path)
        if not target.exists():
            return {"ok": False, "error": "file_not_found", "path": str(target)}

        goto_target = f"{target}:{int(line)}" if line else str(target)
        fallback = self.plan_open_file(path, system_override=system_override)
        return {
            "ok": True,
            "primary_command": ["code", "--goto", goto_target],
            "fallback": fallback,
            "path": str(target),
            "line": int(line) if line else None,
        }

    @service_endpoint(
        inputs={"path": "str", "system_override": "str|None"},
        outputs={"plan": "dict"},
        description="Plan reveal/open-in-explorer action for a file or directory.",
        tags=["shell", "explorer", "planning"],
        side_effects=["filesystem:read"],
    )
    def plan_open_in_explorer(self, path: str, system_override: Optional[str] = None) -> Dict[str, Any]:
        target = _safe_path(path)
        target = target if target.exists() else target.parent
        system_name = _platform_name(system_override)

        if _is_windows(system_name):
            return {"ok": True, "command": ["explorer", str(target)], "path": str(target)}
        if _is_macos(system_name):
            return {"ok": True, "command": ["open", str(target)], "path": str(target)}
        return {"ok": True, "command": ["xdg-open", str(target)], "path": str(target)}

    @service_endpoint(
        inputs={"path": "str", "shell_name": "str", "system_override": "str|None"},
        outputs={"plan": "dict"},
        description="Plan terminal launch command in a target directory.",
        tags=["shell", "terminal", "planning"],
        side_effects=["filesystem:read"],
    )
    def plan_open_terminal(self, path: str, shell_name: str = "default", system_override: Optional[str] = None) -> Dict[str, Any]:
        target = _safe_path(path)
        target = target if target.is_dir() else target.parent
        system_name = _platform_name(system_override)
        shell_choice = (shell_name or "default").strip().lower()

        if _is_windows(system_name):
            if shell_choice in {"powershell", "pwsh"}:
                cmd = ["powershell", "-NoExit", "-Command", f"Set-Location '{target}'"]
            else:
                cmd = ["cmd", "/K", f"cd /d {target}"]
            return {"ok": True, "command": cmd, "path": str(target), "creationflags": int(getattr(subprocess, "CREATE_NEW_CONSOLE", 0))}

        if _is_macos(system_name):
            return {"ok": True, "command": ["open", "-a", "Terminal", str(target)], "path": str(target), "creationflags": 0}

        return {
            "ok": True,
            "command": ["x-terminal-emulator", f"--working-directory={target}"],
            "path": str(target),
            "creationflags": 0,
        }

    @service_endpoint(
        inputs={"command": "list[str]", "creationflags": "int"},
        outputs={"result": "dict"},
        description="Spawn a command and return process metadata.",
        tags=["shell", "process", "execution"],
        side_effects=["process:spawn"],
    )
    def launch_command(self, command: List[str], creationflags: int = 0) -> Dict[str, Any]:
        if not command:
            return {"ok": False, "error": "empty_command"}
        try:
            proc = subprocess.Popen(command, creationflags=creationflags)
            return {"ok": True, "pid": int(proc.pid), "command": command}
        except FileNotFoundError as exc:
            return {"ok": False, "error": "executable_not_found", "detail": str(exc), "command": command}
        except Exception as exc:
            return {"ok": False, "error": "launch_failed", "detail": str(exc), "command": command}

    @service_endpoint(
        inputs={"path": "str", "line": "int|None", "system_override": "str|None", "execute": "bool"},
        outputs={"result": "dict"},
        description="Open file at a line; falls back to default open when VS Code is unavailable. Executes only when execute=True.",
        tags=["shell", "editor", "execution"],
        side_effects=["filesystem:read", "process:spawn"],
    )
    def open_file_at_line(self, path: str, line: Optional[int] = None, system_override: Optional[str] = None, execute: bool = False) -> Dict[str, Any]:
        plan = self.plan_open_file_at_line(path, line=line, system_override=system_override)
        if not plan.get("ok"):
            return plan
        if not execute:
            return {"ok": True, "mode": "planned", "plan": plan}

        primary = self.launch_command(plan["primary_command"], creationflags=int(getattr(subprocess, "CREATE_NO_WINDOW", 0)))
        if primary.get("ok"):
            return {"ok": True, "mode": "executed", "used": "primary", "result": primary}

        fallback = plan.get("fallback", {})
        fallback_cmd = fallback.get("command", [])
        if fallback.get("action") == "startfile" and _is_windows(_platform_name(system_override)):
            try:
                if hasattr(os, "startfile"):
                    os.startfile(str(_safe_path(path)))  # type: ignore[attr-defined]
                    return {"ok": True, "mode": "executed", "used": "fallback_startfile"}
                return {"ok": False, "error": "startfile_unavailable"}
            except Exception as exc:
                return {"ok": False, "error": "fallback_startfile_failed", "detail": str(exc)}

        fallback_launch = self.launch_command(fallback_cmd)
        return {"ok": bool(fallback_launch.get("ok")), "mode": "executed", "used": "fallback_command", "result": fallback_launch}

    @service_endpoint(
        inputs={},
        outputs={"status": "str", "uptime": "float"},
        description="Standardized health check for service status.",
        tags=["diagnostic", "health"],
    )
    def get_health(self):
        return {"status": "online", "uptime": time.time() - self.start_time}