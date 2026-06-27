# Release Notes V3.2.0

V3.2.0 improves dashboard usability and model-training clarity.

## Added

- Guided **开始使用** page.
- Dedicated **模型训练向导** page.
- Sidebar work modes: 新手模式, 研究验证, 运行监控, 高级工具箱.
- Artifact-based recommended next step on the starter page.
- Model-training configuration summary and result-interpretation tabs.
- `src/crypto_quant/ui/product_flow.py` for navigation and training workflow definitions.
- `docs/UI_NAVIGATION_AND_MODEL_TRAINING.md`.
- `docs/VERSION_STATUS_V3_2_0.md`.

## Changed

- Dashboard default navigation no longer exposes every page as one flat list.
- Existing pages are preserved but grouped by user intent.
- README current version and frontend description updated.

## Safety

No live-trading safety switch was relaxed. The release only changes local UI organization and guidance.
