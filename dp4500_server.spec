# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec for DigitalPersona 4500 Web & REST API Server (Windows .exe)

import os
import sys
from PyInstaller.utils.hooks import collect_submodules, collect_data_files

block_cipher = None

# Collect all dp4500 submodules
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
    'dp4500.utils',
    'dp4500.utils.udev',
    'PIL',
    'PIL.Image',
    'numpy',
    'ctypes',
    'http.server',
    'socketserver',
    'webbrowser',
    'threading',
    'json',
]

# Bundle web assets (web_client.html, dp4500-client.js)
datas = [
    ('examples/web_client.html', 'examples'),
    ('examples/dp4500-client.js', 'examples'),
]

# If Windows DLLs (dpfpdd.dll / dpfj.dll / nex_sdk.dll etc.) are in the working directory, bundle them too
binaries = []
for dll in ['DPFPApi.dll', 'dpfpdd.dll', 'dpfj.dll', 'nex_sdk.dll', 'dpfpdd_4k.dll', 'dpfpdd_ptapi.dll', 'dpfr6.dll', 'dpfr7.dll']:
    if os.path.exists(dll):
        binaries.append((dll, '.'))

a = Analysis(
    ['examples/http_server.py'],
    pathex=['.'],
    binaries=binaries,
    datas=datas,
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
    name='dp4500_server',
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
