import re
import sys
from pathlib import Path
import importlib

ROOT = Path(__file__).resolve().parents[1]  # adjust if you place script elsewhere
SRC = ROOT / "src"
MS_DIR = SRC / "microservices"

# Match: from microservice_std_lib import a, b, BaseService, c
BAD_FROM_RE = re.compile(
    r"^(?P<indent>\s*)from\s+(?P<dots>\.?)microservice_std_lib\s+import\s+(?P<items>.+?)\s*$",
    re.MULTILINE,
)

BASE_IMPORT_RE = re.compile(
    r"^\s*from\s+\.?base_service\s+import\s+BaseService\s*$",
    re.MULTILINE,
)

def split_import_items(items: str) -> list[str]:
    # naive but good enough for your import style: comma-separated names
    parts = [p.strip() for p in items.split(",")]
    return [p for p in parts if p]

def join_import_items(items: list[str]) -> str:
    return ", ".join(items)

def fix_file(path: Path) -> bool:
    original = path.read_text(encoding="utf-8")
    text = original

    changed = False

    # 1) Fix "from microservice_std_lib import ... BaseService ..."
    def repl(m: re.Match) -> str:
        nonlocal changed
        indent = m.group("indent")
        dots = m.group("dots") or ""
        items = split_import_items(m.group("items"))
        if "BaseService" not in items:
            return m.group(0)

        items = [x for x in items if x != "BaseService"]
        changed = True
        return f"{indent}from {dots}microservice_std_lib import {join_import_items(items)}"

    text = BAD_FROM_RE.sub(repl, text)

    # 2) If the file uses BaseService, ensure it imports it from base_service
    uses_baseservice = "BaseService" in text
    has_base_import = bool(BASE_IMPORT_RE.search(text))

    if uses_baseservice and not has_base_import:
        # Insert after the last std_lib import block near top if possible.
        insert_after = None

        # Prefer right after microservice_std_lib import line if present
        ms_std = re.search(r"^from\s+microservice_std_lib\s+import\s+.*$", text, re.MULTILINE)
        if ms_std:
            insert_after = ms_std.end()

        if insert_after is not None:
            # Check if the existing import used a dot
            ms_std_match = re.search(r"^from\s+(?P<dots>\.?)microservice_std_lib", text, re.MULTILINE)
            dots = ms_std_match.group("dots") if ms_std_match else ""
            
            text = text[:insert_after] + f"\nfrom {dots}base_service import BaseService" + text[insert_after:]
        else:
            # fallback: add near top (after initial docstring/comments)
            lines = text.splitlines(True)
            i = 0
            if lines and lines[0].lstrip().startswith('"""'):
                # skip docstring block
                i = 1
                while i < len(lines) and '"""' not in lines[i]:
                    i += 1
                if i < len(lines):
                    i += 1
            # skip blank lines
            while i < len(lines) and lines[i].strip() == "":
                i += 1
            lines.insert(i, "from .base_service import BaseService\n")
            text = "".join(lines)

        changed = True

    if changed and text != original:
        backup = path.with_suffix(path.suffix + ".bak")
        if not backup.exists():
            backup.write_text(original, encoding="utf-8")
        path.write_text(text, encoding="utf-8")
        return True

    return False

def verify_imports():
    # mirror app.py path injection
    sys.path.insert(0, str(SRC))
    sys.path.insert(0, str(MS_DIR))

    failures = []
    for py in sorted(MS_DIR.glob("*.py")):
        name = py.stem
        if name in {"base_service", "microservice_std_lib"}:
            continue
        try:
            importlib.import_module(name)
        except Exception as e:
            failures.append((name, repr(e)))

    if failures:
        print("\n[IMPORT VERIFY] Failures:")
        for name, err in failures:
            print(f" - {name}: {err}")
        raise SystemExit(1)
    else:
        print("\n[IMPORT VERIFY] All microservices imported successfully.")

def main():
    if not MS_DIR.exists():
        raise SystemExit(f"Microservices folder not found: {MS_DIR}")

    touched = []
    for py in sorted(MS_DIR.glob("*.py")):
        if py.name.endswith(".bak"):
            continue
        if fix_file(py):
            touched.append(py.name)

    print(f"[FIX] Updated {len(touched)} files.")
    for t in touched:
        print(f" - {t}")

    verify_imports()

if __name__ == "__main__":
    main()


