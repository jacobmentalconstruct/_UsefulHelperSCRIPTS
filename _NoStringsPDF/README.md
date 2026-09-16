# NoStringsPDF

**The Industrial-Grade, Local-First PDF Manipulator.**

NoStringsPDF is a privacy-respecting, lightweight desktop application for managing PDF documents. It runs entirely on your machine—no cloud uploads, no subscriptions, and no watermarks. Just raw, efficient utility.

---

## ⚡ Core Features

### 1. View & Navigate
* **High-Speed Rendering:** Powered by PyMuPDF for instant page loads.
* **Smart Zoom:** Fluid zooming with mouse wheel (Ctrl+Scroll) or toolbar buttons.
* **Thumbnail Grid:** Interactive sidebar for quick navigation.

### 2. Organize & Edit
* **Drag-and-Drop Reordering:** Click and drag thumbnails to rearrange pages. Visual indicators show exactly where pages will land.
* **Visual Rotation:** Rotate individual pages 90° CW or CCW instantly.
* **Delete Pages:** Right-click or press `Delete` to remove unwanted pages.
* **Insert Files:** Inject another PDF document anywhere into your current file.

### 3. Advanced Tools
* **Scanner Interleave:** Fix double-sided scans by merging two files (e.g., "Odd Pages" + "Even Pages"). Includes a **Reverse Order** option for face-down stacks.
* **Smart Split:** Break large documents into chunks based on file size (e.g., "Split into 5MB chunks")—perfect for email limits.
* **Precision Extract:** Save specific pages or ranges (e.g., `1, 3, 5-10`) into a new file.
* **Pro Compression:** Export with granular control over DPI, JPEG Quality, and Grayscale conversion to drastically reduce file size.

---

## 🚀 How to Use

### Installation
**No installation required.** This is a portable application.
1.  Unzip the release folder.
2.  Run `NoStringsPDF.exe`.
3.  (Optional) Right-click a PDF file > **Open with** > Select `NoStringsPDF.exe` to make it your default.

### Key Shortcuts
| Action | Shortcut |
| :--- | :--- |
| **Next Page** | Right Arrow / Scroll Down |
| **Prev Page** | Left Arrow / Scroll Up |
| **Zoom In/Out** | Ctrl + Scroll |
| **Delete Page** | Delete Key |
| **Context Menu** | Right-Click on Viewer |

---

## 🛠️ For Developers

Built with **Python**, **Tkinter**, and **PyMuPDF**.

### Project Structure
* `src/microservices`: Core logic (PDF Engine, UI components, Theme Manager).
* `src/orchestrators`: UI logic and event handling.
* `assets`: Icon resources.

### Running from Source
1.  Run `setup_env.bat` to create the virtual environment.
2.  Run `src/app.py` via the environment python.

### Building the Exe
Run `build_exe.bat`. This script will:
1.  Compile the code using PyInstaller.
2.  Bundle all dependencies.
3.  Copy the `assets` folder.
4.  Generate a release-ready ZIP file.

---

## 📄 License

**MIT License**
Copyright (c) 2025 Jacob Lambert

Free software. Do whatever you want with it.