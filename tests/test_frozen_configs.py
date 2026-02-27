# =============== Frozen Dataclass Config Tests ===============
#
# Comprehensive tests for 6 frozen dataclass configs with __post_init__ validation:
#   1. PointGrouperConfig
#   2. AlarmPersistenceConfig
#   3. CommandAdapterConfig
#   4. StateSyncConfig
#   5. ScheduleServiceConfig
#   6. NotificationConfig

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from csp_lib.equipment.transport.config import PointGrouperConfig
from csp_lib.manager.alarm.config import AlarmPersistenceConfig
from csp_lib.manager.command.adapters.config import CommandAdapterConfig
from csp_lib.manager.schedule.config import ScheduleServiceConfig
from csp_lib.manager.state.config import StateSyncConfig
from csp_lib.notification.config import NotificationConfig

# ---------------------------------------------------------------------------
# 1. PointGrouperConfig
# ---------------------------------------------------------------------------


class TestPointGrouperConfig:
    """PointGrouperConfig 單元測試"""

    def test_default_values(self):
        """預設 fc_max_length 應包含 4 個功能碼，且值正確"""
        config = PointGrouperConfig()
        assert config.fc_max_length == {
            1: 2000,
            2: 2000,
            3: 125,
            4: 125,
        }

    def test_default_dict_is_independent_copy(self):
        """每次建立的預設 dict 應為獨立副本"""
        c1 = PointGrouperConfig()
        c2 = PointGrouperConfig()
        assert c1.fc_max_length is not c2.fc_max_length

    def test_custom_fc_max_length(self):
        """自訂 fc_max_length 應被接受"""
        custom = {3: 50, 4: 80}
        config = PointGrouperConfig(fc_max_length=custom)
        assert config.fc_max_length == {3: 50, 4: 80}

    def test_single_entry(self):
        """僅一個功能碼也應有效"""
        config = PointGrouperConfig(fc_max_length={1: 1})
        assert config.fc_max_length == {1: 1}

    def test_empty_dict_is_valid(self):
        """空字典不違反驗證（無元素可檢查）"""
        config = PointGrouperConfig(fc_max_length={})
        assert config.fc_max_length == {}

    @pytest.mark.parametrize("bad_length", [0, -1, -100])
    def test_zero_or_negative_length_raises(self, bad_length: int):
        """fc_max_length 中任何值 <= 0 應拋 ValueError"""
        with pytest.raises(ValueError, match="最大讀取長度必須大於 0"):
            PointGrouperConfig(fc_max_length={3: bad_length})

    def test_multiple_entries_one_invalid(self):
        """多筆中只要有一筆 <= 0 就應拋 ValueError"""
        with pytest.raises(ValueError, match="最大讀取長度必須大於 0"):
            PointGrouperConfig(fc_max_length={1: 2000, 3: 0})

    def test_error_message_contains_fc_code(self):
        """錯誤訊息應包含功能碼編號"""
        with pytest.raises(ValueError, match="功能碼 99"):
            PointGrouperConfig(fc_max_length={99: -5})

    def test_frozen_immutability(self):
        """PointGrouperConfig 應為不可變"""
        config = PointGrouperConfig()
        with pytest.raises(FrozenInstanceError):
            config.fc_max_length = {}  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 2. AlarmPersistenceConfig
# ---------------------------------------------------------------------------


class TestAlarmPersistenceConfig:
    """AlarmPersistenceConfig 單元測試"""

    def test_default_values(self):
        """預設值應正確"""
        config = AlarmPersistenceConfig()
        assert config.disconnect_code == "DISCONNECT"
        assert config.disconnect_name == "設備斷線"

    def test_custom_values(self):
        """自訂值應被接受"""
        config = AlarmPersistenceConfig(disconnect_code="DC_001", disconnect_name="Link Down")
        assert config.disconnect_code == "DC_001"
        assert config.disconnect_name == "Link Down"

    @pytest.mark.parametrize("empty_val", ["", None])
    def test_empty_disconnect_code_raises(self, empty_val):
        """空的 disconnect_code 應拋 ValueError"""
        with pytest.raises(ValueError, match="disconnect_code 不可為空"):
            AlarmPersistenceConfig(disconnect_code=empty_val)  # type: ignore[arg-type]

    @pytest.mark.parametrize("empty_val", ["", None])
    def test_empty_disconnect_name_raises(self, empty_val):
        """空的 disconnect_name 應拋 ValueError"""
        with pytest.raises(ValueError, match="disconnect_name 不可為空"):
            AlarmPersistenceConfig(disconnect_name=empty_val)  # type: ignore[arg-type]

    def test_whitespace_only_disconnect_code_accepted(self):
        """僅含空白的 disconnect_code 視為非空（truthy），應被接受"""
        config = AlarmPersistenceConfig(disconnect_code="  ")
        assert config.disconnect_code == "  "

    def test_frozen_disconnect_code(self):
        """不可修改 disconnect_code"""
        config = AlarmPersistenceConfig()
        with pytest.raises(FrozenInstanceError):
            config.disconnect_code = "NEW"  # type: ignore[misc]

    def test_frozen_disconnect_name(self):
        """不可修改 disconnect_name"""
        config = AlarmPersistenceConfig()
        with pytest.raises(FrozenInstanceError):
            config.disconnect_name = "NEW"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 3. CommandAdapterConfig
# ---------------------------------------------------------------------------


class TestCommandAdapterConfig:
    """CommandAdapterConfig 單元測試"""

    def test_default_values(self):
        """預設值應正確"""
        config = CommandAdapterConfig()
        assert config.command_channel == "channel:commands:write"
        assert config.result_channel == "channel:commands:result"

    def test_custom_values(self):
        """自訂 channel 名稱應被接受"""
        config = CommandAdapterConfig(command_channel="cmd:in", result_channel="cmd:out")
        assert config.command_channel == "cmd:in"
        assert config.result_channel == "cmd:out"

    @pytest.mark.parametrize("empty_val", ["", None])
    def test_empty_command_channel_raises(self, empty_val):
        """空的 command_channel 應拋 ValueError"""
        with pytest.raises(ValueError, match="command_channel 不可為空"):
            CommandAdapterConfig(command_channel=empty_val)  # type: ignore[arg-type]

    @pytest.mark.parametrize("empty_val", ["", None])
    def test_empty_result_channel_raises(self, empty_val):
        """空的 result_channel 應拋 ValueError"""
        with pytest.raises(ValueError, match="result_channel 不可為空"):
            CommandAdapterConfig(result_channel=empty_val)  # type: ignore[arg-type]

    def test_both_empty_raises(self):
        """兩個 channel 同時為空，應先報 command_channel"""
        with pytest.raises(ValueError, match="command_channel 不可為空"):
            CommandAdapterConfig(command_channel="", result_channel="")

    def test_frozen_command_channel(self):
        """不可修改 command_channel"""
        config = CommandAdapterConfig()
        with pytest.raises(FrozenInstanceError):
            config.command_channel = "new"  # type: ignore[misc]

    def test_frozen_result_channel(self):
        """不可修改 result_channel"""
        config = CommandAdapterConfig()
        with pytest.raises(FrozenInstanceError):
            config.result_channel = "new"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 4. StateSyncConfig
# ---------------------------------------------------------------------------


class TestStateSyncConfig:
    """StateSyncConfig 單元測試"""

    def test_default_values(self):
        """預設值應正確"""
        config = StateSyncConfig()
        assert config.state_ttl == 60
        assert config.online_ttl == 60

    def test_custom_values(self):
        """自訂值應被接受"""
        config = StateSyncConfig(state_ttl=120, online_ttl=30)
        assert config.state_ttl == 120
        assert config.online_ttl == 30

    def test_boundary_value_one(self):
        """最小合法值 1 應被接受"""
        config = StateSyncConfig(state_ttl=1, online_ttl=1)
        assert config.state_ttl == 1
        assert config.online_ttl == 1

    def test_large_ttl(self):
        """大 TTL 值應被接受"""
        config = StateSyncConfig(state_ttl=86400, online_ttl=86400)
        assert config.state_ttl == 86400

    @pytest.mark.parametrize("bad_ttl", [0, -1, -100])
    def test_zero_or_negative_state_ttl_raises(self, bad_ttl: int):
        """state_ttl <= 0 應拋 ValueError"""
        with pytest.raises(ValueError, match="state_ttl 必須大於 0"):
            StateSyncConfig(state_ttl=bad_ttl)

    @pytest.mark.parametrize("bad_ttl", [0, -1, -100])
    def test_zero_or_negative_online_ttl_raises(self, bad_ttl: int):
        """online_ttl <= 0 應拋 ValueError"""
        with pytest.raises(ValueError, match="online_ttl 必須大於 0"):
            StateSyncConfig(online_ttl=bad_ttl)

    def test_error_message_contains_value(self):
        """錯誤訊息應包含實際收到的值"""
        with pytest.raises(ValueError, match="-42"):
            StateSyncConfig(state_ttl=-42)

    def test_both_invalid_raises_state_ttl_first(self):
        """兩者同時不合法，應先拋 state_ttl 的錯誤"""
        with pytest.raises(ValueError, match="state_ttl"):
            StateSyncConfig(state_ttl=0, online_ttl=0)

    def test_frozen_state_ttl(self):
        """不可修改 state_ttl"""
        config = StateSyncConfig()
        with pytest.raises(FrozenInstanceError):
            config.state_ttl = 999  # type: ignore[misc]

    def test_frozen_online_ttl(self):
        """不可修改 online_ttl"""
        config = StateSyncConfig()
        with pytest.raises(FrozenInstanceError):
            config.online_ttl = 999  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 5. ScheduleServiceConfig
# ---------------------------------------------------------------------------


class TestScheduleServiceConfig:
    """ScheduleServiceConfig 單元測試"""

    def test_default_poll_interval_and_timezone(self):
        """預設 poll_interval 與 timezone_name 應正確（site_id 必須提供）"""
        config = ScheduleServiceConfig(site_id="site_001")
        assert config.poll_interval == 30.0
        assert config.timezone_name == "Asia/Taipei"

    def test_default_site_id_is_empty_and_raises(self):
        """預設 site_id 為空字串，建立時應拋 ValueError"""
        with pytest.raises(ValueError, match="site_id 不可為空"):
            ScheduleServiceConfig()

    def test_custom_values(self):
        """自訂值應被接受"""
        config = ScheduleServiceConfig(
            site_id="plant_A",
            poll_interval=10.0,
            timezone_name="UTC",
        )
        assert config.site_id == "plant_A"
        assert config.poll_interval == 10.0
        assert config.timezone_name == "UTC"

    @pytest.mark.parametrize("empty_val", ["", None])
    def test_empty_site_id_raises(self, empty_val):
        """空 site_id 應拋 ValueError"""
        with pytest.raises(ValueError, match="site_id 不可為空"):
            ScheduleServiceConfig(site_id=empty_val)  # type: ignore[arg-type]

    @pytest.mark.parametrize("bad_interval", [0, 0.0, -1, -0.5, -100.0])
    def test_zero_or_negative_poll_interval_raises(self, bad_interval: float):
        """poll_interval <= 0 應拋 ValueError"""
        with pytest.raises(ValueError, match="poll_interval 必須大於 0"):
            ScheduleServiceConfig(site_id="s1", poll_interval=bad_interval)

    def test_boundary_poll_interval_just_above_zero(self):
        """極小正數 poll_interval 應被接受"""
        config = ScheduleServiceConfig(site_id="s1", poll_interval=0.001)
        assert config.poll_interval == pytest.approx(0.001)

    def test_error_message_contains_poll_interval_value(self):
        """錯誤訊息應包含實際值"""
        with pytest.raises(ValueError, match="-5"):
            ScheduleServiceConfig(site_id="s1", poll_interval=-5)

    def test_frozen_site_id(self):
        """不可修改 site_id"""
        config = ScheduleServiceConfig(site_id="s1")
        with pytest.raises(FrozenInstanceError):
            config.site_id = "s2"  # type: ignore[misc]

    def test_frozen_poll_interval(self):
        """不可修改 poll_interval"""
        config = ScheduleServiceConfig(site_id="s1")
        with pytest.raises(FrozenInstanceError):
            config.poll_interval = 99.0  # type: ignore[misc]

    def test_frozen_timezone_name(self):
        """不可修改 timezone_name"""
        config = ScheduleServiceConfig(site_id="s1")
        with pytest.raises(FrozenInstanceError):
            config.timezone_name = "UTC"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 6. NotificationConfig
# ---------------------------------------------------------------------------


class TestNotificationConfig:
    """NotificationConfig 單元測試"""

    def test_default_values(self):
        """預設值應正確"""
        config = NotificationConfig()
        assert config.triggered_label == "觸發"
        assert config.resolved_label == "解除"
        assert config.title_template == "[{level}] {device_id} {name} - {event_label}"

    def test_custom_values(self):
        """自訂值應被接受"""
        config = NotificationConfig(
            triggered_label="TRIGGERED",
            resolved_label="RESOLVED",
            title_template="{device_id}: {name}",
        )
        assert config.triggered_label == "TRIGGERED"
        assert config.resolved_label == "RESOLVED"
        assert config.title_template == "{device_id}: {name}"

    @pytest.mark.parametrize("empty_val", ["", None])
    def test_empty_triggered_label_raises(self, empty_val):
        """空 triggered_label 應拋 ValueError"""
        with pytest.raises(ValueError, match="triggered_label 不可為空"):
            NotificationConfig(triggered_label=empty_val)  # type: ignore[arg-type]

    @pytest.mark.parametrize("empty_val", ["", None])
    def test_empty_resolved_label_raises(self, empty_val):
        """空 resolved_label 應拋 ValueError"""
        with pytest.raises(ValueError, match="resolved_label 不可為空"):
            NotificationConfig(resolved_label=empty_val)  # type: ignore[arg-type]

    @pytest.mark.parametrize("empty_val", ["", None])
    def test_empty_title_template_raises(self, empty_val):
        """空 title_template 應拋 ValueError"""
        with pytest.raises(ValueError, match="title_template 不可為空"):
            NotificationConfig(title_template=empty_val)  # type: ignore[arg-type]

    def test_all_empty_raises_triggered_first(self):
        """三個欄位同時為空，應先報 triggered_label 的錯誤"""
        with pytest.raises(ValueError, match="triggered_label 不可為空"):
            NotificationConfig(triggered_label="", resolved_label="", title_template="")

    def test_whitespace_only_is_accepted(self):
        """僅含空白的字串視為非空（truthy），應被接受"""
        config = NotificationConfig(triggered_label=" ", resolved_label=" ", title_template=" ")
        assert config.triggered_label == " "

    def test_frozen_triggered_label(self):
        """不可修改 triggered_label"""
        config = NotificationConfig()
        with pytest.raises(FrozenInstanceError):
            config.triggered_label = "X"  # type: ignore[misc]

    def test_frozen_resolved_label(self):
        """不可修改 resolved_label"""
        config = NotificationConfig()
        with pytest.raises(FrozenInstanceError):
            config.resolved_label = "X"  # type: ignore[misc]

    def test_frozen_title_template(self):
        """不可修改 title_template"""
        config = NotificationConfig()
        with pytest.raises(FrozenInstanceError):
            config.title_template = "X"  # type: ignore[misc]
