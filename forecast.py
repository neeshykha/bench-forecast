"""Run the forecast and write results/.

    python forecast.py                  # 26 weeks from the as-of date in data/team.json
    python forecast.py --weeks 39       # further out
    python forecast.py --as-of 2026-11-02
"""

from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

import model
from model import Engagement, Engineer, Settings

ROOT = Path(__file__).parent


def _d(s: str | None) -> date | None:
    return date.fromisoformat(s) if s else None


def load(data_dir: Path) -> tuple[dict, list[Engineer], list[Engagement]]:
    team = json.loads((data_dir / "team.json").read_text())
    pipe = json.loads((data_dir / "pipeline.json").read_text())
    engineers = [
        Engineer(id=e["id"], name=e["name"], region=e["region"], skills=frozenset(e["skills"]),
                 start=_d(e.get("start")), end=_d(e.get("end")),
                 pto=tuple(date.fromisoformat(p) for p in e.get("pto", [])))
        for e in team["engineers"]
    ]
    engagements = [
        Engagement(id=g["id"], customer=g["customer"], skill=g["skill"], stage=g["stage"],
                   start=date.fromisoformat(g["start"]), weeks=g["weeks"],
                   hours_per_week=g["hours_per_week"], region=g.get("region"),
                   probability=g.get("probability"))
        for g in pipe["engagements"]
    ]
    bad = sorted({g.stage for g in engagements} - set(model.STAGE_ORDER))
    if bad:
        raise SystemExit(f"unknown stage(s) in pipeline.json: {bad}")
    used = {g.skill for g in engagements} | {k for e in engineers for k in e.skills}
    unlisted = sorted(used - set(team["skills"]))
    if unlisted:
        raise SystemExit(f"skill(s) used but not listed under \"skills\" in team.json: {unlisted}")
    return team, engineers, engagements


def build(data_dir: Path, as_of: date | None, n_weeks: int, s: Settings) -> dict:
    if n_weeks < s.shortfall_weeks:
        raise SystemExit(f"--weeks must be at least {s.shortfall_weeks}, the hiring trigger's window")
    team, engineers, engagements = load(data_dir)
    as_of = as_of or date.fromisoformat(team["as_of"])
    holidays = {r: [date.fromisoformat(d) for d in days] for r, days in team["holidays"].items()}
    runs = {name: model.run(engineers, engagements, as_of, n_weeks, holidays, name, s)
            for name in model.SCENARIOS}
    exp = runs["expected"]
    triggers = model.hiring_triggers(exp, as_of, s)
    bench = model.bench_windows(exp, s)
    benched = model.on_bench(exp, s)
    mismatches = model.skill_mismatches(exp, engineers, s)
    weeks = [w.isoformat() for w in exp.weeks]
    names = {e.id: e.name for e in engineers}
    customers = {g.id: g.customer for g in engagements}

    def top_engagement(eid: str, i: int) -> str | None:
        best, hours = None, 0.0
        for gid, split in exp.by_engagement.items():
            h = split.get(eid, [0.0] * n_weeks)[i]
            if h > hours:
                best, hours = gid, h
        return customers.get(best) if best else None

    return {
        "as_of": as_of.isoformat(),
        "weeks": weeks,
        "settings": s.__dict__,
        "skills": team["skills"],
        "engineers": [{"id": e.id, "name": e.name, "region": e.region, "skills": sorted(e.skills),
                       "start": e.start.isoformat() if e.start else None,
                       "end": e.end.isoformat() if e.end else None} for e in engineers],
        "utilization": {name: [round(u, 4) for u in fc.team_utilization()] for name, fc in runs.items()},
        "team_available": [round(sum(h[i] for h in exp.available.values()), 1) for i in range(n_weeks)],
        "team_assigned": {name: [round(sum(h[i] for h in fc.assigned.values()), 1) for i in range(n_weeks)]
                          for name, fc in runs.items()},
        "engineer_weeks": {
            e.id: [{"available": round(exp.available[e.id][i], 1),
                    "assigned": round(exp.assigned[e.id][i], 1),
                    "free": round(exp.free_hours(e.id)[i], 1),
                    "top": top_engagement(e.id, i)} for i in range(n_weeks)]
            for e in engineers
        },
        "demand": {k: [round(h, 1) for h in v] for k, v in exp.demand.items()},
        "unmet": {name: {k: [round(h, 1) for h in v] for k, v in fc.unmet.items()} for name, fc in runs.items()},
        "engagements": [{"id": g.id, "customer": g.customer, "skill": g.skill, "stage": g.stage,
                         "start": g.start.isoformat(), "weeks": g.weeks, "hours_per_week": g.hours_per_week,
                         "region": g.region,
                         "lead": names.get(exp.leads.get(g.id)) if exp.leads.get(g.id) else None,
                         "lead_note": exp.lead_notes.get(g.id)} for g in engagements],
        "on_bench": {w.isoformat(): [names[e] for e in ids] for w, ids in benched.items()},
        "triggers": [{"skill": t.skill, "need_week": t.need_week.isoformat(), "window_fte": t.window_fte,
                      "peak_fte": t.peak_fte, "req_open_by": t.req_open_by.isoformat(), "late": t.late,
                      "hire_productive": t.hire_productive.isoformat()} for t in triggers],
        "mismatches": [{"week": m.week.isoformat(), "skill": m.short_skill, "short_fte": m.short_fte,
                        "benched": [names[e] for e in m.benched]} for m in mismatches],
        "bench_windows": [{"first_week": b.first_week.isoformat(), "last_week": b.last_week.isoformat(),
                           "low_utilization": b.low_utilization} for b in bench],
    }


def mismatch_summary(result: dict) -> list[tuple[str, int, list[tuple[str, int]]]]:
    """Per short skill: how many weeks, and who sat idle in them, most weeks first.

    A single holiday week of mismatch is noise, so it takes mismatch_min_weeks to show up.
    """
    min_weeks = result["settings"]["mismatch_min_weeks"]
    by_skill: dict[str, dict] = {}
    for m in result["mismatches"]:
        entry = by_skill.setdefault(m["skill"], {"weeks": 0, "idle": {}})
        entry["weeks"] += 1
        for name in m["benched"]:
            entry["idle"][name] = entry["idle"].get(name, 0) + 1
    out = []
    for skill, e in sorted(by_skill.items(), key=lambda kv: -kv[1]["weeks"]):
        if e["weeks"] < min_weeks:
            continue
        out.append((skill, e["weeks"], sorted(e["idle"].items(), key=lambda kv: (-kv[1], kv[0]))))
    return out


def summary(result: dict) -> str:
    u = result["utilization"]["expected"]
    n = len(u)
    near, far = u[: min(13, n)], u
    lines = [
        f"As of {result['as_of']}, {n} weeks out, expected scenario:",
        f"  utilization: next 13 weeks {sum(near) / len(near):.0%}, full horizon {sum(far) / n:.0%} "
        f"(target {result['settings']['target_utilization']:.0%})",
    ]
    low_i = min(range(n), key=lambda i: u[i])
    lines.append(f"  lowest week: {result['weeks'][low_i]} at {u[low_i]:.0%}, "
                 f"on the bench: {', '.join(result['on_bench'][result['weeks'][low_i]]) or 'nobody'}")
    for b in result["bench_windows"]:
        lines.append(f"  bench window: {b['first_week']} to {b['last_week']}, as low as {b['low_utilization']:.0%}")
    for skill, weeks, idle in mismatch_summary(result):
        label = result["skills"].get(skill, skill)
        who = ", ".join(f"{name} ({n})" for name, n in idle)
        lines.append(f"  skill mix: {label} short in {weeks} week(s) while others sit on the bench; "
                     f"cross-train candidates by weeks idle: {who}")
    if not result["triggers"]:
        lines.append("  no hiring trigger inside the horizon")
    for t in result["triggers"]:
        label = result["skills"].get(t["skill"], t["skill"])
        if t["late"]:
            when = (f"too late to hire for (a req opened today lands {t['hire_productive']}); "
                    "cover it with a partner or move start dates")
        else:
            when = f"open the req by {t['req_open_by']}"
        lines.append(f"  gap: {label}, {t['window_fte']} FTE short on average from {t['need_week']} "
                     f"(peak {t['peak_fte']}); {when}")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=ROOT / "data")
    ap.add_argument("--out", type=Path, default=ROOT / "results")
    ap.add_argument("--as-of", type=date.fromisoformat, default=None)
    ap.add_argument("--weeks", type=int, default=26)
    ap.add_argument("--no-html", action="store_true")
    args = ap.parse_args()

    result = build(args.data, args.as_of, args.weeks, Settings())
    args.out.mkdir(exist_ok=True)
    (args.out / "forecast.json").write_text(json.dumps(result, indent=1) + "\n")
    text = summary(result)
    (args.out / "summary.txt").write_text(text + "\n")
    if not args.no_html:
        import render_html
        (args.out / "report.html").write_text(render_html.render(result))
    print(text)


if __name__ == "__main__":
    main()
