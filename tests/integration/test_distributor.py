"""Tests for PowerDistributor classes (EqualDistributor, ProportionalDistributor, SOCBalancingDistributor)."""

from unittest.mock import MagicMock

import pytest

from csp_lib.controller.core import Command
from csp_lib.integration.distributor import (
    DeviceSnapshot,
    EqualDistributor,
    PowerDistributor,
    ProportionalDistributor,
    SOCBalancingDistributor,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _snap(device_id: str, metadata: dict | None = None, capabilities: dict | None = None) -> DeviceSnapshot:
    """Shorthand for creating a DeviceSnapshot."""
    return DeviceSnapshot(
        device_id=device_id,
        metadata=metadata or {},
        capabilities=capabilities or {},
    )


# ===========================================================================
# DeviceSnapshot
# ===========================================================================


class TestDeviceSnapshot:
    def test_frozen_dataclass(self):
        snap = _snap("d1")
        with pytest.raises(AttributeError):
            snap.device_id = "d2"  # type: ignore[misc]

    def test_get_capability_value_with_string(self):
        snap = DeviceSnapshot(
            device_id="d1",
            capabilities={"soc_readable": {"soc": 85.0}},
        )
        assert snap.get_capability_value("soc_readable", "soc") == 85.0

    def test_get_capability_value_with_capability_object(self):
        cap = MagicMock()
        cap.name = "soc_readable"
        snap = DeviceSnapshot(
            device_id="d1",
            capabilities={"soc_readable": {"soc": 72.0}},
        )
        assert snap.get_capability_value(cap, "soc") == 72.0

    def test_get_capability_value_missing_capability(self):
        snap = _snap("d1")
        assert snap.get_capability_value("nonexistent", "slot") is None

    def test_get_capability_value_missing_slot(self):
        snap = DeviceSnapshot(
            device_id="d1",
            capabilities={"soc_readable": {"soc": 50.0}},
        )
        assert snap.get_capability_value("soc_readable", "missing_slot") is None

    def test_default_fields(self):
        snap = DeviceSnapshot(device_id="d1")
        assert snap.metadata == {}
        assert snap.latest_values == {}
        assert snap.capabilities == {}


# ===========================================================================
# PowerDistributor Protocol
# ===========================================================================


class TestPowerDistributorProtocol:
    def test_equal_distributor_is_power_distributor(self):
        assert isinstance(EqualDistributor(), PowerDistributor)

    def test_proportional_distributor_is_power_distributor(self):
        assert isinstance(ProportionalDistributor(), PowerDistributor)

    def test_soc_balancing_distributor_is_power_distributor(self):
        assert isinstance(SOCBalancingDistributor(), PowerDistributor)

    def test_custom_conforming_class_is_power_distributor(self):
        class CustomDistributor:
            def distribute(self, command: Command, devices: list[DeviceSnapshot]) -> dict[str, Command]:
                return {}

        assert isinstance(CustomDistributor(), PowerDistributor)

    def test_non_conforming_class_is_not_power_distributor(self):
        class NotADistributor:
            def something_else(self):
                pass

        assert not isinstance(NotADistributor(), PowerDistributor)


# ===========================================================================
# EqualDistributor
# ===========================================================================


class TestEqualDistributor:
    def test_empty_devices(self):
        dist = EqualDistributor()
        result = dist.distribute(Command(p_target=1000.0, q_target=500.0), [])
        assert result == {}

    def test_single_device_gets_full_power(self):
        dist = EqualDistributor()
        devices = [_snap("d1")]
        result = dist.distribute(Command(p_target=1000.0, q_target=500.0), devices)
        assert result["d1"].p_target == pytest.approx(1000.0)
        assert result["d1"].q_target == pytest.approx(500.0)

    def test_two_devices_equal_split(self):
        dist = EqualDistributor()
        devices = [_snap("d1"), _snap("d2")]
        result = dist.distribute(Command(p_target=1000.0, q_target=600.0), devices)
        assert len(result) == 2
        assert result["d1"].p_target == pytest.approx(500.0)
        assert result["d1"].q_target == pytest.approx(300.0)
        assert result["d2"].p_target == pytest.approx(500.0)
        assert result["d2"].q_target == pytest.approx(300.0)

    def test_three_devices_one_third_each(self):
        dist = EqualDistributor()
        devices = [_snap("d1"), _snap("d2"), _snap("d3")]
        result = dist.distribute(Command(p_target=900.0, q_target=300.0), devices)
        assert len(result) == 3
        for did in ["d1", "d2", "d3"]:
            assert result[did].p_target == pytest.approx(300.0)
            assert result[did].q_target == pytest.approx(100.0)


# ===========================================================================
# ProportionalDistributor
# ===========================================================================


class TestProportionalDistributor:
    def test_empty_devices(self):
        dist = ProportionalDistributor()
        result = dist.distribute(Command(p_target=1500.0, q_target=600.0), [])
        assert result == {}

    def test_two_devices_proportional_by_rated_p(self):
        dist = ProportionalDistributor(rated_key="rated_p")
        devices = [
            _snap("d1", metadata={"rated_p": 500.0}),
            _snap("d2", metadata={"rated_p": 1000.0}),
        ]
        result = dist.distribute(Command(p_target=1500.0, q_target=600.0), devices)
        # d1: 500/1500 = 1/3, d2: 1000/1500 = 2/3
        assert result["d1"].p_target == pytest.approx(500.0)
        assert result["d1"].q_target == pytest.approx(200.0)
        assert result["d2"].p_target == pytest.approx(1000.0)
        assert result["d2"].q_target == pytest.approx(400.0)

    def test_all_rated_zero_fallback_to_equal(self):
        dist = ProportionalDistributor(rated_key="rated_p")
        devices = [
            _snap("d1", metadata={"rated_p": 0.0}),
            _snap("d2", metadata={"rated_p": 0.0}),
        ]
        result = dist.distribute(Command(p_target=1000.0, q_target=400.0), devices)
        # Fallback to equal: each gets 500 / 200
        assert result["d1"].p_target == pytest.approx(500.0)
        assert result["d2"].p_target == pytest.approx(500.0)

    def test_custom_rated_key(self):
        dist = ProportionalDistributor(rated_key="rated_s")
        devices = [
            _snap("d1", metadata={"rated_s": 200.0}),
            _snap("d2", metadata={"rated_s": 800.0}),
        ]
        result = dist.distribute(Command(p_target=1000.0, q_target=0.0), devices)
        assert result["d1"].p_target == pytest.approx(200.0)
        assert result["d2"].p_target == pytest.approx(800.0)

    def test_one_device_missing_rated_key_treated_as_zero(self):
        dist = ProportionalDistributor(rated_key="rated_p")
        devices = [
            _snap("d1", metadata={"rated_p": 1000.0}),
            _snap("d2", metadata={}),  # missing rated_p -> 0
        ]
        result = dist.distribute(Command(p_target=1000.0, q_target=500.0), devices)
        # d1: 1000/1000 = 100%, d2: 0/1000 = 0%
        assert result["d1"].p_target == pytest.approx(1000.0)
        assert result["d2"].p_target == pytest.approx(0.0)

    def test_all_missing_rated_key_fallback_to_equal(self):
        dist = ProportionalDistributor(rated_key="rated_p")
        devices = [_snap("d1"), _snap("d2")]  # no metadata at all
        result = dist.distribute(Command(p_target=800.0, q_target=200.0), devices)
        assert result["d1"].p_target == pytest.approx(400.0)
        assert result["d2"].p_target == pytest.approx(400.0)


# ===========================================================================
# SOCBalancingDistributor
# ===========================================================================


class TestSOCBalancingDistributor:
    def _make_dist(self, **kwargs) -> SOCBalancingDistributor:
        defaults = {
            "rated_key": "rated_p",
            "soc_capability": "soc_readable",
            "soc_slot": "soc",
            "gain": 2.0,
        }
        defaults.update(kwargs)
        return SOCBalancingDistributor(**defaults)

    def test_empty_devices(self):
        dist = self._make_dist()
        result = dist.distribute(Command(p_target=1000.0, q_target=500.0), [])
        assert result == {}

    def test_discharge_higher_soc_gets_more_p(self):
        """Discharging (P>0): device with higher SOC should get more P."""
        dist = self._make_dist()
        devices = [
            _snap("d1", metadata={"rated_p": 500.0}, capabilities={"soc_readable": {"soc": 80.0}}),
            _snap("d2", metadata={"rated_p": 500.0}, capabilities={"soc_readable": {"soc": 40.0}}),
        ]
        result = dist.distribute(Command(p_target=1000.0, q_target=0.0), devices)
        # d1 has higher SOC -> should get more P during discharge
        assert result["d1"].p_target > result["d2"].p_target

    def test_charge_lower_soc_gets_more_p_magnitude(self):
        """Charging (P<0): device with lower SOC should get more |P|."""
        dist = self._make_dist()
        devices = [
            _snap("d1", metadata={"rated_p": 500.0}, capabilities={"soc_readable": {"soc": 80.0}}),
            _snap("d2", metadata={"rated_p": 500.0}, capabilities={"soc_readable": {"soc": 40.0}}),
        ]
        result = dist.distribute(Command(p_target=-1000.0, q_target=0.0), devices)
        # d2 has lower SOC -> should get more |P| during charge (more negative)
        assert abs(result["d2"].p_target) > abs(result["d1"].p_target)

    def test_q_always_proportional_by_rated(self):
        """Q should always be distributed proportionally by rated, not by SOC."""
        dist = self._make_dist()
        devices = [
            _snap("d1", metadata={"rated_p": 500.0}, capabilities={"soc_readable": {"soc": 90.0}}),
            _snap("d2", metadata={"rated_p": 1000.0}, capabilities={"soc_readable": {"soc": 30.0}}),
        ]
        result = dist.distribute(Command(p_target=900.0, q_target=900.0), devices)
        # Q: d1 = 500/1500 * 900 = 300, d2 = 1000/1500 * 900 = 600
        assert result["d1"].q_target == pytest.approx(300.0)
        assert result["d2"].q_target == pytest.approx(600.0)

    def test_all_soc_equal_same_as_proportional(self):
        """When all SOC are equal, P distribution should match proportional."""
        dist = self._make_dist()
        prop_dist = ProportionalDistributor(rated_key="rated_p")
        devices = [
            _snap("d1", metadata={"rated_p": 500.0}, capabilities={"soc_readable": {"soc": 60.0}}),
            _snap("d2", metadata={"rated_p": 1000.0}, capabilities={"soc_readable": {"soc": 60.0}}),
        ]
        cmd = Command(p_target=1500.0, q_target=600.0)
        soc_result = dist.distribute(cmd, devices)
        prop_result = prop_dist.distribute(cmd, devices)
        for did in ["d1", "d2"]:
            assert soc_result[did].p_target == pytest.approx(prop_result[did].p_target)
            assert soc_result[did].q_target == pytest.approx(prop_result[did].q_target)

    def test_no_soc_data_fallback_to_proportional(self):
        """When no device has SOC data, fallback to proportional distribution."""
        dist = self._make_dist()
        devices = [
            _snap("d1", metadata={"rated_p": 500.0}),
            _snap("d2", metadata={"rated_p": 1000.0}),
        ]
        result = dist.distribute(Command(p_target=1500.0, q_target=600.0), devices)
        # Proportional: d1=1/3, d2=2/3
        assert result["d1"].p_target == pytest.approx(500.0)
        assert result["d2"].p_target == pytest.approx(1000.0)

    def test_no_rated_data_fallback_to_equal(self):
        """When total rated is 0, fallback to equal distribution."""
        dist = self._make_dist()
        devices = [
            _snap("d1", capabilities={"soc_readable": {"soc": 80.0}}),
            _snap("d2", capabilities={"soc_readable": {"soc": 40.0}}),
        ]
        result = dist.distribute(Command(p_target=1000.0, q_target=400.0), devices)
        assert result["d1"].p_target == pytest.approx(500.0)
        assert result["d2"].p_target == pytest.approx(500.0)

    def test_one_device_missing_soc_uses_avg(self):
        """Device without SOC should be treated as having the average SOC."""
        dist = self._make_dist()
        # d1 has SOC 80, d2 has no SOC -> avg = 80 -> d2 gets avg_soc
        # With equal rated and same effective SOC, both get equal share
        devices = [
            _snap("d1", metadata={"rated_p": 500.0}, capabilities={"soc_readable": {"soc": 80.0}}),
            _snap("d2", metadata={"rated_p": 500.0}),  # no SOC
        ]
        result = dist.distribute(Command(p_target=1000.0, q_target=0.0), devices)
        # d2 gets avg_soc=80, same as d1 -> deviation=0 -> equal P share
        assert result["d1"].p_target == pytest.approx(result["d2"].p_target)

    def test_total_p_conserved(self):
        """Sum of per-device P should equal system P."""
        dist = self._make_dist()
        devices = [
            _snap("d1", metadata={"rated_p": 500.0}, capabilities={"soc_readable": {"soc": 90.0}}),
            _snap("d2", metadata={"rated_p": 1000.0}, capabilities={"soc_readable": {"soc": 30.0}}),
            _snap("d3", metadata={"rated_p": 750.0}, capabilities={"soc_readable": {"soc": 60.0}}),
        ]
        cmd = Command(p_target=2250.0, q_target=900.0)
        result = dist.distribute(cmd, devices)
        total_p = sum(r.p_target for r in result.values())
        assert total_p == pytest.approx(cmd.p_target)

    def test_total_q_conserved(self):
        """Sum of per-device Q should equal system Q."""
        dist = self._make_dist()
        devices = [
            _snap("d1", metadata={"rated_p": 500.0}, capabilities={"soc_readable": {"soc": 90.0}}),
            _snap("d2", metadata={"rated_p": 1000.0}, capabilities={"soc_readable": {"soc": 30.0}}),
        ]
        cmd = Command(p_target=1500.0, q_target=600.0)
        result = dist.distribute(cmd, devices)
        total_q = sum(r.q_target for r in result.values())
        assert total_q == pytest.approx(cmd.q_target)

    def test_total_p_conserved_with_charge(self):
        """Conservation should hold for charging (negative P) too."""
        dist = self._make_dist()
        devices = [
            _snap("d1", metadata={"rated_p": 500.0}, capabilities={"soc_readable": {"soc": 90.0}}),
            _snap("d2", metadata={"rated_p": 1000.0}, capabilities={"soc_readable": {"soc": 30.0}}),
        ]
        cmd = Command(p_target=-1500.0, q_target=-600.0)
        result = dist.distribute(cmd, devices)
        total_p = sum(r.p_target for r in result.values())
        total_q = sum(r.q_target for r in result.values())
        assert total_p == pytest.approx(cmd.p_target)
        assert total_q == pytest.approx(cmd.q_target)
