"""Tests for DeviceRegistry metadata functionality."""

from unittest.mock import MagicMock, PropertyMock

from csp_lib.integration.registry import DeviceRegistry


def _make_device(device_id: str, responsive: bool = True) -> MagicMock:
    """Create a mock AsyncModbusDevice."""
    dev = MagicMock()
    type(dev).device_id = PropertyMock(return_value=device_id)
    type(dev).is_responsive = PropertyMock(return_value=responsive)
    return dev


class TestRegistryMetadata:
    def test_register_with_metadata(self):
        reg = DeviceRegistry()
        dev = _make_device("d1")
        reg.register(dev, metadata={"rated_p": 500.0, "rated_s": 600.0})
        result = reg.get_metadata("d1")
        assert result == {"rated_p": 500.0, "rated_s": 600.0}

    def test_register_without_metadata_returns_empty_dict(self):
        reg = DeviceRegistry()
        dev = _make_device("d1")
        reg.register(dev)
        assert reg.get_metadata("d1") == {}

    def test_get_metadata_unregistered_returns_empty_dict(self):
        reg = DeviceRegistry()
        assert reg.get_metadata("nonexistent") == {}

    def test_get_metadata_returns_copy(self):
        """Modifying the returned dict should not affect internal state."""
        reg = DeviceRegistry()
        dev = _make_device("d1")
        reg.register(dev, metadata={"rated_p": 500.0})

        returned = reg.get_metadata("d1")
        returned["rated_p"] = 9999.0
        returned["extra_key"] = "should_not_persist"

        # Internal state should be unchanged
        assert reg.get_metadata("d1") == {"rated_p": 500.0}

    def test_unregister_cleans_up_metadata(self):
        reg = DeviceRegistry()
        dev = _make_device("d1")
        reg.register(dev, metadata={"rated_p": 500.0})
        reg.unregister("d1")
        assert reg.get_metadata("d1") == {}

    def test_register_with_metadata_and_traits(self):
        """Metadata and traits can be set together."""
        reg = DeviceRegistry()
        dev = _make_device("d1")
        reg.register(dev, traits=["pcs"], metadata={"rated_p": 1000.0})
        assert reg.get_traits("d1") == {"pcs"}
        assert reg.get_metadata("d1") == {"rated_p": 1000.0}

    def test_metadata_stored_as_copy(self):
        """Modifying the original dict after register should not affect stored metadata."""
        reg = DeviceRegistry()
        dev = _make_device("d1")
        original = {"rated_p": 500.0}
        reg.register(dev, metadata=original)
        original["rated_p"] = 9999.0
        assert reg.get_metadata("d1") == {"rated_p": 500.0}
