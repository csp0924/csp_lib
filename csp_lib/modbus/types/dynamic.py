# =============== Modbus Data Types - Dynamic ===============
#
# 動態長度整數類型實作
#
# 支援任意 16 的倍數位元寬度：
#   - DynamicInt: 動態長度有號整數
#   - DynamicUInt: 動態長度無號整數
#
# 使用範例：
#   uint48 = DynamicUInt(48)  # 48-bit 無號整數，需要 3 個暫存器

from __future__ import annotations

from ..enums import ByteOrder, RegisterOrder
from ..exceptions import ModbusConfigError, ModbusDecodeError, ModbusEncodeError
from .base import ModbusDataType


class _DynamicIntBase(ModbusDataType):
    """
    動態長度整數內部基類

    以 signed 參數化，統一有號/無號整數的暫存器拆分/組合邏輯。
    """

    def __init__(self, bit_width: int, *, signed: bool) -> None:
        if bit_width <= 0:
            raise ModbusConfigError(f"bit_width 必須為正整數，收到: {bit_width}")
        if bit_width % 16 != 0:
            raise ModbusConfigError(f"bit_width 必須為 16 的倍數，收到: {bit_width}")

        self._bit_width = bit_width
        self._register_count = bit_width // 16
        self._signed = signed

        if signed:
            self._max_value = (1 << (bit_width - 1)) - 1
            self._min_value = -(1 << (bit_width - 1))
        else:
            self._max_value = (1 << bit_width) - 1
            self._min_value = 0

    @property
    def register_count(self) -> int:
        return self._register_count

    @property
    def bit_width(self) -> int:
        """位元寬度"""
        return self._bit_width

    def _type_label(self) -> str:
        name = "DynamicInt" if self._signed else "DynamicUInt"
        return f"{name}({self._bit_width})"

    def encode(
        self,
        value: int,
        byte_order: ByteOrder,
        register_order: RegisterOrder,
    ) -> list[int]:
        if not isinstance(value, int):
            raise ModbusEncodeError(f"{self._type_label()} 需要整數，收到: {type(value).__name__}")
        if not self._min_value <= value <= self._max_value:
            raise ModbusEncodeError(f"{self._type_label()} 範圍為 {self._min_value}~{self._max_value}，收到: {value}")

        # 處理負數：轉換為補數表示
        raw = value
        if self._signed and raw < 0:
            raw = (1 << self._bit_width) + raw

        # 將整數分割為多個 16-bit 暫存器 (LSW first)
        registers = []
        for _ in range(self._register_count):
            registers.append(raw & 0xFFFF)
            raw >>= 16

        # 預設 LSW first，若 HIGH_FIRST 則反轉為 MSW first
        if register_order == RegisterOrder.HIGH_FIRST:
            registers.reverse()

        return registers

    def decode(
        self,
        registers: list[int],
        byte_order: ByteOrder,
        register_order: RegisterOrder,
    ) -> int:
        if len(registers) < self._register_count:
            raise ModbusDecodeError(
                f"{self._type_label()} 需要 {self._register_count} 個暫存器，收到: {len(registers)}"
            )

        regs = list(registers[: self._register_count])

        # 還原順序：若 HIGH_FIRST 則反轉回 LSW first 以便組合
        if register_order == RegisterOrder.HIGH_FIRST:
            regs.reverse()

        # 組合為整數 (從 LSW 開始)
        value = 0
        for i, reg in enumerate(regs):
            value |= reg << (16 * i)

        # 處理負數：從補數還原
        if self._signed and value >= (1 << (self._bit_width - 1)):
            value -= 1 << self._bit_width

        return value


class DynamicInt(_DynamicIntBase):
    """
    動態長度有號整數

    支援任意 16 的倍數位元寬度。

    Args:
        bit_width: 位元寬度，必須為 16 的倍數

    Raises:
        ModbusConfigError: bit_width 非 16 的倍數

    使用範例：
        >>> int48 = DynamicInt(48)
        >>> int48.register_count
        3
    """

    def __init__(self, bit_width: int) -> None:
        super().__init__(bit_width, signed=True)


class DynamicUInt(_DynamicIntBase):
    """
    動態長度無號整數

    支援任意 16 的倍數位元寬度。

    Args:
        bit_width: 位元寬度，必須為 16 的倍數

    Raises:
        ModbusConfigError: bit_width 非 16 的倍數

    使用範例：
        >>> uint48 = DynamicUInt(48)
        >>> uint48.register_count
        3
    """

    def __init__(self, bit_width: int) -> None:
        super().__init__(bit_width, signed=False)


__all__ = [
    "DynamicInt",
    "DynamicUInt",
]
