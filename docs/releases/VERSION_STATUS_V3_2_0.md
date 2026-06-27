# V3.2.0 Version Status And Frontend UX Refactor

V3.2.0 focuses on frontend information architecture and model-training usability.

## Main changes

- Added a guided **开始使用** page.
- Added a dedicated **模型训练向导** page.
- Reorganized the sidebar into four work modes:
  - 新手模式
  - 研究验证
  - 运行监控
  - 高级工具箱
- Reduced the default number of visible choices for new users.
- Kept legacy and low-level tools available under advanced navigation.
- Added model-training explanations and artifact-based next-step recommendation.
- Added documentation for UI navigation and model-training interpretation.

## Why this matters

Before V3.2.0, the Streamlit sidebar exposed many pages at once. That was powerful, but it made it hard to know the correct order of operations, especially around model training.

The new structure separates:

- first-run guidance;
- research validation;
- runtime monitoring;
- advanced debugging.

## Current safety posture

V3.2.0 does not relax execution safety:

- live trading remains blocked by default;
- UI live actions remain disabled;
- broker live trading remains disabled;
- local paper trading remains the default execution mode;
- OKX private trading remains intentionally blocked until a dedicated adapter exists.

## Recommended local validation

Run these from the project root after activating `.venv`:

```powershell
.\.venv\Scripts\Activate.ps1
python scripts\check_runtime_env.py --strict
python scripts\run_stability_check.py
python scripts\manage_services.py status
python tests\smoke_test.py
.\start_dashboard.cmd
```

Then open the dashboard and start from **新手模式 → 开始使用**.
