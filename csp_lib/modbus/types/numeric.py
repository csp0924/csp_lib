# =============== Modbus Data Types - Numeric ===============
#
# 固定長度數值類型實作
#
# 支援類型：
#   - Int16 / UInt16: 16-bit 有號/無號整數 (1 暫存器)
#   - Int32 / UInt32: 32-bit 有號/無號整數 (2 暫存器)
#   - Int64 / UInt64: 64-bit 有號/無號整數 (4 暫存器)
#   - Float32: IEEE 754 單精度浮點數 (2 暫存器)
#   - Float64: IEEE 754 雙精度浮點數 (4 暫存器)

from __future__ import annotations

import struct

from ..enums import ByteOrder, RegisterOrder
from ..exceptions import ModbusDecodeError, ModbusEncodeError
from ._register_helpers import assemble_from_registers, split_to_registers
from .base import ModbusDataType


class Int16(ModbusDataType):
    """
    16-bit 有號整數

    範圍: -32768 ~ 32767
    暫存器數: 1
    """

    @property
    def register_count(self) -> int:
        return 1

    def encode(
        self,
        value: int,
        byte_order: ByteOrder,
        register_order: RegisterOrder,
    ) -> list[int]:
        if not isinstance(value, int):
            raise ModbusEncodeError(f"Int16 需要整數，收到: {type(value).__name__}")
        if not -32768 <= value <= 32767:
            raise ModbusEncodeError(f"Int16 範圍為 -32768~32767，收到: {value}")

        # 編碼為 bytes，再轉換為無號整數作為暫存器值
        packed = struct.pack(f"{byte_order.value}h", value)
        return [struct.unpack(f"{byte_order.value}H", packed)[0]]

    def decode(
        self,
        registers: list[int],
        byte_order: ByteOrder,
        register_order: RegisterOrder,
    ) -> int:
        if len(registers) < 1:
            raise ModbusDecodeError(f"Int16 需要 1 個暫存器，收到: {len(registers)}")

        # 將無號暫存器值轉換為有號整數
        packed = struct.pack(f"{byte_order.value}H", registers[0])
        return struct.unpack(f"{byte_order.value}h", packed)[0]


class UInt16(ModbusDataType):
    """
    16-bit 無號整數

    範圍: 0 ~ 65535
    暫存器數: 1
    """

    @property
    def register_count(self) -> int:
        return 1

    def encode(
        self,
        value: int,
        byte_order: ByteOrder,
        register_order: RegisterOrder,
    ) -> list[int]:
        if not isinstance(value, int):
            raise ModbusEncodeError(f"UInt16 需要整數，收到: {type(value).__name__}")
        if not 0 <= value <= 65535:
            raise ModbusEncodeError(f"UInt16 範圍為 0~65535，收到: {value}")

        return [value]

    def decode(
        self,
        registers: list[int],
        byte_order: ByteOrder,
        register_order: RegisterOrder,
    ) -> int:
        if len(registers) < 1:
            raise ModbusDecodeError(f"UInt16 需要 1 個暫存器，收到: {len(registers)}")

        return registers[0]


class _MultiRegisterInt(ModbusDataType):
    """多暫存器整數型別內部基類"""

    _struct_format: str
    _register_count: int
    _type_name: str
    _min_value: int
    _max_value: int

    @property
    def register_count(self) -> int:
        return self._register_count

    def encode(
        self,
        value: int,
        byte_order: ByteOrder,
        register_order: RegisterOrder,
    ) -> list[int]:
        if not isinstance(value, int):
            raise ModbusEncodeError(f"{self._type_name} 需要整數，收到: {type(value).__name__}")
        if not self._min_value <= value <= self._max_value:
            raise ModbusEncodeError(f"{self._type_name} 範圍為 {self._min_value}~{self._max_value}，收到: {value}")

        packed = struct.pack(f"{byte_order.value}{self._struct_format}", value)
        return split_to_registers(packed, self._register_count, byte_order, register_order)

    def decode(
        self,
        registers: list[int],
        byte_order: ByteOrder,
        register_order: RegisterOrder,
    ) -> int:
        if len(registers) < self._register_count:
            raise ModbusDecodeError(f"{self._type_name} 需要 {self._register_count} 個暫存器，收到: {len(registers)}")

        packed = assemble_from_registers(registers, self._register_count, byte_order, register_order)
        return struct.unpack(f"{byte_order.value}{self._struct_format}", packed)[0]


class _MultiRegisterFloat(ModbusDataType):
    """多暫存器浮點型別內部基類"""

    _struct_format: str
    _register_count: int
    _type_name: str

    @property
    def register_count(self) -> int:
        return self._register_count

    def encode(
        self,
        value: float,
        byte_order: ByteOrder,
        register_order: RegisterOrder,
    ) -> list[int]:
        if not isinstance(value, (int, float)):
            raise ModbusEncodeError(f"{self._type_name} 需要數值，收到: {type(value).__name__}")

        packed = struct.pack(f"{byte_order.value}{self._struct_format}", float(value))
        return split_to_registers(packed, self._register_count, byte_order, register_order)

    def decode(
        self,
        registers: list[int],
        byte_order: ByteOrder,
        register_order: RegisterOrder,
    ) -> float:
        if len(registers) < self._register_count:
            raise ModbusDecodeError(f"{self._type_name} 需要 {self._register_count} 個暫存器，收到: {len(registers)}")

        packed = assemble_from_registers(registers, self._register_count, byte_order, register_order)
        return struct.unpack(f"{byte_order.value}{self._struct_format}", packed)[0]


class Int32(_MultiRegisterInt):
    """
    32-bit 有號整數

    範圍: -2147483648 ~ 2147483647
    暫存器數: 2
    """

    _struct_format = "i"
    _register_count = 2
    _type_name = "Int32"
    _min_value = -2147483648
    _max_value = 2147483647


class UInt32(_MultiRegisterInt):
    """
    32-bit 無號整數

    範圍: 0 ~ 4294967295
    暫存器數: 2
    """

    _struct_format = "I"
    _register_count = 2
    _type_name = "UInt32"
    _min_value = 0
    _max_value = 4294967295


class UInt64(_MultiRegisterInt):
    """
    64-bit 無號整數

    範圍: 0 ~ 18446744073709551615
    暫存器數: 4
    """

    _struct_format = "Q"
    _register_count = 4
    _type_name = "UInt64"
    _min_value = 0
    _max_value = 18446744073709551615


class Int64(_MultiRegisterInt):
    """
    64-bit 有號整數

    範圍: -9223372036854775808 ~ 9223372036854775807
    暫存器數: 4
    """

    _struct_format = "q"
    _register_count = 4
    _type_name = "Int64"
    _min_value = -9223372036854775808
    _max_value = 9223372036854775807


class Float32(_MultiRegisterFloat):
    """
    IEEE 754 單精度浮點數

    暫存器數: 2
    """

    _struct_format = "f"
    _register_count = 2
    _type_name = "Float32"


class Float64(_MultiRegisterFloat):
    """
    IEEE 754 雙精度浮點數

    暫存器數: 4
    """

    _struct_format = "d"
    _register_count = 4
    _type_name = "Float64"


__all__ = ["Int16", "UInt16", "Int32", "UInt32", "Int64", "UInt64", "Float32", "Float64"]
