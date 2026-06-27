# Release Notes V2.3

## 主要变化

V2.3 是一次软件包回顾、界面完善和研究工作流收口版本，暂不开放实盘交易。

新增：

- Streamlit 前端 `frontend/app.py`；
- 前端启动脚本 `scripts/run_dashboard.py`；
- 软件包审查模块 `src/crypto_quant/ui/package_audit.py`；
- 软件包审查脚本 `scripts/audit_package.py`；
- 安全研究流程脚本 `scripts/run_safe_research_pipeline.py`；
- 软件回顾与前端说明文档 `docs/SOFTWARE_REVIEW_AND_UI.md`；
- `ui` 配置段，用于限制前端按钮可执行脚本。

## 安全边界

- 不开放实盘自动下单；
- 前端不提供真实交易按钮；
- 前端按钮只允许执行 `ui.allowed_button_scripts` 中的安全脚本；
- Live Trading 总闸仍应保持关闭。

## 推荐启动

```bash
pip install -r requirements.txt
python scripts/run_dashboard.py
```
