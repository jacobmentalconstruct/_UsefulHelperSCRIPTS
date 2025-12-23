"""
SERVICE_NAME: _CodeJanitorMS
ENTRY_POINT: _CodeJanitorMS.py
DEPENDENCIES: None
"""
import re
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional
from microservice_std_lib import service_metadata, service_endpoint

logger = logging.getLogger("CodeJanitor")

RENAME_MAP = {
    "__AppShellMS": "_TkinterAppShellMS",
    "_AppShellMS": "_TkinterAppShellMS",
    "__ThemeManagerMS": "_TkinterThemeManagerMS",
    "_ThemeManagerMS": "_TkinterThemeManagerMS",
    "__SmartExplorerMS": "_TkinterSmartExplorerMS",
    "_SmartExplorerMS": "_TkinterSmartExplorerMS",
    "__UniButtonMS": "_TkinterUniButtonMS",
    "_UniButtonMS": "_TkinterUniButtonMS",
}

@service_metadata(
    name="CodeJanitor",
    version="2.2.0",
    description="Fast version: Skips backup, high verbosity.",
    tags=["maintenance"],
    capabilities=["filesystem:write"]
)
class CodeJanitorMS:
    def __init__(self):
        self.root = Path(".").resolve()

    def enforce_standards(self, dry_run: bool = True):
        print(f"--- 🧹 JANITOR STARTED in {'DRY RUN' if dry_run else 'LIVE'} MODE ---")
        
        files = list(self.root.glob("*.py"))
        print(f"Found {len(files)} Python files to scan.\n")

        # Regex Patterns
        generic_import = re.compile(r'(from|import)\s+__([A-Z])')
        generic_string = re.compile(r'["\']__([A-Z]\w+MS)["\']')
        entry_point = re.compile(r'ENTRY_POINT:\s*__([A-Z]\w+MS\.py)')

        for file_path in files:
            if file_path.name == "_CodeJanitorMS.py": continue
            
            try:
                original = file_path.read_text(encoding="utf-8")
                new = original
                
                # 1. Fix ENTRY_POINT
                new = entry_point.sub(r'ENTRY_POINT: _\1', new)

                # 2. Specific Renames
                for old_name, new_name in RENAME_MAP.items():
                    pattern = re.compile(rf'\b{old_name}\b')
                    if pattern.search(new):
                        new = pattern.sub(new_name, new)

                # 3. Generic Fixes
                new = generic_import.sub(r'\1 _\2', new)
                new = generic_string.sub(r'"_\1"', new)

                if new != original:
                    print(f"🛠️  PATCHING: {file_path.name}")
                    if not dry_run:
                        file_path.write_text(new, encoding="utf-8")
                else:
                    # Verbose check to prove it's running
                    # print(f"    OK: {file_path.name}") 
                    pass

            except Exception as e:
                print(f"❌ ERROR {file_path.name}: {e}")

        print("\n--- 🏁 JANITOR FINISHED ---")

if __name__ == "__main__":
    janitor = CodeJanitorMS()
    # RUN LIVE IMMEDIATELY
    janitor.enforce_standards(dry_run=False)