# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:\\Users\\jacob\\Documents\\_UsefulHelperSCRIPTS\\_TokenizingPATCHER\\src\\app.py'],
    pathex=['C:\\Users\\jacob\\Documents\\_UsefulHelperSCRIPTS\\_TokenizingPATCHER'],
    binaries=[],
    datas=[('C:\\Users\\jacob\\Documents\\_UsefulHelperSCRIPTS\\_TokenizingPATCHER\\assets', 'assets'), ('C:\\Users\\jacob\\Documents\\_UsefulHelperSCRIPTS\\_TokenizingPATCHER\\assets', 'assets'), ('C:\\Users\\jacob\\Documents\\_UsefulHelperSCRIPTS\\_TokenizingPATCHER\\src', 'src')],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='_TokenizingPATCHER',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['C:\\Users\\jacob\\Documents\\_UsefulHelperSCRIPTS\\_TokenizingPATCHER\\assets\\icons\\tokenizing-patcher.ico'],
)
