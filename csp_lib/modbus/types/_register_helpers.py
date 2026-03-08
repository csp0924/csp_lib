# =============== Modbus Data Types - Register Helpers ===============
#
# 多暫存器型別共用的暫存器拆分/組合邏輯
#
# 內部模組，不對外匯出

from __future__ import annotations

import struct

from ..enums import ByteOrder, RegisterOrder


def split_to_registers(
    packed: bytes,
    register_count: int,
    byte_order: ByteOrder,
    register_order: RegisterOrder,
) -> list[int]:
    """
    將 packed bytes 拆分為 16-bit 暫存器列表

    Args:
        packed: struct.pack 產生的 bytes
        register_count: 暫存器數量
        byte_order: 位元組順序
        register_order: 暫存器順序

    Returns:
        暫存器值列表
    """
    bo = byte_order.value
    regs = [struct.unpack(f"{bo}H", packed[i * 2 : i * 2 + 2])[0] for i in range(register_count)]

    if register_count == 2:
        if register_order == RegisterOrder.LOW_FIRST:
            regs.reverse()
    elif register_count == 4:
        if register_order == RegisterOrder.LOW_FIRST:
            regs.reverse()

    return regs


def assemble_from_registers(
    registers: list[int],
    register_count: int,
    byte_order: ByteOrder,
    register_order: RegisterOrder,
) -> bytes:
    """
    將暫存器列表組合為 bytes

    Args:
        registers: 暫存器值列表
        register_count: 暫存器數量
        byte_order: 位元組順序
        register_order: 暫存器順序

    Returns:
        組合後的 bytes
    """
    bo = byte_order.value
    regs = list(registers[:register_count])

    if register_count == 2:
        if register_order == RegisterOrder.HIGH_FIRST:
            high, low = regs[0], regs[1]
        else:
            low, high = regs[0], regs[1]
        return struct.pack(f"{bo}HH", high, low)
    elif register_count == 4:
        if register_order == RegisterOrder.LOW_FIRST:
            regs.reverse()
        fmt = f"{bo}" + "H" * register_count
        return struct.pack(fmt, *regs)

    # Fallback for other register counts
    fmt = f"{bo}" + "H" * register_count
    return struct.pack(fmt, *regs)
