# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for DigitalPersona 4500 CLI Executable (dp4500.exe)

import os
import sys

block_cipher = None

hidden_imports = [
    'dp4500',
    'dp4500.backends',
    'dp4500.backends.base',
    'dp4500.backends.official_sdk',
    'dp4500.backends.mock',
    'dp4500.backends.libfprint',
    'dp4500.image',
    'dp4500.template',
    'dp4500.matching',
    'dp4500.reader',
    'dp4500.manager',
    'dp4500.cli',
    'PIL',
    'PIL.Image',
    'numpy',
    'ctypes',
]

binaries = []
for dll in ['dpfpdd.dll', 'dpfj.dll']:
    if os.path.exists(dll):
        binaries.append((dll, '.'))

a = Analysis(
    ['dp4500/__main__.py'],
    pathex=['.'],
    binaries=binaries,
    datas=[],
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='dp4500',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
