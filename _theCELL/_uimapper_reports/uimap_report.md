# UI Mapper Report
_Generated: 2026-02-12T19:08:12_

**Project Root:** `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL`

## Summary
- Windows detected: **4**
- Widgets detected: **56**
- Unknown cases: **0**
- Parse errors: **0**

## Windows
### win1
- Created at: `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\microservices\_TkinterAppShellMS.py:51:8`
### win3
- Created at: `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\microservices\_OllamaModelSelectorMS.py:131:4`
- Title calls:
  - `root.title('Ollama Selector Test')`
- Geometry calls:
  - `root.geometry('400x100')`
### win4
- Created at: `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\microservices\_TkinterSmartExplorerMS.py:57:4`
### win5
- Created at: `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\microservices\_LogViewMS.py:148:4`
- Title calls:
  - `root.title('Log View Test')`
- Geometry calls:
  - `root.geometry('600x400')`

## Widgets
### Button (15)
- **w10** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:216:8`
  - kwargs:
    - `command` = `self._italic_text`
    - `font` = `Tuple`
    - `text` = `'I'`
  - commands:
    - `self._italic_text`
- **w11** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:218:8`
  - kwargs:
    - `command` = `self._bullet_list`
    - `text` = `'• List'`
  - commands:
    - `self._bullet_list`
- **w12** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:221:8`
  - kwargs:
    - `command` = `self._open_settings`
    - `text` = `'⚙'`
  - commands:
    - `self._open_settings`
- **w19** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:253:8`
  - kwargs:
    - `bg` = `self.colors.get(...)`
    - `command` = `Lambda`
    - `fg` = `self.colors.get(...)`
    - `relief` = `'flat'`
    - `text` = `'💾'`
  - commands:
    - `Lambda`
- **w20** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:256:8`
  - kwargs:
    - `bg` = `self.colors.get(...)`
    - `command` = `Lambda`
    - `fg` = `self.colors.get(...)`
    - `relief` = `'flat'`
    - `text` = `'📂'`
  - commands:
    - `Lambda`
- **w25** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:278:8`
  - kwargs:
    - `bg` = `self.colors.get(...)`
    - `command` = `Lambda`
    - `fg` = `self.colors.get(...)`
    - `relief` = `'flat'`
    - `text` = `'💾'`
  - commands:
    - `Lambda`
- **w26** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:281:8`
  - kwargs:
    - `bg` = `self.colors.get(...)`
    - `command` = `Lambda`
    - `fg` = `self.colors.get(...)`
    - `relief` = `'flat'`
    - `text` = `'📂'`
  - commands:
    - `Lambda`
- **w29** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:305:8`
  - kwargs:
    - `bg` = `self.colors.get(...)`
    - `command` = `self._save_full_template`
    - `fg` = `self.colors.get(...)`
    - `font` = `Tuple`
    - `text` = `'SAVE AS TEMPLATE'`
  - commands:
    - `self._save_full_template`
- **w30** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:315:8`
  - kwargs:
    - `bg` = `self.colors.get(...)`
    - `command` = `Lambda`
    - `fg` = `self.colors.get(...)`
    - `font` = `Tuple`
    - `text` = `'LOAD TEMPLATE'`
  - commands:
    - `Lambda`
- **w31** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:325:8`
  - kwargs:
    - `bg` = `self.colors.get(...)`
    - `command` = `self._submit`
    - `fg` = `self.colors.get(...)`
    - `font` = `Tuple`
    - `text` = `'RUN CELL'`
  - commands:
    - `self._submit`
- **w37** (parent: `w36`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:388:8`
  - kwargs:
    - `bg` = `self.colors.get(...)`
    - `command` = `self._on_accept`
    - `fg` = `self.colors.get(...)`
    - `relief` = `'flat'`
    - `state` = `'disabled'`
    - `text` = `'ACCEPT'`
  - commands:
    - `self._on_accept`
- **w38** (parent: `w36`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:399:8`
  - kwargs:
    - `bg` = `self.colors.get(...)`
    - `command` = `self._on_reject`
    - `fg` = `self.colors.get(...)`
    - `relief` = `'flat'`
    - `state` = `'disabled'`
    - `text` = `'REJECT & EDIT'`
  - commands:
    - `self._on_reject`
- **w39** (parent: `w36`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:410:8`
  - kwargs:
    - `bg` = `self.colors.get(...)`
    - `command` = `self.shell.root.destroy`
    - `fg` = `self.colors.get(...)`
    - `relief` = `'flat'`
    - `text` = `'EXIT CELL'`
  - commands:
    - `self.shell.root.destroy`
- **w44** (parent: `w42`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:447:8`
  - kwargs:
    - `bg` = `self.colors.get(...)`
    - `command` = `self._handle_export`
    - `fg` = `self.colors.get(...)`
    - `relief` = `'flat'`
    - `state` = `'disabled'`
    - `text` = `'EXECUTE'`
  - commands:
    - `self._handle_export`
- **w9** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:214:8`
  - kwargs:
    - `command` = `self._bold_text`
    - `font` = `Tuple`
    - `text` = `'B'`
  - commands:
    - `self._bold_text`

### Combobox (3)
- **w15** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:234:8`
  - kwargs:
    - `textvariable` = `self.model_var`
- **w43** (parent: `w42`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:439:8`
  - kwargs:
    - `state` = `'readonly'`
    - `textvariable` = `self.export_dest_var`
    - `values` = `List`
- **w51** (parent: `w49`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:693:8`
  - kwargs:
    - `state` = `'readonly'`
    - `textvariable` = `theme_var`
    - `values` = `List`
  - layout:
    - `pack(pady=2)`

### Entry (3)
- **w18** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:244:8`
  - kwargs:
    - `bg` = `self.colors.get(...)`
    - `fg` = `self.colors.get(...)`
    - `insertbackground` = `self.colors.get(...)`
- **w47** (parent: `w46`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:601:8`
  - layout:
    - `pack(padx=10, fill='x')`
- **w53** (parent: `w49`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:700:8`
  - kwargs:
    - `bg` = `self.colors.get(...)`
    - `fg` = `self.colors.get(...)`
    - `insertbackground` = `self.colors.get(...)`
    - `relief` = `'flat'`
  - layout:
    - `pack(pady=2)`
  - config:
    - `configure(bg=self.colors.get(...), fg=self.colors.get(...), insertbackground=self.colors.get(...))`

### Frame (17)
- **w17** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:241:8`
  - kwargs:
    - `bg` = `self.colors.get(...)`
- **w2** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:48:8`
  - kwargs:
    - `bg` = `colors.get(...)`
- **w22** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:263:8`
  - kwargs:
    - `bg` = `self.colors.get(...)`
- **w24** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:276:8`
  - kwargs:
    - `bg` = `self.colors.get(...)`
- **w28** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:302:8`
  - kwargs:
    - `bg` = `self.colors.get(...)`
- **w3** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:190:8`
  - kwargs:
    - `bg` = `self.colors.get(...)`
- **w36** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:385:8`
  - kwargs:
    - `bg` = `self.colors.get(...)`
  - layout:
    - `pack(fill='x', padx=10, pady=Tuple)`
- **w4** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:193:8`
  - kwargs:
    - `bg` = `self.colors.get(...)`
- **w41** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:430:8`
  - kwargs:
    - `bg` = `self.colors.get(...)`
- **w42** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:433:8`
  - kwargs:
    - `bg` = `self.colors.get(...)`
  - layout:
    - `pack(fill='x')`
- **w45** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:455:8`
  - kwargs:
    - `bg` = `self.colors.get(...)`
- **w48** (parent: `w46`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:636:8`
  - kwargs:
    - `bg` = `self.colors.get(...)`
  - layout:
    - `pack(pady=10)`
- **w5** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:196:8`
  - kwargs:
    - `bg` = `self.colors.get(...)`
- **w54** (parent: `w49`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:711:8`
  - kwargs:
    - `bg` = `self.colors.get(...)`
  - layout:
    - `pack(side='bottom', fill='x', pady=20)`
  - config:
    - `configure(bg=self.colors.get(...))`
- **w55** (parent: `w54`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:798:8`
  - kwargs:
    - `bg` = `self.colors.get(...)`
  - layout:
    - `pack(anchor='center')`
- **w6** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:200:8`
  - kwargs:
    - `bg` = `self.colors.get(...)`
- **w8** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:210:8`
  - kwargs:
    - `bg` = `self.colors.get(...)`

### Label (6)
- **w14** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:231:8`
  - kwargs:
    - `bg` = `self.colors.get(...)`
    - `fg` = `self.colors.get(...)`
    - `text` = `'Model:'`
- **w16** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:239:8`
  - kwargs:
    - `bg` = `self.colors.get(...)`
    - `fg` = `self.colors.get(...)`
    - `text` = `'System Role:'`
- **w21** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:261:8`
  - kwargs:
    - `bg` = `self.colors.get(...)`
    - `fg` = `self.colors.get(...)`
    - `text` = `'System Prompt:'`
- **w50** (parent: `w49`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:689:8`
  - kwargs:
    - `bg` = `self.colors.get(...)`
    - `fg` = `self.colors.get(...)`
    - `text` = `'Theme:'`
  - layout:
    - `pack(pady=Tuple)`
  - config:
    - `configure(bg=self.colors.get(...), fg=self.colors.get(...))`
- **w52** (parent: `w49`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:697:8`
  - kwargs:
    - `bg` = `self.colors.get(...)`
    - `fg` = `self.colors.get(...)`
    - `text` = `'Window Size (WxH):'`
  - layout:
    - `pack(pady=Tuple)`
  - config:
    - `configure(bg=self.colors.get(...), fg=self.colors.get(...))`
- **w7** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:204:8`
  - kwargs:
    - `bg` = `self.colors.get(...)`
    - `fg` = `self.colors.get(...)`
    - `font` = `Tuple`
    - `text` = `'Type in your idea HERE.'`

### LabelFrame (4)
- **w13** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:225:8`
  - kwargs:
    - `bd` = `1`
    - `bg` = `self.colors.get(...)`
    - `fg` = `self.colors.get(...)`
    - `font` = `Tuple`
    - `relief` = `'solid'`
    - `text` = `' Inference Parameters '`
- **w32** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:338:8`
  - kwargs:
    - `bd` = `1`
    - `bg` = `self.colors.get(...)`
    - `fg` = `self.colors.get(...)`
    - `font` = `Tuple`
    - `relief` = `'solid'`
    - `text` = `' Inference Console '`
- **w34** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:363:8`
  - kwargs:
    - `bd` = `1`
    - `bg` = `self.colors.get(...)`
    - `fg` = `self.colors.get(...)`
    - `font` = `Tuple`
    - `relief` = `'solid'`
    - `text` = `' Result + HITL '`
- **w40** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:421:8`
  - kwargs:
    - `bd` = `1`
    - `bg` = `self.colors.get(...)`
    - `fg` = `self.colors.get(...)`
    - `font` = `Tuple`
    - `relief` = `'solid'`
    - `text` = `' Export / Spawn '`

### Menu (1)
- **w56** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:813:8`
  - kwargs:
    - `tearoff` = `0`

### Text (4)
- **w23** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:266:8`
  - kwargs:
    - `bg` = `self.colors.get(...)`
    - `fg` = `self.colors.get(...)`
    - `font` = `Tuple`
    - `height` = `3`
    - `insertbackground` = `self.colors.get(...)`
- **w27** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:288:8`
  - kwargs:
    - `bg` = `self.colors.get(...)`
    - `fg` = `self.colors.get(...)`
    - `font` = `Tuple`
    - `insertbackground` = `self.colors.get(...)`
    - `selectbackground` = `self.colors.get(...)`
    - `undo` = `True`
    - `wrap` = `'word'`
- **w33** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:347:8`
  - kwargs:
    - `bg` = `self.colors.get(...)`
    - `fg` = `self.colors.get(...)`
    - `font` = `Tuple`
    - `height` = `6`
    - `insertbackground` = `self.colors.get(...)`
    - `wrap` = `'word'`
- **w35** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:372:8`
  - kwargs:
    - `bg` = `self.colors.get(...)`
    - `fg` = `self.colors.get(...)`
    - `font` = `Tuple`
    - `height` = `8`
    - `insertbackground` = `self.colors.get(...)`
    - `wrap` = `'word'`

### Toplevel (2)
- **w46** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:592:8`
  - config:
    - `configure(bg=self.colors.get(...))`
  - binds:
    - `'<Return>' -> Lambda`
    - `'<Escape>' -> Lambda`
- **w49** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:668:8`
  - config:
    - `configure(bg=self.colors.get(...))`
    - `configure(bg=self.colors.get(...))`

### Treeview (1)
- **w1** (parent: `None`) — created at `C:\Users\jacob\Documents\_UsefulHelperSCRIPTS\_theCELL\src\ui.py:35:8`
  - kwargs:
    - `columns` = `Tuple`
    - `show` = `'headings'`


## Unknown Cases
_None._

## Parse Errors
_None._
