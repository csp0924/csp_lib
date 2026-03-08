# =============== ModeManager - update_mode_strategy & async_unregister Tests ===============
#
# 測試覆蓋：
# - update_mode_strategy() 正確替換策略
# - update_mode_strategy() 活躍模式觸發 on_deactivate/on_activate
# - update_mode_strategy() 非活躍模式不觸發生命週期
# - update_mode_strategy() 觸發 _notify_change
# - async_unregister() 活躍模式觸發 on_deactivate + _notify_change
# - async_unregister() 非活躍模式僅移除
# - add_base_mode / remove_base_mode 的 source 參數

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from csp_lib.controller.system.mode import ModeManager, ModePriority, SwitchSource


def _make_strategy(name: str = "strategy") -> MagicMock:
    """建立帶有 on_activate/on_deactivate 的 mock 策略"""
    s = MagicMock()
    s.on_activate = AsyncMock()
    s.on_deactivate = AsyncMock()
    s.__str__ = lambda self: name
    return s


class TestUpdateModeStrategy:
    """update_mode_strategy 測試"""

    @pytest.mark.asyncio
    async def test_replaces_strategy(self):
        """應正確替換已註冊模式的策略"""
        mm = ModeManager()
        old_s = _make_strategy("old")
        new_s = _make_strategy("new")

        mm.register("pq", old_s, ModePriority.SCHEDULE)
        await mm.update_mode_strategy("pq", new_s)

        assert mm.registered_modes["pq"].strategy is new_s

    @pytest.mark.asyncio
    async def test_active_mode_triggers_lifecycle(self):
        """活躍模式替換策略應觸發 on_deactivate/on_activate"""
        mm = ModeManager()
        old_s = _make_strategy("old")
        new_s = _make_strategy("new")

        mm.register("pq", old_s, ModePriority.SCHEDULE)
        await mm.set_base_mode("pq")

        await mm.update_mode_strategy("pq", new_s)

        old_s.on_deactivate.assert_awaited_once()
        new_s.on_activate.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_inactive_mode_no_lifecycle(self):
        """非活躍模式替換策略不應觸發生命週期"""
        mm = ModeManager()
        old_s = _make_strategy("old")
        new_s = _make_strategy("new")

        mm.register("pq", old_s, ModePriority.SCHEDULE)
        # 不設定為 base mode，模式未啟用

        await mm.update_mode_strategy("pq", new_s)

        old_s.on_deactivate.assert_not_awaited()
        new_s.on_activate.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_triggers_notify_change_when_active(self):
        """活躍模式替換策略應觸發 on_strategy_change"""
        callback = AsyncMock()
        mm = ModeManager(on_strategy_change=callback)
        old_s = _make_strategy("old")
        new_s = _make_strategy("new")

        mm.register("pq", old_s, ModePriority.SCHEDULE)
        await mm.set_base_mode("pq")
        callback.reset_mock()

        await mm.update_mode_strategy("pq", new_s)

        callback.assert_awaited_once_with(old_s, new_s)

    @pytest.mark.asyncio
    async def test_notify_change_inactive_sends_none(self):
        """非活躍模式替換策略 _notify_change 收到 (None, None)"""
        callback = AsyncMock()
        mm = ModeManager(on_strategy_change=callback)
        old_s = _make_strategy("old")
        new_s = _make_strategy("new")

        mm.register("pq", old_s, ModePriority.SCHEDULE)
        # 非活躍：old_effective=None, new_effective=None → 不觸發（因 None is None）
        await mm.update_mode_strategy("pq", new_s)

        callback.assert_not_awaited()

    @pytest.mark.asyncio
    async def test_unregistered_mode_raises(self):
        """替換不存在的模式應拋出 KeyError"""
        mm = ModeManager()
        with pytest.raises(KeyError, match="not_exist"):
            await mm.update_mode_strategy("not_exist", _make_strategy())

    @pytest.mark.asyncio
    async def test_updates_description(self):
        """應更新描述"""
        mm = ModeManager()
        s1 = _make_strategy()
        s2 = _make_strategy()

        mm.register("pq", s1, ModePriority.SCHEDULE, "old desc")
        await mm.update_mode_strategy("pq", s2, description="new desc")

        assert mm.registered_modes["pq"].description == "new desc"

    @pytest.mark.asyncio
    async def test_preserves_description_when_none(self):
        """description=None 時保留原描述"""
        mm = ModeManager()
        s1 = _make_strategy()
        s2 = _make_strategy()

        mm.register("pq", s1, ModePriority.SCHEDULE, "original")
        await mm.update_mode_strategy("pq", s2)

        assert mm.registered_modes["pq"].description == "original"

    @pytest.mark.asyncio
    async def test_records_source(self):
        """應記錄 SwitchSource"""
        mm = ModeManager()
        s1 = _make_strategy()
        s2 = _make_strategy()

        mm.register("pq", s1, ModePriority.SCHEDULE)
        await mm.update_mode_strategy("pq", s2, source=SwitchSource.SCHEDULE)

        assert mm.last_switch_source == SwitchSource.SCHEDULE

    @pytest.mark.asyncio
    async def test_override_mode_triggers_lifecycle(self):
        """在 override 堆疊中的模式替換策略也應觸發生命週期"""
        mm = ModeManager()
        old_s = _make_strategy("old")
        new_s = _make_strategy("new")

        mm.register("protect", old_s, ModePriority.PROTECTION)
        await mm.push_override("protect")

        await mm.update_mode_strategy("protect", new_s)

        old_s.on_deactivate.assert_awaited_once()
        new_s.on_activate.assert_awaited_once()


class TestAsyncUnregister:
    """async_unregister 測試"""

    @pytest.mark.asyncio
    async def test_active_mode_triggers_deactivate(self):
        """活躍模式 async_unregister 應觸發 on_deactivate"""
        mm = ModeManager()
        s = _make_strategy()

        mm.register("pq", s, ModePriority.SCHEDULE)
        await mm.set_base_mode("pq")

        await mm.async_unregister("pq")

        s.on_deactivate.assert_awaited_once()
        assert "pq" not in mm.registered_modes
        assert mm.base_mode_names == []

    @pytest.mark.asyncio
    async def test_active_mode_triggers_notify_change(self):
        """活躍模式 async_unregister 應觸發 _notify_change"""
        callback = AsyncMock()
        mm = ModeManager(on_strategy_change=callback)
        s = _make_strategy()

        mm.register("pq", s, ModePriority.SCHEDULE)
        await mm.set_base_mode("pq")
        callback.reset_mock()

        await mm.async_unregister("pq")

        # old=s (effective before), new=None (effective after)
        callback.assert_awaited_once_with(s, None)

    @pytest.mark.asyncio
    async def test_inactive_mode_no_lifecycle(self):
        """非活躍模式 async_unregister 不觸發生命週期"""
        mm = ModeManager()
        s = _make_strategy()

        mm.register("pq", s, ModePriority.SCHEDULE)
        await mm.async_unregister("pq")

        s.on_deactivate.assert_not_awaited()
        assert "pq" not in mm.registered_modes

    @pytest.mark.asyncio
    async def test_removes_from_override_stack(self):
        """async_unregister 應從 override 堆疊中移除"""
        mm = ModeManager()
        s = _make_strategy()

        mm.register("protect", s, ModePriority.PROTECTION)
        await mm.push_override("protect")

        await mm.async_unregister("protect")

        assert mm.active_override_names == []
        assert "protect" not in mm.registered_modes

    @pytest.mark.asyncio
    async def test_unregistered_mode_raises(self):
        """移除不存在的模式應拋出 KeyError"""
        mm = ModeManager()
        with pytest.raises(KeyError, match="not_exist"):
            await mm.async_unregister("not_exist")

    @pytest.mark.asyncio
    async def test_records_source(self):
        """應記錄 SwitchSource"""
        mm = ModeManager()
        s = _make_strategy()

        mm.register("pq", s, ModePriority.SCHEDULE)
        await mm.async_unregister("pq", source=SwitchSource.SCHEDULE)

        assert mm.last_switch_source == SwitchSource.SCHEDULE


class TestAddRemoveBaseModeSource:
    """add_base_mode / remove_base_mode 的 source 參數測試"""

    @pytest.mark.asyncio
    async def test_add_base_mode_records_source(self):
        """add_base_mode 應記錄 source"""
        mm = ModeManager()
        s = _make_strategy()

        mm.register("pq", s, ModePriority.SCHEDULE)
        await mm.add_base_mode("pq", source=SwitchSource.SCHEDULE)

        assert mm.last_switch_source == SwitchSource.SCHEDULE

    @pytest.mark.asyncio
    async def test_remove_base_mode_records_source(self):
        """remove_base_mode 應記錄 source"""
        mm = ModeManager()
        s = _make_strategy()

        mm.register("pq", s, ModePriority.SCHEDULE)
        await mm.add_base_mode("pq")
        await mm.remove_base_mode("pq", source=SwitchSource.SCHEDULE)

        assert mm.last_switch_source == SwitchSource.SCHEDULE

    @pytest.mark.asyncio
    async def test_add_base_mode_default_source_none(self):
        """add_base_mode 預設 source 為 None，不改變 last_switch_source"""
        mm = ModeManager()
        s = _make_strategy()

        mm.register("pq", s, ModePriority.SCHEDULE)
        await mm.add_base_mode("pq")

        assert mm.last_switch_source is None
