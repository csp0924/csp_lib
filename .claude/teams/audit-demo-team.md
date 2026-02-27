# Audit-Demo Team (品質稽核與整合示範團隊)

## Composition

品質稽核 + 整合修復 + 測試強化 + 全系統示範，4 階段流水線。

### Members

| Agent | Role | Phase |
|-------|------|-------|
| test-planner | 測試缺口稽核 | Phase 1: 稽核 (parallel) |
| architect | 整合斷點稽核 | Phase 1: 稽核 (parallel), Phase 2: 修復設計 |
| security-reviewer | 安全缺口稽核 | Phase 1: 稽核 (parallel) |
| implementer | 修復實作 + Demo 建置 | Phase 2: 修復實作, Phase 4: Demo |
| doc-organizer | 文件更新 | Phase 4: 文件 (parallel) |

### Pipeline

```
Phase 1 (Audit)           Phase 2 (Fix)              Phase 3 (Test)         Phase 4 (Demo+Docs)
[test-planner      ]      architect → implementer     test-planner           [implementer    ]
[architect         ]  →                            →                      →  [               ]
[security-reviewer ]                                                         [doc-organizer  ]
```

## Coordination Rules

### Phase 1: Audit (平行稽核)

3 agents read-only 同時掃描，各自產出稽核報告：

| Agent | Focus | Output |
|-------|-------|--------|
| test-planner | 測試缺口：無測試模組、薄覆蓋模組、缺失邊緣案例、anti-patterns | `coverage_gap_report` |
| architect | 整合斷點：未匯出 class、未連接介面、依賴方向違規、unused API | `integration_gap_report` |
| security-reviewer | 安全缺口：Modbus write bounds、shared state without lock、hardcoded secrets | `security_gap_report` |

**Gate**: 三份報告合併為 `audit_report` 才進入 Phase 2。

### Phase 2: Fix Design + Implementation (修復整合斷點)

1. architect 讀取 `audit_report` → 產出 `fix_plan`（介面補丁、`__init__.py` 更新、optional parameters）
2. implementer 根據 `fix_plan` 實作 → ruff + mypy + 既有測試無 regression
3. 迭代：architect ↔ implementer（max 2）

**Gate**: ruff pass, mypy pass, existing tests pass。

### Phase 3: Test Hardening (補齊測試)

1. test-planner 根據 `coverage_gap_report` + Phase 2 新增碼 → 補測試 + 邊緣案例
2. 迭代：test-planner → implementer（max 3，修 bug）

**Gate**: all tests pass, no critical gaps remaining。

### Phase 4: Demo Build + Documentation (平行)

- implementer 建立 `examples/demo_full_system.py`：SimulationServer + AsyncModbusDevice + SystemController，單一 `async def main()` 入口（不含 GUI）
- doc-organizer 更新 README + CHANGELOG + 文件缺口

**Gate**: demo runs without error, README updated, CHANGELOG updated。

### Iteration Loops (迭代迴圈)

| Loop | Agents | Max Iterations | Exit Condition |
|------|--------|----------------|----------------|
| Fix Refinement | architect ↔ implementer | 2 | implementer 確認修復完成，ruff + mypy pass |
| Test-Fix | test-planner → implementer | 3 | 全部測試通過 |

### Escalation Rules

- 超過 max iterations → 升級給 human review
- architect 判定修復需變更 public API → 回到 Phase 1 重新評估影響
- security-reviewer 發現 critical → 強制中斷，通知 human

## File Ownership Boundary (檔案所有權邊界)

嚴格非重疊，依 Phase 區分寫入權限：

| Path | Ph1 | Ph2 | Ph3 | Ph4 |
|------|-----|-----|-----|-----|
| `csp_lib/**/*.py` | read | **write** (implementer) | read | **write** (implementer: demo utils only) |
| `tests/**/*.py` | read | read | **write** (test-planner) | read |
| `examples/*.py` | read | read | read | **write** (implementer) |
| `docs/**/*.md`, `CHANGELOG.md`, `README.md` | read | read | read | **write** (doc-organizer) |
| `pyproject.toml`, `.github/**`, `build_wheel.py`, `setup.py` | read | read | read | read (human only) |

**Special case**: Phase 2 implementer 只能修改 `csp_lib/**/*.py`；Phase 4 implementer 只能新增 `examples/*.py`。

## Handoff Protocols

### Phase 1 → Phase 2: Audit → Fix Design

```yaml
handoff:
  from: [test-planner, architect, security-reviewer]
  to: architect
  artifact: audit_report
  required_fields:
    - coverage_gap_report (from test-planner)
    - integration_gap_report (from architect)
    - security_gap_report (from security-reviewer)
  validation:
    - 3 reports all completed
    - each report has severity classification
  gate: 3 reports completed
  on_failure: incomplete agent re-runs audit
```

### Phase 2 → Phase 3: Fix Implementation → Test Hardening

```yaml
handoff:
  from: implementer
  to: test-planner
  artifact: implementation_result
  required_fields:
    - files_created OR files_modified (at least 1)
    - verification.ruff_check = pass
    - verification.ruff_format = pass
    - verification.mypy = pass
    - verification.existing_tests = pass
  validation:
    - ruff + mypy 全部通過
    - 既有測試無 regression
  gate: [ruff pass, mypy pass, existing tests pass]
  on_failure: implementer 修復 lint/type/regression 錯誤
```

### Phase 3 → Phase 4: Test Hardening → Demo + Docs

```yaml
handoff:
  from: test-planner
  to: [implementer, doc-organizer]
  artifact: test_result
  required_fields:
    - all new tests pass
    - no critical coverage gaps remaining
    - test count summary
  validation:
    - pytest 全部通過
    - critical gaps resolved
  gate: [all tests pass, no critical gaps remaining]
  on_failure: test-planner → implementer fix loop (max 3)
```

### Completion Gate

```yaml
completion:
  gate:
    - demo runs without error
    - README updated
    - CHANGELOG updated
  validation:
    - "uv run python examples/demo_full_system.py" exits 0
    - CHANGELOG contains audit-demo entry
    - README references demo entry point
```

## Final Output

```yaml
audit_demo_output:
  audit_report:
    coverage_gaps: CoverageGapReport
    integration_gaps: IntegrationGapReport
    security_gaps: SecurityGapReport
    resolved_count: int
    remaining_count: int
  demo:
    entry_point: "examples/demo_full_system.py"
    run_command: "uv run python examples/demo_full_system.py"
  test_hardening:
    new_test_files: string[]
    new_test_count: int
```

## Activation

使用此團隊模板進行品質稽核與整合示範：

```
/team audit-demo-team
```

或手動依序啟動各階段：

1. 同時啟動 test-planner、architect、security-reviewer 進行 Phase 1 稽核
2. 合併三份報告為 `audit_report`，交給 architect 設計修復方案
3. implementer 根據 `fix_plan` 實作修復（Phase 2）
4. test-planner 根據缺口報告補齊測試（Phase 3）
5. 同時啟動 implementer（建立 demo）與 doc-organizer（更新文件）（Phase 4）
