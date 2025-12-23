"""
SERVICE_NAME: _CodeJanitorMS
ENTRY_POINT: _CodeJanitorMS.py
DEPENDENCIES: None
"""
import os
import re
import logging
from pathlib import Path

# ==============================================================================
# CONFIGURATION
# ==============================================================================
# Map of Old Names -> New Names (Add any others you renamed manually!)
RENAME_MAP = {
    "__AppShellMS": "_TkinterAppShellMS",
    "_AppShellMS": "_TkinterAppShellMS",
    
    "__ThemeManagerMS": "_TkinterThemeManagerMS",
    "_ThemeManagerMS": "_TkinterThemeManagerMS",
    
    "__SmartExplorerMS": "_TkinterSmartExplorerMS",
    "_SmartExplorerMS": "_TkinterSmartExplorerMS",
    
    "__UniButtonMS": "_TkinterUniButtonMS",
    "_UniButtonMS": "_TkinterUniButtonMS",
    
    # Generic catch-all for the double-underscore removal
    "__": "_"
}

logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')
logger = logging.getLogger("Janitor")

def clean_imports_and_references():
    root = Path(".")
    files = list(root.glob("*.py"))
    
    print(f"🧹 Janitor scanning {len(files)} files for broken links...")
    
    for file_path in files:
        if file_path.name == "_CodeJanitorMS.py": continue
        
        try:
            original = file_path.read_text(encoding="utf-8")
            content = original
            
            # 1. Apply Specific Renames (Tkinter, etc)
            for old, new in RENAME_MAP.items():
                if old == "__": continue # Skip the generic one for now
                
                # Regex to match "from X import", "import X", or string "X"
                # We use word boundaries \b to avoid replacing substrings incorrectly
                pattern = re.compile(rf'\b{old}\b')
                if pattern.search(content):
                    content = pattern.sub(new, content)
            
            # 2. Apply Generic Double-Underscore Removal (from __AuthMS import...)
            # Looks for "from __WordMS" and turns it into "from _WordMS"
            content = re.sub(r'(from|import)\s+__([A-Z]\w+MS)', r'\1 _\2', content)
            
            # 3. Fix String References (e.g. in ServiceRegistry or prompts)
            content = re.sub(r'["\']__([A-Z]\w+MS)["\']', r'"_\1"', content)

            if content != original:
                file_path.write_text(content, encoding="utf-8")
                print(f"   ✨ Patched: {file_path.name}")
                
        except Exception as e:
            print(f"   ❌ Error reading {file_path.name}: {e}")

if __name__ == "__main__":
    clean_imports_and_references()
    print("\n✅ Link Fix Complete. Ready for Task 2.")