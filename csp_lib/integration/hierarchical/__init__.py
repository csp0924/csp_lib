# =============== Hierarchical Control Module ===============
#
# 階層控制介面定義
#
# SCADA → Area → Site → Device 四層架構的核心協定：
#   - SubExecutorAgent: 遠端子執行器代理協定
#   - TransportAdapter: 傳輸抽象協定
#   - DispatchCommand: 調度命令資料結構
#   - StatusReport: 狀態回報資料結構

from .agent import SubExecutorAgent
from .status import ExecutorStatus, StatusReport
from .transport import DispatchCommand, TransportAdapter

__all__ = [
    "SubExecutorAgent",
    "TransportAdapter",
    "DispatchCommand",
    "ExecutorStatus",
    "StatusReport",
]
