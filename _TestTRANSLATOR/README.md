# _LogicINJECTOR

A local AI tool to inject raw Python logic into standardized microservice boilerplates.

## Current Architecture ("Rewrite Strategy")
- **Engine:** Python (Tkinter) + Ollama
- **Model:** `qwen2.5-coder:7b` (Recommended)
- **Method:** Sends Origin + Boilerplate to LLM and asks it to merge them while fixing bugs.

## How to Use
1. Run `python LogicInjector.py`.
2. Select your `Origin Logic` file (the raw script).
3. Select your `Boilerplate` file (the class structure).
4. Click **INJECT & SAVE**.
5. **Review the Output:** Check the bottom of the file to ensure the `if __name__` block is indented correctly.

## Roadmap / Future Improvements
### The "Mad Libs" Architecture (Planned)
The current method relies on the LLM to rewrite the *entire* file, which risks dropping imports or helper functions.
**Future Plan:**
1. **Templating:** Convert Boilerplate into a template string with tags (e.g., `<IMPORTS>`, `<LOGIC>`).
2. **Extraction:** Ask LLM *only* to extract the logic chunks, not rewrite the whole file.
3. **Assembly:** Python script inserts the chunks into the safe template.
   - *Benefit:* 100% guarantee that class structure and helpers are never deleted.
   - *Benefit:* Allows use of smaller/faster models (3B).