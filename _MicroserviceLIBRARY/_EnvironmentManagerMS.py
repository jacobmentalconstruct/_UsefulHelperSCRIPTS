"""
SERVICE_NAME: _EnvironmentManagerMS
ENTRY_POINT: _EnvironmentManagerMS.py
DEPENDENCIES: None
"""
import os
import sys
import subprocess
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional, Union

from microservice_std_lib import service_metadata, service_endpoint

logger = logging.getLogger("EnvManager")

@service_metadata(
    name="EnvironmentManager",
    version="1.0.0",
    description="Manages Python runtime resolution and process execution.",
    tags=["runtime", "python", "venv", "process"],
    capabilities=["os:shell", "os:process"]
)
class EnvironmentManagerMS:
    """
    The Operator.
    Finds the right Python interpreter (System vs Venv) and launches processes.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}

    @service_endpoint(
        inputs={"project_path": "str", "config_override": "str"},
        outputs={"interpreter": "str", "source": "str"},
        description="Determines the absolute path to the Python interpreter for a given project.",
        tags=["runtime", "resolve"]
    )
    def resolve_python(self, project_path: str, config_override: Optional[str] = None) -> Dict[str, str]:
        """
        Priority:
        1. Explicit config override
        2. Local .venv
        3. System default (py or sys.executable)
        """
        path = Path(project_path).resolve()

        # 1. Explicit
        if config_override:
            # If relative, resolve against project
            if os.path.sep in config_override or "/" in config_override:
                return {"interpreter": str((path / config_override).resolve()), "source": "explicit"}
            return {"interpreter": config_override, "source": "command"}

        # 2. Local Venv
        # Windows
        win_venv = path / ".venv" / "Scripts" / "python.exe"
        if win_venv.exists(): return {"interpreter": str(win_venv), "source": "venv"}
        
        # Unix
        nix_venv = path / ".venv" / "bin" / "python"
        if nix_venv.exists(): return {"interpreter": str(nix_venv), "source": "venv"}

        # 3. System Fallback
        if os.name == "nt":
            return {"interpreter": "py", "source": "system_launcher"}
        return {"interpreter": sys.executable, "source": "system_default"}

    @service_endpoint(
        inputs={"project_path": "str", "script_rel_path": "str", "env_vars": "Dict"},
        outputs={"pid": "int"},
        description="Launches a python script in a subprocess using the resolved environment.",
        tags=["runtime", "execute"],
        side_effects=["os:process"]
    )
    def launch_script(self, 
                      project_path: str, 
                      script_rel_path: str = "src/app.py", 
                      env_vars: Dict[str, str] = None) -> int:
        
        root = Path(project_path).resolve()
        script = root / script_rel_path
        
        if not script.exists():
            raise FileNotFoundError(f"Script not found: {script}")

        # Resolve Python
        python_info = self.resolve_python(str(root))
        cmd = [python_info["interpreter"], str(script)]
        
        # Prepare Env
        proc_env = os.environ.copy()
        if env_vars:
            proc_env.update(env_vars)

        logger.info(f"Launching {cmd} in {root} via {python_info['source']}")

        # Launch
        if os.name == "nt":
            # New console window on Windows
            proc = subprocess.Popen(
                cmd, 
                cwd=str(root), 
                env=proc_env,
                creationflags=subprocess.CREATE_NEW_CONSOLE
            )
        else:
            proc = subprocess.Popen(cmd, cwd=str(root), env=proc_env)
            
        return proc.pid

if __name__ == "__main__":
    mgr = EnvironmentManagerMS()
    # Self-test: Resolve own environment
    print("Resolved Self:", mgr.resolve_python("."))
