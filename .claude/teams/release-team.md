# Release Team (發版團隊)

## Composition

發版準備團隊，負責確認所有品質關卡通過並準備發版所需的版號更新與文件。

### Members

| Agent | Role | Phase |
|-------|------|-------|
| test-planner | 完整測試驗證 | Phase 1: Quality Gate (parallel) |
| security-reviewer | 安全最終審查 | Phase 1: Quality Gate (parallel) |
| feature-driver | 版號確認與 CHANGELOG 定稿 | Phase 2: Release Prep (parallel) |
| doc-organizer | 文件最終確認 | Phase 2: Release Prep (parallel) |
| implementer | 版號更新 (pyproject.toml, __init__.py) | Phase 3: Version Bump |

### Pipeline

```
Phase 1 (Quality Gate)          Phase 2 (Release Prep)        Phase 3 (Version Bump)
[test-planner       ]           [feature-driver    ]
                     ──────────→                    ──────────→ implementer
[security-reviewer  ]           [doc-organizer     ]
```

**Gate rule**: 每個階段必須全部通過才進入下一階段。

## Coordination Rules

### Phase 1: Quality Gate (品質關卡)

兩個代理同時進行最終品質驗證：

```yaml
quality_gate:
  test-planner:
    scope: full_test_suite
    actions:
      - run: "uv run pytest tests/ -v --tb=short"
      - run: "uv run pytest tests/ --cov=csp_lib --cov-report=term-missing"
      - verify: all tests pass
      - verify: coverage >= 80%
    output:
      status: pass|fail
      test_count: int
      pass_count: int
      fail_count: int
      coverage_pct: float
      failures: TestFailure[]  # if any

  security-reviewer:
    scope: full_codebase
    actions:
      - review: all csp_lib/**/*.py
      - review: all tests/**/*.py (for credential leaks)
      - verify: no critical findings
      - verify: no unresolved high findings
    output:
      status: pass|fail
      findings_summary: FindingsSummary
      blocking_issues: string[]  # critical/high items

  gate_pass_condition:
    - test-planner.status = pass
    - security-reviewer.status = pass
    - security-reviewer.blocking_issues.length = 0

  on_gate_fail:
    - 產出失敗報告，列出阻擋發版的問題
    - 回傳給 feature-team 修復
    - 修復後重新進入 Phase 1
```

### Phase 2: Release Prep (發版準備)

通過品質關卡後，兩個代理同時準備發版資料：

```yaml
release_prep:
  feature-driver:
    actions:
      - 確認 version_target 與實際變更一致
      - 確認 SemVer 版號正確（major/minor/patch）
      - 定稿 CHANGELOG 條目
    output:
      confirmed_version: string
      changelog_final: ChangelogEntry
      breaking_changes: string[]  # if any

  doc-organizer:
    actions:
      - 驗證 CHANGELOG.md 格式與內容
      - 驗證 README.md 更新
      - 驗證所有新 API 有文件
      - 確認文件交叉引用完整
    output:
      status: pass|fail
      doc_issues: string[]  # if any
      changelog_valid: boolean
      readme_valid: boolean

  prep_pass_condition:
    - feature-driver.confirmed_version is set
    - doc-organizer.status = pass

  on_prep_fail:
    - doc-organizer 直接修復文件問題
    - feature-driver 調整 CHANGELOG
    - 重新驗證
```

### Phase 3: Version Bump (版號更新)

最終由 implementer 執行版號更新：

```yaml
version_bump:
  implementer:
    actions:
      - update: pyproject.toml → version = confirmed_version
      - update: csp_lib/__init__.py → __version__ = confirmed_version
      - verify:
          - "uv run ruff check csp_lib/__init__.py"
          - "python -c \"import csp_lib; print(csp_lib.__version__)\""
    output:
      version_updated: boolean
      files_changed: string[]
      verification: pass|fail

  bump_pass_condition:
    - implementer.verification = pass
    - version matches confirmed_version
```

## Release Checklist (發版檢查清單)

最終產出的發版檢查清單：

```yaml
release_checklist:
  version: string                    # 發版版號
  date: string                       # 預定發版日期
  ready_to_tag: boolean              # 是否可以打 tag

  quality:
    all_tests_pass: boolean
    test_coverage_pct: float
    no_security_critical: boolean
    no_security_high: boolean

  documentation:
    changelog_updated: boolean
    readme_updated: boolean
    api_docs_complete: boolean

  version:
    pyproject_toml_updated: boolean
    init_py_updated: boolean
    version_consistent: boolean      # 所有位置版號一致

  ci_cd:
    lint_pass: boolean
    type_check_pass: boolean
    cython_build_pass: boolean       # python build_wheel.py

  breaking_changes: string[]         # 重大變更列表 (if any)

  sign_off:
    test-planner: pass|fail
    security-reviewer: pass|fail
    feature-driver: pass|fail
    doc-organizer: pass|fail
    implementer: pass|fail

  ready_to_tag_rules:
    all_must_be_true:
      - quality.all_tests_pass
      - quality.no_security_critical
      - quality.no_security_high
      - documentation.changelog_updated
      - version.version_consistent
      - ci_cd.lint_pass
      - ci_cd.type_check_pass
      - all sign_off = pass
```

## File Ownership (Release Mode)

| Directory / File | Phase 1 | Phase 2 | Phase 3 |
|-----------------|---------|---------|---------|
| `csp_lib/**/*.py` | read | read | **write** (implementer: version only) |
| `tests/**/*.py` | read (run) | read | read |
| `docs/**/*.md` | read | **write** (doc-organizer) | read |
| `CHANGELOG.md` | read | **write** (doc-organizer) | read |
| `README.md` | read | **write** (doc-organizer) | read |
| `pyproject.toml` | read | read | **write** (implementer: version only) |
| `.github/**` | read | read | read |

## Activation

使用此團隊模板準備發版：

```
/team release-team --version "0.4.0" --branch "v0.4.0"
```

## Post-Release

發版後的後續步驟（由 human 執行）：

```bash
# 1. 確認 release_checklist.ready_to_tag = true
# 2. 建立 git tag
git tag -a v0.4.0 -m "Release v0.4.0"
git push origin v0.4.0
# 3. GitHub Actions 自動觸發 CI/CD → 建構 wheel → 發布到 PyPI
# 4. 驗證 PyPI 上的新版本
pip install csp0924_lib==0.4.0
```
