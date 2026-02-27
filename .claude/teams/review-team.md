# Review Team (審查團隊)

## Composition

程式碼審查與品質保證團隊。全程唯讀，不修改任何檔案，僅產出統一審查報告。

### Members

| Agent | Role | Phase |
|-------|------|-------|
| security-reviewer | 安全檢視 | Phase 1 (parallel) |
| test-planner | 測試驗證 | Phase 1 (parallel) |
| performance-optimizer | 效能分析 | Phase 1 (parallel) |
| architect | 架構審查 | Phase 2 (aggregate) |
| doc-organizer | 文件完整性 | Phase 2 (aggregate) |

### Pipeline

```
Phase 1 (Parallel Review)              Phase 2 (Aggregation)
[security-reviewer  ]                  architect (架構總評)
[test-planner       ]  ──────────────→
[performance-optimizer]                doc-organizer (文件缺口)
```

## Coordination Rules

### Review Scope

所有代理在此團隊中均為 **read-only 模式**，不修改任何檔案：

| Agent | Review Focus |
|-------|-------------|
| security-reviewer | 安全漏洞、ICS 安全、並發安全 |
| test-planner | 測試覆蓋率、測試品質、缺失測試案例 |
| performance-optimizer | 效能瓶頸、Cython 相容性、資源使用 |
| architect | 架構合規性、依賴方向、API 設計品質 |
| doc-organizer | 文件完整性、docstring 品質、CHANGELOG 一致性 |

### Phase 1: Parallel Review

三個代理同時審查，各自產出獨立報告：

```yaml
parallel_reviews:
  security-reviewer:
    input: files_to_review (changed files)
    output: security_report
    timeout: 10min
  test-planner:
    input: files_implemented + existing tests
    output: test_coverage_report (read-only analysis, no new test files)
    timeout: 10min
  performance-optimizer:
    input: target_files + performance_context
    output: optimization_result (analysis only, no code changes)
    timeout: 10min
```

### Phase 2: Aggregation

architect 與 doc-organizer 彙整 Phase 1 結果：

```yaml
aggregation:
  architect:
    input: [security_report, test_coverage_report, optimization_result, changed_files]
    output: architecture_review
    focus:
      - 架構層級依賴方向驗證
      - 設計模式使用合理性
      - API 合約一致性
      - Phase 1 findings 的架構影響評估
  doc-organizer:
    input: [changed_files, existing_docs]
    output: doc_gap_report
    focus:
      - 新增 API 是否有文件
      - CHANGELOG 是否更新
      - docstring 品質
```

## Unified Review Report

最終產出統一報告格式：

```yaml
review_report:
  timestamp: datetime
  reviewed_files: string[]
  overall_verdict: pass|fail|pass_with_warnings

  sections:
    security:
      status: pass|fail|warning
      critical_count: int
      high_count: int
      summary: string
      details: SecurityReport    # from security-reviewer

    tests:
      status: pass|fail|warning
      coverage_pct: float
      missing_tests: string[]
      summary: string
      details: TestCoverageReport  # from test-planner

    performance:
      status: pass|fail|warning
      high_impact_count: int
      cython_compatible: boolean
      summary: string
      details: OptimizationResult  # from performance-optimizer

    architecture:
      status: pass|fail|warning
      dependency_violations: int
      api_consistency: boolean
      summary: string
      details: ArchitectureReview  # from architect

    documentation:
      status: pass|fail|warning
      undocumented_apis: string[]
      changelog_up_to_date: boolean
      summary: string
      details: DocGapReport        # from doc-organizer

  verdict_rules:
    fail_if:
      - security.critical_count > 0
      - security.high_count > 0 (unresolved)
      - tests.status = fail
      - architecture.dependency_violations > 0
    warn_if:
      - performance.high_impact_count > 0
      - documentation.undocumented_apis.length > 0
      - tests.coverage_pct < 80
```

## File Ownership (Review Mode)

審查模式下所有代理均為 read-only：

| Directory / File | Access |
|-----------------|--------|
| `csp_lib/**/*.py` | read-only |
| `tests/**/*.py` | read-only |
| `docs/**/*.md` | read-only |
| `CHANGELOG.md` | read-only |
| `README.md` | read-only |
| `pyproject.toml` | read-only |
| All other files | read-only |

## Activation

使用此團隊模板進行程式碼審查：

```
/team review-team --files "csp_lib/controller/*.py" --context "new strategy implementation"
```

或針對整個分支的變更：

```
/team review-team --diff "main..feature-branch"
```

## Exit Criteria

審查完成條件：
1. 所有 Phase 1 代理已提交報告
2. Phase 2 彙整完成
3. review_report.overall_verdict 已產出
4. 如有 fail → 產出修復優先順序清單交回 feature-team
