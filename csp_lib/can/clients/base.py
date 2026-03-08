# =============== CAN Client - Base ===============
#
# CAN 客戶端抽象基底類別

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Callable

from csp_lib.can.config import CANFrame


class AsyncCANClientBase(ABC):
    """
    CAN 客戶端抽象基底

    定義連線管理、被動監聽、主動發送、請求-回應四組介面。
    """

    # =============== 連線管理 ===============

    @abstractmethod
    async def connect(self) -> None:
        """建立連線"""

    @abstractmethod
    async def disconnect(self) -> None:
        """斷開連線"""

    @abstractmethod
    async def is_connected(self) -> bool:
        """檢查是否已連線"""

    # =============== 被動監聽 ===============

    @abstractmethod
    async def start_listener(self) -> None:
        """啟動背景接收"""

    @abstractmethod
    async def stop_listener(self) -> None:
        """停止背景接收"""

    @abstractmethod
    def subscribe(self, can_id: int, handler: Callable[[CANFrame], Any]) -> Callable[[], None]:
        """
        訂閱指定 CAN ID 的訊框

        Args:
            can_id: 要訂閱的 CAN ID
            handler: 收到訊框時的回調函數

        Returns:
            取消訂閱的函數
        """

    # =============== 主動發送 ===============

    @abstractmethod
    async def send(self, can_id: int, data: bytes) -> None:
        """
        發送 CAN 訊框

        Args:
            can_id: CAN 訊框 ID
            data: 訊框資料（最多 8 bytes）
        """

    # =============== 請求-回應 ===============

    @abstractmethod
    async def request(
        self,
        can_id: int,
        data: bytes,
        response_id: int,
        timeout: float = 1.0,
    ) -> CANFrame:
        """
        發送請求並等待回應

        Args:
            can_id: 發送的 CAN ID
            data: 請求資料
            response_id: 期望回應的 CAN ID
            timeout: 逾時時間（秒）

        Returns:
            回應訊框

        Raises:
            CANTimeoutError: 等待回應逾時
        """


__all__ = [
    "AsyncCANClientBase",
]
