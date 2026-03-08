# =============== CAN Module ===============
#
# CAN Bus 協議層
#
# 提供 CAN 客戶端抽象和 python-can 實作。

from .clients import AsyncCANClientBase, PythonCANClient
from .config import CANBusConfig, CANFrame
from .exceptions import CANConnectionError, CANError, CANSendError, CANTimeoutError

__all__ = [
    # Config
    "CANBusConfig",
    "CANFrame",
    # Exceptions
    "CANError",
    "CANConnectionError",
    "CANTimeoutError",
    "CANSendError",
    # Clients
    "AsyncCANClientBase",
    "PythonCANClient",
]
