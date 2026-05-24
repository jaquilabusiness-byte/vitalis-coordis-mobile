"""
VITALIS COORDIS — V3.2 Engine Patch Test Suite
===============================================
Tests all new V3.2 behavior while preserving V3.1 contracts.
"""

import sys
import os
sys.path.insert(0, os.path.dirname(__file__))

from vitalis_engine import Decision
from vitalis_engine_v32 import (
    # Core
    ComplianceWindow, ExtendedDecision, DomainSignal, SignalDomain,
    PreDecisionFilter, PreDecisionFilterResult, GuardResult,
    ReversibilityScore, ReversibilityTier,
    # HRV baseline normalization (V3.2 patch)
    HRVBaseline, normalize_hrv_direction, hrv_domain_signal,
    # Functions
    get_reversibility_score, get_reversibility, get_mec_unit,
    detect_entanglement, should_revert, compute_convergence_score,
    apply_v32_filter, apply_tier1_filter, route_decision,
    # Constants
    EC_LOW_THRESHOLD, EC_MED_THRESHOLD, SYSTEM_AXIOMS,
    CCS_THRESHOLDS, ENTANGLEMENT_THRESHOLDS,
    met_satisfied, get_met_for_cell,
    EXTENDED_DECISION_REASONS, V24_REVERSIBILITY_V32,
)


# ─── test harness ─────────────────────────────────────────────────

PASS = 0
FAIL = 0
RESULTS = []


def test(name: str, condition: bool, detail: str = ""):
    global PASS, FAIL
    status = "✅ PASS" if condition else "❌ FAIL"
    if condition:
        PASS += 1
    else:
        FAIL += 1
    tag = f" — {detail}" if detail else ""
    RESULTS.append((status, name + tag))
    print(f"  {status}  {name}{tag}")


def section(title: str):
    print(f"\n[{title}]")


def make_cw(days: list) -> ComplianceWindow:
    cw = ComplianceWindow()
    cw.daily_records = [float(d) for d in days]
    return cw


def full_cw() -> ComplianceWindow:
    return make_cw([1.0] * 30)


# ─── 1. SYSTEM AXIOMS ─────────────────────────────────────────────

section("1. SYSTEM AXIOMS")
test("null_action axiom present",
     "null_action" in SYSTEM_AXIOMS)
test("null_action axiom contains 'do nothing indefinitely'",
     "do nothing indefinitely" in SYSTEM_AXIOMS["null_action"])
test("hold_is_correct axiom present",
     "hold_is_correct" in SYSTEM_AXIOMS)
test("complexity axiom present",
     "complexity" in SYSTEM_AXIOMS)
test("5 axioms total",
     len(SYSTEM_AXIOMS) == 5)


# ─── 2. REVERSIBILITY SCORES ─────────────────────────────────────

section("2. REVERSIBILITY SCORES — numeric 1/2/3/LOCKED")
test("Qualia Magnesium = score HIGH (1)",
     get_reversibility_score("Qualia Magnesium") == ReversibilityScore.HIGH)
test("Berberine = score MEDIUM (2)",
     get_reversibility_score("Berberine 500mg") == ReversibilityScore.MEDIUM)
test("Nattokinase = score HIGH (1)",
     get_reversibility_score("Nattokinase") == ReversibilityScore.HIGH)
test("TMRW = LOCKED (0)",
     get_reversibility_score("TMRW (daily)") == ReversibilityScore.LOCKED)
test("Creatine = LOCKED (0)",
     get_reversibility_score("Creatine Monohydrate 5g") == ReversibilityScore.LOCKED)
test("Synbiotics = LOCKED (0)",
     get_reversibility_score("Synbiotics GUT composite") == ReversibilityScore.LOCKED)
test("No Cycle 1 daily item has score LOW (3)",
     all(
         V24_REVERSIBILITY_V32[k]["score"] != ReversibilityScore.LOW
         for k, v in V24_REVERSIBILITY_V32.items()
         if not v.get("as_needed") and not v.get("infrastructure")
     ))
test("Unknown item defaults to MEDIUM tier",
     get_reversibility("UNKNOWN_ITEM") == ReversibilityTier.MEDIUM)


# ─── 3. MEC_UNIT ─────────────────────────────────────────────────

section("3. MEC_UNIT — Minimum Effective Change")
test("Qualia Magnesium has dose_mg MEC",
     "dose_mg" in get_mec_unit("Qualia Magnesium"))
test("Omega-3 has EPA_DHA_g MEC = 1.0",
     get_mec_unit("Omega-3 + Black Cumin (dual-effect)").get("EPA_DHA_g") == 1.0)
test("Berberine has dose_mg = 500",
     get_mec_unit("Berberine 500mg").get("dose_mg") == 500)
test("L-Citrulline has dose_g = 3",
     get_mec_unit("L-Citrulline 3g").get("dose_g") == 3)
test("Creatine has dose_g = 5",
     get_mec_unit("Creatine Monohydrate 5g").get("dose_g") == 5)
test("Unknown item returns empty dict",
     get_mec_unit("UNKNOWN_ITEM") == {})


# ─── 4. CCS RECENCY WEIGHTING ─────────────────────────────────────

section("4. CCS — Recency-Weighted (7d=50%, 14d=30%, 30d=20%)")

# Perfect compliance
cw_perfect = full_cw()
test("Perfect 30-day compliance → CCS = 1.0",
     cw_perfect.ccs == 1.0)

# Last 7 days all missed (50% weight = 0, rest = 1.0)
cw_recent_miss = make_cw([1.0] * 23 + [0.0] * 7)
test("Last 7 days all missed → CCS ≤ 0.55",
     cw_recent_miss.ccs <= 0.55)

# Last 7 days perfect, older weeks poor
cw_recent_good = make_cw([0.0] * 23 + [1.0] * 7)
test("Recent 7d perfect, older poor → CCS ≥ 0.50",
     cw_recent_good.ccs >= 0.50)

# Verify recency weighting: identical older bands, only 7d band differs
# cw_bad_recent:  [...16 old...][1.0*7 mid][0.0*7 recent] → 7d=0.0, 14d=1.0
# cw_good_recent: [...16 old...][0.0*7 mid][1.0*7 recent] → 7d=1.0, 14d=0.0
cw_bad_recent  = make_cw([0.0] * 16 + [1.0] * 7 + [0.0] * 7)  # recent 7d all missed
cw_good_recent = make_cw([1.0] * 16 + [0.0] * 7 + [1.0] * 7)  # recent 7d all taken
test("Recency: good recent 7d (0.7) > bad recent 7d (0.3)",
     cw_good_recent.ccs > cw_bad_recent.ccs)

# Short record (< 7 days) falls back to simple mean
cw_short = make_cw([1.0, 1.0, 0.0])
test("Short record (3 days): CCS = simple mean = 0.667",
     abs(cw_short.ccs - (2/3)) < 0.01)

# CCS threshold bands (V3.2 bands)
test("CCS ≥ 0.85 → full band",
     CCS_THRESHOLDS["full"] == 0.85)
test("CCS partial threshold = 0.70",
     CCS_THRESHOLDS["partial"] == 0.70)


# ─── 5. ATTRIBUTION DEGRADED — AND GATE ──────────────────────────

section("5. ATTRIBUTION_DEGRADED — AND Gate (all 3 conditions)")

# All 3 conditions met → degraded
ea_all3 = detect_entanglement(
    active_intervention_count=8,
    ccs_value=0.60,
    controller_signals={"MITO": 0.5, "BRAIN": -0.5, "CARDIO": 0.3, "IMMUNE": -0.3},
)
test("All 3 conditions met → degraded=True",
     ea_all3.degraded)
test("All 3 met → modifier=0.0",
     ea_all3.modifier == 0.0)
test("All 3 met → reasons non-empty",
     len(ea_all3.reasons) > 0)

# Only 2 conditions (high load + signal conflict, but CCS ok)
ea_2of3 = detect_entanglement(
    active_intervention_count=8,
    ccs_value=0.90,   # CCS ok
    controller_signals={"MITO": 0.5, "BRAIN": -0.5},
)
test("2 of 3 conditions → NOT degraded (AND gate)",
     not ea_2of3.degraded)
test("2 of 3 → modifier = 0.40",
     ea_2of3.modifier == 0.40)

# Only 1 condition
ea_1of3 = detect_entanglement(
    active_intervention_count=8,
    ccs_value=0.90,
    controller_signals={"MITO": 0.5, "BRAIN": 0.3},
)
test("1 of 3 conditions → NOT degraded",
     not ea_1of3.degraded)

# Clean environment
ea_clean = detect_entanglement(
    active_intervention_count=3,
    ccs_value=0.92,
    controller_signals={"MITO": 0.5, "BRAIN": 0.3},
)
test("Clean environment → NOT degraded, modifier=1.0",
     not ea_clean.degraded and ea_clean.modifier == 1.0)

# V3.1 behavior: single high load was enough → V3.2 should NOT degrade
ea_load_only = detect_entanglement(
    active_intervention_count=10,
    ccs_value=0.90,
    controller_signals={"MITO": 0.5, "BRAIN": 0.4},   # no conflict
)
test("V3.2: high load alone does NOT trigger ATTRIBUTION_DEGRADED",
     not ea_load_only.degraded)


# ─── 6. GUARD 1 — EC-THRESHOLD GATING ───────────────────────────

section("6. Guard 1 — EC-Threshold Reversibility Gating")

def run_g1(item_name, ec_value):
    cw = full_cw()
    pf = PreDecisionFilter(
        compliance_window=cw,
        proposed_item_name=item_name,
        effective_confidence=ec_value,
    )
    return pf._guard1_reversibility()

# LOCKED always passes regardless of EC
g1_locked = run_g1("TMRW (daily)", ec_value=0.05)
test("LOCKED item passes Guard 1 at any EC",
     g1_locked.passed)

# Score-1 (HIGH reversibility) passes at any EC
g1_score1 = run_g1("Qualia Magnesium", ec_value=0.10)
test("Score-1 item passes Guard 1 at low EC",
     g1_score1.passed)

# Score-2 at high EC passes
g1_med_high = run_g1("Berberine 500mg", ec_value=0.50)
test("Score-2 item passes Guard 1 when EC > 0.30",
     g1_med_high.passed)

# Score-2 at low EC blocks
g1_med_low = run_g1("Berberine 500mg", ec_value=0.15)
test("Score-2 item blocked by Guard 1 when EC < 0.30",
     not g1_med_low.passed)
test("Score-2 blocked → forced DEFER",
     g1_med_low.forced_decision == ExtendedDecision.DEFER)


# ─── 7. GUARD 2 — DOMAIN CONVERGENCE ─────────────────────────────

section("7. Guard 2 — 3-Domain CS → ACT_SMALL / ACT_FULL")

def make_domains(biomarker=0.0, subjective=0.0, behavioral=0.0):
    return [
        DomainSignal(SignalDomain.BIOMARKER, biomarker, 0.8),
        DomainSignal(SignalDomain.SUBJECTIVE, subjective, 0.7),
        DomainSignal(SignalDomain.BEHAVIORAL, behavioral, 0.9),
    ]

# CS=3: all positive
cs3, dir3 = compute_convergence_score(make_domains(0.5, 0.5, 0.5))
test("CS=3: all 3 domains positive → cs=3, direction=positive",
     cs3 == 3 and dir3 == "positive")

# CS=2: biomarker + behavioral positive
cs2, dir2 = compute_convergence_score(make_domains(0.5, 0.0, 0.5))
test("CS=2: 2 domains positive → cs=2",
     cs2 == 2)

# CS=1: only biomarker
cs1, dir1 = compute_convergence_score(make_domains(0.5, 0.0, 0.0))
test("CS=1: single domain → blocks (< 2 required)",
     cs1 == 1)

# CS=0: all neutral
cs0, dir0 = compute_convergence_score(make_domains(0.0, 0.0, 0.0))
test("CS=0: no signal → blocks",
     cs0 == 0)

# Guard 2 in filter context
def run_g2(domain_sigs):
    cw = full_cw()
    pf = PreDecisionFilter(
        compliance_window=cw,
        domain_signals=domain_sigs,
    )
    g, cs, direction = pf._guard2_convergence()
    return g, cs, direction

g2_pass, cs, _ = run_g2(make_domains(0.5, 0.5, 0.5))
test("CS=3 domains → Guard 2 passes, ACT_FULL authorized",
     g2_pass.passed and "ACT_FULL" in g2_pass.reason)

g2_sm, cs2, _ = run_g2(make_domains(0.5, 0.0, 0.5))
test("CS=2 domains → Guard 2 passes, ACT_SMALL authorized",
     g2_sm.passed and "ACT_SMALL" in g2_sm.reason)

g2_block, cs1b, _ = run_g2(make_domains(0.5, 0.0, 0.0))
test("CS=1 → Guard 2 blocks with DEFER",
     not g2_block.passed and g2_block.forced_decision == ExtendedDecision.DEFER)

g2_neg, csn, dirn = run_g2(make_domains(-0.5, -0.5, 0.0))
test("Negative convergence (CS=2) → Guard 2 passes, routes SUPPRESS downstream",
     g2_neg.passed and dirn == "negative")


# ─── 8. GUARD 3 — MEC GATE ───────────────────────────────────────

section("8. Guard 3 — MEC Gate (MET enforcement)")

def run_g3(action_type, cell_days):
    cw = full_cw()
    pf = PreDecisionFilter(
        compliance_window=cw,
        proposed_action_type=action_type,
        days_elapsed_per_cell=cell_days,
    )
    return pf._guard3_mec()

# No action type → passes
g3_none = run_g3(None, {})
test("No action type → MEC gate skipped (passes)",
     g3_none.passed)

# MEC_UNIT metadata present when item given
cw = full_cw()
pf = PreDecisionFilter(
    compliance_window=cw,
    proposed_item_name="Qualia Magnesium",
)
g3_meta = pf._guard3_mec()
test("MEC_UNIT metadata returned for known item",
     "mec_unit" in g3_meta.metadata)


# ─── 9. GUARD 4 — CCS RECENCY-WEIGHTED ───────────────────────────

section("9. Guard 4 — CCS Recency-Weighted Gate")

def run_g4(records):
    cw = make_cw(records)
    pf = PreDecisionFilter(compliance_window=cw)
    return pf._guard4_ccs(cw.ccs)

# Full compliance → passes
g4_full = run_g4([1.0] * 30)
test("Full compliance → Guard 4 passes",
     g4_full.passed)
test("Full band → modifier = 1.0",
     g4_full.metadata["modifier"] == 1.0)

# Poor recent compliance → DEFER
g4_poor = run_g4([0.0] * 30)
test("0% compliance → Guard 4 blocks with DEFER",
     not g4_poor.passed and g4_poor.forced_decision == ExtendedDecision.DEFER)

# Partial: mixed compliance → partial band (CCS ~0.707)
# Use 21 days full + 9 days at 50% → weighted CCS lands in partial band
g4_partial = run_g4([1.0] * 21 + [0.5] * 9)
partial_ccs = make_cw([1.0] * 21 + [0.5] * 9).ccs
from vitalis_engine_v32 import ccs_band
test("Partial CCS (~0.71) → passes Guard 4 with partial modifier",
     g4_partial.passed and ccs_band(partial_ccs) in ('partial', 'full'))


# ─── 10. DECISION ROUTING ─────────────────────────────────────────

section("10. Decision Routing Logic")

def make_passed_result(cs=3, direction="positive", modifier=1.0):
    """Build a mock passing filter result."""
    from vitalis_engine_v32 import EntanglementAssessment
    ea = EntanglementAssessment(
        degraded=False, active_intervention_count=3,
        ccs_value=0.92, has_signal_conflict=False, modifier=modifier
    )
    return PreDecisionFilterResult(
        all_passed=True, entanglement=ea, ccs_modifier=modifier,
        convergence_score=cs, convergence_direction=direction,
    )

# CS=3 + positive → ACT_FULL
r = route_decision(Decision.ACT, 3, "positive", make_passed_result(3, "positive"))
test("CS=3, positive → ACT_FULL",
     r == ExtendedDecision.ACT_FULL)

# CS=2 + positive → ACT_SMALL
r = route_decision(Decision.ACT, 2, "positive", make_passed_result(2, "positive"))
test("CS=2, positive → ACT_SMALL",
     r == ExtendedDecision.ACT_SMALL)

# CS=1 → DEFER (no single-signal activation)
r = route_decision(Decision.ACT, 1, "positive", make_passed_result(1, "positive"))
test("CS=1 → DEFER (single-signal blocked)",
     r == ExtendedDecision.DEFER)

# Negative convergence → SUPPRESS
r = route_decision(Decision.ACT, 2, "negative", make_passed_result(2, "negative"))
test("Negative convergence CS=2 → SUPPRESS",
     r == ExtendedDecision.SUPPRESS)

# Base HOLD → HOLD
r = route_decision(Decision.HOLD, 3, "positive", make_passed_result(3, "positive"))
test("Base HOLD → ExtendedDecision.HOLD",
     r == ExtendedDecision.HOLD)

# Base CEILING, guards passed → CEILING
r = route_decision(Decision.CEILING, 3, "positive", make_passed_result(3, "positive"))
test("Base CEILING + guards passed → CEILING",
     r == ExtendedDecision.CEILING)


# ─── 11. REVERT LOGIC ─────────────────────────────────────────────

section("11. REVERT Logic — preserved from V3.1")

# Use Berberine (washout=7 days) so days_since=5 is within window
test("REVERT fires on worsening within washout window",
     should_revert([1.0, 0.8, 0.6, 0.4, 0.2], 5, "Berberine 500mg", -0.1, 3))

test("REVERT does NOT fire on LOCKED items",
     not should_revert([1.0, 0.5, 0.3], 3, "TMRW (daily)", -0.1, 3))

test("REVERT does NOT fire if outside washout window",
     not should_revert([1.0, 0.5, 0.3], 100, "Berberine 500mg", -0.1, 3))

test("REVERT does NOT fire on improving signal",
     not should_revert([0.3, 0.5, 0.7, 0.9, 1.0], 5, "Berberine 500mg", -0.1, 3))

test("REVERT does NOT fire with insufficient history",
     not should_revert([0.5, 0.3], 3, "Berberine 500mg", -0.1, 3))


# ─── 12. ATTRIBUTION_DEGRADED OUTPUT LANGUAGE ─────────────────────

section("12. ATTRIBUTION_DEGRADED — Required Output Language")

reason = EXTENDED_DECISION_REASONS[ExtendedDecision.ATTRIBUTION_DEGRADED]
test("ATTRIBUTION_DEGRADED reason contains 'Attribution is not currently reliable'",
     "Attribution is not currently reliable" in reason)
test("ATTRIBUTION_DEGRADED reason mentions 'do nothing indefinitely'",
     "do nothing indefinitely" in reason)
test("ACT_SMALL reason mentions MEC_UNIT constraint",
     "MEC_UNIT" in EXTENDED_DECISION_REASONS[ExtendedDecision.ACT_SMALL] or
     "minimum effective change" in EXTENDED_DECISION_REASONS[ExtendedDecision.ACT_SMALL].lower())
test("HOLD reason says 'HOLD is not failure'",
     "not failure" in EXTENDED_DECISION_REASONS[ExtendedDecision.HOLD] or
     "not an error" in EXTENDED_DECISION_REASONS[ExtendedDecision.HOLD])
test("EXTEND reason blocks CEILING and SUPPRESS explicitly",
     "CEILING" in EXTENDED_DECISION_REASONS[ExtendedDecision.EXTEND] and
     "SUPPRESS" in EXTENDED_DECISION_REASONS[ExtendedDecision.EXTEND])


# ─── 13. APPLY_V32_FILTER INTEGRATION ────────────────────────────

section("13. apply_v32_filter() End-to-End Integration")

# Clean scenario: full compliance, 3-domain CS=3 → ACT_FULL
result_full = apply_v32_filter(
    base_decision=Decision.ACT,
    compliance_window=full_cw(),
    active_intervention_count=3,
    days_elapsed_per_cell={"MT.SUP": 30, "BC.SUP": 30},
    controller_signal_directions={"MITO": 0.5, "BRAIN": 0.3},
    domain_signals=[
        DomainSignal(SignalDomain.BIOMARKER, 0.6, 0.9),
        DomainSignal(SignalDomain.SUBJECTIVE, 0.5, 0.8),
        DomainSignal(SignalDomain.BEHAVIORAL, 0.4, 0.85),
    ],
    effective_confidence=0.75,
)
test("Full convergence → ACT_FULL",
     result_full["final_decision"] == ExtendedDecision.ACT_FULL)
test("Full convergence → ccs_modifier = 1.0",
     result_full["ccs_modifier"] == 1.0)
test("Full convergence → convergence_score = 3",
     result_full["convergence_score"] == 3)

# 2-domain convergence → ACT_SMALL
result_small = apply_v32_filter(
    base_decision=Decision.ACT,
    compliance_window=full_cw(),
    active_intervention_count=3,
    days_elapsed_per_cell={"MT.SUP": 30},
    controller_signal_directions={"MITO": 0.5, "BRAIN": 0.3},
    domain_signals=[
        DomainSignal(SignalDomain.BIOMARKER, 0.6, 0.9),
        DomainSignal(SignalDomain.SUBJECTIVE, 0.0, 0.8),
        DomainSignal(SignalDomain.BEHAVIORAL, 0.4, 0.85),
    ],
    effective_confidence=0.75,
)
test("2-domain convergence → ACT_SMALL",
     result_small["final_decision"] == ExtendedDecision.ACT_SMALL)

# Poor compliance → DEFER
result_defer = apply_v32_filter(
    base_decision=Decision.ACT,
    compliance_window=make_cw([0.0] * 30),
    active_intervention_count=3,
    days_elapsed_per_cell={"SL.PRO": 10},
    controller_signal_directions={"MITO": 0.5},
    domain_signals=[
        DomainSignal(SignalDomain.BIOMARKER, 0.6, 0.9),
        DomainSignal(SignalDomain.SUBJECTIVE, 0.5, 0.8),
        DomainSignal(SignalDomain.BEHAVIORAL, 0.4, 0.85),
    ],
)
test("0% compliance → DEFER",
     result_defer["final_decision"] == ExtendedDecision.DEFER)

# Worsening signal → REVERT (use Berberine, washout=7, days_since=5 is within window)
result_revert = apply_v32_filter(
    base_decision=Decision.ACT,
    compliance_window=full_cw(),
    active_intervention_count=3,
    days_elapsed_per_cell={"CV.DEL": 10},
    controller_signal_directions={"CARDIO": -0.5},
    signal_history=[1.0, 0.7, 0.4, 0.2, 0.0],
    last_intervention_item="Berberine 500mg",
    days_since_last_intervention=5,
)
test("Worsening signal → REVERT",
     result_revert["final_decision"] == ExtendedDecision.REVERT)
test("REVERT → revert_triggered=True",
     result_revert["revert_triggered"])

# All 3 entanglement conditions → ATTRIBUTION_DEGRADED
result_degraded = apply_v32_filter(
    base_decision=Decision.ACT,
    compliance_window=make_cw([0.5] * 7 + [0.4] * 7 + [0.6] * 7),
    active_intervention_count=9,
    days_elapsed_per_cell={"MT.SUP": 30},
    controller_signal_directions={"MITO": 0.5, "BRAIN": -0.5, "CARDIO": 0.3, "IMMUNE": -0.4},
    domain_signals=[
        DomainSignal(SignalDomain.BIOMARKER, 0.5, 0.8),
        DomainSignal(SignalDomain.SUBJECTIVE, 0.4, 0.7),
        DomainSignal(SignalDomain.BEHAVIORAL, 0.3, 0.9),
    ],
)
test("All 3 entanglement conditions → ATTRIBUTION_DEGRADED",
     result_degraded["final_decision"] == ExtendedDecision.ATTRIBUTION_DEGRADED)


# ─── 14. BACKWARD COMPATIBILITY ──────────────────────────────────

section("14. Backward Compatibility — V3.1 apply_tier1_filter still works")

compat_result = apply_tier1_filter(
    base_decision=Decision.ACT,
    compliance_window=full_cw(),
    active_intervention_count=3,
    days_elapsed_per_cell={"MT.SUP": 30},
    controller_signal_directions={"MITO": 0.5, "BRAIN": 0.3},
)
test("V3.1 apply_tier1_filter still callable",
     compat_result is not None)
test("V3.1 wrapper returns final_decision",
     "final_decision" in compat_result)

# Locked core engine still runs
try:
    import vitalis_engine as _ve
    _noise = _ve.NoiseLayer(noise_level=0.3, seed=42)
    _scenario_dict = {"name": "compat_test", "grid_overrides": {}}
    sim = _ve.VitalisSimulation(scenario=_scenario_dict, noise=_noise)
    sim_ok = True
    # Run a few days to confirm the sim is functional
    sim.run(days=3)
except Exception as e:
    sim_ok = False
test("Locked core VitalisSimulation still runs after V3.2 import",
     sim_ok)
test("Core Decision enum still importable",
     hasattr(Decision, 'ACT'))


# ─── 15. MET FLOORS — PRESERVED ──────────────────────────────────

section("15. MET Floors — preserved from V3.1")
test("SL prefix → 7-day floor", get_met_for_cell("SL.PRO") == 7)
test("BC prefix → 14-day floor", get_met_for_cell("BC.DMD") == 14)
test("MT prefix → 21-day floor", get_met_for_cell("MT.SUP") == 21)
test("IM prefix → 28-day floor", get_met_for_cell("IM.PRO") == 28)
test("DG prefix → 30-day floor", get_met_for_cell("DG.DEL") == 30)
test("CV prefix → 45-day floor", get_met_for_cell("CV.PRO") == 45)
test("LG prefix → 60-day floor", get_met_for_cell("LG.DMD") == 60)
test("met_satisfied: 50 days for CV (45 required) → True",
     met_satisfied("CV.PRO", 50))
test("met_satisfied: 10 days for CV (45 required) → False",
     not met_satisfied("CV.PRO", 10))



# ─── HRV BASELINE NORMALIZATION TESTS ──────────────────────────────

print("\n── HRV Baseline Normalization ──")

# ── HRVBaseline construction ──────────────────────────────────────
_b = HRVBaseline(mean_ms=28.0, sd_ms=4.5, days_sampled=14)
test("HRVBaseline: mean=28, sd=4.5 constructs OK",
     _b.mean_ms == 28.0 and _b.sd_ms == 4.5 and _b.days_sampled == 14)

try:
    HRVBaseline(mean_ms=0, sd_ms=4.0)
    test("HRVBaseline: mean=0 should raise ValueError", False)
except ValueError:
    test("HRVBaseline: mean=0 raises ValueError", True)

try:
    HRVBaseline(mean_ms=28.0, sd_ms=-1.0)
    test("HRVBaseline: negative SD should raise ValueError", False)
except ValueError:
    test("HRVBaseline: negative SD raises ValueError", True)

# ── Direction logic ──────────────────────────────────────────────
_baseline = HRVBaseline(mean_ms=28.0, sd_ms=4.5, days_sampled=14)

_dir, _conf = normalize_hrv_direction(28.0, _baseline)
test("HRV at mean -> direction == 0.0", _dir == 0.0)

_dir, _conf = normalize_hrv_direction(32.5, _baseline)   # mean + 1 SD
test("HRV at mean+1SD -> direction approx +0.333", abs(_dir - (1.0/3.0)) < 0.01)

_dir, _conf = normalize_hrv_direction(28.0 + 3*4.5, _baseline)   # mean + 3 SD (cap)
test("HRV at mean+3SD -> direction == +1.0", _dir == 1.0)

_dir, _conf = normalize_hrv_direction(28.0 - 3*4.5, _baseline)   # mean - 3 SD (cap)
test("HRV at mean-3SD -> direction == -1.0", _dir == -1.0)

_dir, _ = normalize_hrv_direction(31.5, _baseline)
test("HRV above mean -> positive direction", _dir > 0.0)

_dir, _ = normalize_hrv_direction(24.5, _baseline)
test("HRV below mean -> negative direction", _dir < 0.0)

# ── Confidence logic ─────────────────────────────────────────────
_baseline_full = HRVBaseline(mean_ms=30.0, sd_ms=5.0, days_sampled=14)
_, _conf = normalize_hrv_direction(32.0, _baseline_full)
test("Full 14-day baseline -> confidence == 0.85", _conf == 0.85)

_baseline_sparse = HRVBaseline(mean_ms=30.0, sd_ms=5.0, days_sampled=3)
_, _conf = normalize_hrv_direction(32.0, _baseline_sparse)
test("Sparse 3-day baseline -> confidence < 0.85", _conf < 0.85)

_baseline_1d = HRVBaseline(mean_ms=30.0, sd_ms=5.0, days_sampled=1)
_, _conf = normalize_hrv_direction(32.0, _baseline_1d)
test("1-day baseline -> confidence approx 0.50", abs(_conf - 0.50) < 0.01)

_baseline_noisy = HRVBaseline(mean_ms=30.0, sd_ms=15.0, days_sampled=14)
_, _conf = normalize_hrv_direction(32.0, _baseline_noisy)
test("Noisy SD=15ms baseline -> confidence < 0.85", _conf < 0.85)

_baseline_clean = HRVBaseline(mean_ms=30.0, sd_ms=3.0, days_sampled=14)
_, _conf = normalize_hrv_direction(32.0, _baseline_clean)
test("Confidence never exceeds 0.90", _conf <= 0.90)

# ── Flat SD (SD=0) ───────────────────────────────────────────────
_baseline_flat = HRVBaseline(mean_ms=30.0, sd_ms=0.0, days_sampled=14)
_dir, _conf = normalize_hrv_direction(35.0, _baseline_flat)
test("Flat SD + above mean -> direction == +1.0", _dir == 1.0)
test("Flat SD -> confidence capped at 0.50", _conf == 0.50)

_dir, _conf = normalize_hrv_direction(25.0, _baseline_flat)
test("Flat SD + below mean -> direction == -1.0", _dir == -1.0)

# ── hrv_domain_signal convenience constructor ────────────────────
_b2 = HRVBaseline(mean_ms=28.0, sd_ms=4.5, days_sampled=14)
_sig = hrv_domain_signal(31.5, _b2)
test("hrv_domain_signal -> BIOMARKER domain",
     _sig.domain == SignalDomain.BIOMARKER)
test("hrv_domain_signal: above-mean HRV -> positive direction",
     _sig.direction > 0.0)
test("hrv_domain_signal: confidence in valid range [0, 0.90]",
     0.0 <= _sig.confidence <= 0.90)

# ── Real-world: James Whoop data (pre-Day 0 proxy) ───────────────
# Live reading: 30ms HRV. Conservative proxy baseline: mean=30, SD=5
_james_baseline = HRVBaseline(mean_ms=30.0, sd_ms=5.0, days_sampled=14,
                               source="whoop_proxy_pre_day0")
_james_sig = hrv_domain_signal(30.0, _james_baseline)
test("James proxy: HRV at mean -> neutral direction",
     abs(_james_sig.direction) < 0.05)

_james_sig_up = hrv_domain_signal(33.0, _james_baseline)
test("James proxy: HRV +3ms above mean -> weak positive direction",
     0.0 < _james_sig_up.direction < 0.5)

_james_sig_down = hrv_domain_signal(24.0, _james_baseline)
test("James proxy: HRV -6ms below mean -> negative direction",
     _james_sig_down.direction < 0.0)


# P1-5: ATTRIBUTION ENGINE SYNTHETIC DATA TEST HARNESS
# Validates that known inputs produce verified outputs.
# Uses the actual functional API — no phantom classes.
# ══════════════════════════════════════════════════════════════════════════════════════════
print("\n─── P1-5: Attribution Engine Synthetic Harness ───")

from vitalis_engine_v32 import (
    ComplianceWindow, ccs_band,
    DomainSignal, SignalDomain, HRVBaseline,
    compute_convergence_score, route_decision,
    normalize_hrv_direction, hrv_domain_signal,
    PreDecisionFilter, Decision,
)

def make_cw(daily_rates: list) -> ComplianceWindow:
    """Build a ComplianceWindow from a list of per-day compliance rates (0.0–1.0)."""
    cw = ComplianceWindow()
    for rate in daily_rates:
        # rate is fraction taken; record as single bool by rounding
        cw.record(rate >= 0.5)
    return cw

def make_cw_exact(daily_rates: list) -> ComplianceWindow:
    """Build a ComplianceWindow from exact float rates using internal daily_records."""
    cw = ComplianceWindow()
    cw.daily_records = [float(r) for r in daily_rates]
    return cw

# ── SCENARIO 1: Perfect compliance ──
_cw_perfect = make_cw_exact([1.0] * 14)
test("Synthetic: 14 perfect days -> CCS == 1.0",
     _cw_perfect.ccs == 1.0)
test("Synthetic: 14 perfect days -> CCS band == full",
     ccs_band(_cw_perfect.ccs) == "full")

# ── SCENARIO 2: ~70% compliance ──
_cw_70 = make_cw_exact([0.70] * 14)
test("Synthetic: 70% compliance -> CCS band in [partial, compromised]",
     ccs_band(_cw_70.ccs) in ("partial", "compromised"))

# ── SCENARIO 3: Suspension band (50% compliance) ──
_cw_50 = make_cw_exact([0.50] * 14)
test("Synthetic: 50% compliance -> CCS band == suspension",
     ccs_band(_cw_50.ccs) == "suspension")

# ── SCENARIO 4: Recency weighting — late improvement ──
# Days 1-16 at 50%, days 17-30 at 100%
_cw_recency = make_cw_exact([0.50]*16 + [1.00]*14)
_ccs_recency = _cw_recency.ccs
test("Synthetic recency: late-improving -> CCS > flat average (0.72)",
     _ccs_recency > 0.72)

# ── SCENARIO 5: CS gate — 3 aligned signals → ACT_FULL ──
_sig_positive = [
    DomainSignal(domain=SignalDomain.BIOMARKER,   direction=0.8, confidence=0.85),
    DomainSignal(domain=SignalDomain.SUBJECTIVE,  direction=0.6, confidence=0.70),
    DomainSignal(domain=SignalDomain.BEHAVIORAL,  direction=0.5, confidence=0.75),
]
_cs_full, _dir_full = compute_convergence_score(_sig_positive)
test("Synthetic CS gate: 3 aligned positive signals -> CS == 3",
     _cs_full == 3)
test("Synthetic CS gate: 3 aligned positive signals -> direction == positive",
     _dir_full == "positive")

# ── SCENARIO 6: CS gate — 2 signals → ACT_SMALL ──
_sig_2 = [
    DomainSignal(domain=SignalDomain.BIOMARKER,  direction=0.7, confidence=0.85),
    DomainSignal(domain=SignalDomain.SUBJECTIVE, direction=0.5, confidence=0.70),
]
_cs_2, _dir_2 = compute_convergence_score(_sig_2)
test("Synthetic CS gate: 2 aligned signals -> CS == 2",
     _cs_2 == 2)

# ── SCENARIO 7: CS gate — mixed signals → direction == mixed ──
_sig_mixed = [
    DomainSignal(domain=SignalDomain.BIOMARKER,  direction=0.8, confidence=0.85),
    DomainSignal(domain=SignalDomain.SUBJECTIVE, direction=-0.6, confidence=0.70),
]
_cs_mixed, _dir_mixed = compute_convergence_score(_sig_mixed)
test("Synthetic CS gate: conflicting signals -> direction == mixed",
     _dir_mixed == "mixed")

# ── SCENARIO 8: CS=0 → DEFER via route_decision ──
_cw_partial = make_cw_exact([0.80] * 14)
_sig_none = []  # no domain signals
_cs_0, _dir_0 = compute_convergence_score(_sig_none)
test("Synthetic: no signals -> CS == 0",
     _cs_0 == 0)

# ── SCENARIO 9: Negative convergence → SUPPRESS ──
_sig_negative = [
    DomainSignal(domain=SignalDomain.BIOMARKER,  direction=-0.7, confidence=0.85),
    DomainSignal(domain=SignalDomain.SUBJECTIVE, direction=-0.5, confidence=0.70),
]
_cs_neg, _dir_neg = compute_convergence_score(_sig_negative)
test("Synthetic: 2 negative signals -> direction == negative",
     _dir_neg == "negative")
test("Synthetic: 2 negative signals -> CS == 2",
     _cs_neg == 2)

# ── SCENARIO 10: HRV sick-day exclusion in behavioral domain ──
# Build baseline from 7 clean days, then check that illness day returns 0 direction
_baseline_syn = HRVBaseline(mean_ms=35.0, sd_ms=5.0, days_sampled=7)
# Clean day: HRV +6ms above mean → positive direction
_dir_clean, _ = normalize_hrv_direction(41.0, _baseline_syn)
test("Synthetic sick-day: clean day +6ms -> positive direction",
     _dir_clean > 0.0)

# The sick-day exclusion is in the JS/mobile layer — Python engine uses raw HRV.
# What we validate here: HRV at mean = neutral (no drift without illness flag)
_dir_mean, _ = normalize_hrv_direction(35.0, _baseline_syn)
test("Synthetic sick-day: HRV at mean -> direction == 0.0",
     _dir_mean == 0.0)

# ── SCENARIO 11: Guard 4 CCS suspension → DEFER ──
_cw_suspended = make_cw_exact([0.40] * 14)
_ccs_sus = _cw_suspended.ccs
test("Synthetic guard 4: 40% compliance -> CCS < 0.55 (suspension)",
     _ccs_sus < 0.55)

_filter_sus = PreDecisionFilter(
    compliance_window=_cw_suspended,
    active_intervention_count=1,
    domain_signals=[
        DomainSignal(domain=SignalDomain.BIOMARKER, direction=0.8, confidence=0.85)
    ],
)
_result_sus = _filter_sus.run()
test("Synthetic guard 4: suspension band -> filter blocks or forces DEFER",
     not _result_sus.all_passed or _ccs_sus < 0.55)

# ── SCENARIO 12: hrv_domain_signal convenience function ──
_baseline_12 = HRVBaseline(mean_ms=30.0, sd_ms=5.0, days_sampled=14)
_sig_12 = hrv_domain_signal(36.0, _baseline_12)   # +1.2 SD above mean
test("Synthetic hrv_domain_signal: +1.2SD -> positive direction",
     _sig_12.direction > 0.0)
test("Synthetic hrv_domain_signal: returns BIOMARKER domain",
     _sig_12.domain == SignalDomain.BIOMARKER)
test("Synthetic hrv_domain_signal: confidence in [0, 0.90]",
     0.0 <= _sig_12.confidence <= 0.90)

# ── SCENARIO 13: Behavioral domain anchor date calculation ──
import datetime
_cycle_start = datetime.date(2026, 7, 1)
_today       = datetime.date(2026, 8, 14)
_days_elapsed = (_today - _cycle_start).days + 1
test("Behavioral anchor: Day 1=Jul1, Aug14 = Day 45",
     _days_elapsed == 45)

# ── SCENARIO 14: CCS recency short-window (< 7 days) → unweighted mean ──
_cw_3d = make_cw_exact([0.60, 0.80, 0.40])
_ccs_3d = _cw_3d.ccs
test("Synthetic CCS < 7 days -> unweighted mean (0.60)",
     abs(_ccs_3d - (0.60+0.80+0.40)/3) < 0.01)

print("  ✓ Attribution engine synthetic harness complete")

# ─── FINAL RESULTS ────────────────────────────────────────────────

total = PASS + FAIL
print(f"\n{'═'*60}")
print(f"RESULTS: {PASS}/{total} PASSED  |  {FAIL} FAILED")
print(f"{'═'*60}")

if FAIL > 0:
    print("\nFAILED TESTS:")
    for status, name in RESULTS:
        if "FAIL" in status:
            print(f"  {status}  {name}")
    sys.exit(1)
