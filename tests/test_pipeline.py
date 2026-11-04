from datetime import datetime

from conftest import NOW, VIENNA
from fermentation_agent.models import DoughRequest, Mixing
from fermentation_agent.pipeline import plan_offline


def request(target: datetime, **overrides) -> DoughRequest:
    return DoughRequest(**dict(pizza_count=4, room_temp_c=22, mixing=Mixing.HAND, target_time=target) | overrides)


def phase_hours(result):
    return [(s["name"], s["hours"]) for s in result.trace[1]["arguments"]["phases"]]


def test_default_plan(tmp_path):
    result = plan_offline(request(datetime(2026, 11, 7, 19, tzinfo=VIENNA)), NOW,
                          confirm=lambda r: True, output_path=tmp_path / "plan.ics")
    assert result.status == "planned"
    assert not result.summary_replaced  # template summary passes the output guardrail
    assert phase_hours(result) == [("bulk", 2), ("cold retard", 24), ("final proof", 4)]
    assert [t["tool"] for t in result.trace] == [
        "submit_request", "build_timeline", "calculate_yeast_percentage",
        "calculate_water_temperature", "calculate_bakers_math", "finish_plan"]
    assert result.ics_path.exists()


def test_night_conflict_moves_cold_retard():
    # Bake Sat 12:00: 24 h → mixing Fri 04:55; 23/25/22/26 h are night starts too; 21 h → Fri 07:55.
    result = plan_offline(request(datetime(2026, 11, 7, 12, tzinfo=VIENNA)), NOW)
    assert result.status == "planned"
    assert ("cold retard", 21) in phase_hours(result)


def test_too_soon_falls_back_to_same_day_dough():
    result = plan_offline(request(datetime(2026, 11, 7, 19, tzinfo=VIENNA)), datetime(2026, 11, 7, 8, tzinfo=VIENNA))
    assert result.status == "planned"
    assert phase_hours(result) == [("bulk", 2), ("final proof", 4)]
    assert result.yeast.yeast_pct > 0.4  # short fermentation needs more yeast


def test_early_bake_uses_overnight_final_proof():
    # Bake Sat 07:30: no cold plan avoids night steps, but a same-day dough proofs overnight.
    result = plan_offline(request(datetime(2026, 11, 7, 7, 30, tzinfo=VIENNA)), NOW)
    assert result.status == "planned"
    assert phase_hours(result) == [("bulk", 2), ("final proof", 9)]


def test_impossible_plan_fails_with_reason():
    # 2.5 h before the bake time even the shortest same-day dough cannot be made.
    result = plan_offline(request(datetime(2026, 11, 7, 7, 30, tzinfo=VIENNA)), datetime(2026, 11, 7, 5, tzinfo=VIENNA))
    assert result.status == "failed"
    assert "earliest possible start" in result.message


def test_invalid_request_rejected():
    result = plan_offline(request(datetime(2026, 11, 7, 19, tzinfo=VIENNA), hydration_pct=95), NOW)
    assert result.status == "rejected"
    assert "batter" in result.message
