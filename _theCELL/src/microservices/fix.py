import os
import re

def repair_microservices():
    # Targets for relative import conversion
    targets = ["base_service", "microservice_std_lib"]
    
    # Pattern: Matches 'from X import' or 'import X' where X is a target
    # but specifically avoids lines that already start with a dot.
    patterns = {
        target: (
            re.compile(rf"^(?!\s*from\s+\.)(\s*from\s+{target}\s+import)"),
            rf"from .{target} import"
        ) for target in targets
    }

    # Identify current directory (intended to be src/microservices/)
    current_dir = os.path.dirname(os.path.abspath(__file__))
    files_processed = 0
    files_repaired = 0

    print(f"--- Starting Import Repair in: {current_dir} ---")

    for filename in os.listdir(current_dir):
        if filename.endswith(".py") and filename not in ["repair_imports.py", "base_service.py", "microservice_std_lib.py"]:
            file_path = os.path.join(current_dir, filename)
            files_processed += 1
            
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()

            new_content = content
            modified = False

            for target, (pattern, replacement) in patterns.items():
                if pattern.search(new_content):
                    new_content = pattern.sub(replacement, new_content)
                    modified = True

            if modified:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                print(f"✅ Repaired: {filename}")
                files_repaired += 1
            else:
                # No change needed
                pass

    print(f"\n--- Scan Complete ---")
    print(f"Files Checked: {files_processed}")
    print(f"Files Repaired: {files_repaired}")

if __name__ == "__main__":
    repair_microservices()