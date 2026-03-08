# =============== Manager Base Tests - DeviceEventSubscriber ===============
#
# DeviceEventSubscriber 基底類別單元測試
#
# 測試覆蓋：
# - subscribe() 呼叫 _register_events() 並儲存 cancel callbacks
# - subscribe() 同一設備兩次為冪等操作
# - unsubscribe() 呼叫 cancel callbacks 並觸發 _on_unsubscribe()
# - unsubscribe() 未訂閱設備的邊界情況
# - cancel callbacks 確實在 unsubscribe 時被呼叫
# - 多設備獨立訂閱/取消訂閱

from __future__ import annotations

from typing import Callable
from unittest.mock import MagicMock

import pytest

from csp_lib.manager.base import DeviceEventSubscriber

# ======================== Test Fixtures & Helpers ========================


class ConcreteSubscriber(DeviceEventSubscriber):
    """Concrete implementation of DeviceEventSubscriber for testing."""

    def __init__(self) -> None:
        super().__init__()
        self.register_events_calls: list[str] = []
        self.on_unsubscribe_calls: list[str] = []
        self._cancel_callbacks_per_device: dict[str, list[MagicMock]] = {}

    def _register_events(self, device) -> list[Callable[[], None]]:
        self.register_events_calls.append(device.device_id)
        # Create trackable cancel callbacks for this device
        cb1 = MagicMock(name=f"cancel_cb1_{device.device_id}")
        cb2 = MagicMock(name=f"cancel_cb2_{device.device_id}")
        callbacks = [cb1, cb2]
        self._cancel_callbacks_per_device[device.device_id] = callbacks
        return callbacks

    def _on_unsubscribe(self, device_id: str) -> None:
        self.on_unsubscribe_calls.append(device_id)


class ConcreteSubscriberNoCleanup(DeviceEventSubscriber):
    """Concrete subscriber that does NOT override _on_unsubscribe (tests default no-op)."""

    def _register_events(self, device) -> list[Callable[[], None]]:
        cb = MagicMock(name=f"cancel_{device.device_id}")
        return [cb]


def _make_mock_device(device_id: str) -> MagicMock:
    """Create a MagicMock mimicking AsyncModbusDevice with a device_id."""
    device = MagicMock()
    device.device_id = device_id
    return device


# ======================== Subscribe Tests ========================


class TestDeviceEventSubscriberSubscribe:
    """subscribe() method tests"""

    @pytest.fixture
    def subscriber(self) -> ConcreteSubscriber:
        return ConcreteSubscriber()

    def test_subscribe_calls_register_events(self, subscriber: ConcreteSubscriber):
        """subscribe() should call _register_events() with the device"""
        device = _make_mock_device("dev_001")

        subscriber.subscribe(device)

        assert subscriber.register_events_calls == ["dev_001"]

    def test_subscribe_stores_cancel_callbacks(self, subscriber: ConcreteSubscriber):
        """subscribe() should store the cancel callbacks returned by _register_events()"""
        device = _make_mock_device("dev_001")

        subscriber.subscribe(device)

        assert "dev_001" in subscriber._unsubscribes
        assert len(subscriber._unsubscribes["dev_001"]) == 2

    def test_subscribe_same_device_twice_is_idempotent(self, subscriber: ConcreteSubscriber):
        """subscribe() same device twice should skip the second call (idempotent)"""
        device = _make_mock_device("dev_001")

        subscriber.subscribe(device)
        subscriber.subscribe(device)

        # _register_events should only have been called once
        assert subscriber.register_events_calls == ["dev_001"]
        # Still only 2 callbacks stored
        assert len(subscriber._unsubscribes["dev_001"]) == 2

    def test_subscribe_multiple_devices(self, subscriber: ConcreteSubscriber):
        """subscribe() should track each device independently"""
        dev1 = _make_mock_device("dev_001")
        dev2 = _make_mock_device("dev_002")
        dev3 = _make_mock_device("dev_003")

        subscriber.subscribe(dev1)
        subscriber.subscribe(dev2)
        subscriber.subscribe(dev3)

        assert subscriber.register_events_calls == ["dev_001", "dev_002", "dev_003"]
        assert set(subscriber._unsubscribes.keys()) == {"dev_001", "dev_002", "dev_003"}


# ======================== Unsubscribe Tests ========================


class TestDeviceEventSubscriberUnsubscribe:
    """unsubscribe() method tests"""

    @pytest.fixture
    def subscriber(self) -> ConcreteSubscriber:
        return ConcreteSubscriber()

    def test_unsubscribe_calls_cancel_callbacks(self, subscriber: ConcreteSubscriber):
        """unsubscribe() should invoke all stored cancel callbacks"""
        device = _make_mock_device("dev_001")
        subscriber.subscribe(device)

        # Grab references to the cancel mocks before unsubscribe pops them
        cancel_cbs = subscriber._cancel_callbacks_per_device["dev_001"]

        subscriber.unsubscribe(device)

        for cb in cancel_cbs:
            cb.assert_called_once()

    def test_unsubscribe_calls_on_unsubscribe_hook(self, subscriber: ConcreteSubscriber):
        """unsubscribe() should call _on_unsubscribe() with the device_id"""
        device = _make_mock_device("dev_001")
        subscriber.subscribe(device)

        subscriber.unsubscribe(device)

        assert subscriber.on_unsubscribe_calls == ["dev_001"]

    def test_unsubscribe_removes_device_from_internal_dict(self, subscriber: ConcreteSubscriber):
        """unsubscribe() should remove the device_id from _unsubscribes"""
        device = _make_mock_device("dev_001")
        subscriber.subscribe(device)

        subscriber.unsubscribe(device)

        assert "dev_001" not in subscriber._unsubscribes

    def test_unsubscribe_not_subscribed_device_is_noop(self, subscriber: ConcreteSubscriber):
        """unsubscribe() on a device that was never subscribed should be a no-op"""
        device = _make_mock_device("dev_unknown")

        # Should not raise
        subscriber.unsubscribe(device)

        assert subscriber.on_unsubscribe_calls == []
        assert "dev_unknown" not in subscriber._unsubscribes

    def test_unsubscribe_already_unsubscribed_device_is_noop(self, subscriber: ConcreteSubscriber):
        """unsubscribe() called twice on the same device should only act on the first call"""
        device = _make_mock_device("dev_001")
        subscriber.subscribe(device)

        subscriber.unsubscribe(device)
        subscriber.unsubscribe(device)  # second call

        # _on_unsubscribe should only be called once
        assert subscriber.on_unsubscribe_calls == ["dev_001"]

    def test_unsubscribe_on_unsubscribe_called_after_cancel_callbacks(self, subscriber: ConcreteSubscriber):
        """_on_unsubscribe() should be called AFTER all cancel callbacks have been invoked"""
        device = _make_mock_device("dev_001")
        subscriber.subscribe(device)

        cancel_cbs = subscriber._cancel_callbacks_per_device["dev_001"]
        call_order: list[str] = []

        # Track ordering via side_effect
        cancel_cbs[0].side_effect = lambda: call_order.append("cancel_0")
        cancel_cbs[1].side_effect = lambda: call_order.append("cancel_1")

        # Monkey-patch _on_unsubscribe to track order
        original_on_unsub = subscriber._on_unsubscribe

        def tracking_on_unsub(device_id: str) -> None:
            call_order.append("on_unsubscribe")
            original_on_unsub(device_id)

        subscriber._on_unsubscribe = tracking_on_unsub  # type: ignore[assignment]

        subscriber.unsubscribe(device)

        assert call_order == ["cancel_0", "cancel_1", "on_unsubscribe"]


# ======================== Multi-Device Independence Tests ========================


class TestDeviceEventSubscriberMultiDevice:
    """Tests for independent management of multiple device subscriptions"""

    @pytest.fixture
    def subscriber(self) -> ConcreteSubscriber:
        return ConcreteSubscriber()

    def test_unsubscribe_one_does_not_affect_others(self, subscriber: ConcreteSubscriber):
        """Unsubscribing one device should leave other devices subscribed"""
        dev1 = _make_mock_device("dev_001")
        dev2 = _make_mock_device("dev_002")

        subscriber.subscribe(dev1)
        subscriber.subscribe(dev2)

        subscriber.unsubscribe(dev1)

        # dev_001 should be gone, dev_002 should remain
        assert "dev_001" not in subscriber._unsubscribes
        assert "dev_002" in subscriber._unsubscribes

    def test_unsubscribe_one_only_calls_its_cancel_callbacks(self, subscriber: ConcreteSubscriber):
        """Unsubscribing one device should only invoke that device's cancel callbacks"""
        dev1 = _make_mock_device("dev_001")
        dev2 = _make_mock_device("dev_002")

        subscriber.subscribe(dev1)
        subscriber.subscribe(dev2)

        dev1_cbs = subscriber._cancel_callbacks_per_device["dev_001"]
        dev2_cbs = subscriber._cancel_callbacks_per_device["dev_002"]

        subscriber.unsubscribe(dev1)

        # dev_001 callbacks called
        for cb in dev1_cbs:
            cb.assert_called_once()

        # dev_002 callbacks NOT called
        for cb in dev2_cbs:
            cb.assert_not_called()

    def test_subscribe_after_unsubscribe_re_registers(self, subscriber: ConcreteSubscriber):
        """Re-subscribing a previously unsubscribed device should call _register_events() again"""
        device = _make_mock_device("dev_001")

        subscriber.subscribe(device)
        subscriber.unsubscribe(device)
        subscriber.subscribe(device)

        # _register_events should have been called twice
        assert subscriber.register_events_calls == ["dev_001", "dev_001"]
        assert "dev_001" in subscriber._unsubscribes

    def test_on_unsubscribe_receives_correct_device_id(self, subscriber: ConcreteSubscriber):
        """_on_unsubscribe() should receive the correct device_id for each device"""
        dev1 = _make_mock_device("dev_001")
        dev2 = _make_mock_device("dev_002")

        subscriber.subscribe(dev1)
        subscriber.subscribe(dev2)

        subscriber.unsubscribe(dev2)
        subscriber.unsubscribe(dev1)

        assert subscriber.on_unsubscribe_calls == ["dev_002", "dev_001"]


# ======================== Default Behavior Tests ========================


class TestDeviceEventSubscriberDefaults:
    """Tests for default / base class behavior"""

    def test_base_register_events_raises_not_implemented(self):
        """Base _register_events() should raise NotImplementedError"""
        # Directly instantiate the base class (it has no ABC enforcement)
        base = DeviceEventSubscriber()
        device = _make_mock_device("dev_001")

        with pytest.raises(NotImplementedError):
            base.subscribe(device)

    def test_default_on_unsubscribe_is_noop(self):
        """Default _on_unsubscribe() should be a no-op (no exception)"""
        subscriber = ConcreteSubscriberNoCleanup()
        device = _make_mock_device("dev_001")

        subscriber.subscribe(device)
        # Should not raise even though _on_unsubscribe is not overridden
        subscriber.unsubscribe(device)

    def test_initial_unsubscribes_dict_is_empty(self):
        """Newly created subscriber should have an empty _unsubscribes dict"""
        subscriber = ConcreteSubscriber()
        assert subscriber._unsubscribes == {}


# ======================== Cancel Callback Invocation Tests ========================


class TestCancelCallbackInvocation:
    """Focused tests on cancel callback mechanics"""

    def test_cancel_callbacks_called_with_no_arguments(self):
        """Cancel callbacks should be called with zero arguments"""
        subscriber = ConcreteSubscriber()
        device = _make_mock_device("dev_001")
        subscriber.subscribe(device)

        cancel_cbs = subscriber._cancel_callbacks_per_device["dev_001"]

        subscriber.unsubscribe(device)

        for cb in cancel_cbs:
            cb.assert_called_once_with()

    def test_empty_cancel_callback_list(self):
        """If _register_events returns an empty list, unsubscribe should still call _on_unsubscribe"""

        class EmptyRegistrationSubscriber(DeviceEventSubscriber):
            def __init__(self) -> None:
                super().__init__()
                self.on_unsub_called = False

            def _register_events(self, device) -> list[Callable[[], None]]:
                return []

            def _on_unsubscribe(self, device_id: str) -> None:
                self.on_unsub_called = True

        subscriber = EmptyRegistrationSubscriber()
        device = _make_mock_device("dev_001")

        subscriber.subscribe(device)
        subscriber.unsubscribe(device)

        assert subscriber.on_unsub_called is True
        assert "dev_001" not in subscriber._unsubscribes

    def test_real_cancel_callback_removes_handler(self):
        """Integration-style test: cancel callbacks from a real-ish device.on() actually work"""
        handlers: dict[str, list] = {}

        def fake_on(event: str, handler) -> Callable[[], None]:
            if event not in handlers:
                handlers[event] = []
            handlers[event].append(handler)

            def cancel() -> None:
                if event in handlers and handler in handlers[event]:
                    handlers[event].remove(handler)

            return cancel

        class RealishSubscriber(DeviceEventSubscriber):
            def _register_events(self, device) -> list[Callable[[], None]]:
                return [
                    device.on("event_a", self._handler_a),
                    device.on("event_b", self._handler_b),
                ]

            def _handler_a(self, payload):
                pass

            def _handler_b(self, payload):
                pass

        device = MagicMock()
        device.device_id = "dev_001"
        device.on = fake_on

        subscriber = RealishSubscriber()
        subscriber.subscribe(device)

        # Verify handlers were registered
        assert len(handlers.get("event_a", [])) == 1
        assert len(handlers.get("event_b", [])) == 1

        subscriber.unsubscribe(device)

        # Verify handlers were removed
        assert len(handlers.get("event_a", [])) == 0
        assert len(handlers.get("event_b", [])) == 0
