# Builds the Windows app into dist/control_devices/.
#
#     .venv\Scripts\python.exe -m PyInstaller control_devices.spec --noconfirm
#
# A folder rather than a single .exe: it starts faster, because nothing has to be
# unpacked on each launch, and antivirus tools tend to flag it less often.

from PyInstaller.utils.hooks import collect_all

# MediaPipe loads native libraries and data files that PyInstaller cannot see by itself.
mediapipe_datas, mediapipe_binaries, mediapipe_imports = collect_all("mediapipe")

analysis = Analysis(
    ["windows_app.py"],
    datas=[("models/hand_landmarker.task", "models")] + mediapipe_datas,
    binaries=mediapipe_binaries,
    hiddenimports=mediapipe_imports,
)

archive = PYZ(analysis.pure)

executable = EXE(
    archive,
    analysis.scripts,
    # Unbuffered, so messages appear at once even when the output is sent to a file.
    [("u", None, "OPTION")],
    exclude_binaries=True,
    name="control_devices",
    # The console shows the instructions and the gesture log.
    console=True,
)

COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    name="control_devices",
)
