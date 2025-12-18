import os
import re

def sync_class_names():
    print("--- 🔄 Starting Class Name Sync ---")
    
    # Get all python files in the current folder
    files = [f for f in os.listdir('.') if f.endswith('.py')]
    
    updates_count = 0

    for filename in files:
        # We only strictly enforce this on your "MS" files (starting with __)
        # to avoid messing up system files like base_service.py
        if not filename.startswith("__"):
            continue

        # 1. Determine the Target Class Name
        # Remove extension
        name_no_ext = filename[:-3] 
        # Remove leading underscores (e.g., "__CartridgeServiceMS" -> "CartridgeServiceMS")
        target_class_name = name_no_ext.lstrip("_")

        # 2. Read the file
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()

        # 3. Find the current class definition
        # Regex explanation:
        # ^class\s+  -> Starts with 'class' followed by whitespace
        # (\w+)      -> Capture the class name (Group 1)
        # (.*):      -> Capture inheritance/rest of line until colon (Group 2)
        match = re.search(r'class\s+(\w+)(.*):', content)

        if match:
            current_class_name = match.group(1)
            inheritance_part = match.group(2)

            # 4. Check if mismatch
            if current_class_name != target_class_name:
                print(f"🔧 Updating {filename}...")
                print(f"   - Old: class {current_class_name}")
                print(f"   - New: class {target_class_name}")

                # 5. Replace the definition line
                # We use regex sub to replace only the definition line
                new_def_line = f"class {target_class_name}{inheritance_part}:"
                content = content.replace(match.group(0), new_def_line)

                # 6. OPTIONAL: Attempt to replace self-references in the file
                # If the file instantiates itself (e.g. app = OldName()), update that too.
                # Use word boundaries (\b) to avoid replacing partial words.
                content = re.sub(rf'\b{current_class_name}\b', target_class_name, content)

                # 7. Write back
                with open(filename, 'w', encoding='utf-8') as f:
                    f.write(content)
                
                updates_count += 1
            else:
                print(f"✅ {filename} is already correct ({target_class_name}).")
        else:
            print(f"⚠️ Skipped {filename}: Could not find a standard class definition.")

    print(f"--- ✨ Sync Complete. Updated {updates_count} files. ---")

if __name__ == "__main__":
    sync_class_names()