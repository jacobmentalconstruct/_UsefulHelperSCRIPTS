# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:\\Users\\petya\\Documents\\_JacobBIN\\_UsefulHelperSCRIPTS\\_UsefulHelperScriptsMENU\\src\\app.pyw'],
    pathex=['C:\\Users\\petya\\Documents\\_JacobBIN\\_UsefulHelperSCRIPTS\\_UsefulHelperScriptsMENU'],
    binaries=[],
    datas=[('C:\\Users\\petya\\Documents\\_JacobBIN\\_UsefulHelperSCRIPTS\\_UsefulHelperScriptsMENU\\assets', 'assets'), ('C:\\Users\\petya\\Documents\\_JacobBIN\\_UsefulHelperSCRIPTS\\_UsefulHelperScriptsMENU\\assets', 'assets')],
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
    [],
    exclude_binaries=True,
    name='_UsefulHelperScriptsMENU',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['C:\\Users\\petya\\Documents\\_JacobBIN\\_UsefulHelperSCRIPTS\\_UsefulHelperScriptsMENU\\assets\\icons\\_UsefulHelperSCRIPTS.ico'],
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='_UsefulHelperScriptsMENU',
)
