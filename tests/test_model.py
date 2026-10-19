import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import model  # noqa: E402
from model import Engagement, Engineer, Settings  # noqa: E402

MON = date(2027, 1, 4)          # a Monday
S = Settings()
FULL = S.hours_per_week * S.planning_ceiling   # 34 billable hours in a clean week


def eng(id, skills=("sec",), region="US", **kw):
    return Engineer(id=id, name=id.title(), region=region, skills=frozenset(skills), **kw)


def job(id, skill="sec", stage="closed", start=MON, weeks=4, hours=20.0, **kw):
    return Engagement(id=id, customer=id.title(), skill=skill, stage=stage, start=start,
                      weeks=weeks, hours_per_week=hours, **kw)


def run(engineers, engagements, n=6, scenario="expected", holidays=None, s=S):
    return model.run(engineers, engagements, MON, n, holidays or {}, scenario, s)


# --- supply -------------------------------------------------------------------

def test_holiday_and_pto_cut_available_hours():
    weeks = model.week_starts(MON, 3)
    e = eng("a", pto=(MON + timedelta(weeks=2),))
    hours = model.available_hours(e, weeks, {"US": [MON + timedelta(days=1)]}, S)
    assert hours == [32.0, 40.0, 0.0]


def test_holiday_in_another_region_does_not_count():
    weeks = model.week_starts(MON, 1)
    assert model.available_hours(eng("a", region="IE"), weeks, {"US": [MON]}, S) == [40.0]


def test_start_and_end_dates_trim_partial_weeks():
    weeks = model.week_starts(MON, 3)
    starter = eng("a", start=MON + timedelta(days=9))      # Wednesday of week 2
    leaver = eng("b", end=MON + timedelta(days=7))         # Monday of week 2
    assert model.available_hours(starter, weeks, {}, S) == [0.0, 24.0, 40.0]
    assert model.available_hours(leaver, weeks, {}, S) == [40.0, 8.0, 0.0]


def test_holiday_outside_a_partial_week_is_not_subtracted():
    weeks = model.week_starts(MON, 1)
    us = {"US": [MON, MON + timedelta(days=3), MON + timedelta(days=4)]}   # Mon, Thu, Fri
    starter = eng("a", start=MON + timedelta(days=2))                       # starts Wednesday
    leaver = eng("b", end=MON + timedelta(days=1))                          # last day Tuesday
    assert model.available_hours(starter, weeks, us, S) == [8.0]           # Wed only; Thu/Fri are holidays
    assert model.available_hours(leaver, weeks, us, S) == [8.0]            # Tue only; Mon is a holiday


def test_pto_on_any_weekday_takes_that_whole_week():
    weeks = model.week_starts(MON, 2)
    assert model.available_hours(eng("a", pto=(MON + timedelta(days=9),)), weeks, {}, S) == [40.0, 0.0]


def test_weekend_start_ramps_from_the_next_monday():
    s = Settings(ramp_weeks=2, ramp_factor=0.5)
    weeks = model.week_starts(MON, 4)
    e = eng("a", start=MON + timedelta(days=5))                             # a Saturday
    cap = model.billable_capacity(e, model.available_hours(e, weeks, {}, s), weeks, s)
    assert cap == [0.0, FULL / 2, FULL / 2, FULL]


def test_new_hire_ramps_at_reduced_capacity():
    s = Settings(ramp_weeks=2, ramp_factor=0.5)
    weeks = model.week_starts(MON, 3)
    e = eng("a", start=MON)
    cap = model.billable_capacity(e, model.available_hours(e, weeks, {}, s), weeks, s)
    assert cap == [FULL / 2, FULL / 2, FULL]


# --- demand -------------------------------------------------------------------

@pytest.mark.parametrize("scenario,expected", [("booked", 0.0), ("expected", 0.5 * 20), ("stretch", 20.0)])
def test_scenarios_weight_a_best_case_deal(scenario, expected):
    g = job("x", stage="best_case")
    assert model.engagement_demand(g, model.week_starts(MON, 1), scenario) == [expected]


def test_probability_override_beats_stage_default():
    g = job("x", stage="pipeline", probability=0.6)
    assert g.weight("expected") == 0.6
    assert g.weight("booked") == 0.0


def test_engagement_that_started_before_the_horizon_still_counts():
    g = job("x", start=MON - timedelta(weeks=2), weeks=3)
    assert model.engagement_demand(g, model.week_starts(MON, 2), "booked") == [20.0, 0.0]


# --- allocation ---------------------------------------------------------------

def test_hours_are_conserved():
    team = [eng("a"), eng("b")]
    jobs = [job("x", hours=30), job("y", hours=30), job("z", hours=30)]
    fc = run(team, jobs, n=4)
    for i in range(4):
        assigned = sum(h[i] for h in fc.assigned.values())
        unmet = sum(h[i] for h in fc.unmet.values())
        assert assigned + unmet == pytest.approx(90.0)


def test_nobody_is_planned_past_the_ceiling():
    team = [eng("a")]
    fc = run(team, [job("x", hours=30), job("y", hours=30)], n=4)
    for i in range(4):
        assert fc.assigned["a"][i] <= fc.capacity["a"][i] + 1e-9
    assert fc.unmet["sec"][0] == pytest.approx(60 - FULL)


def test_only_engineers_with_the_skill_get_the_work():
    team = [eng("a", skills=("sec",)), eng("b", skills=("ai",))]
    fc = run(team, [job("x", skill="ai", hours=10)], n=1)
    assert fc.assigned["a"] == [0.0]
    assert fc.assigned["b"] == [10.0]


def test_skill_nobody_has_is_all_unmet():
    fc = run([eng("a")], [job("x", skill="ai", hours=10)], n=1)
    assert fc.unmet["ai"] == [10.0]
    assert fc.leads["x"] is None


def test_lead_engineer_keeps_the_engagement_across_weeks():
    team = [eng("a"), eng("b")]
    fc = run(team, [job("x", hours=20, weeks=4)], n=4)
    lead = fc.leads["x"]
    assert fc.by_engagement["x"].keys() == {lead}
    assert fc.by_engagement["x"][lead] == [20.0] * 4


def test_lead_on_pto_hands_off_only_that_week():
    # b is busier, so a leads; a's PTO week goes to b and comes straight back
    team = [eng("a", pto=(MON + timedelta(weeks=1),)), eng("b")]
    jobs = [job("busy", hours=20, weeks=4), job("x", hours=20, weeks=4, stage="commit")]
    fc = run(team, jobs, n=4, scenario="stretch")
    assert fc.leads["busy"] == "b" and fc.leads["x"] == "a"
    split = fc.by_engagement["x"]
    assert split["a"] == [20.0, 0.0, 20.0, 20.0]
    assert split["b"] == [0.0, 14.0, 0.0, 0.0]          # b's 34 billable less its 20 on 'busy'
    assert fc.unmet["sec"][1] == pytest.approx(6.0)


def test_closed_work_is_staffed_before_pipeline():
    team = [eng("a")]
    jobs = [job("maybe", stage="best_case", hours=30), job("signed", stage="closed", hours=30)]
    fc = run(team, jobs, n=1, scenario="stretch")
    assert fc.by_engagement["signed"]["a"] == [30.0]
    assert fc.unmet["sec"][0] == pytest.approx(30 + 30 - FULL)


def test_no_lead_when_nobody_with_the_skill_has_room():
    team = [eng("a")]
    jobs = [job("big", hours=FULL, weeks=2), job("late", hours=10, weeks=2, stage="commit")]
    fc = run(team, jobs, n=2, scenario="stretch")
    assert fc.leads["late"] is None and fc.lead_notes["late"] == "no_room"
    assert fc.unmet["sec"] == [10.0, 10.0]


def test_lead_notes_say_why_there_is_no_lead():
    fc = run([eng("a")], [job("later", start=MON + timedelta(weeks=8)), job("ai", skill="ai")], n=4)
    assert fc.lead_notes == {"later": "outside_horizon", "ai": "no_skill"}


def test_someone_with_room_beats_someone_present_with_none():
    # 'full' is here at kickoff but booked solid; 'late' joins week 2 with room
    team = [eng("full"), eng("late", start=MON + timedelta(weeks=1))]
    jobs = [job("solid", hours=FULL, weeks=4), job("x", hours=10, weeks=4, stage="commit")]
    fc = run(team, jobs, n=4, scenario="stretch")
    assert fc.leads["solid"] == "full"
    assert fc.leads["x"] == "late"


def test_region_preference_breaks_ties():
    team = [eng("a", region="US"), eng("b", region="IE")]
    fc = run(team, [job("x", hours=10, region="IE")], n=1)
    assert fc.leads["x"] == "b"


def test_lead_is_on_the_team_at_kickoff():
    # 'late' has far more room overall but joins in week 3; 'busy' is here from day one
    team = [eng("late", start=MON + timedelta(weeks=2)), eng("busy")]
    jobs = [job("other", hours=10, weeks=6), job("x", hours=20, weeks=6, stage="commit")]
    fc = run(team, jobs, n=6, scenario="stretch")
    assert fc.leads["x"] == "busy"


def test_region_preference_beats_a_little_more_room():
    team = [eng("us", region="US"), eng("ie", region="IE")]
    jobs = [job("ie_side", hours=5, weeks=4, region="IE"), job("x", hours=20, weeks=4, region="IE", stage="commit")]
    fc = run(team, jobs, n=4, scenario="stretch")
    assert fc.leads["ie_side"] == "ie"
    assert fc.leads["x"] == "ie"     # ie can still cover all 20 hours, so region wins over us's extra room


# --- signals ------------------------------------------------------------------

def _unmet_forecast(gaps_fte, s=S):
    """A forecast with a given unmet-demand curve and nothing else."""
    weeks = model.week_starts(MON, len(gaps_fte))
    per_fte = s.hours_per_week * s.target_utilization
    return model.Forecast("expected", weeks, {}, {}, {}, {}, {"ai": [g * per_fte for g in gaps_fte]}, {})


def test_window_average_is_measured_from_the_need_week():
    fc = _unmet_forecast([0.1, 0.8, 0.8, 0.8, 0.8, 0, 0, 0])
    [t] = model.hiring_triggers(fc, as_of=MON)
    assert t.need_week == MON + timedelta(weeks=1)
    assert t.window_fte == pytest.approx(0.8)


def test_both_conditions_are_required():
    # three short weeks of four, but the average lands under 0.5
    assert model.hiring_triggers(_unmet_forecast([0.5, 0.5, 0.5, 0.4]), as_of=MON) == []
    # the average clears 0.5, but only two weeks are short on their own
    assert model.hiring_triggers(_unmet_forecast([1.5, 0.5, 0.0, 0.0]), as_of=MON) == []
    # both
    assert len(model.hiring_triggers(_unmet_forecast([0.5, 0.5, 0.5, 0.5]), as_of=MON)) == 1


def test_req_due_this_week_is_not_late_midweek():
    fc = _unmet_forecast([0] * 14 + [1.0] * 4)
    [t] = model.hiring_triggers(fc, as_of=MON + timedelta(days=2))   # Wednesday of the req week
    assert t.req_open_by == MON
    assert t.late is False


def test_sustained_gap_triggers_a_hire_with_lead_time():
    fc = _unmet_forecast([0, 0, 0.6, 0.6, 0.6, 0.6, 0.6, 0])
    [t] = model.hiring_triggers(fc, as_of=MON)
    assert t.need_week == MON + timedelta(weeks=2)
    assert t.req_open_by == t.need_week - timedelta(weeks=S.time_to_hire_weeks + S.ramp_weeks)
    assert t.late is True    # fourteen weeks of lead time against a gap two weeks out
    assert t.hire_productive == MON + timedelta(weeks=14)


def test_one_holiday_week_does_not_trigger_a_hire():
    fc = _unmet_forecast([0, 2.0, 0, 0, 0, 0, 0, 0])
    assert model.hiring_triggers(fc, as_of=MON) == []


def test_holiday_spike_plus_one_marginal_week_does_not_trigger():
    fc = _unmet_forecast([0, 0.55, 1.5, 0.3, 0.3, 0, 0, 0])
    assert model.hiring_triggers(fc, as_of=MON) == []


def test_gap_far_enough_out_is_not_late():
    fc = _unmet_forecast([0] * 20 + [1.0] * 4)
    [t] = model.hiring_triggers(fc, as_of=MON)
    assert t.late is False
    assert t.req_open_by == MON + timedelta(weeks=6)


def test_bench_and_mismatch_flag_idle_people_without_the_short_skill():
    team = [eng("a", skills=("sec",)), eng("b", skills=("ai",))]
    jobs = [job("x", skill="ai", hours=60, weeks=6)]
    fc = run(team, jobs, n=6)
    assert all("a" in names for names in model.on_bench(fc).values())
    mm = model.skill_mismatches(fc, team)
    assert mm and all(m.short_skill == "ai" and m.benched == ("a",) for m in mm)


def test_ramping_new_hire_fully_booked_is_not_on_the_bench():
    s = Settings(ramp_weeks=4, ramp_factor=0.5)
    team = [eng("new", start=MON)]
    fc = run(team, [job("x", hours=FULL / 2, weeks=4)], n=4, s=s)
    assert fc.engineer_utilization("new")[0] < s.bench_threshold   # low against raw hours...
    assert all(names == [] for names in model.on_bench(fc, s).values())   # ...but not idle


def test_team_utilization_ignores_people_not_working():
    team = [eng("a"), eng("b", start=MON + timedelta(weeks=4))]
    fc = run(team, [job("x", hours=28, weeks=2)], n=2)
    assert fc.team_utilization() == [pytest.approx(0.7), pytest.approx(0.7)]


# --- the CLI and the report -------------------------------------------------------

def _write_data(tmp_path, engagements, extra_skills=()):
    import json
    team = {"as_of": "2027-01-04", "skills": {"sec": "Security", **{k: k for k in extra_skills}},
            "holidays": {}, "engineers": [{"id": "a", "name": "Ann", "region": "US", "skills": ["sec"]}]}
    (tmp_path / "team.json").write_text(json.dumps(team))
    (tmp_path / "pipeline.json").write_text(json.dumps({"engagements": engagements}))
    return tmp_path


def test_report_renders_the_data_it_was_given(tmp_path):
    import forecast, render_html
    data = _write_data(tmp_path, [
        {"id": "x", "customer": "Xylo Corp", "skill": "sec", "stage": "closed", "start": "2027-01-04",
         "weeks": 4, "hours_per_week": 20},
        {"id": "y", "customer": "Yarrow Ltd", "skill": "sec", "stage": "commit", "start": "2027-01-04",
         "weeks": 4, "hours_per_week": 10}])
    page = render_html.render(forecast.build(data, None, 6, S))
    assert "2 engagements" in page and "Xylo Corp" in page and "Yarrow Ltd" in page
    assert "Harbor Mutual" not in page


def test_unlisted_skill_is_rejected(tmp_path):
    import forecast
    data = _write_data(tmp_path, [{"id": "x", "customer": "X", "skill": "ai", "stage": "closed",
                                   "start": "2027-01-04", "weeks": 4, "hours_per_week": 20}])
    with pytest.raises(SystemExit, match="ai"):
        forecast.load(data)


def test_too_few_weeks_is_rejected():
    import forecast
    with pytest.raises(SystemExit, match="at least 4"):
        forecast.build(Path(__file__).resolve().parents[1] / "data", None, 1, S)


# --- the shipped data ---------------------------------------------------------

def test_shipped_forecast_builds_and_is_sane():
    import forecast
    result = forecast.build(Path(__file__).resolve().parents[1] / "data", None, 26, S)
    assert len(result["weeks"]) == 26
    for name, util in result["utilization"].items():
        assert all(0.0 <= u <= S.planning_ceiling + 1e-9 for u in util), name
    booked, expected, stretch = (result["utilization"][k] for k in ("booked", "expected", "stretch"))
    assert all(b <= e + 1e-9 <= st + 2e-9 for b, e, st in zip(booked, expected, stretch))
