# Validation record

Validated on 2026-09-01 from commit `9eeae1abb5e1325908ef61150d910a770376c9e5` on Windows with Python 3.13.

## Command and result

```powershell
py -3.13 -m venv work/envs/creative-litang --system-site-packages
work/envs/creative-litang/Scripts/python.exe -m pip install -r requirements.txt
work/envs/creative-litang/Scripts/python.exe -m pytest -q tests --ignore=tests/test_anr_smoke.py
```

Result: 37 passed.

`tests/test_anr_smoke.py` was excluded because it requires an external ANR installation, detector model, and associated runtime that are intentionally absent from the source repository.

## UI check

The current `app` module was launched from the isolated snapshot. The screenshot `docs/screenshots/toolbox-home.png` uses the neutral output path `C:\Temp\litang-demo-output`; no image was imported and no processing job was started.

This record does not validate the external detector, Real-CUGAN runtime, Windows one-click archive, or historical Android APK.
