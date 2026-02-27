# Feature Team (功能開發團隊)

## Composition

完整功能開發團隊，涵蓋從需求到交付的全流程。

### Members

| Agent | Role | Phase |
|-------|------|-------|
| feature-driver | 功能推進 | Phase 1: 需求拆解 |
| architect | 架構設計 | Phase 2: 架構設計 |
| implementer | 功能實現 | Phase 3: 程式實作 |
| test-planner | 測試規劃 | Phase 4: 驗證 (parallel) |
| security-reviewer | 安全檢視 | Phase 4: 驗證 (parallel) |
| performance-optimizer | 效能優化 | Phase 5: 效能 |
| doc-organizer | 文件整理 | Phase 6: 文件 |

### Pipeline

```
Phase 1          Phase 2          Phase 3          Phase 4                Phase 5              Phase 6
feature-driver → architect    →   implementer  →  [test-planner      →   performance      →   doc-organizer
                                                    ∥                     -optimizer
                                                   security-reviewer]
```

## Coordination Rules

### Iteration Loops (迭代迴圈)

| Loop | Agents | Max Iterations | Exit Condition |
|------|--------|----------------|----------------|
| Design Refinement | architect ↔ implementer | 2 | implementer 確認設計可實作 |
| Test-Fix | test-planner → implementer | 3 | 全部測試通過 |
| Security-Fix | security-reviewer → implementer | 2 | 無 critical/high findings |

### Escalation Rules

- 超過 max iterations → 升級給 human review
- architect 判定 feasibility = rejected → 回到 feature-driver 修改需求
- security-reviewer 發現 critical → 強制中斷，通知 human

## File Ownership Boundary (檔案所有權邊界)

嚴格非重疊，確保無寫入衝突：

| Directory / File | Owner | Others |
|-----------------|-------|--------|
| `csp_lib/**/*.py` | implementer | read (all others) |
| `tests/**/*.py` | test-planner | read (all others) |
| `docs/**/*.md` | doc-organizer | read (all others) |
| `CHANGELOG.md` | doc-organizer | read (feature-driver drafts in handoff) |
| `README.md`, `BUILDING.md` | doc-organizer | read |
| `examples/*.py` | implementer | read |
| `project.md` | feature-driver | read |
| `pyproject.toml` | human (manual) | read |
| `.github/**` | human (manual) | read |
| `build_wheel.py`, `setup.py` | human (manual) | read |

**Special case**: performance-optimizer 可寫入 `csp_lib/**/*.py`，但必須經 implementer 協調確認。

## Handoff Protocols

### Phase 1 → Phase 2: Requirement → Architecture

```yaml
handoff:
  from: feature-driver
  to: architect
  artifact: feature_spec
  required_fields:
    - version_target
    - affected_layers
    - work_items (at least 1)
    - acceptance_criteria (at least 3)
    - risks (at least 1)
  validation:
    - work_items 無循環依賴
    - affected_layers 均為合法值
  on_failure: feature-driver 補充缺失欄位
```

### Phase 2 → Phase 3: Architecture → Implementation

```yaml
handoff:
  from: architect
  to: implementer
  artifact: architecture_decision
  required_fields:
    - api_contracts (at least 1)
    - dependency_map (all directions = valid)
    - new_files OR modified_files (at least 1)
  validation:
    - 無層級依賴違規 (dependency_map)
    - api_contracts 型別簽名完整
  on_failure: architect 修正設計
```

### Phase 3 → Phase 4: Implementation → Verification

```yaml
handoff:
  from: implementer
  to: [test-planner, security-reviewer]  # parallel
  artifact: implementation_result
  required_fields:
    - files_created OR files_modified (at least 1)
    - verification.ruff_check = pass
    - verification.ruff_format = pass
    - verification.mypy = pass
  validation:
    - ruff + mypy 全部通過
    - import test 通過
  on_failure: implementer 修復 lint/type 錯誤
```

### Phase 4 → Phase 5: Verification → Performance

```yaml
handoff:
  from: [test-planner, security-reviewer]
  to: performance-optimizer
  artifact: [test_result, security_report]
  required_fields:
    test_result:
      - all tests pass
      - coverage >= 80%
    security_report:
      - no critical findings
      - no high findings (or all remediated)
  validation:
    - 測試全部通過
    - 安全報告無 critical/high 未解決
  on_failure:
    - test failures → implementer 修復 (test-fix loop)
    - security findings → implementer 修復 (security-fix loop)
```

### Phase 5 → Phase 6: Performance → Documentation

```yaml
handoff:
  from: performance-optimizer
  to: doc-organizer
  artifact: optimization_result
  required_fields:
    - cython_compatibility.compatible = true (or issues all resolved)
    - analysis (at least scanned target files)
  validation:
    - Cython 相容
    - 無 high impact 未處理的效能問題
  on_failure: implementer 套用 optimization_suggestions
```

## Activation

使用此團隊模板開發新功能：

```
/team feature-team --feature "功能名稱" --description "功能描述"
```

或手動依序啟動各階段：

1. 啟動 feature-driver 拆解需求
2. 將 feature_spec 交給 architect
3. 將 architecture_decision 交給 implementer
4. 同時啟動 test-planner 與 security-reviewer
5. 通過後啟動 performance-optimizer
6. 最後啟動 doc-organizer 更新文件
