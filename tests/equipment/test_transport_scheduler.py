# =============== Equipment Transport Tests - Scheduler ===============
#
# ReadScheduler 讀取排程器單元測試
#
# 測試覆蓋：
# - 建構：各種 always/rotating 組合
# - get_next_groups(): 僅固定群組、僅輪替群組、混合模式
# - peek_next_groups(): 不推進索引
# - reset(): 重置輪替索引
# - 邊界情況：空群組、單一輪替群組回繞、多次呼叫循環

from __future__ import annotations

from csp_lib.equipment.transport.base import ReadGroup
from csp_lib.equipment.transport.scheduler import ReadScheduler

# ======================== Helper Factories ========================


def _make_group(fc: int = 3, start: int = 0, count: int = 1) -> ReadGroup:
    """建立簡單的 ReadGroup（不帶點位，用於排程測試）"""
    return ReadGroup(function_code=fc, start_address=start, count=count, points=())


# ======================== Construction Tests ========================


class TestReadSchedulerConstruction:
    """ReadScheduler 建構測試"""

    def test_default_construction(self):
        """預設建構：無 always 與 rotating"""
        scheduler = ReadScheduler()

        assert scheduler.current_rotating_index == 0
        assert scheduler.rotating_count == 0
        assert scheduler.has_rotating is False

    def test_construction_with_always_only(self):
        """僅提供 always_groups"""
        groups = [_make_group(start=0), _make_group(start=10)]
        scheduler = ReadScheduler(always_groups=groups)

        assert scheduler.rotating_count == 0
        assert scheduler.has_rotating is False

    def test_construction_with_rotating_only(self):
        """僅提供 rotating_groups"""
        rot_a = [_make_group(start=100)]
        rot_b = [_make_group(start=200)]
        scheduler = ReadScheduler(rotating_groups=[rot_a, rot_b])

        assert scheduler.rotating_count == 2
        assert scheduler.has_rotating is True
        assert scheduler.current_rotating_index == 0

    def test_construction_with_both(self):
        """同時提供 always 與 rotating"""
        always = [_make_group(start=0)]
        rot = [[_make_group(start=100)], [_make_group(start=200)]]
        scheduler = ReadScheduler(always_groups=always, rotating_groups=rot)

        assert scheduler.rotating_count == 2
        assert scheduler.has_rotating is True

    def test_construction_with_none_values(self):
        """明確傳入 None"""
        scheduler = ReadScheduler(always_groups=None, rotating_groups=None)

        assert scheduler.rotating_count == 0
        assert scheduler.has_rotating is False

    def test_construction_with_empty_sequences(self):
        """傳入空序列"""
        scheduler = ReadScheduler(always_groups=[], rotating_groups=[])

        assert scheduler.rotating_count == 0
        assert scheduler.has_rotating is False

    def test_construction_copies_inputs(self):
        """建構時應複製輸入序列（修改原始不影響排程器）"""
        always = [_make_group(start=0)]
        rot_a = [_make_group(start=100)]
        rot_groups = [rot_a]

        scheduler = ReadScheduler(always_groups=always, rotating_groups=rot_groups)

        # 修改原始列表
        always.append(_make_group(start=999))
        rot_groups.append([_make_group(start=888)])

        # 排程器不受影響
        result = scheduler.get_next_groups()
        assert len(result) == 2  # 1 always + 1 rotating (rot_a)
        assert scheduler.rotating_count == 1


# ======================== Always-Only Tests ========================


class TestGetNextGroupsAlwaysOnly:
    """get_next_groups() 僅有固定群組"""

    def test_returns_all_always_groups(self):
        """每次都回傳所有 always_groups"""
        g1 = _make_group(start=0)
        g2 = _make_group(start=10)
        scheduler = ReadScheduler(always_groups=[g1, g2])

        result = scheduler.get_next_groups()

        assert len(result) == 2
        assert result[0] == g1
        assert result[1] == g2

    def test_multiple_calls_return_same_groups(self):
        """多次呼叫都回傳相同群組"""
        g1 = _make_group(start=0)
        scheduler = ReadScheduler(always_groups=[g1])

        for _ in range(5):
            result = scheduler.get_next_groups()
            assert result == [g1]

    def test_returns_new_list_each_call(self):
        """每次回傳新的列表實例"""
        scheduler = ReadScheduler(always_groups=[_make_group()])

        r1 = scheduler.get_next_groups()
        r2 = scheduler.get_next_groups()

        assert r1 is not r2
        assert r1 == r2


# ======================== Rotating-Only Tests ========================


class TestGetNextGroupsRotatingOnly:
    """get_next_groups() 僅有輪替群組"""

    def test_first_call_returns_first_rotating(self):
        """第一次呼叫回傳 rotating_groups[0]"""
        rot_a = [_make_group(start=100)]
        rot_b = [_make_group(start=200)]
        scheduler = ReadScheduler(rotating_groups=[rot_a, rot_b])

        result = scheduler.get_next_groups()

        assert result == rot_a

    def test_second_call_returns_second_rotating(self):
        """第二次呼叫回傳 rotating_groups[1]"""
        rot_a = [_make_group(start=100)]
        rot_b = [_make_group(start=200)]
        scheduler = ReadScheduler(rotating_groups=[rot_a, rot_b])

        scheduler.get_next_groups()  # 消耗第一組
        result = scheduler.get_next_groups()

        assert result == rot_b

    def test_rotation_advances_index(self):
        """每次 get_next_groups 推進 rotating_index"""
        rot_a = [_make_group(start=100)]
        rot_b = [_make_group(start=200)]
        rot_c = [_make_group(start=300)]
        scheduler = ReadScheduler(rotating_groups=[rot_a, rot_b, rot_c])

        assert scheduler.current_rotating_index == 0

        scheduler.get_next_groups()
        assert scheduler.current_rotating_index == 1

        scheduler.get_next_groups()
        assert scheduler.current_rotating_index == 2

        scheduler.get_next_groups()
        assert scheduler.current_rotating_index == 0  # 回繞

    def test_three_groups_full_cycle(self):
        """三組輪替完整循環"""
        rot_a = [_make_group(start=100)]
        rot_b = [_make_group(start=200)]
        rot_c = [_make_group(start=300)]
        scheduler = ReadScheduler(rotating_groups=[rot_a, rot_b, rot_c])

        assert scheduler.get_next_groups() == rot_a
        assert scheduler.get_next_groups() == rot_b
        assert scheduler.get_next_groups() == rot_c
        # 回繞
        assert scheduler.get_next_groups() == rot_a
        assert scheduler.get_next_groups() == rot_b
        assert scheduler.get_next_groups() == rot_c

    def test_rotating_groups_with_multiple_groups_per_slot(self):
        """每個輪替槽位含多個 ReadGroup"""
        rot_a = [_make_group(start=100), _make_group(start=110)]
        rot_b = [_make_group(start=200), _make_group(start=210), _make_group(start=220)]
        scheduler = ReadScheduler(rotating_groups=[rot_a, rot_b])

        result1 = scheduler.get_next_groups()
        assert len(result1) == 2
        assert result1 == rot_a

        result2 = scheduler.get_next_groups()
        assert len(result2) == 3
        assert result2 == rot_b


# ======================== Mixed Mode Tests ========================


class TestGetNextGroupsMixed:
    """get_next_groups() 混合固定 + 輪替群組"""

    def test_always_plus_first_rotating(self):
        """第一次呼叫回傳 always + rotating[0]"""
        always_g = _make_group(start=0)
        rot_a = [_make_group(start=100)]
        rot_b = [_make_group(start=200)]
        scheduler = ReadScheduler(always_groups=[always_g], rotating_groups=[rot_a, rot_b])

        result = scheduler.get_next_groups()

        assert len(result) == 2
        assert result[0] == always_g
        assert result[1] == rot_a[0]

    def test_always_plus_second_rotating(self):
        """第二次呼叫回傳 always + rotating[1]"""
        always_g = _make_group(start=0)
        rot_a = [_make_group(start=100)]
        rot_b = [_make_group(start=200)]
        scheduler = ReadScheduler(always_groups=[always_g], rotating_groups=[rot_a, rot_b])

        scheduler.get_next_groups()  # 消耗 rot_a
        result = scheduler.get_next_groups()

        assert len(result) == 2
        assert result[0] == always_g
        assert result[1] == rot_b[0]

    def test_full_cycle_mixed(self):
        """完整循環：always 始終在前"""
        a1 = _make_group(start=0)
        a2 = _make_group(start=10)
        rot_x = [_make_group(start=100)]
        rot_y = [_make_group(start=200)]
        rot_z = [_make_group(start=300)]
        scheduler = ReadScheduler(always_groups=[a1, a2], rotating_groups=[rot_x, rot_y, rot_z])

        for cycle in range(2):
            r1 = scheduler.get_next_groups()
            assert r1 == [a1, a2, rot_x[0]], f"cycle={cycle}, call=0"

            r2 = scheduler.get_next_groups()
            assert r2 == [a1, a2, rot_y[0]], f"cycle={cycle}, call=1"

            r3 = scheduler.get_next_groups()
            assert r3 == [a1, a2, rot_z[0]], f"cycle={cycle}, call=2"

    def test_always_groups_order_preserved(self):
        """always_groups 的順序應被保留"""
        g1 = _make_group(start=0, count=1)
        g2 = _make_group(start=10, count=2)
        g3 = _make_group(start=20, count=3)
        scheduler = ReadScheduler(always_groups=[g1, g2, g3])

        result = scheduler.get_next_groups()

        assert result[0].count == 1
        assert result[1].count == 2
        assert result[2].count == 3


# ======================== Peek Tests ========================


class TestPeekNextGroups:
    """peek_next_groups() 測試"""

    def test_peek_returns_same_as_get_without_advancing(self):
        """peek 結果與接下來的 get 一致"""
        rot_a = [_make_group(start=100)]
        rot_b = [_make_group(start=200)]
        scheduler = ReadScheduler(rotating_groups=[rot_a, rot_b])

        peeked = scheduler.peek_next_groups()
        actual = scheduler.get_next_groups()

        assert peeked == actual

    def test_peek_does_not_advance_index(self):
        """多次 peek 不推進索引"""
        rot_a = [_make_group(start=100)]
        rot_b = [_make_group(start=200)]
        scheduler = ReadScheduler(rotating_groups=[rot_a, rot_b])

        assert scheduler.current_rotating_index == 0

        scheduler.peek_next_groups()
        assert scheduler.current_rotating_index == 0

        scheduler.peek_next_groups()
        assert scheduler.current_rotating_index == 0

        scheduler.peek_next_groups()
        assert scheduler.current_rotating_index == 0

    def test_peek_multiple_times_returns_consistent_result(self):
        """連續 peek 多次都回傳同樣結果"""
        always_g = _make_group(start=0)
        rot_a = [_make_group(start=100)]
        rot_b = [_make_group(start=200)]
        scheduler = ReadScheduler(always_groups=[always_g], rotating_groups=[rot_a, rot_b])

        results = [scheduler.peek_next_groups() for _ in range(5)]

        for r in results:
            assert r == [always_g, rot_a[0]]

    def test_peek_after_get_reflects_new_position(self):
        """get 推進後，peek 反映新位置"""
        rot_a = [_make_group(start=100)]
        rot_b = [_make_group(start=200)]
        scheduler = ReadScheduler(rotating_groups=[rot_a, rot_b])

        # 初始 peek -> rot_a
        assert scheduler.peek_next_groups() == rot_a

        # get 推進
        scheduler.get_next_groups()

        # peek 現在應為 rot_b
        assert scheduler.peek_next_groups() == rot_b

    def test_peek_with_always_only(self):
        """無 rotating 時 peek 回傳 always"""
        g1 = _make_group(start=0)
        scheduler = ReadScheduler(always_groups=[g1])

        assert scheduler.peek_next_groups() == [g1]

    def test_peek_empty_scheduler(self):
        """空排程器 peek 回傳空列表"""
        scheduler = ReadScheduler()

        assert scheduler.peek_next_groups() == []

    def test_peek_returns_new_list_each_call(self):
        """peek 每次回傳新的列表實例"""
        scheduler = ReadScheduler(always_groups=[_make_group()])

        p1 = scheduler.peek_next_groups()
        p2 = scheduler.peek_next_groups()

        assert p1 is not p2
        assert p1 == p2


# ======================== Reset Tests ========================


class TestReset:
    """reset() 測試"""

    def test_reset_sets_index_to_zero(self):
        """reset 將索引歸零"""
        rot_a = [_make_group(start=100)]
        rot_b = [_make_group(start=200)]
        rot_c = [_make_group(start=300)]
        scheduler = ReadScheduler(rotating_groups=[rot_a, rot_b, rot_c])

        scheduler.get_next_groups()
        scheduler.get_next_groups()
        assert scheduler.current_rotating_index == 2

        scheduler.reset()

        assert scheduler.current_rotating_index == 0

    def test_reset_makes_get_return_first_rotating(self):
        """reset 後 get 從第一組開始"""
        rot_a = [_make_group(start=100)]
        rot_b = [_make_group(start=200)]
        scheduler = ReadScheduler(rotating_groups=[rot_a, rot_b])

        scheduler.get_next_groups()  # rot_a, index -> 1
        scheduler.get_next_groups()  # rot_b, index -> 0

        scheduler.get_next_groups()  # rot_a, index -> 1
        scheduler.reset()

        result = scheduler.get_next_groups()
        assert result == rot_a

    def test_reset_on_fresh_scheduler_is_noop(self):
        """新建排程器 reset 無副作用"""
        scheduler = ReadScheduler(rotating_groups=[[_make_group()]])

        scheduler.reset()

        assert scheduler.current_rotating_index == 0

    def test_reset_without_rotating_is_safe(self):
        """無 rotating 時 reset 不拋異常"""
        scheduler = ReadScheduler(always_groups=[_make_group()])

        scheduler.reset()  # 不應拋異常

        assert scheduler.current_rotating_index == 0

    def test_reset_midway_through_cycle(self):
        """循環中途 reset 重新從頭開始"""
        rot_a = [_make_group(start=100)]
        rot_b = [_make_group(start=200)]
        rot_c = [_make_group(start=300)]
        scheduler = ReadScheduler(rotating_groups=[rot_a, rot_b, rot_c])

        scheduler.get_next_groups()  # rot_a -> index 1
        scheduler.get_next_groups()  # rot_b -> index 2

        scheduler.reset()

        # 重新從 rot_a 開始
        assert scheduler.get_next_groups() == rot_a
        assert scheduler.get_next_groups() == rot_b
        assert scheduler.get_next_groups() == rot_c
        assert scheduler.get_next_groups() == rot_a


# ======================== Empty Groups Edge Case ========================


class TestEmptyGroups:
    """空群組邊界情況"""

    def test_empty_scheduler_returns_empty_list(self):
        """無 always 也無 rotating 回傳空列表"""
        scheduler = ReadScheduler()

        assert scheduler.get_next_groups() == []

    def test_empty_always_with_rotating(self):
        """空 always 但有 rotating"""
        rot = [_make_group(start=100)]
        scheduler = ReadScheduler(always_groups=[], rotating_groups=[rot])

        result = scheduler.get_next_groups()
        assert result == rot

    def test_always_with_empty_rotating(self):
        """有 always 但空 rotating"""
        g = _make_group(start=0)
        scheduler = ReadScheduler(always_groups=[g], rotating_groups=[])

        result = scheduler.get_next_groups()
        assert result == [g]

    def test_rotating_slot_with_empty_group_list(self):
        """輪替槽位本身是空列表"""
        rot_a = [_make_group(start=100)]
        rot_empty: list[ReadGroup] = []
        rot_c = [_make_group(start=300)]
        scheduler = ReadScheduler(rotating_groups=[rot_a, rot_empty, rot_c])

        # 第一次: rot_a
        r1 = scheduler.get_next_groups()
        assert len(r1) == 1
        assert r1 == rot_a

        # 第二次: empty -> 回傳空
        r2 = scheduler.get_next_groups()
        assert r2 == []

        # 第三次: rot_c
        r3 = scheduler.get_next_groups()
        assert len(r3) == 1
        assert r3 == rot_c

    def test_rotating_slot_with_empty_group_list_mixed(self):
        """混合模式下空輪替槽位只回傳 always"""
        always_g = _make_group(start=0)
        rot_empty: list[ReadGroup] = []
        scheduler = ReadScheduler(always_groups=[always_g], rotating_groups=[rot_empty])

        result = scheduler.get_next_groups()

        assert result == [always_g]


# ======================== Single Rotating Group Wrap-Around ========================


class TestSingleRotatingGroupWrapAround:
    """單一輪替群組回繞測試"""

    def test_single_rotating_always_returns_same(self):
        """只有一組 rotating，每次都回傳同一組"""
        rot = [_make_group(start=100), _make_group(start=110)]
        scheduler = ReadScheduler(rotating_groups=[rot])

        for _ in range(10):
            result = scheduler.get_next_groups()
            assert result == rot

    def test_single_rotating_index_stays_at_zero(self):
        """只有一組 rotating，索引始終在 0（0 % 1 == 0）"""
        scheduler = ReadScheduler(rotating_groups=[[_make_group()]])

        for _ in range(5):
            scheduler.get_next_groups()
            assert scheduler.current_rotating_index == 0

    def test_single_rotating_with_always(self):
        """一組 rotating 加 always"""
        always_g = _make_group(start=0)
        rot = [_make_group(start=100)]
        scheduler = ReadScheduler(always_groups=[always_g], rotating_groups=[rot])

        for _ in range(5):
            result = scheduler.get_next_groups()
            assert result == [always_g, rot[0]]


# ======================== Multiple Calls Cycling Tests ========================


class TestMultipleCallsCycling:
    """多次呼叫循環驗證"""

    def test_two_groups_cycle_ten_times(self):
        """兩組輪替循環 10 次"""
        rot_a = [_make_group(start=100)]
        rot_b = [_make_group(start=200)]
        scheduler = ReadScheduler(rotating_groups=[rot_a, rot_b])

        for i in range(20):
            result = scheduler.get_next_groups()
            expected = rot_a if i % 2 == 0 else rot_b
            assert result == expected, f"call={i}"

    def test_five_groups_cycle(self):
        """五組輪替循環驗證"""
        groups = [[_make_group(start=i * 100)] for i in range(5)]
        scheduler = ReadScheduler(rotating_groups=groups)

        for cycle in range(3):
            for i in range(5):
                result = scheduler.get_next_groups()
                assert result == groups[i], f"cycle={cycle}, slot={i}"

    def test_index_property_tracks_correctly(self):
        """current_rotating_index 屬性在完整循環中正確追蹤"""
        scheduler = ReadScheduler(rotating_groups=[[_make_group()] for _ in range(4)])

        indices = []
        for _ in range(12):
            indices.append(scheduler.current_rotating_index)
            scheduler.get_next_groups()

        expected = [0, 1, 2, 3, 0, 1, 2, 3, 0, 1, 2, 3]
        assert indices == expected

    def test_interleaved_peek_and_get(self):
        """交錯使用 peek 與 get"""
        rot_a = [_make_group(start=100)]
        rot_b = [_make_group(start=200)]
        rot_c = [_make_group(start=300)]
        scheduler = ReadScheduler(rotating_groups=[rot_a, rot_b, rot_c])

        # peek -> rot_a (index 0, not advanced)
        assert scheduler.peek_next_groups() == rot_a

        # get -> rot_a (index 0 -> 1)
        assert scheduler.get_next_groups() == rot_a

        # peek -> rot_b (index 1, not advanced)
        assert scheduler.peek_next_groups() == rot_b
        assert scheduler.peek_next_groups() == rot_b

        # get -> rot_b (index 1 -> 2)
        assert scheduler.get_next_groups() == rot_b

        # get -> rot_c (index 2 -> 0)
        assert scheduler.get_next_groups() == rot_c

        # peek -> rot_a (index 0, wrapped around)
        assert scheduler.peek_next_groups() == rot_a

    def test_reset_during_cycling(self):
        """循環過程中穿插 reset"""
        rot_a = [_make_group(start=100)]
        rot_b = [_make_group(start=200)]
        rot_c = [_make_group(start=300)]
        scheduler = ReadScheduler(rotating_groups=[rot_a, rot_b, rot_c])

        assert scheduler.get_next_groups() == rot_a  # index -> 1
        assert scheduler.get_next_groups() == rot_b  # index -> 2

        scheduler.reset()

        assert scheduler.get_next_groups() == rot_a  # index -> 1
        assert scheduler.get_next_groups() == rot_b  # index -> 2
        assert scheduler.get_next_groups() == rot_c  # index -> 0

        scheduler.reset()

        assert scheduler.get_next_groups() == rot_a  # index -> 1


# ======================== Properties Tests ========================


class TestProperties:
    """屬性測試"""

    def test_rotating_count_zero(self):
        """無 rotating 時 count 為 0"""
        scheduler = ReadScheduler()
        assert scheduler.rotating_count == 0

    def test_rotating_count_matches_input(self):
        """rotating_count 與輸入數量一致"""
        groups = [[_make_group()] for _ in range(7)]
        scheduler = ReadScheduler(rotating_groups=groups)
        assert scheduler.rotating_count == 7

    def test_has_rotating_false_when_empty(self):
        """無 rotating 時 has_rotating 為 False"""
        scheduler = ReadScheduler()
        assert scheduler.has_rotating is False

    def test_has_rotating_true_when_present(self):
        """有 rotating 時 has_rotating 為 True"""
        scheduler = ReadScheduler(rotating_groups=[[_make_group()]])
        assert scheduler.has_rotating is True

    def test_current_rotating_index_initial(self):
        """初始 rotating_index 為 0"""
        scheduler = ReadScheduler(rotating_groups=[[_make_group()], [_make_group()]])
        assert scheduler.current_rotating_index == 0
