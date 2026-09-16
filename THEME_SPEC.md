## **THEME\_SPEC.md**

### **🎨 Suite-Wide Visual Identity**

**Version:** 1.0 (Based on Project Mapper Aesthetic)  
**Philosophy:** High-contrast dark mode using "Midnight Blue" and "Deep Slate" foundations with "Deep Blue" interactive accents.

### ---

**1\. Core Color Palette**

| Element | Hex Code | Usage |
| :---- | :---- | :---- |
| **Primary Background** | \#1e1e2f | Main Window background and selector modal background.  |
| **Secondary Background** | \#151521 | Listboxes, Text Areas, and "Inset" regions.  |
| **Widget Surface** | \#2a2a3f | Buttons and Toolbars before interaction.  |
| **Action Accent** | \#007ACC | Selection highlights, Hover states, and "Create" buttons.  |
| **Status Accent** | \#00FF00 | Terminal outputs or success messages in text areas. |

### ---

**2\. Typography**

* **Primary UI Font:** Segoe UI, size 9 or 10\.

* **Code/Mono Font:** Consolas, size 9\.

* **Heading Style:** Segoe UI, 10, Bold.

### ---

**3\. Widget Specifications (Tkinter/ttk)**

To maintain alignment in future tools, follow these standard styling rules:

* **Listboxes:** \* borderwidth: 0  
  * highlightthickness: 1  
  * highlightbackground: \#333333

* **Buttons (TButton):**  
  * Use the clam theme as a base.

  * Map the active (hover) state to the **Action Accent** (\#007ACC).

* **Input Fields:**  
  * Use insertbackground: white to ensure the blinking cursor is visible on dark backgrounds.

### ---

**4\. Component Implementation Logic**

When building a new microservice or app, ensure the UI initialization includes:

1. Setting the root window background to \#1e1e2f.  
2. Configuring a ttk.Style that maps background colors for TFrame and TLabel to match the Primary Background.  
3. Explicitly setting Canvas backgrounds to \#1e1e2f to avoid the default Tkinter gray flickering.

