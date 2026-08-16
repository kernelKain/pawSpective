# Controlled demo source

Place the manually recorded 5–15 second landscape clip here as
`controlled-demo-original.mp4`. Keep it below 30 MB and include one red toy,
one blue toy, a green background, and a moving subject with minimal shake.

The source clip is intentionally not committed. Build the offline cache with:

```powershell
$env:PAWSPECTIVE_DEMO_MODE = "false"
.\.venv\Scripts\python.exe scripts\build_demo_cache.py --force
```
