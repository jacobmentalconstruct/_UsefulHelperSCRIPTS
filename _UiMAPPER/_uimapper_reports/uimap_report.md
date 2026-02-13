# UI Mapper Report
_Generated: 2026-02-12T18:44:23_

**Project Root:** `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER`

## Summary
- Windows detected: **2**
- Widgets detected: **23**
- Unknown cases: **0**
- Parse errors: **0**

## Windows
### win1
- Created at: `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER\src\microservices\_TkinterAppShellMS.py:51:8`
### win4
- Created at: `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER\src\microservices\_TkinterSmartExplorerMS.py:57:4`

## Widgets
### Button (4)
- **w10** (parent: `w8`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER\src\ui.py:222:8`
  - kwargs:
    - `command` = `self._browse_folder`
    - `text` = `'Browse…'`
  - layout:
    - `grid(row=1, column=1, sticky='e', padx=Tuple, pady=Tuple)`
  - commands:
    - `self._browse_folder`
- **w14** (parent: `w8`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER\src\ui.py:237:8`
  - kwargs:
    - `command` = `self._run_clicked`
    - `style` = `'Accent.TButton'`
    - `text` = `'Run'`
  - layout:
    - `grid(row=6, column=0, sticky='ew', pady=Tuple)`
  - commands:
    - `self._run_clicked`
- **w15** (parent: `w8`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER\src\ui.py:240:8`
  - kwargs:
    - `command` = `self._cancel_clicked`
    - `text` = `'Cancel'`
  - layout:
    - `grid(row=7, column=0, sticky='ew', pady=Tuple)`
  - commands:
    - `self._cancel_clicked`
- **w16** (parent: `w8`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER\src\ui.py:243:8`
  - kwargs:
    - `command` = `self._open_report_folder`
    - `text` = `'Open Report Folder'`
  - layout:
    - `grid(row=8, column=0, sticky='ew', pady=Tuple)`
  - commands:
    - `self._open_report_folder`

### Checkbutton (2)
- **w11** (parent: `w8`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER\src\ui.py:226:8`
  - kwargs:
    - `text` = `'Include .pyw'`
    - `variable` = `self.var_include_pyw`
  - layout:
    - `grid(row=2, column=0, sticky='w', pady=Tuple)`
- **w12** (parent: `w8`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER\src\ui.py:229:8`
  - kwargs:
    - `text` = `'Enable inference (Ollama)'`
    - `variable` = `self.var_enable_inference`
  - layout:
    - `grid(row=3, column=0, sticky='w', pady=Tuple)`

### Entry (2)
- **w13** (parent: `w8`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER\src\ui.py:233:8`
  - kwargs:
    - `textvariable` = `self.var_model`
  - layout:
    - `grid(row=5, column=0, columnspan=2, sticky='ew', pady=Tuple)`
- **w9** (parent: `w8`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER\src\ui.py:220:8`
  - kwargs:
    - `textvariable` = `self.var_project_root`
    - `width` = `42`
  - layout:
    - `grid(row=1, column=0, sticky='ew', pady=Tuple)`

### Frame (8)
- **w1** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER\src\ui.py:158:8`
  - kwargs:
    - `style` = `'TFrame'`
- **w2** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER\src\ui.py:182:8`
  - kwargs:
    - `style` = `'Panel.TFrame'`
  - layout:
    - `pack(fill='x', padx=10, pady=Tuple)`
- **w20** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER\src\ui.py:280:8`
  - kwargs:
    - `style` = `'Panel.TFrame'`
  - layout:
    - `pack(fill='x', pady=Tuple)`
- **w21** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER\src\ui.py:287:8`
  - kwargs:
    - `style` = `'TFrame'`
  - layout:
    - `pack(fill='x', padx=10, pady=Tuple)`
- **w5** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER\src\ui.py:195:8`
  - kwargs:
    - `style` = `'TFrame'`
  - layout:
    - `pack(fill='both', expand=True, padx=10, pady=6)`
- **w6** (parent: `w5`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER\src\ui.py:199:8`
  - kwargs:
    - `style` = `'Panel.TFrame'`
  - layout:
    - `pack(side='left', fill='y', padx=Tuple, pady=0)`
  - config:
    - `configure(padding=10)`
- **w7** (parent: `w5`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER\src\ui.py:206:8`
  - kwargs:
    - `style` = `'Panel.TFrame'`
  - layout:
    - `pack(side='left', fill='both', expand=True, padx=Tuple, pady=0)`
  - config:
    - `configure(padding=10)`
- **w8** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER\src\ui.py:215:8`
  - kwargs:
    - `style` = `'Panel.TFrame'`
  - layout:
    - `pack(fill='x')`

### Label (3)
- **w17** (parent: `w8`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER\src\ui.py:248:8`
  - kwargs:
    - `background` = `THEME.panel`
    - `style` = `'Muted.TLabel'`
    - `text` = `''`
- **w3** (parent: `w2`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER\src\ui.py:185:8`
  - kwargs:
    - `background` = `THEME.panel`
    - `font` = `Tuple`
    - `foreground` = `THEME.fg`
    - `text` = `'UiMAPPER'`
  - layout:
    - `grid(row=0, column=0, sticky='w', padx=10, pady=8)`
- **w4** (parent: `w2`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER\src\ui.py:188:8`
  - kwargs:
    - `background` = `THEME.panel`
    - `style` = `'Muted.TLabel'`
    - `text` = `'idle'`

### Text (2)
- **w18** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER\src\ui.py:254:8`
  - kwargs:
    - `bg` = `THEME.entry_bg`
    - `fg` = `THEME.fg`
    - `height` = `18`
    - `insertbackground` = `THEME.fg`
    - `relief` = `'flat'`
    - `wrap` = `'word'`
  - layout:
    - `pack(fill='both', expand=False)`
  - config:
    - `configure(state='disabled')`
- **w23** (parent: `w22`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER\src\ui.py:427:8`
  - kwargs:
    - `bg` = `THEME.entry_bg`
    - `fg` = `THEME.fg`
    - `insertbackground` = `THEME.fg`
    - `relief` = `'flat'`
    - `wrap` = `'none'`
  - layout:
    - `pack(fill='both', expand=True, padx=10, pady=10)`
  - config:
    - `configure(state='disabled')`

### Toplevel (1)
- **w22** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER\src\ui.py:423:8`
  - config:
    - `configure(bg=THEME.bg)`

### Treeview (1)
- **w19** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER\src\ui.py:271:8`
  - kwargs:
    - `columns` = `cols`
    - `height` = `18`
    - `show` = `'headings'`
  - layout:
    - `pack(fill='both', expand=True)`


## Unknown Cases
_None._

## Parse Errors
_None._
