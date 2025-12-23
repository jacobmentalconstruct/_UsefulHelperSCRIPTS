"""
SERVICE_NAME: _CodeJanitorMS
ENTRY_POINT: __CodeJanitorMS.py
DEPENDENCIES: None
"""

import os
import re
import shutil
import datetime
import logging
from pathlib import Path
from typing import Dict, List, Any, Optional

from microservice_std_lib import service_metadata, service_endpoint

# ==============================================================================
# CONFIGURATION
# ==============================================================================
logger = logging.getLogger("CodeJanitor")

# Files to ignore during mass operations
IGNORE_PATTERNS = {
    r"^\.",                # Hidden files
    r"^__pycache__",       # Python cache
    r"^venv",              # Virtual env
    r".*\.git.*",          # Git
    r".*\.db$",            # Databases
    r"_CodeJanitorMS\.py"  # Don't let the janitor scrub himself while running
}

# ==============================================================================
# MICROSERVICE CLASS
# ==============================================================================

@service_metadata(
    name="CodeJanitor",
    version="1.0.0",
    description="Automated maintenance service: Enforces file naming conventions, patches imports, and manages backups.",
    tags=["maintenance", "refactoring", "utility"],
    capabilities=["filesystem:write", "filesystem:read"]
)
class CodeJanitorMS:
    """
    The Custodian: Keeps the microservice ecosystem clean and standardized.
    Can rename files, patch source code, and create emergency backups.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.config = config or {}
        self.root = Path(self.config.get("root_path", ".")).resolve()

    @service_endpoint(
        inputs={"backup_name": "str"},
        outputs={"archive_path": "str"},
        description="Creates a timestamped ZIP archive of the entire project.",
        tags=["maintenance", "backup"],
        side_effects=["filesystem:write"]
    )
    def create_snapshot(self, backup_name: str = "auto_backup") -> str:
        """Creates a safety snapshot of the codebase."""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        archive_name = f"{backup_name}_{timestamp}"
        
        # Create a _backups folder if it doesn't exist
        backup_dir = self.root / "_backups"
        backup_dir.mkdir(exist_ok=True)
        
        output_path = backup_dir / archive_name
        
        # We use shutil.make_archive
        # Note: We exclude _backups to prevent recursion if running from root
        def filter_func(path_str):
            p = Path(path_str)
            if "_backups" in p.parts: return False
            if "__pycache__" in p.parts: return False
            if ".git" in p.parts: return False
            return True

        # shutil doesn't have a native filter in older python versions, 
        # so we might just zip the root. 
        # For a robust implementation, we'd manually zip. 
        # Here we use the simple approach:
        
        archive = shutil.make_archive(
            str(output_path), 
            'zip', 
            root_dir=self.root
        )
        
        logger.info(f"✅ Snapshot created: {archive}")
        return str(archive)

    @service_endpoint(
        inputs={"dry_run": "bool"},
        outputs={"renamed": "List[str]", "patched": "List[str]"},
        description="Scans the folder and enforces the '_NameMS.py' single-underscore convention.",
        tags=["maintenance", "refactoring"],
        side_effects=["filesystem:write"]
    )
    def enforce_standards(self, dry_run: bool = True) -> Dict[str, List[str]]:
        """
        The Migration Logic.
        1. Renames __Name.py -> _Name.py
        2. Patches imports (from __Name import) -> (from _Name import)
        """
        renamed_files = []
        patched_files = []
        
        files = [f for f in self.root.glob("*.py")]
        
        # Regex setup
        import_pattern = re.compile(r'(from|import)\s+__([A-Z])')
        string_pattern = re.compile(r'["\']__([A-Z]\w+MS)["\']')

        # 1. Patch Content First
        for file_path in files:
            if file_path.name == "_CodeJanitorMS.py": continue
            
            try:
                original_content = file_path.read_text(encoding="utf-8")
                new_content = original_content
                
                # Fix imports: "from __Auth" -> "from _Auth"
                new_content = import_pattern.sub(r'\1 _\2', new_content)
                # Fix strings: "__AuthMS" -> "_AuthMS"
                new_content = string_pattern.sub(r'"_\1"', new_content)
                
                # Special fix for Registry logic if it exists
                if "ServiceRegistry" in file_path.name:
                    new_content = new_content.replace('item.name.startswith("__")', 'item.name.startswith("_")')

                if new_content != original_content:
                    patched_files.append(file_path.name)
                    if not dry_run:
                        file_path.write_text(new_content, encoding="utf-8")
                        
            except Exception as e:
                logger.error(f"Failed to read {file_path}: {e}")

        # 2. Rename Files
        for file_path in files:
            name = file_path.name
            if name.startswith("__") and len(name) > 2 and name[2].isupper():
                new_name = "_" + name[2:]
                renamed_files.append(f"{name} -> {new_name}")
                
                if not dry_run:
                    try:
                        file_path.rename(self.root / new_name)
                    except OSError as e:
                        logger.error(f"Rename failed for {name}: {e}")

        status = "[DRY RUN] " if dry_run else "[LIVE] "
        logger.info(f"{status}Standards Enforcement Complete.")
        return {
            "renamed": renamed_files,
            "patched": patched_files
        }

    @service_endpoint(
        inputs={"find_pattern": "str", "replace_pattern": "str", "dry_run": "bool"},
        outputs={"affected_files": "List[str]"},
        description="Performs a regex Find & Replace across all Python files in the directory.",
        tags=["refactoring", "utility"],
        side_effects=["filesystem:write"]
    )
    def global_replace(self, find_pattern: str, replace_pattern: str, dry_run: bool = True) -> List[str]:
        """
        Global Search & Replace. 
        Useful if you rename a dependency or change a config key everywhere.
        """
        affected = []
        regex = re.compile(find_pattern)
        
        for file_path in self.root.glob("*.py"):
            if file_path.name == "_CodeJanitorMS.py": continue
            
            try:
                content = file_path.read_text(encoding="utf-8")
                if regex.search(content):
                    affected.append(file_path.name)
                    if not dry_run:
                        new_content = regex.sub(replace_pattern, content)
                        file_path.write_text(new_content, encoding="utf-8")
            except Exception:
                pass
                
        return affected

# --- Independent Test Block ---
if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    
    # We run in Dry Run mode by default to be safe
    janitor = CodeJanitorMS()
    print("Service ready:", janitor)
    
    print("\n--- Running Standards Check (Dry Run) ---")
    report = janitor.enforce_standards(dry_run=True)
    
    print(f"Files to Rename: {len(report['renamed'])}")
    for f in report['renamed']: print(f"  {f}")
    
    print(f"Files to Patch:  {len(report['patched'])}")
    for f in report['patched']: print(f"  {f}")

    # Uncomment to actually create a backup
    # janitor.create_snapshot("pre_migration_backup")