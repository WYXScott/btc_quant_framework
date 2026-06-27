# Windows venv / pip launcher fix

If `pip install -r requirements.txt` shows a launcher error containing an old path, delete and recreate the virtual environment. Prefer a path without Chinese characters or spaces.

```powershell
cd C:\btc_quant_framework_v3_0_2
if (Test-Path .venv) { Remove-Item -Recurse -Force .venv }
py -3 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
python -m pip install -r requirements.txt
```

Use `python -m pip ...` instead of `pip ...` to avoid stale pip.exe launcher paths.
