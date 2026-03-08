# =============== Tests - CAN Signal Codec ===============
#
# 測試 CAN 信號編解碼的對稱性

from csp_lib.equipment.processing.can_encoder import CANFieldEncoder, CANSignalDefinition
from csp_lib.equipment.processing.can_parser import CANField, CANFrameParser


class TestCANFieldEncoder:
    """測試 CANFieldEncoder 的編碼功能"""

    def test_encode_physical_simple(self):
        """簡單的 1:1 解析度"""
        signal = CANSignalDefinition(
            can_id=0x200,
            field=CANField("power", 0, 16, resolution=1.0),
        )
        assert CANFieldEncoder.encode_physical(signal, 5000) == 5000

    def test_encode_physical_with_resolution(self):
        """帶解析度的編碼"""
        signal = CANSignalDefinition(
            can_id=0x200,
            field=CANField("voltage", 0, 16, resolution=0.1),
        )
        # physical=380.5 → raw = (380.5 - 0) / 0.1 = 3805
        assert CANFieldEncoder.encode_physical(signal, 380.5) == 3805

    def test_encode_physical_with_offset(self):
        """帶偏移量的編碼"""
        signal = CANSignalDefinition(
            can_id=0x100,
            field=CANField("temperature", 0, 8, resolution=1.0, offset=-40.0),
        )
        # physical=25 → raw = (25 - (-40)) / 1.0 = 65
        assert CANFieldEncoder.encode_physical(signal, 25) == 65

    def test_encode_physical_with_resolution_and_offset(self):
        """帶解析度和偏移量的編碼"""
        signal = CANSignalDefinition(
            can_id=0x100,
            field=CANField("current", 0, 16, resolution=0.1, offset=-3200.0),
        )
        # physical=100.0 → raw = (100.0 - (-3200.0)) / 0.1 = 33000
        assert CANFieldEncoder.encode_physical(signal, 100.0) == 33000

    def test_encode_physical_clamp_max(self):
        """超出 bit 範圍的值被 clamp"""
        signal = CANSignalDefinition(
            can_id=0x200,
            field=CANField("small", 0, 8, resolution=1.0),
        )
        # 8-bit max = 255, 超出應 clamp
        assert CANFieldEncoder.encode_physical(signal, 300) == 255

    def test_encode_physical_clamp_min(self):
        """負值被 clamp 到 0"""
        signal = CANSignalDefinition(
            can_id=0x200,
            field=CANField("val", 0, 8, resolution=1.0),
        )
        assert CANFieldEncoder.encode_physical(signal, -10) == 0

    def test_encode_physical_custom_max_raw(self):
        """自定義 max_raw 限制"""
        signal = CANSignalDefinition(
            can_id=0x200,
            field=CANField("limited", 0, 16, resolution=1.0),
            max_raw=1000,
        )
        assert CANFieldEncoder.encode_physical(signal, 2000) == 1000

    def test_encode_physical_custom_min_raw(self):
        """自定義 min_raw 限制"""
        signal = CANSignalDefinition(
            can_id=0x200,
            field=CANField("limited", 0, 16, resolution=1.0),
            min_raw=100,
        )
        assert CANFieldEncoder.encode_physical(signal, 50) == 100

    def test_pack_field_basic(self):
        """基本的 pack 操作"""
        signal = CANSignalDefinition(
            can_id=0x200,
            field=CANField("val", 0, 8, resolution=1.0),
        )
        result = CANFieldEncoder.pack_field(0, signal, 0xAB)
        assert result & 0xFF == 0xAB

    def test_pack_field_preserves_other_bits(self):
        """pack 操作不影響其他 bit"""
        signal = CANSignalDefinition(
            can_id=0x200,
            field=CANField("val", 8, 8, resolution=1.0),
        )
        # buffer 的 bit 0-7 已有 0xFF
        result = CANFieldEncoder.pack_field(0xFF, signal, 0xAB)
        assert result & 0xFF == 0xFF  # bit 0-7 保持不變
        assert (result >> 8) & 0xFF == 0xAB  # bit 8-15 被更新

    def test_pack_field_clears_old_value(self):
        """pack 操作先清除舊值再寫入"""
        signal = CANSignalDefinition(
            can_id=0x200,
            field=CANField("val", 0, 8, resolution=1.0),
        )
        # 先寫 0xFF
        buf = CANFieldEncoder.pack_field(0, signal, 0xFF)
        assert buf & 0xFF == 0xFF
        # 再寫 0x00，舊值應被清除
        buf = CANFieldEncoder.pack_field(buf, signal, 0x00)
        assert buf & 0xFF == 0x00


class TestEncodeDecodeRoundTrip:
    """測試編碼-解碼往返一致性"""

    def test_roundtrip_simple(self):
        """簡單的編解碼往返"""
        field = CANField("power", 0, 16, resolution=1.0)
        signal = CANSignalDefinition(can_id=0x200, field=field)

        # 編碼
        raw = CANFieldEncoder.encode_physical(signal, 5000)
        buf = CANFieldEncoder.pack_field(0, signal, raw)
        frame_bytes = buf.to_bytes(8, byteorder="little")

        # 解碼
        parser = CANFrameParser(source_name="test", fields=[field])
        result = parser.process({"test": int.from_bytes(frame_bytes, byteorder="big")})
        assert result["power"] == 5000.0

    def test_roundtrip_with_resolution(self):
        """帶解析度的編解碼往返"""
        field = CANField("voltage", 8, 16, resolution=0.1, decimals=1)
        signal = CANSignalDefinition(can_id=0x200, field=field)

        # 編碼
        raw = CANFieldEncoder.encode_physical(signal, 380.5)
        buf = CANFieldEncoder.pack_field(0, signal, raw)
        frame_bytes = buf.to_bytes(8, byteorder="little")

        # 解碼
        parser = CANFrameParser(source_name="test", fields=[field])
        result = parser.process({"test": int.from_bytes(frame_bytes, byteorder="big")})
        assert result["voltage"] == 380.5

    def test_roundtrip_with_offset(self):
        """帶偏移量的編解碼往返"""
        field = CANField("temp", 0, 8, resolution=1.0, offset=-40.0, as_int=True)
        signal = CANSignalDefinition(can_id=0x100, field=field)

        # 編碼
        raw = CANFieldEncoder.encode_physical(signal, 25)
        buf = CANFieldEncoder.pack_field(0, signal, raw)
        frame_bytes = buf.to_bytes(8, byteorder="little")

        # 解碼
        parser = CANFrameParser(source_name="test", fields=[field])
        result = parser.process({"test": int.from_bytes(frame_bytes, byteorder="big")})
        assert result["temp"] == 25

    def test_roundtrip_multiple_fields(self):
        """多欄位的編解碼往返"""
        fields = [
            CANField("soc", 0, 8, resolution=0.4, decimals=1),
            CANField("voltage", 8, 16, resolution=0.1, decimals=1),
            CANField("current", 24, 16, resolution=0.1, offset=-3200.0, decimals=1),
        ]
        signals = [CANSignalDefinition(can_id=0x100, field=f) for f in fields]

        # 編碼
        buf = 0
        test_values = {"soc": 85.2, "voltage": 380.5, "current": 100.0}
        for sig in signals:
            raw = CANFieldEncoder.encode_physical(sig, test_values[sig.field.name])
            buf = CANFieldEncoder.pack_field(buf, sig, raw)

        frame_bytes = buf.to_bytes(8, byteorder="little")

        # 解碼
        parser = CANFrameParser(source_name="test", fields=fields)
        result = parser.process({"test": int.from_bytes(frame_bytes, byteorder="big")})

        assert result["soc"] == 85.2
        assert result["voltage"] == 380.5
        assert result["current"] == 100.0
