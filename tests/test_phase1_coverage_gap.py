"""Phase 1 – Coverage Gap (Donut Hole) & Catastrophic Phase Tests.

Verifies that _simulate_fill_cost correctly detects phase transitions
at CMS 2025 thresholds:
  - Initial Coverage Limit: $5,030
  - Catastrophic TrOOP Threshold: $8,000
  - Coverage Gap coinsurance: 25%
  - OOP Cap: $2,000
"""
from __future__ import annotations

import pytest

from cms_mpd.recommend import (
    ANNUAL_OOP_CAP,
    CATASTROPHIC_TROOP_THRESHOLD,
    INITIAL_COVERAGE_LIMIT,
    FillCostResult,
    _compute_catastrophic_cost,
    _compute_coverage_gap_cost,
    _simulate_fill_cost,
)


# ── Helpers ──────────────────────────────────────────────────────────────


def _make_basis(
    *,
    unit_cost: float = 10.0,
    tier_family: str = "brand",
    days_supply: int = 30,
    is_insulin: bool = False,
    deductible_applies: bool = False,
    is_excluded: bool = False,
    has_prior_auth: bool = False,
    has_step_therapy: bool = False,
    has_quantity_limit: bool = False,
) -> dict:
    """Build a minimal cost-basis dict for testing."""
    return {
        "unit_cost": unit_cost,
        "tier_family": tier_family,
        "tier_level_value": 3,
        "days_supply": days_supply,
        "is_insulin": is_insulin,
        "deductible_applies": deductible_applies,
        "is_excluded": is_excluded,
        "has_prior_auth": has_prior_auth,
        "has_step_therapy": has_step_therapy,
        "has_quantity_limit": has_quantity_limit,
        # Initial coverage cost-sharing rules (copay type=1, $25 copay)
        "init_pref_cost_type": 1,
        "init_pref_cost_amt": 25.0,
        "init_pref_cost_min": None,
        "init_pref_cost_max": None,
        "init_nonpref_cost_type": 1,
        "init_nonpref_cost_amt": 40.0,
        "init_nonpref_cost_min": None,
        "init_nonpref_cost_max": None,
        "init_mail_pref_cost_type": 1,
        "init_mail_pref_cost_amt": 30.0,
        "init_mail_pref_cost_min": None,
        "init_mail_pref_cost_max": None,
        "init_mail_nonpref_cost_type": 1,
        "init_mail_nonpref_cost_amt": 45.0,
        "init_mail_nonpref_cost_min": None,
        "init_mail_nonpref_cost_max": None,
        # Pre-deductible fields
        "pre_pref_cost_type": None,
        "pre_pref_cost_amt": None,
        "pre_pref_cost_min": None,
        "pre_pref_cost_max": None,
        "pre_nonpref_cost_type": None,
        "pre_nonpref_cost_amt": None,
        "pre_nonpref_cost_min": None,
        "pre_nonpref_cost_max": None,
        "pre_mail_pref_cost_type": None,
        "pre_mail_pref_cost_amt": None,
        "pre_mail_pref_cost_min": None,
        "pre_mail_pref_cost_max": None,
        "pre_mail_nonpref_cost_type": None,
        "pre_mail_nonpref_cost_amt": None,
        "pre_mail_nonpref_cost_min": None,
        "pre_mail_nonpref_cost_max": None,
        # Insulin fields
        "insulin_pref_copay": None,
        "insulin_nonpref_copay": None,
        "insulin_pref_mail_copay": None,
        "insulin_nonpref_mail_copay": None,
    }


def _make_channel_summary(
    *,
    has_pref_retail: bool = True,
    pref_retail_brand_fee_30: float = 2.0,
    pref_retail_generic_fee_30: float = 1.0,
) -> dict:
    """Build a minimal channel summary dict."""
    return {
        "has_pref_retail": has_pref_retail,
        "has_nonpref_retail": True,
        "has_pref_mail": True,
        "has_nonpref_mail": True,
        "pref_retail_brand_fee_30": pref_retail_brand_fee_30,
        "pref_retail_brand_fee_60": pref_retail_brand_fee_30,
        "pref_retail_brand_fee_90": pref_retail_brand_fee_30,
        "pref_retail_generic_fee_30": pref_retail_generic_fee_30,
        "pref_retail_generic_fee_60": pref_retail_generic_fee_30,
        "pref_retail_generic_fee_90": pref_retail_generic_fee_30,
        "nonpref_retail_brand_fee_30": 3.0,
        "nonpref_retail_brand_fee_60": 3.0,
        "nonpref_retail_brand_fee_90": 3.0,
        "nonpref_retail_generic_fee_30": 2.0,
        "nonpref_retail_generic_fee_60": 2.0,
        "nonpref_retail_generic_fee_90": 2.0,
        "pref_mail_brand_fee_30": 0.0,
        "pref_mail_brand_fee_60": 0.0,
        "pref_mail_brand_fee_90": 0.0,
        "pref_mail_generic_fee_30": 0.0,
        "pref_mail_generic_fee_60": 0.0,
        "pref_mail_generic_fee_90": 0.0,
        "nonpref_mail_brand_fee_30": 0.0,
        "nonpref_mail_brand_fee_60": 0.0,
        "nonpref_mail_brand_fee_90": 0.0,
        "nonpref_mail_generic_fee_30": 0.0,
        "nonpref_mail_generic_fee_60": 0.0,
        "nonpref_mail_generic_fee_90": 0.0,
        "pref_retail_floor": 0.0,
        "nonpref_retail_floor": 0.0,
        "pref_mail_floor": 0.0,
        "nonpref_mail_floor": 0.0,
    }


# ── Unit tests for gap/catastrophic cost helpers ─────────────────────────


class TestCoverageGapCostHelpers:
    """Verify _compute_coverage_gap_cost and _compute_catastrophic_cost."""

    def test_gap_cost_generic_25_pct(self):
        assert _compute_coverage_gap_cost(100.0, "generic") == pytest.approx(25.0)

    def test_gap_cost_brand_25_pct(self):
        assert _compute_coverage_gap_cost(200.0, "brand") == pytest.approx(50.0)

    def test_gap_cost_zero(self):
        assert _compute_coverage_gap_cost(0.0, "generic") == 0.0

    def test_catastrophic_cost_generic_copay(self):
        # Generic: min($4.50, negotiated)
        assert _compute_catastrophic_cost(100.0, "generic") == pytest.approx(4.50)

    def test_catastrophic_cost_generic_cheaper_than_copay(self):
        # If negotiated < $4.50, pay negotiated
        assert _compute_catastrophic_cost(2.00, "generic") == pytest.approx(2.00)

    def test_catastrophic_cost_brand_5_pct(self):
        # Brand: max($4.50, 5% coinsurance), capped at $44
        # $200 * 5% = $10 > $4.50 → $10
        assert _compute_catastrophic_cost(200.0, "brand") == pytest.approx(10.0)

    def test_catastrophic_cost_brand_floor(self):
        # Brand: $50 * 5% = $2.50 < $4.50 → $4.50
        assert _compute_catastrophic_cost(50.0, "brand") == pytest.approx(4.50)

    def test_catastrophic_cost_brand_cap_at_44(self):
        # Brand: $2000 * 5% = $100 → capped at $44
        assert _compute_catastrophic_cost(2000.0, "brand") == pytest.approx(44.0)


# ── Phase transition tests ───────────────────────────────────────────────


class TestInitialCoveragePhase:
    """Fill with total drug spending below $5,030 stays in initial coverage."""

    def test_initial_coverage_phase_detected(self):
        basis = _make_basis(unit_cost=10.0)
        channel_summary = _make_channel_summary()
        result = _simulate_fill_cost(
            basis, channel_summary, "pref_retail",
            quantity=30.0, remaining_deductible=0.0,
            oop_accumulated=0.0, lis_status="none",
            total_drug_spending_accumulated=0.0,
        )
        assert result is not None
        assert "coverage_gap" not in result.coverage_phase
        assert "catastrophic" not in result.coverage_phase
        assert result.coverage_gap_oop == 0.0
        assert result.catastrophic_oop == 0.0

    def test_total_drug_spending_tracked(self):
        basis = _make_basis(unit_cost=10.0)
        channel_summary = _make_channel_summary()
        result = _simulate_fill_cost(
            basis, channel_summary, "pref_retail",
            quantity=30.0, remaining_deductible=0.0,
            oop_accumulated=0.0, lis_status="none",
            total_drug_spending_accumulated=100.0,
        )
        assert result is not None
        assert result.total_drug_spending_before == pytest.approx(100.0)
        assert result.total_drug_spending_after > 100.0


class TestCoverageGapPhase:
    """Fill with total drug spending ≥ $5,030 enters coverage gap."""

    def test_coverage_gap_detected(self):
        basis = _make_basis(unit_cost=20.0)
        channel_summary = _make_channel_summary()
        result = _simulate_fill_cost(
            basis, channel_summary, "pref_retail",
            quantity=30.0, remaining_deductible=0.0,
            oop_accumulated=500.0, lis_status="none",
            total_drug_spending_accumulated=5500.0,  # Already past $5,030
        )
        assert result is not None
        assert result.coverage_phase == "coverage_gap"
        assert result.coverage_gap_oop > 0
        # 25% of negotiated price
        expected_gap_cost = result.negotiated_price * 0.25
        assert result.coverage_gap_oop == pytest.approx(expected_gap_cost)

    def test_straddling_initial_to_gap(self):
        """Fill that crosses the $5,030 threshold mid-fill."""
        basis = _make_basis(unit_cost=10.0)
        channel_summary = _make_channel_summary()
        # TDS at 5000, fill adds ~302 → crosses 5030
        result = _simulate_fill_cost(
            basis, channel_summary, "pref_retail",
            quantity=30.0, remaining_deductible=0.0,
            oop_accumulated=400.0, lis_status="none",
            total_drug_spending_accumulated=5000.0,
        )
        assert result is not None
        assert "_then_coverage_gap" in result.coverage_phase
        assert result.coverage_gap_oop > 0
        # Gap portion = tds_after - 5030
        gap_portion = result.total_drug_spending_after - INITIAL_COVERAGE_LIMIT
        assert gap_portion > 0
        assert result.coverage_gap_oop == pytest.approx(gap_portion * 0.25, rel=0.01)


class TestCatastrophicPhase:
    """Fill with total drug spending ≥ $8,000 enters catastrophic."""

    def test_catastrophic_detected(self):
        basis = _make_basis(unit_cost=20.0)
        channel_summary = _make_channel_summary()
        result = _simulate_fill_cost(
            basis, channel_summary, "pref_retail",
            quantity=30.0, remaining_deductible=0.0,
            oop_accumulated=1800.0, lis_status="none",
            total_drug_spending_accumulated=9000.0,  # Past $8,000
        )
        assert result is not None
        assert result.coverage_phase == "catastrophic"
        assert result.catastrophic_oop > 0
        assert result.coverage_gap_oop == 0.0
        # Brand catastrophic: min(max($4.50, 5% * negotiated), $44, negotiated)
        negotiated = result.negotiated_price
        expected = min(max(4.50, negotiated * 0.05), 44.0, negotiated)
        assert result.catastrophic_oop == pytest.approx(expected)

    def test_straddling_gap_to_catastrophic(self):
        """Fill that crosses $8,000 TrOOP mid-fill."""
        basis = _make_basis(unit_cost=100.0)  # Large per-unit cost
        channel_summary = _make_channel_summary()
        # TDS at 7900, fill adds ~3002 → crosses 8000
        result = _simulate_fill_cost(
            basis, channel_summary, "pref_retail",
            quantity=30.0, remaining_deductible=0.0,
            oop_accumulated=1900.0, lis_status="none",
            total_drug_spending_accumulated=7900.0,
        )
        assert result is not None
        assert result.coverage_phase == "coverage_gap_then_catastrophic"
        assert result.coverage_gap_oop > 0
        assert result.catastrophic_oop > 0

    def test_catastrophic_generic_minimal_copay(self):
        basis = _make_basis(unit_cost=5.0, tier_family="generic")
        channel_summary = _make_channel_summary()
        result = _simulate_fill_cost(
            basis, channel_summary, "pref_retail",
            quantity=30.0, remaining_deductible=0.0,
            oop_accumulated=1500.0, lis_status="none",
            total_drug_spending_accumulated=10000.0,
        )
        assert result is not None
        assert result.coverage_phase == "catastrophic"
        # Generic catastrophic: min($4.50, negotiated)
        assert result.catastrophic_oop == pytest.approx(min(4.50, result.negotiated_price))


class TestOopCapInteraction:
    """Verify OOP cap ($2,000) still applies across all phases."""

    def test_oop_cap_in_gap_phase(self):
        basis = _make_basis(unit_cost=20.0)
        channel_summary = _make_channel_summary()
        result = _simulate_fill_cost(
            basis, channel_summary, "pref_retail",
            quantity=30.0, remaining_deductible=0.0,
            oop_accumulated=1990.0,  # Near cap
            lis_status="none",
            total_drug_spending_accumulated=6000.0,  # In gap
        )
        assert result is not None
        assert result.total_oop <= ANNUAL_OOP_CAP - 1990.0 + 0.01

    def test_oop_cap_already_reached(self):
        basis = _make_basis(unit_cost=20.0)
        channel_summary = _make_channel_summary()
        result = _simulate_fill_cost(
            basis, channel_summary, "pref_retail",
            quantity=30.0, remaining_deductible=0.0,
            oop_accumulated=2000.0,  # Already at cap
            lis_status="none",
            total_drug_spending_accumulated=6000.0,
        )
        assert result is not None
        assert result.total_oop == 0.0
        assert result.oop_cap_applied is True


class TestLISInCoverageGap:
    """Verify LIS adjustments work in coverage gap."""

    def test_full_lis_caps_in_gap(self):
        basis = _make_basis(unit_cost=20.0, tier_family="brand")
        channel_summary = _make_channel_summary()
        result = _simulate_fill_cost(
            basis, channel_summary, "pref_retail",
            quantity=30.0, remaining_deductible=0.0,
            oop_accumulated=100.0, lis_status="full",
            total_drug_spending_accumulated=6000.0,
        )
        assert result is not None
        # Full LIS brand cap is $12.15
        assert result.lis_adjusted_oop <= 12.15
        assert result.total_oop <= 12.15


class TestBackwardCompatibility:
    """Verify existing initial-coverage fills still work identically."""

    def test_initial_coverage_without_tds(self):
        """Call without total_drug_spending_accumulated (default=0.0)."""
        basis = _make_basis(unit_cost=10.0)
        channel_summary = _make_channel_summary()
        result = _simulate_fill_cost(
            basis, channel_summary, "pref_retail",
            quantity=30.0, remaining_deductible=0.0,
            oop_accumulated=0.0, lis_status="none",
        )
        assert result is not None
        assert result.coverage_phase == "initial_coverage_rule"
        assert result.total_drug_spending_before == 0.0
        assert result.total_drug_spending_after > 0.0

    def test_deductible_phase_still_works(self):
        basis = _make_basis(unit_cost=10.0, deductible_applies=True)
        channel_summary = _make_channel_summary()
        result = _simulate_fill_cost(
            basis, channel_summary, "pref_retail",
            quantity=30.0, remaining_deductible=100.0,
            oop_accumulated=0.0, lis_status="none",
            total_drug_spending_accumulated=0.0,
        )
        assert result is not None
        assert "deductible" in result.coverage_phase
        assert result.deductible_exposure > 0
