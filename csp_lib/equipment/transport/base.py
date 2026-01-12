# =============== Equipment IO - Reader ===============
#
# 分組讀取器
#
# 自動合併相鄰點位以減少請求次數

from __future__ import annotations

from dataclasses import dataclass, field
from itertools import groupby
from typing import TYPE_CHECKING, Any, Sequence

if TYPE_CHECKING:
    from ..core.point import ReadPoint


@dataclass(slots=True, frozen=True)
class ReadGroup:
    """讀取群組（不可變）"""

    function_code: int
    start_address: int
    count: int
    points: tuple[ReadPoint, ...] = field(default_factory=tuple)


class PointGrouper:
    """
    點位分組器

    將點位合併成群組以減少請求次數。

    使用範例：
        grouper = PointGrouper()
        groups = grouper.group(points)
    """

    # 各功能碼的最大讀取長度
    FC_MAX_LENGTH: dict[int, int] = {
        1: 2000,  # Read Coils
        2: 2000,  # Read Discrete Inputs
        3: 125,  # Read Holding Registers
        4: 125,  # Read Input Registers
    }

    def group(self, points: Sequence[ReadPoint]) -> list[ReadGroup]:
        """
        計算點位分組

        Args:
            points: 點位列表

        Returns:
            分組後的 ReadGroup 列表
        """
        if not points:
            return []

        sorted_points = sorted(points, key=lambda p: (p.read_group, p.function_code, p.address))

        groups: list[ReadGroup] = []

        for (_, function_code), function_point in groupby(sorted_points, key=lambda p: (p.read_group, p.function_code)):
            groups.extend(self._merge_consecutive(list(function_point), function_code))

        return groups

    def decode(self, group: ReadGroup, raw_data: list[int] | list[bool]) -> dict[str, Any]:
        """
        解碼群組讀取結果

        Args:
            group: 讀取群組
            raw_data: 原始資料

        Returns:
            {點位名稱: 值} 字典

        Raises:
            ValueError: 資料長度不足以解碼點位
        """
        result: dict[str, Any] = {}

        for point in group.points:
            # 計算偏移
            offset = point.address - group.start_address
            length = point.data_type.register_count

            # 提取資料切片並驗證長度
            data_slice = list(raw_data[offset : offset + length])
            if len(data_slice) < length:
                raise ValueError(
                    f"資料不足以解碼點位 '{point.name}': "
                    f"期望 {length} 個暫存器，實際 {len(data_slice)} "
                    f"(offset={offset}, group.count={group.count})"
                )

            # 解碼
            value = point.data_type.decode(
                registers=data_slice,
                byte_order=point.byte_order,
                register_order=point.register_order,
            )

            if point.pipeline:
                value = point.pipeline.process(value)

            result[point.name] = value

        return result

    def _merge_consecutive(
        self, points: list[ReadPoint], function_code: int, max_length: int | None = None
    ) -> list[ReadGroup]:
        """
        合併連續點位成群組

        Args:
            points: 已排序的點位列表
            function_code: 功能碼
            max_length: 最大讀取長度（可選）

        Returns:
            合併後的 ReadGroup 列表
        """
        max_length = max_length or self.FC_MAX_LENGTH.get(function_code, 125)
        groups: list[ReadGroup] = []

        current: list[ReadPoint] = []
        start = 0
        end = 0

        for point in points:
            p_start = point.address
            p_end = p_start + point.data_type.register_count

            if not current:
                current, start, end = [point], p_start, p_end
                continue

            if p_end - start <= max_length:
                current.append(point)
                end = max(end, p_end)
                continue

            groups.append(
                ReadGroup(function_code=function_code, start_address=start, count=end - start, points=tuple(current))
            )

        if current:
            groups.append(
                ReadGroup(function_code=function_code, start_address=start, count=end - start, points=tuple(current))
            )

        return groups
