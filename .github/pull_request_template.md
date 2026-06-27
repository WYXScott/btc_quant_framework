## Summary
<!-- Briefly describe the change and its motivation -->



## Scope
<!-- Which modules/docs/configs are touched? -->



## Checklist

- [ ] Smoke test passed: `python tests/smoke_test.py`
- [ ] Config/defaults are safety-gated (no live trading enabled)
- [ ] Docs updated (README, INDEX, version-status, release-notes)
- [ ] New scripts referenced in `scripts/run_stability_check.py` `_check_allowed_scripts`
- [ ] New services registered in `config/config.yaml` → `managed_services.allowed`

## Version
<!-- If this is a new version bump, confirm these are in sync: -->
- [ ] `pyproject.toml` `version`
- [ ] `config/config.yaml` `project.version`
- [ ] `README.md` version badge
- [ ] `docs/INDEX.md` version links
