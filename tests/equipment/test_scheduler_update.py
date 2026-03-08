# =============== Equipment Transport Tests - Scheduler update_groups ===============

from __future__ import annotations

from csp_lib.equipment.transport.base import ReadGroup
from csp_lib.equipment.transport.scheduler import ReadScheduler


def _make_group(fc: int = 3, start: int = 0, count: int = 1) -> ReadGroup:
    return ReadGroup(function_code=fc, start_address=start, count=count, points=())


class TestUpdateGroups:
    """update_groups() 測試"""

    def test_update_always_groups(self):
        """更新 always_groups"""
        g1 = _make_group(start=0)
        scheduler = ReadScheduler(always_groups=[g1])

        g2 = _make_group(start=10)
        scheduler.update_groups(always_groups=[g2])

        result = scheduler.get_next_groups()
        assert result == [g2]

    def test_update_rotating_groups(self):
        """更新 rotating_groups"""
        rot_a = [_make_group(start=100)]
        rot_b = [_make_group(start=200)]
        scheduler = ReadScheduler(rotating_groups=[rot_a, rot_b])

        # 推進到 index 1
        scheduler.get_next_groups()
        assert scheduler.current_rotating_index == 1

        # 更新 rotating → index 重置為 0
        rot_c = [_make_group(start=300)]
        scheduler.update_groups(rotating_groups=[rot_c])

        assert scheduler.current_rotating_index == 0
        assert scheduler.rotating_count == 1
        assert scheduler.get_next_groups() == rot_c

    def test_update_both(self):
        """同時更新 always 和 rotating"""
        scheduler = ReadScheduler(
            always_groups=[_make_group(start=0)],
            rotating_groups=[[_make_group(start=100)]],
        )

        new_always = _make_group(start=50)
        new_rot = [_make_group(start=500)]
        scheduler.update_groups(always_groups=[new_always], rotating_groups=[new_rot])

        result = scheduler.get_next_groups()
        assert result == [new_always, new_rot[0]]

    def test_update_none_keeps_original(self):
        """None 表示保持不變"""
        g1 = _make_group(start=0)
        rot_a = [_make_group(start=100)]
        scheduler = ReadScheduler(always_groups=[g1], rotating_groups=[rot_a])

        scheduler.update_groups(always_groups=None, rotating_groups=None)

        result = scheduler.get_next_groups()
        assert result == [g1, rot_a[0]]

    def test_update_only_always_keeps_rotating(self):
        """只更新 always，rotating 不變"""
        rot_a = [_make_group(start=100)]
        scheduler = ReadScheduler(
            always_groups=[_make_group(start=0)],
            rotating_groups=[rot_a],
        )

        new_always = _make_group(start=50)
        scheduler.update_groups(always_groups=[new_always])

        result = scheduler.get_next_groups()
        assert result[0] == new_always
        assert result[1] == rot_a[0]

    def test_update_only_rotating_keeps_always(self):
        """只更新 rotating，always 不變"""
        g1 = _make_group(start=0)
        scheduler = ReadScheduler(
            always_groups=[g1],
            rotating_groups=[[_make_group(start=100)]],
        )

        new_rot = [_make_group(start=500)]
        scheduler.update_groups(rotating_groups=[new_rot])

        result = scheduler.get_next_groups()
        assert result[0] == g1
        assert result[1] == new_rot[0]
        assert scheduler.current_rotating_index == 0  # reset after update

    def test_update_to_empty(self):
        """更新為空"""
        scheduler = ReadScheduler(
            always_groups=[_make_group(start=0)],
            rotating_groups=[[_make_group(start=100)]],
        )

        scheduler.update_groups(always_groups=[], rotating_groups=[])

        result = scheduler.get_next_groups()
        assert result == []

    def test_update_rotating_resets_index(self):
        """更新 rotating 後 index 重置"""
        rot_a = [_make_group(start=100)]
        rot_b = [_make_group(start=200)]
        rot_c = [_make_group(start=300)]
        scheduler = ReadScheduler(rotating_groups=[rot_a, rot_b, rot_c])

        scheduler.get_next_groups()  # index -> 1
        scheduler.get_next_groups()  # index -> 2

        new_rot_x = [_make_group(start=400)]
        new_rot_y = [_make_group(start=500)]
        scheduler.update_groups(rotating_groups=[new_rot_x, new_rot_y])

        assert scheduler.current_rotating_index == 0
        assert scheduler.get_next_groups() == new_rot_x
        assert scheduler.get_next_groups() == new_rot_y

    def test_update_copies_input(self):
        """update_groups 應複製輸入"""
        new_always = [_make_group(start=50)]
        scheduler = ReadScheduler()
        scheduler.update_groups(always_groups=new_always)

        new_always.append(_make_group(start=999))

        result = scheduler.get_next_groups()
        assert len(result) == 1
