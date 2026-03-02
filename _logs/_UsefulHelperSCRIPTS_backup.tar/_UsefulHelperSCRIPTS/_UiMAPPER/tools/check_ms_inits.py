from __future__ import annotations

import sys
from pathlib import Path
import importlib
import inspect
import pkgutil


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    if str(repo_root) not in sys.path:
        sys.path.insert(0, str(repo_root))

    ms_dir = repo_root / "src" / "microservices"
    if not ms_dir.exists():
        raise SystemExit(f"Cannot find microservices folder at: {ms_dir}")

    pkg_name = "src.microservices"

    print(f"Scanning: {ms_dir}")
    print("")

    for m in pkgutil.iter_modules([str(ms_dir)]):
        mod_name = f"{pkg_name}.{m.name}"
        try:
            mod = importlib.import_module(mod_name)
        except Exception as e:
            print(f"[IMPORT FAIL] {mod_name}: {e}")
            continue

        for name, obj in vars(mod).items():
            if isinstance(obj, type) and name.endswith("MS"):
                try:
                    sig = inspect.signature(obj.__init__)
                except Exception:
                    continue

                params = list(sig.parameters.values())[1:]  # skip self
                required = [
                    p for p in params
                    if p.default is inspect._empty
                    and p.kind in (p.POSITIONAL_OR_KEYWORD, p.KEYWORD_ONLY)
                ]
                if required:
                    print(f"{name}.__init__ requires: {[p.name for p in required]}  ({mod_name})")


if __name__ == "__main__":
    main()
