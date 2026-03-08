# =============== Tests - CAN Frame Buffer ===============
#
# 測試 Frame Buffer 的位元級操作

import threading

import pytest

from csp_lib.equipment.processing.can_encoder import (
    CANFrameBuffer,
    CANSignalDefinition,
    FrameBufferConfig,
)
from csp_lib.equipment.processing.can_parser import CANField


class TestCANFrameBuffer:
    """測試 CANFrameBuffer"""

    def _make_buffer(self) -> CANFrameBuffer:
        """建立測試用的 buffer"""
        return CANFrameBuffer(
            configs=[FrameBufferConfig(can_id=0x200)],
            signals=[
                CANSignalDefinition(0x200, CANField("power_target", 0, 16, resolution=1.0)),
                CANSignalDefinition(0x200, CANField("mode", 16, 4, resolution=1.0)),
                CANSignalDefinition(0x200, CANField("start_stop", 20, 1, resolution=1.0)),
            ],
        )

    def test_initial_frame_is_zeros(self):
        """初始 frame 為全零"""
        buf = self._make_buffer()
        assert buf.get_frame(0x200) == b"\x00" * 8

    def test_set_signal_updates_frame(self):
        """set_signal 更新 frame"""
        buf = self._make_buffer()
        buf.set_signal("power_target", 5000)
        frame = buf.get_frame(0x200)
        # 5000 = 0x1388, little-endian: 0x88, 0x13
        assert frame[0] == 0x88
        assert frame[1] == 0x13

    def test_set_signal_preserves_other_bits(self):
        """set_signal 不影響其他 bit"""
        buf = self._make_buffer()
        buf.set_signal("power_target", 5000)
        buf.set_signal("start_stop", 1)

        frame = buf.get_frame(0x200)
        # power_target bit 0-15: 5000 (0x1388)
        assert frame[0] == 0x88
        assert frame[1] == 0x13
        # start_stop bit 20: 1 → byte 2 的 bit 4 = 0x10
        assert frame[2] & 0x10 == 0x10

    def test_set_signal_overwrites_previous(self):
        """set_signal 覆蓋先前的值"""
        buf = self._make_buffer()
        buf.set_signal("power_target", 5000)
        buf.set_signal("power_target", 1000)
        frame = buf.get_frame(0x200)
        # 1000 = 0x03E8, little-endian: 0xE8, 0x03
        assert frame[0] == 0xE8
        assert frame[1] == 0x03

    def test_set_raw(self):
        """set_raw 直接設定原始值"""
        buf = self._make_buffer()
        buf.set_raw("mode", 0xF)
        frame = buf.get_frame(0x200)
        # mode bit 16-19: 0xF → byte 2 的 bit 0-3 = 0x0F
        assert frame[2] & 0x0F == 0x0F

    def test_multiple_signals_same_frame(self):
        """多個信號寫入同一 frame"""
        buf = self._make_buffer()
        buf.set_signal("power_target", 1000)
        buf.set_signal("mode", 3)
        buf.set_signal("start_stop", 1)

        frame = buf.get_frame(0x200)

        # 驗證各信號值：使用 little-endian 64-bit 解讀
        frame_int = int.from_bytes(frame, byteorder="little")
        assert (frame_int >> 0) & 0xFFFF == 1000  # power_target
        assert (frame_int >> 16) & 0xF == 3  # mode
        assert (frame_int >> 20) & 0x1 == 1  # start_stop

    def test_multiple_can_ids(self):
        """多個 CAN ID 獨立管理"""
        buf = CANFrameBuffer(
            configs=[
                FrameBufferConfig(can_id=0x200),
                FrameBufferConfig(can_id=0x300),
            ],
            signals=[
                CANSignalDefinition(0x200, CANField("power", 0, 16, resolution=1.0)),
                CANSignalDefinition(0x300, CANField("heartbeat", 0, 32, resolution=1.0)),
            ],
        )

        buf.set_signal("power", 5000)
        buf.set_signal("heartbeat", 12345678)

        # 0x200 frame 只有 power
        frame_200 = buf.get_frame(0x200)
        assert int.from_bytes(frame_200[:2], "little") == 5000

        # 0x300 frame 只有 heartbeat
        frame_300 = buf.get_frame(0x300)
        assert int.from_bytes(frame_300[:4], "little") == 12345678

    def test_get_signal(self):
        """get_signal 回傳信號定義"""
        buf = self._make_buffer()
        sig = buf.get_signal("power_target")
        assert sig.can_id == 0x200
        assert sig.field.name == "power_target"

    def test_get_signal_not_found(self):
        """get_signal 不存在時拋出 KeyError"""
        buf = self._make_buffer()
        with pytest.raises(KeyError):
            buf.get_signal("nonexistent")

    def test_set_signal_not_found(self):
        """set_signal 不存在時拋出 KeyError"""
        buf = self._make_buffer()
        with pytest.raises(KeyError):
            buf.set_signal("nonexistent", 0)

    def test_get_frame_not_found(self):
        """get_frame CAN ID 不存在時拋出 KeyError"""
        buf = self._make_buffer()
        with pytest.raises(KeyError):
            buf.get_frame(0x999)

    def test_initial_data(self):
        """初始資料配置"""
        buf = CANFrameBuffer(
            configs=[FrameBufferConfig(can_id=0x200, initial_data=b"\xff" * 8)],
            signals=[CANSignalDefinition(0x200, CANField("val", 0, 8, resolution=1.0))],
        )
        frame = buf.get_frame(0x200)
        assert frame == b"\xff" * 8

    def test_thread_safety(self):
        """多線程同時寫入不 crash"""
        buf = self._make_buffer()
        errors = []

        def writer(name: str, value: int):
            try:
                for _ in range(1000):
                    buf.set_signal(name, value)
                    buf.get_frame(0x200)
            except Exception as e:
                errors.append(e)

        threads = [
            threading.Thread(target=writer, args=("power_target", 5000)),
            threading.Thread(target=writer, args=("mode", 3)),
            threading.Thread(target=writer, args=("start_stop", 1)),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert not errors
