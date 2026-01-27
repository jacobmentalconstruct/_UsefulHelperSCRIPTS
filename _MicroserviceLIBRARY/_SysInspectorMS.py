import platform
import subprocess
import sys
import datetime
import logging
from typing import Any, Dict, List, Optional
from microservice_std_lib import service_metadata, service_endpoint
logger = logging.getLogger('SysInspector')

@service_metadata(name='SysInspector', version='1.0.0', description='Gathers hardware and environment statistics via shell commands.', tags=['system', 'audit', 'hardware'], capabilities=['os:shell', 'compute'], internal_dependencies=['microservice_std_lib'], external_dependencies=[])
class SysInspectorMS:
    """
    The Auditor: Gathers hardware and environment statistics.
    Supports: Windows (WMIC), Linux (lscpu/lspci), and macOS (sysctl/system_profiler).
    """

    def __init__(self, config: Optional[Dict[str, Any]]=None):
        self.config = config or {}

    @service_endpoint(inputs={}, outputs={'report': 'str'}, description='Runs the full audit and returns a formatted string report.', tags=['system', 'report'], side_effects=['os:read'])
    def generate_report(self) -> str:
        """
        Runs the full audit and returns a formatted string report.
        """
        system_os = platform.system()
        timestamp = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        report = [f'System Audit Report', f'Generated: {timestamp}', f'OS: {system_os} {platform.release()} ({platform.machine()})', '-' * 40, '']
        report.append('--- Hardware Information ---')
        if system_os == 'Windows':
            report.extend(self._audit_windows())
        elif system_os == 'Linux':
            report.extend(self._audit_linux())
        elif system_os == 'Darwin':
            report.extend(self._audit_mac())
        else:
            report.append('Unsupported Operating System for detailed hardware audit.')
        report.append('\n--- Software Environment ---')
        report.append(f'Python Version: {platform.python_version()}')
        report.append(f'Python Executable: {sys.executable}')
        return '\n'.join(report)

    def _run_cmd(self, cmd: str) -> str:
        """Helper to run shell commands safely."""
        try:
            result = subprocess.run(cmd, text=True, capture_output=True, check=False, shell=True, timeout=5)
            if result.returncode == 0 and result.stdout:
                return result.stdout.strip()
            elif result.stderr:
                return f'[Cmd Error]: {result.stderr.strip()}'
            return '[No Output]'
        except Exception as e:
            return f'[Execution Error]: {e}'

    def _audit_windows(self) -> List[str]:
        data = []
        data.append('CPU: ' + self._run_cmd('wmic cpu get name'))
        data.append('GPU: ' + self._run_cmd('wmic path win32_videocontroller get name'))
        try:
            mem_str = self._run_cmd('wmic computersystem get totalphysicalmemory').splitlines()[-1]
            mem_bytes = int(mem_str)
            data.append(f'Memory: {mem_bytes / 1024 ** 3:.2f} GB')
        except:
            data.append('Memory: Could not retrieve total physical memory.')
        data.append('\nDisks:')
        data.append(self._run_cmd('wmic diskdrive get model,size'))
        return data

    def _audit_linux(self) -> List[str]:
        data = []
        data.append('CPU: ' + self._run_cmd("lscpu | grep 'Model name'"))
        data.append('GPU: ' + self._run_cmd('lspci | grep -i vga'))
        data.append('Memory:\n' + self._run_cmd('free -h'))
        data.append('\nDisks:\n' + self._run_cmd('lsblk -o NAME,SIZE,MODEL'))
        return data

    def _audit_mac(self) -> List[str]:
        data = []
        data.append('CPU: ' + self._run_cmd('sysctl -n machdep.cpu.brand_string'))
        data.append('GPU:\n' + self._run_cmd("system_profiler SPDisplaysDataType | grep -E 'Chipset Model|VRAM'"))
        data.append('Memory Details:\n' + self._run_cmd("system_profiler SPMemoryDataType | grep -E 'Size|Type|Speed'"))
        try:
            mem_bytes = int(self._run_cmd('sysctl -n hw.memsize'))
            data.append(f'Total Memory: {mem_bytes / 1024 ** 3:.2f} GB')
        except:
            pass
        data.append('\nDisks:\n' + self._run_cmd('diskutil list physical'))
        return data
if __name__ == '__main__':
    inspector = SysInspectorMS()
    print('Service ready:', inspector)
    print('Running System Inspector...')
    print('\n' + inspector.generate_report())
