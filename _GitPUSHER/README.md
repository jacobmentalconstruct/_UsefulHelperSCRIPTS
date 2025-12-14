Based on the code provided, here is a professional, comprehensive, and clean `README.md` file. It highlights the dual nature of the tool (GUI + CLI), its zero-dependency architecture, and its safety features.

-----

# Git Commit & Push Helper

A lightweight, zero-dependency Python tool designed to streamline the `git add .` $\to$ `git commit` $\to$ `git push` workflow. It features a modern Dark Mode GUI for desktop use and a fully functional CLI for automation scripts.

## 🚀 Features

  * **Hybrid Interface:** Run it as a GUI application or a Command Line utility.
  * **Workflow Automation:** Performs `add`, `commit`, and `push` in a single action.
  * **Safety First:**
      * Validates that the target folder is a Git repository.
      * **Stop-gap Logic:** Warns you (or blocks operation) if a `.gitignore` file is missing, preventing the accidental commit of virtual environments or build artifacts.
  * **Zero Dependencies:** Built entirely with the Python Standard Library (`tkinter`, `subprocess`, etc.). No `pip install` required.
  * **Dark Mode UI:** A custom-styled Tkinter interface designed for low-eye-strain environments.
  * **Recursion Detection:** Intelligently detects if you are using the tool to commit changes to the tool's own repository.

## 📋 Prerequisites

  * **Python 3.x**
  * **Git** (Must be installed and accessible via system PATH)

## 🛠️ Installation

1.  Clone this repository or download `app.py`.
2.  That's it. There are no external requirements to install.

## 🖥️ Usage: GUI Mode

Simply run the script without arguments:

```bash
python app.py
```

### interface Controls

  * **Repository:** Defaults to the current working directory. You can type a path or use the **"…"** button to browse.
  * **Commit Message:** Enter your message here. Press `<Enter>` to trigger the commit.
  * **Log Window:** Displays real-time output from the Git subprocesses.

> **Note:** If you launch the app from within a git repository, it will automatically detect the root and prepopulate the path.

## ⌨️ Usage: CLI Mode

You can use the tool in headless environments or build scripts by passing arguments.

### Basic Commit & Push

```bash
python app.py -m "Refactored the core engine"
```

### Specify a different repository

```bash
python app.py --repo "C:/Projects/MyWebsite" -m "Update CSS"
```

### Push Only (Skip commit)

```bash
python app.py --push-only
```

### Force commit without .gitignore

By default, the CLI will fail if `.gitignore` is missing. You can override this:

```bash
python app.py -m "Initial commit" --force-without-gitignore
```

### CLI Arguments Reference

| Argument | Description |
| :--- | :--- |
| `-r`, `--repo` | Path to the target repository (Default: current dir). |
| `-m`, `--message` | The commit message (Required unless using `--push-only`). |
| `--push-only` | Skips `add` and `commit`, executes only `git push`. |
| `--force-without-gitignore` | Bypasses the safety check for missing `.gitignore` files. |

## 🛡️ Safety Mechanisms

### The `.gitignore` Check

One of the most common mistakes in rapid development is running `git add .` inside a folder containing a `venv/` or `node_modules/`.

  * **GUI:** Prompts a Human-in-the-Loop (HITL) warning dialog asking for confirmation before proceeding.
  * **CLI:** Aborts immediately unless the `--force-without-gitignore` flag is used.

### Porcelain Status

The tool utilizes `git status --porcelain` to programmatically ensure the working tree actually has changes before attempting a commit, preventing empty commit errors.

## 📄 License

Open Source. Feel free to modify and integrate into your own workflows.