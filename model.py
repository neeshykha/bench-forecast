"""Rolling capacity model for a professional services engineering team.

Weekly buckets. Supply comes from engineers (hours, holidays, PTO, start and
end dates, ramp). Demand comes from a pipeline of engagements, each weighted by
its deal stage. Allocation keeps one engineer on an engagement for as long as
their week has room, because a mid-engagement handoff costs more than it saves.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta

STAGE_ORDER = ("closed", "commit", "best_case", "pipeline")
DEFAULT_PROBABILITY = {"closed": 1.0, "commit": 0.8, "best_case": 0.5, "pipeline": 0.2}

# Which stages count, and at what weight, in each scenario.
SCENARIOS = {
    "booked": {"closed": 1.0},
    "expected": None,  # every stage at its probability
    "stretch": {"closed": 1.0, "commit": 1.0, "best_case": 1.0},
}


@dataclass(frozen=True)
class Settings:
    hours_per_week: float = 40.0
    target_utilization: float = 0.70   # billable hours / available hours
    planning_ceiling: float = 0.85     # most of a week we'll ever plan as billable
    bench_threshold: float = 0.50      # below this utilization, an engineer is "on the bench"
    ramp_weeks: int = 6                # a new hire's first weeks...
    ramp_factor: float = 0.5           # ...at this share of normal billable capacity
    time_to_hire_weeks: int = 8        # req open to signed offer to start date
    shortfall_fte: float = 0.5         # unmet demand, averaged over the window, that counts as a real gap
    shortfall_weeks: int = 4           # rolling window...
    shortfall_share: float = 0.75      # ...and the share of its weeks that must be short on their own
    bench_weeks: int = 4               # consecutive low weeks before it's a bench problem
    bench_window_margin: float = 0.10  # ...where "low" means this far under target
    lead_cover_share: float = 0.9      # a lead who can carry this much of an engagement "covers" it
    mismatch_min_weeks: int = 2        # a skill-mix gap has to last this long to be worth a cross-train


@dataclass(frozen=True)
class Engineer:
    id: str
    name: str
    region: str
    skills: frozenset[str]
    start: date | None = None          # None = already on the team
    end: date | None = None            # last day, for attrition or a transfer
    pto: tuple[date, ...] = ()         # any day in a week marks that whole week off


@dataclass(frozen=True)
class Engagement:
    id: str
    customer: str
    skill: str
    stage: str
    start: date                        # Monday of the first week
    weeks: int
    hours_per_week: float
    region: str | None = None          # preferred delivery region, if the customer cares
    probability: float | None = None   # overrides the stage default

    def weight(self, scenario: str) -> float:
        rule = SCENARIOS[scenario]
        if rule is None:
            return self.probability if self.probability is not None else DEFAULT_PROBABILITY[self.stage]
        return rule.get(self.stage, 0.0)


@dataclass
class Forecast:
    scenario: str
    weeks: list[date]
    available: dict[str, list[float]]                  # engineer -> hours they're working
    capacity: dict[str, list[float]]                   # engineer -> billable hours we'd plan
    assigned: dict[str, list[float]]                   # engineer -> billable hours assigned
    demand: dict[str, list[float]]                     # skill -> hours wanted
    unmet: dict[str, list[float]]                      # skill -> hours nobody could take
    leads: dict[str, str | None]                       # engagement -> lead engineer
    by_engagement: dict[str, dict[str, list[float]]] = field(default_factory=dict)
    lead_notes: dict[str, str] = field(default_factory=dict)   # engagement -> why it has no lead

    def team_utilization(self) -> list[float]:
        out = []
        for i in range(len(self.weeks)):
            avail = sum(h[i] for h in self.available.values())
            used = sum(h[i] for h in self.assigned.values())
            out.append(used / avail if avail else 0.0)
        return out

    def engineer_utilization(self, eng_id: str) -> list[float]:
        return [u / a if a else 0.0 for u, a in zip(self.assigned[eng_id], self.available[eng_id])]

    def free_hours(self, eng_id: str) -> list[float]:
        return [max(c - u, 0.0) for c, u in zip(self.capacity[eng_id], self.assigned[eng_id])]


def monday(d: date) -> date:
    return d - timedelta(days=d.weekday())


def week_starts(start: date, n: int) -> list[date]:
    first = monday(start)
    return [first + timedelta(weeks=i) for i in range(n)]


def available_hours(eng: Engineer, weeks: list[date], holidays: dict[str, list[date]],
                    s: Settings) -> list[float]:
    """Hours an engineer is actually working each week, before any billable math.

    Only the weekdays they're on the team count, and only holidays on those days
    come off, so a Monday holiday doesn't cut the week of someone starting Wednesday.
    """
    off = {monday(d) for d in eng.pto}
    holiday = set(holidays.get(eng.region, []))
    out = []
    for wk in weeks:
        first = max(wk, eng.start) if eng.start else wk
        last = min(wk + timedelta(days=4), eng.end) if eng.end else wk + timedelta(days=4)
        if wk in off or first > last:
            out.append(0.0)
            continue
        days = [first + timedelta(days=k) for k in range((last - first).days + 1)]
        worked = sum(1 for d in days if d.weekday() < 5 and d not in holiday)
        out.append(worked * s.hours_per_week / 5)
    return out


def ramp_start(eng: Engineer) -> date | None:
    """The Monday of a new hire's first working week; a weekend start ramps from the next one."""
    if not eng.start:
        return None
    return monday(eng.start) + (timedelta(weeks=1) if eng.start.weekday() >= 5 else timedelta())


def billable_capacity(eng: Engineer, avail: list[float], weeks: list[date], s: Settings) -> list[float]:
    """Hours we'd plan as billable: the ceiling, cut further while a new hire ramps."""
    first = ramp_start(eng)
    out = []
    for wk, hrs in zip(weeks, avail):
        cap = hrs * s.planning_ceiling
        if first is not None and 0 <= (wk - first).days // 7 < s.ramp_weeks:
            cap *= s.ramp_factor
        out.append(cap)
    return out


def engagement_demand(eng: Engagement, weeks: list[date], scenario: str) -> list[float]:
    w = eng.weight(scenario)
    first = eng.start - timedelta(days=eng.start.weekday())
    span = {first + timedelta(weeks=k) for k in range(eng.weeks)}
    return [eng.hours_per_week * w if wk in span else 0.0 for wk in weeks]


def run(engineers: list[Engineer], engagements: list[Engagement], start: date, n_weeks: int,
        holidays: dict[str, list[date]], scenario: str = "expected",
        s: Settings | None = None) -> Forecast:
    s = s or Settings()
    weeks = week_starts(start, n_weeks)
    avail = {e.id: available_hours(e, weeks, holidays, s) for e in engineers}
    cap = {e.id: billable_capacity(e, avail[e.id], weeks, s) for e in engineers}
    assigned = {e.id: [0.0] * n_weeks for e in engineers}
    skills = sorted({g.skill for g in engagements} | {k for e in engineers for k in e.skills})
    demand = {k: [0.0] * n_weeks for k in skills}
    unmet = {k: [0.0] * n_weeks for k in skills}
    leads: dict[str, str | None] = {}
    by_eng: dict[str, dict[str, list[float]]] = {}

    def free(eid: str, i: int) -> float:
        return cap[eid][i] - assigned[eid][i]

    notes: dict[str, str] = {}
    ordered = sorted(engagements, key=lambda g: (STAGE_ORDER.index(g.stage), g.start, g.id))
    for g in ordered:
        need = engagement_demand(g, weeks, scenario)
        live = [i for i, h in enumerate(need) if h > 0]
        if not live:
            leads[g.id] = None
            notes[g.id] = "outside_horizon" if g.weight(scenario) > 0 else "not_in_scenario"
            continue
        for i in live:
            demand[g.skill][i] += need[i]
        pool = [e for e in engineers if g.skill in e.skills]

        def room(e: Engineer) -> float:
            return sum(min(max(free(e.id, i), 0.0), need[i]) for i in live)

        if not pool or max(room(e) for e in pool) <= 1e-9:
            leads[g.id] = None
            notes[g.id] = "no_skill" if not pool else "no_room"
            for i in live:
                unmet[g.skill][i] += need[i]
            continue

        total = sum(need[i] for i in live)

        def lead_score(e: Engineer) -> tuple:
            # Someone with room at all, then someone working the week it kicks off,
            # then someone who can carry nearly all of it, then the customer's region,
            # then the most room. A lead who joins three weeks in isn't the lead.
            r = room(e)
            return (r > 1e-9, cap[e.id][live[0]] > 0, r >= s.lead_cover_share * total,
                    bool(g.region) and e.region == g.region, r, -len(e.skills), e.id)

        lead = max(pool, key=lead_score)
        leads[g.id] = lead.id
        split = by_eng.setdefault(g.id, {})
        for i in live:
            left = need[i]
            order = [lead] + sorted((e for e in pool if e.id != lead.id),
                                    key=lambda e: (-free(e.id, i), e.id))
            for e in order:
                take = min(left, max(free(e.id, i), 0.0))
                if take <= 1e-9:
                    continue
                assigned[e.id][i] += take
                split.setdefault(e.id, [0.0] * n_weeks)[i] += take
                left -= take
                if left <= 1e-9:
                    break
            if left > 1e-9:
                unmet[g.skill][i] += left

    return Forecast(scenario, weeks, avail, cap, assigned, demand, unmet, leads, by_eng, notes)


@dataclass(frozen=True)
class HiringTrigger:
    skill: str
    need_week: date          # first short week of the first window that clears both bars
    window_fte: float        # average shortfall over the shortfall_weeks starting at need_week
    peak_fte: float          # worst single week from need_week on
    req_open_by: date        # need_week minus time to hire and ramp
    late: bool               # req_open_by is already behind the as-of date
    hire_productive: date    # if the req opened on the as-of date, when the hire carries full load


@dataclass(frozen=True)
class BenchWindow:
    first_week: date
    last_week: date
    low_utilization: float


def fte(hours: float, s: Settings) -> float:
    """Engineers needed to cover these hours at target utilization."""
    return hours / (s.hours_per_week * s.target_utilization)


def hiring_triggers(fc: Forecast, as_of: date, s: Settings | None = None) -> list[HiringTrigger]:
    """One trigger per skill: the first window where the gap is real.

    Real means two things over shortfall_weeks: the average gap is at least
    shortfall_fte, and at least shortfall_share of those weeks are that short on
    their own. The req date works backward from when the work needs a fully
    ramped person, which is the part a quarter-at-a-time plan misses.
    """
    s = s or Settings()
    lead_time = timedelta(weeks=s.time_to_hire_weeks + s.ramp_weeks)
    w = s.shortfall_weeks
    out = []
    for skill, hours in fc.unmet.items():
        gaps = [fte(h, s) for h in hours]
        for i in range(len(gaps) - w + 1):
            window = gaps[i:i + w]
            short = [j for j, g in enumerate(window) if g >= s.shortfall_fte]
            # The average alone lets one huge holiday week stand in for a month of gap,
            # and half the window still lets a holiday plus one marginal week through.
            if sum(window) / w >= s.shortfall_fte and len(short) >= s.shortfall_share * w:
                first = i + short[0]
                need = fc.weeks[first]
                req = need - lead_time
                ahead = gaps[first:first + w]
                out.append(HiringTrigger(skill, need, round(sum(ahead) / len(ahead), 2),
                                         round(max(gaps[first:]), 2), req,
                                         req < monday(as_of), as_of + lead_time))
                break
    return sorted(out, key=lambda t: t.need_week)


def bench_windows(fc: Forecast, s: Settings | None = None) -> list[BenchWindow]:
    """Stretches where the whole team sits under target long enough to matter."""
    s = s or Settings()
    util = fc.team_utilization()
    low = [u < s.target_utilization - s.bench_window_margin for u in util]
    out, run_start = [], None
    for i, flag in enumerate(low + [False]):
        if flag and run_start is None:
            run_start = i
        elif not flag and run_start is not None:
            if i - run_start >= s.bench_weeks:
                out.append(BenchWindow(fc.weeks[run_start], fc.weeks[i - 1],
                                       round(min(util[run_start:i]), 3)))
            run_start = None
    return out


@dataclass(frozen=True)
class SkillMismatch:
    week: date
    short_skill: str
    short_fte: float
    benched: tuple[str, ...]   # people with free time who lack that skill


def skill_mismatches(fc: Forecast, engineers: list[Engineer],
                     s: Settings | None = None) -> list[SkillMismatch]:
    """Weeks where one skill is short while people without it sit on the bench.

    A hire fixes the shortage; cross-training one of these people fixes it and the bench.
    """
    s = s or Settings()
    skills_of = {e.id: e.skills for e in engineers}
    benched = on_bench(fc, s)
    out = []
    for i, wk in enumerate(fc.weeks):
        for skill, hours in fc.unmet.items():
            gap = fte(hours[i], s)
            idle = tuple(eid for eid in benched[wk] if skill not in skills_of[eid])
            if gap >= s.shortfall_fte and idle:
                out.append(SkillMismatch(wk, skill, round(gap, 2), idle))
    return out


def on_bench(fc: Forecast, s: Settings | None = None) -> dict[date, list[str]]:
    """Engineers working that week with less than half of their plannable hours assigned.

    Measured against plannable capacity, not raw hours, so a ramping new hire
    who is as booked as we'd ever book them doesn't read as idle.
    """
    s = s or Settings()
    out: dict[date, list[str]] = {}
    for i, wk in enumerate(fc.weeks):
        out[wk] = sorted(eid for eid in fc.assigned
                         if fc.capacity[eid][i] > 0
                         and fc.assigned[eid][i] < s.bench_threshold * fc.capacity[eid][i])
    return out
