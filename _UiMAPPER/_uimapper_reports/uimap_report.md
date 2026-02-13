# UI Mapper Report
_Generated: 2026-02-12T19:07:55_

**Project Root:** `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER`

## Summary
- Windows detected: **2**
- Widgets detected: **26**
- Unknown cases: **0**
- Parse errors: **0**

## Windows
### win1
- Created at: `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER\src\microservices\_TkinterAppShellMS.py:51:8`
### win4
- Created at: `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER\src\microservices\OllamaModelSelectorMS.py:213:4`
- Title calls:
  - `root.title('Ollama Selector Test')`
- Geometry calls:
  - `root.geometry('520x120')`

## Widgets
### Button (4)
- **w10** (parent: `w8`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER\src\ui.py:225:8`
  - kwargs:
    - `command` = `self._browse_folder`
    - `text` = `'Browse…'`
  - layout:
    - `grid(row=1, column=1, sticky='e', padx=Tuple, pady=Tuple)`
  - commands:
    - `self._browse_folder`
- **w13** (parent: `w8`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER\src\ui.py:250:8`
  - kwargs:
    - `command` = `self._run_clicked`
    - `style` = `'Accent.TButton'`
    - `text` = `'Run'`
  - layout:
    - `grid(row=6, column=0, sticky='ew', pady=Tuple)`
  - commands:
    - `self._run_clicked`
- **w14** (parent: `w8`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER\src\ui.py:253:8`
  - kwargs:
    - `command` = `self._cancel_clicked`
    - `text` = `'Cancel'`
  - layout:
    - `grid(row=7, column=0, sticky='ew', pady=Tuple)`
  - commands:
    - `self._cancel_clicked`
- **w15** (parent: `w8`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER\src\ui.py:256:8`
  - kwargs:
    - `command` = `self._open_report_folder`
    - `text` = `'Open Report Folder'`
  - layout:
    - `grid(row=8, column=0, sticky='ew', pady=Tuple)`
  - commands:
    - `self._open_report_folder`

### Checkbutton (2)
- **w11** (parent: `w8`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER\src\ui.py:229:8`
  - kwargs:
    - `text` = `'Include .pyw'`
    - `variable` = `self.var_include_pyw`
  - layout:
    - `grid(row=2, column=0, sticky='w', pady=Tuple)`
- **w12** (parent: `w8`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER\src\ui.py:232:8`
  - kwargs:
    - `text` = `'Enable inference (Ollama)'`
    - `variable` = `self.var_enable_inference`
  - layout:
    - `grid(row=3, column=0, sticky='w', pady=Tuple)`

### Entry (1)
- **w9** (parent: `w8`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER\src\ui.py:223:8`
  - kwargs:
    - `textvariable` = `self.var_project_root`
    - `width` = `42`
  - layout:
    - `grid(row=1, column=0, sticky='ew', pady=Tuple)`

### Frame (10)
- **w1** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER\src\ui.py:161:8`
  - kwargs:
    - `style` = `'TFrame'`
- **w19** (parent: `w18`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER\src\ui.py:287:8`
  - kwargs:
    - `style` = `'Panel.TFrame'`
- **w2** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER\src\ui.py:185:8`
  - kwargs:
    - `style` = `'Panel.TFrame'`
  - layout:
    - `pack(fill='x', padx=10, pady=Tuple)`
- **w21** (parent: `w18`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER\src\ui.py:301:8`
  - kwargs:
    - `style` = `'Panel.TFrame'`
- **w23** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER\src\ui.py:314:8`
  - kwargs:
    - `style` = `'Panel.TFrame'`
  - layout:
    - `pack(fill='x', pady=Tuple)`
- **w24** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER\src\ui.py:321:8`
  - kwargs:
    - `style` = `'TFrame'`
  - layout:
    - `pack(fill='x', padx=10, pady=Tuple)`
- **w5** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER\src\ui.py:198:8`
  - kwargs:
    - `style` = `'TFrame'`
  - layout:
    - `pack(fill='both', expand=True, padx=10, pady=6)`
- **w6** (parent: `w5`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER\src\ui.py:202:8`
  - kwargs:
    - `style` = `'Panel.TFrame'`
  - layout:
    - `pack(side='left', fill='y', padx=Tuple, pady=0)`
  - config:
    - `configure(padding=10)`
- **w7** (parent: `w5`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER\src\ui.py:209:8`
  - kwargs:
    - `style` = `'Panel.TFrame'`
  - layout:
    - `pack(side='left', fill='both', expand=True, padx=Tuple, pady=0)`
  - config:
    - `configure(padding=10)`
- **w8** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER\src\ui.py:218:8`
  - kwargs:
    - `style` = `'Panel.TFrame'`
  - layout:
    - `pack(fill='x')`

### Label (3)
- **w16** (parent: `w8`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER\src\ui.py:261:8`
  - kwargs:
    - `background` = `THEME.panel`
    - `style` = `'Muted.TLabel'`
    - `text` = `''`
- **w3** (parent: `w2`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER\src\ui.py:188:8`
  - kwargs:
    - `background` = `THEME.panel`
    - `font` = `Tuple`
    - `foreground` = `THEME.fg`
    - `text` = `'UiMAPPER'`
  - layout:
    - `grid(row=0, column=0, sticky='w', padx=10, pady=8)`
- **w4** (parent: `w2`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER\src\ui.py:191:8`
  - kwargs:
    - `background` = `THEME.panel`
    - `style` = `'Muted.TLabel'`
    - `text` = `'idle'`

### Notebook (1)
- **w18** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER\src\ui.py:283:8`
  - layout:
    - `pack(fill='both', expand=True)`

### Text (2)
- **w17** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER\src\ui.py:267:8`
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
- **w26** (parent: `w25`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER\src\ui.py:557:8`
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
- **w25** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER\src\ui.py:553:8`
  - config:
    - `configure(bg=THEME.bg)`

### Treeview (2)
- **w20** (parent: `w19`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER\src\ui.py:291:8`
  - kwargs:
    - `columns` = `cols`
    - `height` = `18`
    - `show` = `'headings'`
  - layout:
    - `pack(fill='both', expand=True)`
- **w22** (parent: `w21`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_UiMAPPER\src\ui.py:305:8`
  - kwargs:
    - `columns` = `st_cols`
    - `height` = `18`
    - `show` = `'tree headings'`
  - layout:
    - `pack(fill='both', expand=True)`


## Unknown Cases
_None._

## Parse Errors
_None._
