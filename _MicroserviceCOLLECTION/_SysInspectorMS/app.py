import platform
import subprocess
import sys
import datetime
from typing import Any, Dict, List, Optional
from microservice_std_lib import service_metadata, service_endpoint

@service_metadata(
name="SysInspector",
version="1.0.0",
description="Gathers hardware and environment statistics via shell commands.",
tags=["system", "audit", "hardware"],
capabilities=["os:shell", "compute"]
)
class SysInspectorMS:
    """
The Auditor: Gathers hardware and environment statistics.
Supports: Windows (WMIC), Linux (lscpu/lspci), and macOS (sysctl/system_profiler).
"""

def __init__(self, config: Optional[Dict[str, Any]] = None):
self.config = config or {}

@service_endpoint(
inputs={},
outputs={"report": "str"},
description="Runs the full audit and returns a formatted string report.",
tags=["system", "report"],
side_effects=["os:read"]
)
def generate_report(self) -> str:
        """
        Runs the full audit and returns a formatted string report.
        """
        system_os = platform.system()
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        
        report = [
            f"System Audit Report",
            f"Generated: {timestamp}",
            f"OS: {system_os} {platform.release()} ({platform.machine()})",
            "-" * 40,
            ""
        ]

        # 1. Hardware Section
        report.append("--- Hardware Information ---")
        if system_os == "Windows":
            report.extend(self._audit_windows())
        elif system_os == "Linux":
            report.extend(self._audit_linux())
        elif system_os == "Darwin":
            report.extend(self._audit_mac())
        else:
            report.append("Unsupported Operating System for detailed hardware audit.")

        # 2. Software Section
        report.append("\n--- Software Environment ---")
        report.append(f"Python Version: {platform.python_version()}")
        report.append(f"Python Executable: {sys.executable}")
        
        return "\n".join(report)

    def _run_cmd(self, cmd: str) -> str:
        """Helper to run shell commands safely."""
        try:
            # shell=True is often required for piped commands, specifically on Windows/Linux
            result = subprocess.run(
                cmd, 
                text=True, 
                capture_output=True, 
                check=False, 
                shell=True, 
                timeout=5
            )
            if result.returncode == 0 and result.stdout:
                return result.stdout.strip()
            elif result.stderr:
                return f"[Cmd Error]: {result.stderr.strip()}"
            return "[No Output]"
        except Exception as e:
            return f"[Execution Error]: {e}"

    # --- OS Specific Implementations ---

    def _audit_windows(self) -> list[str]:
        data = []
        # CPU
        data.append("CPU: " + self._run_cmd("wmic cpu get name"))
        # GPU
        data.append("GPU: " + self._run_cmd("wmic path win32_videocontroller get name"))
        # RAM
        try:
            mem_str = self._run_cmd("wmic computersystem get totalphysicalmemory").splitlines()[-1]
            mem_bytes = int(mem_str)
            data.append(f"Memory: {mem_bytes / (1024**3):.2f} GB")
        except:
            data.append("Memory: Could not retrieve total physical memory.")
        # Disk
        data.append("\nDisks:")
        data.append(self._run_cmd("wmic diskdrive get model,size"))
        return data

    def _audit_linux(self) -> list[str]:
        data = []
        # CPU
        data.append("CPU: " + self._run_cmd("lscpu | grep 'Model name'"))
        # GPU (Requires lspci, usually in pciutils)
        data.append("GPU: " + self._run_cmd("lspci | grep -i vga"))
        # RAM
        data.append("Memory:\n" + self._run_cmd("free -h"))
        # Disk
        data.append("\nDisks:\n" + self._run_cmd("lsblk -o NAME,SIZE,MODEL"))
        return data

    def _audit_mac(self) -> list[str]:
        data = []
        # CPU
        data.append("CPU: " + self._run_cmd("sysctl -n machdep.cpu.brand_string"))
        # GPU
        data.append("GPU:\n" + self._run_cmd("system_profiler SPDisplaysDataType | grep -E 'Chipset Model|VRAM'"))
        # RAM
        data.append("Memory Details:\n" + self._run_cmd("system_profiler SPMemoryDataType | grep -E 'Size|Type|Speed'"))
        # RAM Total
        try:
            mem_bytes = int(self._run_cmd('sysctl -n hw.memsize'))
            data.append(f"Total Memory: {mem_bytes / (1024**3):.2f} GB")
        except: 
            pass
        # Disk
data.append("\nDisks:\n" + self._run_cmd("diskutil list physical"))
        return data

# --- Independent Test Block ---
if __name__ == "__main__":
    inspector = SysInspectorMS()
    print("Service ready:", inspector)
    print("Running System Inspector...")
    print("\n" + inspector.generate_report())
