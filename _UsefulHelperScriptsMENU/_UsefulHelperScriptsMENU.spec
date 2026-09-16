# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:\\Users\\jacob\\Documents\\_UsefulHelperSCRIPTS\\_UsefulHelperScriptsMENU\\src\\app.pyw'],
    pathex=['C:\\Users\\jacob\\Documents\\_UsefulHelperSCRIPTS\\_UsefulHelperScriptsMENU'],
    binaries=[],
    datas=[('C:\\Users\\jacob\\Documents\\_UsefulHelperSCRIPTS\\_UsefulHelperScriptsMENU\\assets', 'assets'), ('C:\\Users\\jacob\\Documents\\_UsefulHelperSCRIPTS\\_UsefulHelperScriptsMENU\\assets', 'assets'), ('C:\\Users\\jacob\\Documents\\_UsefulHelperSCRIPTS\\_UsefulHelperScriptsMENU\\src', 'src'), ('C:\\Users\\jacob\\Documents\\_UsefulHelperSCRIPTS\\_UsefulHelperScriptsMENU\\build', 'build'), ('C:\\Users\\jacob\\Documents\\_UsefulHelperSCRIPTS\\_UsefulHelperScriptsMENU\\dist', 'dist')],
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
    name='_UsefulHelperScriptsMENU',
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
    icon=['C:\\Users\\jacob\\Documents\\_UsefulHelperSCRIPTS\\_UsefulHelperScriptsMENU\\assets\\icons\\_UsefulHelperSCRIPTS.ico'],
)
