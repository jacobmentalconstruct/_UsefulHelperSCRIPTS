# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['C:\\Users\\petya\\Documents\\_JacobBIN\\_UsefulHelperSCRIPTS\\_GitPUSHER\\src\\app.py'],
    pathex=['C:\\Users\\petya\\Documents\\_JacobBIN\\_UsefulHelperSCRIPTS\\_GitPUSHER'],
    binaries=[],
    datas=[('C:\\Users\\petya\\Documents\\_JacobBIN\\_UsefulHelperSCRIPTS\\_GitPUSHER\\assets', 'assets'), ('C:\\Users\\petya\\Documents\\_JacobBIN\\_UsefulHelperSCRIPTS\\_GitPUSHER\\assets', 'assets')],
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
    name='_GitPUSHER',
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
    icon=['C:\\Users\\petya\\Documents\\_JacobBIN\\_UsefulHelperSCRIPTS\\_GitPUSHER\\assets\\icons\\_GitPUSHER.ico'],
)
