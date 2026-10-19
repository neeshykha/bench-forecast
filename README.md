# bench-forecast

Most services capacity plans answer next week. The expensive question is who's on
the bench in March, and whether the engineer you need for February meant opening a
req last month.

This forecasts a professional services engineering team 26 weeks out. Feed it the
team and a pipeline of engagements, each weighted by deal stage, and it says three
things:

- **Who's on the bench when**, engineer by engineer, week by week.
- **Where the skill mix breaks**: weeks when one skill is short while people without
  it sit idle.
- **When each req has to open**, counting the weeks it takes to hire someone and the
  weeks before they carry a full load.

Standard library Python, no dependencies, synthetic data. Every person and customer
in `data/` is made up.

→ [`results/report.html`](results/report.html) (download it; GitHub won't render it) ·
[`results/summary.txt`](results/summary.txt)

---

## What it says about the sample team

Nine engineers, six in the US and three in Ireland, as of October 19, 2026. A new
hire lands November 30, one engineer starts twelve weeks of parental leave in
January, and another transfers out at the end of February. The pipeline holds 24
engagements, and most of next quarter isn't signed yet.

- **Utilization holds near the 70% target** for the next 13 weeks, with a soft
  stretch in early January (53% the week of January 11) as fall engagements wrap
  before the commits start.
- **AI agents is the gap.** From February 15 the team is short 0.7 engineers on
  average, and 2 in the week of March 15, when one of the three people with the
  skill is out. Eight weeks to hire plus six to ramp means **the req opens by
  November 9**, three weeks from the as-of date. A plan built a quarter at a time
  finds this gap in January, and a req opened then doesn't produce a fully ramped
  engineer until mid-April, two months into the gap.
- **Signed work alone says the opposite.** Booked utilization drops under 40% the
  first week of January, to about a fifth by February, and to zero after March 15.
  Planning on signed work says the team is idle by spring; planning on the stretch
  case puts it at the 85% ceiling from mid-February through mid-March. The expected
  line runs between them, and the band shows how far apart they are.

---

## How it works

**Supply.** Each engineer works 40 hours a week minus their region's holidays and
their PTO, from their start date to their last day. Planning stops at 85% of that;
the rest is internal work, enablement, and presales help. A new hire plans at half
capacity for six weeks.

**Demand.** Each engagement wants so many hours a week of one skill for so many
weeks. Three scenarios read the same pipeline:

| Scenario | Signed | Commit | Best case | Pipeline |
|---|---|---|---|---|
| Booked | 100% | 0 | 0 | 0 |
| Expected | 100% | 80% | 50% | 20% |
| Stretch | 100% | 100% | 100% | 0 |

**Allocation.** Signed work is staffed first, then commit, then the rest. Each
engagement gets one lead for its whole run: someone with room, working the week it
kicks off, able to carry at least 90% of it, and in the customer's region if it has
one, in that order. When the lead's week is full, the overflow goes to whoever else
has the skill and the most room that week. Whatever's left is unstaffed demand for
that skill, and an engagement nobody has room for gets no lead and says so.

**Signals.** An engineer is on the bench in a week when less than half of their
plannable hours are assigned. A skill triggers a hire when, over any 4 weeks, it's
short half an engineer on average and that short in at least 3 of them. The req
date works backward from the first short week.

---

## The judgment calls

**One lead per engagement.** The cheapest-looking schedule moves people between
customers every week to fill holes. Each of those moves is a handoff the customer
pays for in context, so the model keeps a lead on an engagement and only spills
overflow. The lead has to have room and be working the week it kicks off, then
has to be able to carry nearly all of it, and only then does the customer's region
break the tie. An early version picked whoever had the most room across the whole
run, which made a new hire the lead on a signed engagement that started three weeks
before he did. A later one named a lead who carried none of the hours; now an
engagement nobody can take shows up as unstaffed, with the reason.

**A holiday week never hires anyone.** Demand doesn't pause for Thanksgiving, so
holiday weeks always look short. The first version averaged the gap over four weeks;
a test showed that one 2-engineer holiday spike averages to exactly the threshold.
Requiring half the window to be short on its own let a holiday plus one marginal week
through, and that put a false "too late to hire" on security automation in November.
The average and three of four short weeks, together, is the rule that held.

**The bench is measured against what we'd plan, not raw hours.** A new hire at half
capacity who's fully booked bills under half their hours. Against raw hours that
reads as idle; against plannable hours it reads as ramping, which is what it is.

**Work back from when the work needs a ramped person.** The gap date isn't the
decision date. The decision date is the gap minus hiring and ramp, and for this team
that's 14 weeks, a full quarter earlier than the gap shows up.

---

## Run it

```bash
python3 synth.py        # rewrites data/ (already committed)
python3 forecast.py     # writes results/forecast.json, summary.txt, report.html
python3 forecast.py --weeks 39 --as-of 2026-11-02
```

Tests:

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest
```

Every number the model uses lives in `Settings` in [`model.py`](model.py): target
utilization, planning ceiling, bench threshold, ramp, time to hire, and the trigger
window.

---

## What it doesn't do yet

- **Skills are yes or no.** Real teams have a primary skill and two they can cover
  in a pinch at lower speed.
- **Stage weights are defaults.** They should come from the team's own win rates by
  stage, re-fit every quarter.
- **Partners aren't a supply line.** A services partner is how you cover a gap a
  hire can't reach in time, and the model should be able to say how much partner
  capacity closes it.
- **Allocation is greedy, not optimal.** Good enough to see the shape of a quarter,
  not to staff next Tuesday.
- **Demand ignores holidays**, so holiday weeks look tighter than they will be. The
  trigger rule absorbs it; the heatmap still shows it.

---

## Why I built it

I run technical support, where capacity means a shift schedule and a queue: I've
rebuilt a schedule through a constraint scheduler and watched monthly case volume
double on the same headcount. Services capacity is a different problem. The work
arrives as engagements with start dates and probabilities, and the hard part is
seeing a quarter or two ahead. I hadn't built a rolling services forecast before, so
I built one in the open.
