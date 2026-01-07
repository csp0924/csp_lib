# =============== Controller Module ===============
#
# 控制器模組頂層匯出
#
# 提供便捷的 import 路徑：
#   from csp_lib.controller import Strategy, Command, StrategyExecutor

from .core import (
    Command,
    SystemBase,
    ConfigMixin,
    StrategyContext,
    ExecutionMode,
    ExecutionConfig,
    Strategy,
)

from .executor import StrategyExecutor

from .services import PVDataService

from .strategies import (
    PQModeStrategy,
    PQModeConfig,
    PVSmoothStrategy,
    PVSmoothConfig,
    ScheduleStrategy,
    StopStrategy,
)

__all__ = [
    # Core
    "Command",
    "SystemBase",
    "ConfigMixin",
    "StrategyContext",
    "ExecutionMode",
    "ExecutionConfig",
    "Strategy",
    # Executor
    "StrategyExecutor",
    # Services
    "PVDataService",
    # Strategies
    "PQModeStrategy",
    "PQModeConfig",
    "PVSmoothStrategy",
    "PVSmoothConfig",
    "ScheduleStrategy",
    "StopStrategy",
]
