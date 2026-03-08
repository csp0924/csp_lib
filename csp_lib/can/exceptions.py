# =============== CAN - Exceptions ===============
#
# CAN Bus 例外層次結構

from __future__ import annotations


class CANError(Exception):
    """CAN Bus 基礎例外"""


class CANConnectionError(CANError):
    """CAN Bus 連線錯誤"""


class CANTimeoutError(CANError):
    """CAN Bus 逾時錯誤"""


class CANSendError(CANError):
    """CAN Bus 發送錯誤"""


__all__ = [
    "CANError",
    "CANConnectionError",
    "CANTimeoutError",
    "CANSendError",
]
