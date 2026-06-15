"""
Automated conversation tests for SoundCraft Jamie agent.

Each scenario is a multi-turn conversation with assertions checked
against every response. Run with:

    python -m tests.run_tests              # all scenarios
    python -m tests.run_tests budget       # scenarios whose name contains "budget"
    python -m tests.run_tests --verbose    # print full conversation transcript
"""
import argparse
import sys
import traceback
from dataclasses import dataclass, field
from typing import Callable

# Ensure project root is on the path when run from repo root
import os
_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _root)

# Load .env before importing agent modules so get_secret() sees the key
from dotenv import load_dotenv
load_dotenv(os.path.join(_root, ".env"))

from agent.startup import ensure_db
from agent.soundcraft_agent import SoundCraftAgent


# ── Assertion helpers ─────────────────────────────────────────────────────────

def _extract_prices(text: str) -> list[float]:
    """Extract dollar amounts from response text, requiring at least one digit."""
    import re
    return [float(m.replace(",", "")) for m in re.findall(r"\$(\d[\d,]*(?:\.\d+)?)", text)]


def assert_price_range(response: str, min_price: float, max_price: float) -> str | None:
    """Return failure message if no price in [min_price, max_price] appears in the response."""
    prices = _extract_prices(response)
    if not any(min_price <= p <= max_price for p in prices):
        return f"Expected a price between ${min_price:,.0f}–${max_price:,.0f}, found prices: {prices}"
    return None


def assert_no_price_range(response: str, min_price: float, max_price: float) -> str | None:
    """Return failure message if a price in the unwanted range appears."""
    prices = _extract_prices(response)
    bad = [p for p in prices if min_price <= p <= max_price]
    if bad:
        return f"Unexpected prices in ${min_price:,.0f}–${max_price:,.0f} range: {bad}"
    return None


def assert_recommended_category(expected_category: str) -> Callable[[SoundCraftAgent], str | None]:
    """Agent-level check: at least one recommended product is in the expected category/subcategory."""
    def check(agent: SoundCraftAgent) -> str | None:
        if not agent.last_recommended_ids:
            return "Agent has no last_recommended_ids — no search was performed"
        import duckdb
        from agent.soundcraft_agent import DB_PATH
        con = duckdb.connect(str(DB_PATH), read_only=True)
        try:
            ids_placeholder = ", ".join("?" * len(agent.last_recommended_ids))
            rows = con.execute(
                f"SELECT product_name, category, subcategory FROM dim_products WHERE product_id IN ({ids_placeholder})",
                agent.last_recommended_ids,
            ).fetchall()
        finally:
            con.close()
        match = any(
            expected_category.lower() in (cat or "").lower() or expected_category.lower() in (sub or "").lower()
            for _, cat, sub in rows
        )
        if not match:
            cats = [(cat, sub) for _, cat, sub in rows]
            return f"Expected at least one '{expected_category}' product, got: {cats}"
        return None
    return check


def assert_recommended_prices_in_range(min_price: float, max_price: float) -> Callable[[SoundCraftAgent], str | None]:
    """Agent-level check: verify that recommended product IDs are priced within the given range."""
    def check(agent: SoundCraftAgent) -> str | None:
        if not agent.last_recommended_ids:
            return "Agent has no last_recommended_ids — no search was performed"
        import duckdb
        from agent.soundcraft_agent import DB_PATH
        con = duckdb.connect(str(DB_PATH), read_only=True)
        try:
            ids_placeholder = ", ".join("?" * len(agent.last_recommended_ids))
            rows = con.execute(
                f"SELECT product_name, price FROM dim_products WHERE product_id IN ({ids_placeholder})",
                agent.last_recommended_ids,
            ).fetchall()
        finally:
            con.close()
        out_of_range = [(name, float(price)) for name, price in rows if not (min_price <= float(price) <= max_price)]
        if len(out_of_range) == len(rows):
            return (
                f"All {len(rows)} recommended products are outside ${min_price:,.0f}–${max_price:,.0f}: "
                + ", ".join(f"{n} (${p:,.0f})" for n, p in out_of_range)
            )
        return None
    return check


def assert_contains(phrases: list[str]) -> Callable[[str], str | None]:
    """All phrases must appear."""
    def check(response: str) -> str | None:
        lowered = response.lower()
        missing = [p for p in phrases if p.lower() not in lowered]
        if missing:
            return f"Response missing expected phrases: {missing}"
        return None
    return check


def assert_any_contains(phrases: list[str]) -> Callable[[str], str | None]:
    """At least one phrase must appear."""
    def check(response: str) -> str | None:
        lowered = response.lower()
        if not any(p.lower() in lowered for p in phrases):
            return f"Response must contain at least one of: {phrases}"
        return None
    return check


def assert_not_contains(phrases: list[str]) -> Callable[[str], str | None]:
    def check(response: str) -> str | None:
        lowered = response.lower()
        found = [p for p in phrases if p.lower() in lowered]
        if found:
            return f"Response should NOT contain: {found}"
        return None
    return check


def assert_handoff_logged(agent: SoundCraftAgent) -> str | None:
    if not agent.handoff_logged:
        return "Expected agent.handoff_logged=True but no handoff was recorded"
    return None


def assert_no_handoff(agent: SoundCraftAgent) -> str | None:
    if agent.handoff_logged:
        return "Expected no handoff but agent.handoff_logged=True"
    return None


# ── Scenario definition ───────────────────────────────────────────────────────

@dataclass
class Turn:
    message: str
    # Per-turn checks: callable(response_text) -> error_str | None
    response_checks: list[Callable[[str], str | None]] = field(default_factory=list)
    # Agent-state checks after this turn: callable(agent) -> error_str | None
    agent_checks: list[Callable[[SoundCraftAgent], str | None]] = field(default_factory=list)


@dataclass
class Scenario:
    name: str
    description: str
    turns: list[Turn]


# ── Scenario definitions ──────────────────────────────────────────────────────

SCENARIOS: list[Scenario] = [

    Scenario(
        name="budget_respect_high_end",
        description="Customer says 'around $3500' — Jamie must recommend guitars in that range, not cheap ones.",
        turns=[
            Turn("Hi, I'm looking for an electric guitar around $3500."),
            Turn("I'm an intermediate player, I mostly play blues and rock. I don't have a specific brand in mind."),
            Turn(
                "I have a basic Squier and a small practice amp. Looking to upgrade the guitar.",
                agent_checks=[assert_recommended_prices_in_range(1500, 5000)],
            ),
        ],
    ),

    Scenario(
        name="budget_respect_mid_range",
        description="Customer budget is $500 — results should be in that range, not premium.",
        turns=[
            Turn("I want to get started with acoustic guitar. My budget is around $500."),
            Turn(
                "I'm a complete beginner, just want something to learn on at home.",
                agent_checks=[assert_recommended_prices_in_range(100, 900)],
            ),
        ],
    ),

    Scenario(
        name="human_escalation_immediate",
        description="Customer explicitly asks for a human — Jamie must trigger handoff immediately.",
        turns=[
            Turn("I need help picking a drum kit."),
            Turn(
                "Actually, can I just talk to a real person? I'd rather speak with someone.",
                response_checks=[
                    assert_any_contains(["sales engineer", "specialist", "engineer", "person", "team member"]),
                    assert_not_contains(["search tool", "technical issue", "having trouble"]),
                ],
                agent_checks=[assert_handoff_logged],
            ),
        ],
    ),

    Scenario(
        name="out_of_catalog_honesty",
        description="Customer asks about a violin — Jamie must be honest about catalog scope, not blame the search tool.",
        turns=[
            Turn("Do you carry violins? I'm looking for a student violin around $300."),
        ],
        # response checks applied to the final turn
    ),

    Scenario(
        name="recommendation_then_handoff",
        description="Normal full conversation ending in product recommendations and a handoff.",
        turns=[
            Turn("Hey I'm looking for a microphone for home recording."),
            Turn("I mostly record vocals and acoustic guitar. Budget is around $200."),
            Turn(
                "I'm an intermediate singer-songwriter. I record in my bedroom — nothing treated.",
                agent_checks=[
                    assert_handoff_logged,
                    assert_recommended_prices_in_range(50, 500),
                ],
            ),
        ],
    ),

    Scenario(
        name="no_duplicate_owned_gear",
        description="Customer already owns a Strat — Jamie should recommend amps, not guitars.",
        turns=[
            Turn("I already have a Fender Stratocaster. Looking for an amp to go with it, around $800."),
            Turn("I play at home mostly, a little bit of jamming with friends. Intermediate level."),
            Turn(
                "No I don't have any other gear besides the Strat.",
                agent_checks=[
                    assert_recommended_category("Amplifier"),
                    assert_recommended_prices_in_range(300, 1500),
                ],
            ),
        ],
    ),

]

# Attach out-of-catalog checks directly to the turn
SCENARIOS[3].turns[0].response_checks = [
    assert_contains(["outside", "specialty", "orchestral", "focus"]),
    assert_not_contains(["search tool", "technical issue", "trouble finding", "couldn't find"]),
]


# ── Runner ────────────────────────────────────────────────────────────────────

@dataclass
class TurnResult:
    turn_index: int
    message: str
    response: str
    failures: list[str]


@dataclass
class ScenarioResult:
    scenario: Scenario
    passed: bool
    turn_results: list[TurnResult]
    error: str | None = None  # unexpected exception


def run_scenario(scenario: Scenario, verbose: bool = False) -> ScenarioResult:
    ensure_db()
    agent = SoundCraftAgent()
    transcript: list[dict] = []
    turn_results: list[TurnResult] = []

    try:
        for i, turn in enumerate(scenario.turns):
            response, _ = agent.send(turn.message, transcript)
            transcript.append({"role": "user", "content": turn.message})
            transcript.append({"role": "assistant", "content": response})

            failures = []
            for check in turn.response_checks:
                err = check(response)
                if err:
                    failures.append(err)
            for check in turn.agent_checks:
                err = check(agent)
                if err:
                    failures.append(err)

            turn_results.append(TurnResult(i, turn.message, response, failures))

            if verbose:
                print(f"\n  Turn {i + 1}")
                print(f"  Customer : {turn.message}")
                print(f"  Jamie    : {response}")
                if failures:
                    for f in failures:
                        print(f"  FAIL     : {f}")

    except Exception:
        return ScenarioResult(
            scenario=scenario,
            passed=False,
            turn_results=turn_results,
            error=traceback.format_exc(),
        )

    all_passed = all(not tr.failures for tr in turn_results)
    return ScenarioResult(scenario=scenario, passed=all_passed, turn_results=turn_results)


def run_all(filter_str: str | None = None, verbose: bool = False) -> bool:
    scenarios = SCENARIOS
    if filter_str:
        scenarios = [s for s in SCENARIOS if filter_str.lower() in s.name.lower()]
        if not scenarios:
            print(f"No scenarios match '{filter_str}'")
            return False

    print(f"\nRunning {len(scenarios)} scenario(s)...\n")
    results: list[ScenarioResult] = []

    for scenario in scenarios:
        print(f"  {scenario.name} ... ", end="", flush=True)
        if verbose:
            print(f"\n  {scenario.description}")
        result = run_scenario(scenario, verbose=verbose)
        results.append(result)

        if result.error:
            print("ERROR")
            print(f"    {result.error}")
        elif result.passed:
            print("PASS")
        else:
            print("FAIL")
            for tr in result.turn_results:
                for f in tr.failures:
                    print(f"    turn {tr.turn_index + 1}: {f}")
                    if not verbose:
                        print(f"    response: {tr.response[:300]}...")

    passed = sum(1 for r in results if r.passed)
    failed = len(results) - passed
    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed out of {len(results)}")

    return failed == 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run SoundCraft agent conversation tests")
    parser.add_argument("filter", nargs="?", help="Only run scenarios whose name contains this string")
    parser.add_argument("--verbose", "-v", action="store_true", help="Print full conversation transcripts")
    args = parser.parse_args()

    success = run_all(filter_str=args.filter, verbose=args.verbose)
    sys.exit(0 if success else 1)
