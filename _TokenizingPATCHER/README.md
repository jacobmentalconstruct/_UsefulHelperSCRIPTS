# **\_TokenizingPATCHER v4.3**

***TokenizingPATCHER*** is a precision code modification utility designed to apply surgical updates to source files using a structured JSON patching schema. Unlike traditional line-based diff tools, it tokenizes lines into indentation, content, and trailing whitespace, allowing it to maintain perfect structural alignment even when code is moved across different nesting levels.

## **🚀 Key Features**

* **Intelligent Tokenization**: Preserves file integrity by separating leading indentation from logical content.  
* **Hybrid Interface**:  
  * **GUI Mode**: A modern, dark-themed Tkinter interface for manual patch management, versioning, and real-time diff previews.  
  * **CLI Mode**: A headless entry point for automated pipelines and CI/CD integration.  
* **Validation Engine**: A "Dry Run" system that verifies "Hunk" matches before committing any changes to disk.  
* **Structural Indentation**:  
  * **Relative Mode**: Automatically re-calculates patch indentation to match the target file's current scope.  
  * **Strict Mode**: Forces the patch's exact whitespace (ideal for YAML or strictly linted files).  
* **Safety "Linked" UI**: The "Unified Button Group" allows users to link the *Validate* and *Apply* actions to ensure only verified patches are executed.

## **🛠 Usage**

### **1\. GUI Mode (Showcase)**

Launch the rich interface by running the script directly:  
python app.py

* **Load File**: Open the source file you wish to modify.  
* **Input Patch**: Paste your JSON schema into the patch editor.  
* **Validate**: Check the status bar for match success. Toggle "Show Diff Preview" to see exactly what will change.  
* **Apply**: Commit the changes to the editor.  
* **Version**: Enable versioning to save the result with a custom suffix (e.g., main\_v1.0.py).

### **2\. CLI Mode (Automation)**

Integrate the patcher into your scripts:  
python app.py \<target\_file\> \<patch\_json\> \--output \<output\_file\>

**Flags:**

* \--force-indent: Disable relative indentation logic.  
* \--dry-run: Exit with success/failure status without writing to the file.

## **📄 Patch Schema Definition**

The patcher expects a JSON object containing a list of hunks. Each hunk represents a single search-and-replace operation.  
{  
  "hunks": \[  
    {  
      "description": "Human readable summary of the change",  
      "search\_block": "def old\_method():\\n    print('hello')",  
      "replace\_block": "def new\_method():\\n    print('world')",  
      "use\_patch\_indent": false  
    }  
  \]  
}

### **Hunk Parameters:**

| Key | Type | Description |
| :---- | :---- | :---- |
| search\_block | String | The exact text to find (multi-line supported). |
| replace\_block | String | The text to insert in place of the search block. |
| use\_patch\_indent | Boolean | If true, ignores the target file's indentation and uses the JSON's literal whitespace. |

## **⚖️ Technical Requirements**

* **Python 3.8+**  
* **Standard Library Only**: No external pip installs required (uses tkinter, json, difflib, re, argparse).