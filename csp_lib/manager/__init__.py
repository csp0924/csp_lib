# =============== Manager ===============
#
# 管理器模組
#
# 提供各類管理器功能：
#   - alarm: 告警持久化管理
#   - device: 設備讀取管理

from .alarm import (
    AlarmPersistenceManager,
    AlarmRecord,
    AlarmRepository,
    AlarmStatus,
    AlarmType,
    MongoAlarmRepository,
)
from .device import (
    DeviceGroup,
    DeviceManager,
)

__all__ = [
    # Alarm
    "AlarmPersistenceManager",
    "AlarmRepository",
    "MongoAlarmRepository",
    "AlarmRecord",
    "AlarmStatus",
    "AlarmType",
    # Device
    "DeviceGroup",
    "DeviceManager",
]
