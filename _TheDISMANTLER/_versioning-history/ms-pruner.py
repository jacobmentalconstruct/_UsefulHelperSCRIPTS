import os
import shutil
from pathlib import Path

def collect_logic():
    # Define targets
    base_dir = Path(".")
    keep_dir = base_dir / "_V2_LOGIC_SEED"
    os.makedirs(keep_dir, exist_ok=True)

    # Map of {Source File Path : New Descriptive Name}
    files_to_harvest = {
        "src/_LEGACY_MICROSERVICES/_OllamaModelSelectorMS.py": "ai_connector_logic.py",
        "src/_LEGACY_MICROSERVICES/_LogViewMS.py": "logging_sink_logic.py",
        "src/_LEGACY_MICROSERVICES/_DataCurationTOOLS/viewer.py": "ui_notebook_scaffold.py",
        "src/_LEGACY_MICROSERVICES/_DataCurationTOOLS/db/schema.py": "sqlite_schema.py",
        "src/_LEGACY_MICROSERVICES/_DataCurationTOOLS/db/query.py": "sliding_window_queries.py",
        "src/_LEGACY_MICROSERVICES/_DataCurationTOOLS/pipeline/detect.py": "file_detection_logic.py",
        "src/_LEGACY_MICROSERVICES/_DataCurationTOOLS/chunkers/treesitter.py": "ast_parser_logic.py",
        "src/_LEGACY_MICROSERVICES/_DataCurationTOOLS/diff_engine.py": "version_tracking.py",
        "src/_LEGACY_MICROSERVICES/_DataCurationTOOLS/settings_dialog.py": "modal_factory_base.py"
    }

    print(f"--- Harvesting logic for v2.0 build ---")
    for src_rel, dest_name in files_to_harvest.items():
        src_path = base_dir / src_rel
        if src_path.exists():
            shutil.copy2(src_path, keep_dir / dest_name)
            print(f"✓ Collected: {src_rel}")
        else:
            print(f"✗ Missing: {src_rel}")

    print(f"\nLogic seeds are ready in: {keep_dir}")

if __name__ == "__main__":
    collect_logic()