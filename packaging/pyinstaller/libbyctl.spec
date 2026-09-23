# Build with: pyinstaller packaging/pyinstaller/libbyctl.spec
from PyInstaller.utils.hooks import collect_submodules

hiddenimports = []
try:
    hiddenimports.extend(collect_submodules("keyring.backends"))
except Exception:
    # macOS uses the native `security` CLI and intentionally has no keyring dependency.
    pass

a = Analysis(
    ["src/libbyctl/__main__.py"],
    pathex=["src"],
    binaries=[],
    datas=[],
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="libbyctl",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)
