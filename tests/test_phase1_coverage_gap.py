"""Coverage-phase regression tests for 2025 redesign defaults and explicit 2024 mode."""
from __future__ import annotations

import pytest

from cms_mpd.config import PipelineConfig
from cms_mpd.recommend import (
    ANNUAL_OOP_CAP,
    BENEFIT_DESIGN_2024,
    BENEFIT_DESIGN_2025,
    CATASTROPHIC_TROOP_THRESHOLD,
    INITIAL_COVERAGE_LIMIT,
    _compute_catastrophic_cost,
    _compute_coverage_gap_cost,
    _resolve_plan_benefit_design,
    _simulate_fill_cost,
)


def _make_basis(
    *,
    unit_cost: float = 10.0,
    tier_family: str = "brand",
    days_supply: int = 30,
    is_insulin: bool = False,
    deductible_applies: bool = False,
) -> dict:
    return {
        "unit_cost": unit_cost,
        "tier_family": tier_family,
        "tier_level_value": 3,
        "days_supply": days_supply,
        "is_insulin": is_insulin,
        "deductible_applies": deductible_applies,
        "is_excluded": False,
        "has_prior_auth": False,
        "has_step_therapy": False,
        "has_quantity_limit": False,
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
        "insulin_pref_copay": None,
        "insulin_nonpref_copay": None,
        "insulin_pref_mail_copay": None,
        "insulin_nonpref_mail_copay": None,
    }


def _make_channel_summary(
    *,
    pref_retail_brand_fee_30: float = 2.0,
    pref_retail_generic_fee_30: float = 1.0,
) -> dict:
    return {
        "has_pref_retail": True,
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


class TestBenefitDesignResolution:
    def test_auto_mode_uses_2025_redesign_for_2025_contracts(self):
        config = PipelineConfig(snapshot_quarter="2025-Q3", benefit_design_mode="auto")
        contract_year, design = _resolve_plan_benefit_design(2025, config)
        assert contract_year == 2025
        assert design == BENEFIT_DESIGN_2025

    def test_auto_mode_uses_2024_standard_for_2024_contracts(self):
        config = PipelineConfig(snapshot_quarter="2025-Q3", benefit_design_mode="auto")
        contract_year, design = _resolve_plan_benefit_design(2024, config)
        assert contract_year == 2024
        assert design == BENEFIT_DESIGN_2024

    def test_explicit_mode_overrides_contract_year(self):
        config = PipelineConfig(snapshot_quarter="2025-Q3", benefit_design_mode=BENEFIT_DESIGN_2024)
        contract_year, design = _resolve_plan_benefit_design(2025, config)
        assert contract_year == 2025
        assert design == BENEFIT_DESIGN_2024


class TestCostHelpers:
    def test_coverage_gap_cost_is_25_percent(self):
        assert _compute_coverage_gap_cost(200.0, "brand") == pytest.approx(50.0)
        assert _compute_coverage_gap_cost(100.0, "generic") == pytest.approx(25.0)

    def test_2024_catastrophic_cost_is_zero(self):
        assert _compute_catastrophic_cost(200.0, "brand") == 0.0
        assert _compute_catastrophic_cost(50.0, "generic") == 0.0


class Test2025RedesignDefaults:
    def test_default_behavior_never_enters_gap_or_catastrophic(self):
        basis = _make_basis(unit_cost=20.0)
        channel_summary = _make_channel_summary()
        result = _simulate_fill_cost(
            basis,
            channel_summary,
            "pref_retail",
            quantity=30.0,
            remaining_deductible=0.0,
            oop_accumulated=500.0,
            lis_status="none",
            total_drug_spending_accumulated=9000.0,
        )
        assert result is not None
        assert result.benefit_design == BENEFIT_DESIGN_2025
        assert "coverage_gap" not in result.coverage_phase
        assert "catastrophic" not in result.coverage_phase
        assert result.coverage_gap_oop == 0.0
        assert result.catastrophic_oop == 0.0

    def test_annual_oop_cap_applies_in_2025_redesign(self):
        basis = _make_basis(unit_cost=20.0)
        channel_summary = _make_channel_summary()
        result = _simulate_fill_cost(
            basis,
            channel_summary,
            "pref_retail",
            quantity=30.0,
            remaining_deductible=0.0,
            oop_accumulated=1990.0,
            lis_status="none",
            total_drug_spending_accumulated=9000.0,
        )
        assert result is not None
        assert result.benefit_design == BENEFIT_DESIGN_2025
        assert result.total_oop == pytest.approx(10.0)
        assert result.oop_after == pytest.approx(ANNUAL_OOP_CAP)
        assert result.oop_cap_applied is True

    def test_fills_are_free_after_cap_is_reached(self):
        basis = _make_basis(unit_cost=20.0)
        channel_summary = _make_channel_summary()
        result = _simulate_fill_cost(
            basis,
            channel_summary,
            "pref_retail",
            quantity=30.0,
            remaining_deductible=0.0,
            oop_accumulated=ANNUAL_OOP_CAP,
            lis_status="none",
            total_drug_spending_accumulated=12000.0,
        )
        assert result is not None
        assert result.total_oop == 0.0
        assert result.oop_cap_applied is True
        assert result.coverage_gap_oop == 0.0
        assert result.catastrophic_oop == 0.0


class Test2024StandardMode:
    def test_catastrophic_depends_on_troop_not_total_drug_spend(self):
        basis = _make_basis(unit_cost=20.0)
        channel_summary = _make_channel_summary()
        result = _simulate_fill_cost(
            basis,
            channel_summary,
            "pref_retail",
            quantity=30.0,
            remaining_deductible=0.0,
            oop_accumulated=100.0,
            lis_status="none",
            total_drug_spending_accumulated=9000.0,
            benefit_design=BENEFIT_DESIGN_2024,
            troop_accumulated=100.0,
        )
        assert result is not None
        assert result.benefit_design == BENEFIT_DESIGN_2024
        assert result.coverage_phase == "coverage_gap"
        assert result.coverage_gap_oop > 0.0
        assert result.catastrophic_oop == 0.0
        assert result.troop_before == pytest.approx(100.0)
        assert result.troop_after == pytest.approx(100.0 + result.coverage_gap_oop)

    def test_initial_limit_straddle_uses_segmented_math_without_double_charging(self):
        basis = _make_basis(unit_cost=10.0)
        channel_summary = _make_channel_summary()
        result = _simulate_fill_cost(
            basis,
            channel_summary,
            "pref_retail",
            quantity=30.0,
            remaining_deductible=0.0,
            oop_accumulated=400.0,
            lis_status="none",
            total_drug_spending_accumulated=5000.0,
            benefit_design=BENEFIT_DESIGN_2024,
            troop_accumulated=400.0,
        )
        assert result is not None
        assert result.coverage_phase == "initial_coverage_rule_then_coverage_gap"
        assert result.negotiated_price == pytest.approx(302.0)
        assert result.coverage_gap_oop == pytest.approx((result.negotiated_price - 30.0) * 0.25)
        expected_initial_cost = 25.0 * (30.0 / result.negotiated_price)
        expected_total = expected_initial_cost + result.coverage_gap_oop
        assert result.total_oop == pytest.approx(expected_total, rel=1e-4)
        assert result.total_oop < 93.0
        assert result.total_drug_spending_before == pytest.approx(5000.0)
        assert result.total_drug_spending_after == pytest.approx(5000.0 + result.negotiated_price)

    def test_gap_to_catastrophic_straddle_caps_gap_at_remaining_troop(self):
        basis = _make_basis(unit_cost=500.0)
        channel_summary = _make_channel_summary()
        result = _simulate_fill_cost(
            basis,
            channel_summary,
            "pref_retail",
            quantity=30.0,
            remaining_deductible=0.0,
            oop_accumulated=1950.0,
            lis_status="none",
            total_drug_spending_accumulated=INITIAL_COVERAGE_LIMIT + 100.0,
            benefit_design=BENEFIT_DESIGN_2024,
            troop_accumulated=CATASTROPHIC_TROOP_THRESHOLD - 50.0,
        )
        assert result is not None
        assert result.coverage_phase == "coverage_gap_then_catastrophic"
        assert result.coverage_gap_oop == pytest.approx(50.0)
        assert result.catastrophic_oop == 0.0
        assert result.total_oop == pytest.approx(50.0)
        assert result.troop_after == pytest.approx(CATASTROPHIC_TROOP_THRESHOLD)

    def test_lis_adjustment_still_applies_inside_2024_gap_logic(self):
        basis = _make_basis(unit_cost=20.0, tier_family="brand")
        channel_summary = _make_channel_summary()
        result = _simulate_fill_cost(
            basis,
            channel_summary,
            "pref_retail",
            quantity=30.0,
            remaining_deductible=0.0,
            oop_accumulated=100.0,
            lis_status="full",
            total_drug_spending_accumulated=6000.0,
            benefit_design=BENEFIT_DESIGN_2024,
            troop_accumulated=100.0,
        )
        assert result is not None
        assert result.coverage_phase == "coverage_gap"
        assert result.coverage_gap_oop > 12.15
        assert result.lis_adjusted_oop <= 12.15
        assert result.total_oop <= 12.15
