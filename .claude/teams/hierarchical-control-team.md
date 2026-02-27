# Hierarchical Control Design Team (階層控制設計團隊)

## Composition

階層控制架構設計團隊，涵蓋從擴展點分析到原型實作的全流程。聚焦於 SubExecutorAgent Protocol、TransportAdapter 抽象、gRPC 服務定義、以及 CascadingStrategy 專用 Demo。

### Members

| Agent | Role | Phase |
|-------|------|-------|
| architect | 擴展點分析 + 架構設計 | Phase 1: 分析 (parallel), Phase 2: 設計 (parallel) |
| security-reviewer | 遠端 dispatch 安全評估 | Phase 1: 分析 (parallel) |
| performance-optimizer | 傳輸效能分析 | Phase 1: 分析 (parallel) |
| feature-driver | 需求規格定義 | Phase 2: 規格 (parallel) |
| implementer | 原型實作 | Phase 3: 實作 (parallel) |
| test-planner | 測試撰寫 | Phase 3: 測試 (parallel) |
| doc-organizer | 文件整理 | Phase 4: 文件 |

### Pipeline

```
Phase 1 (Analysis)           Phase 2 (Design)         Phase 3 (Prototype)       Phase 4 (Docs)
[architect            ]      [architect      ]         [implementer    ]         doc-organizer
[security-reviewer    ]  →   [               ]  →      [               ]  →
[performance-optimizer]      [feature-driver ]         [test-planner   ]
```

## Coordination Rules

### Phase 1: Analysis (平行分析，read-only)

3 agents read-only 同時分析，各自產出分析報告：

| Agent | Focus | Output |
|-------|-------|--------|
| architect | 擴展點盤點（`set_context_provider`、`set_on_command`、`ExecutionMode.TRIGGERED`、`push_override`）、介面缺口分析、層級放置建議、CascadingStrategy 多層適用性 | `extension_point_analysis` |
| security-reviewer | 遠端 dispatch 認證/授權風險、Command 注入風險、override 堆疊安全邊界、SCADA 多層信任模型 | `hierarchical_security_assessment` |
| performance-optimizer | gRPC vs Redis 延遲/吞吐量比較、protobuf vs JSON 序列化成本、sub-executor 規模評估、Cython 相容性 | `transport_performance_analysis` |

**Gate**: 三份報告合併為 `phase1_analysis` 才進入 Phase 2。

### Phase 2: Architecture Design + Requirements (平行設計)

architect 與 feature-driver 同時進行，互不阻塞：

**architect 設計**：
- Topic A: `examples/11_cascading_strategy.py` 範例結構（PQ+QV+capacity clamping）
- Topic B: `SubExecutorAgent` Protocol 放在 Layer 6（`csp_lib/integration/hierarchical/`）
- Topic C: `.proto` 服務定義（`ControlDispatchService`, `StatusReportService`）+ `TransportAdapter` Protocol
- Topic D: SCADA → Area → Site → Device 四層架構圖

**feature-driver 定義**：
- 版本目標 0.4.0（minor: 新功能，向後相容）
- 7 個 work items（demo、protocol、dataclass、transport、proto、redis impl、grpc impl）
- 驗收標準 + 風險評估

**Gate**: `hierarchical_architecture_decision` + `hierarchical_feature_spec` 通過一致性驗證（層級依賴無違規、work items 覆蓋所有設計產出）。

### Phase 3: Prototype Implementation + Testing (平行)

implementer 與 test-planner 同時進行：

**implementer 實作**：
- `examples/11_cascading_strategy.py` — 顯式 CascadingStrategy demo（delta-based clamping）
- `csp_lib/integration/hierarchical/` — `SubExecutorAgent` Protocol + `DispatchCommand` + `StatusReport` dataclasses
- `csp_lib/grpc/` — `.proto` 定義 + `TransportAdapter` Protocol
- 驗證：ruff + mypy + demo 可執行

**test-planner 測試**：
- `tests/integration/test_sub_executor_agent.py`
- `tests/integration/test_transport_adapter.py`
- `tests/controller/test_cascading_strategy_extended.py`

**Gate**: ruff pass, mypy pass, all tests pass, demo exits 0。

### Phase 4: Documentation (文件化)

doc-organizer 統整所有產出：
- `docs/architecture/hierarchical-control.md`（Mermaid 架構圖：SCADA → Area → Site → Device）
- `CHANGELOG.md` 新增 0.4.0 hierarchical control 條目
- `README.md` 更新 optional dependency 與架構說明

**Gate**: 文件完整、CHANGELOG 已更新、README 已更新。

### Iteration Loops (迭代迴圈)

| Loop | Agents | Max Iterations | Exit Condition |
|------|--------|----------------|----------------|
| Design Consistency | architect ↔ feature-driver | 2 | feature_spec work items 覆蓋所有 architecture_decision 產出 |
| Prototype-Fix | test-planner → implementer | 3 | 全部測試通過 |

### Escalation Rules

- 超過 max iterations → 升級給 human review
- architect 判定現有擴展點不足以支撐設計 → 回到 Phase 1 重新評估，必要時建議修改現有 API（標記為 breaking change）
- security-reviewer 發現 critical（如：無認證遠端 dispatch）→ 強制中斷，通知 human

## File Ownership Boundary (檔案所有權邊界)

嚴格非重疊，依 Phase 區分寫入權限：

| Path | Ph1 | Ph2 | Ph3 | Ph4 |
|------|-----|-----|-----|-----|
| `csp_lib/integration/hierarchical/**` | — | read | **write** (implementer) | read |
| `csp_lib/grpc/**` | — | read | **write** (implementer) | read |
| `examples/11_cascading_strategy.py` | — | read | **write** (implementer) | read |
| `tests/**` (new test files only) | — | read | **write** (test-planner) | read |
| `docs/architecture/hierarchical-control.md` | — | — | — | **write** (doc-organizer) |
| `CHANGELOG.md`, `README.md` | read | read | read | **write** (doc-organizer) |
| `csp_lib/**/*.py` (existing) | read | read | read | read |
| `pyproject.toml`, `.github/**`, `build_wheel.py`, `setup.py` | read | read | read | read (human only) |

**Important**: Phase 3 implementer 僅新建模組，不修改現有檔案，避免原型階段破壞 API 穩定性。

## Handoff Protocols

### Phase 1 → Phase 2: Analysis → Design

```yaml
handoff:
  from: [architect, security-reviewer, performance-optimizer]
  to: [architect, feature-driver]
  artifact: phase1_analysis
  required_fields:
    - extension_point_analysis (from architect)
    - hierarchical_security_assessment (from security-reviewer)
    - transport_performance_analysis (from performance-optimizer)
  validation:
    - 3 reports all completed
    - each report has severity/priority classification
  gate: 3 reports completed
  on_failure: incomplete agent re-runs analysis
```

### Phase 2 → Phase 3: Design → Prototype

```yaml
handoff:
  from: [architect, feature-driver]
  to: [implementer, test-planner]
  artifact: [hierarchical_architecture_decision, hierarchical_feature_spec]
  required_fields:
    hierarchical_architecture_decision:
      - api_contracts (SubExecutorAgent, TransportAdapter, DispatchCommand, StatusReport)
      - dependency_map (all directions = valid, SubExecutorAgent @ L6, TransportAdapter @ L6)
      - new_files (at least 1)
      - proto_definitions (ControlDispatchService, StatusReportService)
    hierarchical_feature_spec:
      - version_target = 0.4.0
      - work_items (at least 5)
      - acceptance_criteria (at least 3)
      - risks (at least 1)
  validation:
    - 無層級依賴違規 (dependency_map)
    - work_items 覆蓋所有 architecture_decision 產出
    - api_contracts 型別簽名完整
  gate: [consistency check pass, no dependency violations]
  on_failure: architect ↔ feature-driver 迭代修正 (max 2)
```

### Phase 3 → Phase 4: Prototype → Documentation

```yaml
handoff:
  from: [implementer, test-planner]
  to: doc-organizer
  artifact: [implementation_result, test_result]
  required_fields:
    implementation_result:
      - files_created (at least 1)
      - verification.ruff_check = pass
      - verification.ruff_format = pass
      - verification.mypy = pass
      - demo_executable = true
    test_result:
      - all tests pass
      - test count summary
  validation:
    - ruff + mypy 全部通過
    - pytest 全部通過
    - demo exits 0
  gate: [ruff pass, mypy pass, all tests pass, demo exits 0]
  on_failure: test-planner → implementer fix loop (max 3)
```

### Completion Gate

```yaml
completion:
  gate:
    - examples/11_cascading_strategy.py runs without error
    - SubExecutorAgent Protocol defined and testable
    - TransportAdapter Protocol defined
    - .proto service definitions exist
    - All tests pass
    - Architecture doc created
    - CHANGELOG updated
    - README updated
  validation:
    - "uv run python examples/11_cascading_strategy.py" exits 0
    - "uv run pytest tests/integration/test_sub_executor_agent.py -v" passes
    - "uv run pytest tests/integration/test_transport_adapter.py -v" passes
    - CHANGELOG contains hierarchical control entry
    - README references hierarchical control
```

## Key Design Decisions

1. **SubExecutorAgent 放 Layer 6 (Integration)** — 依賴 Controller 的 Command/StrategyContext (L4)，但屬多站編排概念，符合 Integration 層定位
2. **TransportAdapter Protocol 放 Layer 6 (Integration)** — 抽象傳輸介面，具體實作在 L7 (Redis) / L8 (gRPC)
3. **Phase 3 不修改現有檔案** — 僅新建模組，避免原型階段破壞 API 穩定性
4. **`csp_lib[grpc]` 作為新 optional dependency** — 沿用 `[modbus]`、`[mongo]`、`[redis]` 的慣例
5. **SCADA → Area → Site → Device 四層架構** — 對應工業控制系統實際部署拓撲

## Final Output

```yaml
hierarchical_control_output:
  analysis:
    extension_points: ExtensionPointAnalysis
    security_assessment: HierarchicalSecurityAssessment
    transport_performance: TransportPerformanceAnalysis
  architecture:
    architecture_decision: HierarchicalArchitectureDecision
    feature_spec: HierarchicalFeatureSpec
    proto_definitions: [ControlDispatchService, StatusReportService]
  prototype:
    demo: "examples/11_cascading_strategy.py"
    new_modules: ["csp_lib/integration/hierarchical/", "csp_lib/grpc/"]
    new_protocols: [SubExecutorAgent, TransportAdapter, DispatchCommand, StatusReport]
    test_files: string[]
  documentation:
    architecture_doc: "docs/architecture/hierarchical-control.md"
    changelog_updated: boolean
    readme_updated: boolean
```

## Activation

使用此團隊模板進行階層控制架構設計：

```
/team hierarchical-control-team
```

或手動依序啟動各階段：

1. 同時啟動 architect、security-reviewer、performance-optimizer 進行 Phase 1 分析
2. 合併三份報告為 `phase1_analysis`，同時啟動 architect（設計）與 feature-driver（規格）
3. 將 `hierarchical_architecture_decision` + `hierarchical_feature_spec` 交給 implementer 與 test-planner（Phase 3）
4. 最後啟動 doc-organizer 更新文件（Phase 4）
