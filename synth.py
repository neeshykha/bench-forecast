"""Write the synthetic team and pipeline to data/.

Every name and customer here is made up. The shape is not: a nine-person PS
engineering team split across the US and Ireland, a new hire landing mid-quarter,
a parental leave, a transfer out, holiday weeks, and a pipeline where most of
next quarter is still unsigned.

    python synth.py
"""

from __future__ import annotations

import json
from pathlib import Path

DATA = Path(__file__).parent / "data"

AS_OF = "2026-10-19"

SKILLS = {
    "security-automation": "Security automation",
    "it-ops": "IT ops",
    "cloud-identity": "Cloud & identity",
    "ai-agents": "AI agents",
}

HOLIDAYS = {
    "US": ["2026-11-26", "2026-11-27", "2026-12-25", "2027-01-01", "2027-01-18", "2027-02-15"],
    "IE": ["2026-12-25", "2026-12-28", "2027-01-01", "2027-02-01", "2027-03-17", "2027-03-29"],
}

TEAM = [
    {"id": "maya", "name": "Maya Chen", "region": "US",
     "skills": ["security-automation", "cloud-identity"], "pto": ["2026-12-21"]},
    {"id": "luis", "name": "Luis Ortega", "region": "US",
     "skills": ["security-automation", "it-ops"], "pto": ["2026-12-28"]},
    {"id": "priya", "name": "Priya Nair", "region": "US",
     "skills": ["it-ops", "ai-agents"], "pto": ["2027-03-15"]},
    {"id": "sam", "name": "Sam Whitfield", "region": "US",
     "skills": ["cloud-identity"], "pto": ["2026-11-23"]},
    {"id": "dana", "name": "Dana Brooks", "region": "US",
     "skills": ["security-automation"],
     # twelve weeks of parental leave
     "pto": [f"2027-{m:02d}-{d:02d}" for m, d in
             [(1, 4), (1, 11), (1, 18), (1, 25), (2, 1), (2, 8), (2, 15), (2, 22),
              (3, 1), (3, 8), (3, 15), (3, 22)]]},
    {"id": "jordan", "name": "Jordan Ellis", "region": "US",
     "skills": ["it-ops", "ai-agents"], "start": "2026-11-30"},
    {"id": "aoife", "name": "Aoife Byrne", "region": "IE",
     "skills": ["security-automation", "ai-agents"], "pto": ["2026-12-21", "2026-12-28"]},
    {"id": "cian", "name": "Cian Murphy", "region": "IE",
     "skills": ["it-ops", "cloud-identity"], "pto": ["2026-12-28"]},
    {"id": "niamh", "name": "Niamh Doyle", "region": "IE",
     "skills": ["security-automation"], "end": "2027-02-26"},
]

PIPELINE = [
    # signed and in flight
    {"id": "harbor", "customer": "Harbor Mutual", "skill": "security-automation", "stage": "closed",
     "start": "2026-10-05", "weeks": 14, "hours_per_week": 35, "region": "US"},
    {"id": "kestrel", "customer": "Kestrel Logistics", "skill": "it-ops", "stage": "closed",
     "start": "2026-09-28", "weeks": 12, "hours_per_week": 20},
    {"id": "brightwater", "customer": "Brightwater Energy", "skill": "cloud-identity", "stage": "closed",
     "start": "2026-10-12", "weeks": 16, "hours_per_week": 25},
    {"id": "larkspur", "customer": "Larkspur Health", "skill": "security-automation", "stage": "closed",
     "start": "2026-10-19", "weeks": 10, "hours_per_week": 30, "region": "US"},
    {"id": "meridian", "customer": "Meridian Retail", "skill": "security-automation", "stage": "closed",
     "start": "2026-09-21", "weeks": 12, "hours_per_week": 30, "region": "IE"},
    {"id": "fenwick", "customer": "Fenwick Bank", "skill": "cloud-identity", "stage": "closed",
     "start": "2026-11-02", "weeks": 20, "hours_per_week": 20, "region": "IE"},
    {"id": "oakline", "customer": "Oakline Media", "skill": "ai-agents", "stage": "closed",
     "start": "2026-10-19", "weeks": 8, "hours_per_week": 25},
    {"id": "tidewater", "customer": "Tidewater Insurance", "skill": "it-ops", "stage": "closed",
     "start": "2026-11-09", "weeks": 14, "hours_per_week": 20},
    {"id": "quarry", "customer": "Quarry Systems", "skill": "ai-agents", "stage": "closed",
     "start": "2026-09-14", "weeks": 16, "hours_per_week": 30},
    {"id": "lumen", "customer": "Lumen Payments", "skill": "security-automation", "stage": "closed",
     "start": "2026-11-16", "weeks": 18, "hours_per_week": 25},
    {"id": "vantage", "customer": "Vantage Freight", "skill": "security-automation", "stage": "closed",
     "start": "2026-10-19", "weeks": 6, "hours_per_week": 20},
    # commit
    {"id": "cobalt", "customer": "Cobalt Freight", "skill": "security-automation", "stage": "commit",
     "start": "2027-01-04", "weeks": 16, "hours_per_week": 35},
    {"id": "granite", "customer": "Granite Pharma", "skill": "ai-agents", "stage": "commit",
     "start": "2027-01-11", "weeks": 20, "hours_per_week": 40},
    {"id": "northfield", "customer": "Northfield Utilities", "skill": "it-ops", "stage": "commit",
     "start": "2026-12-07", "weeks": 12, "hours_per_week": 25},
    {"id": "saltmarsh", "customer": "Saltmarsh Labs", "skill": "security-automation", "stage": "commit",
     "start": "2027-01-18", "weeks": 14, "hours_per_week": 30, "region": "IE"},
    {"id": "orchard", "customer": "Orchard Health", "skill": "cloud-identity", "stage": "commit",
     "start": "2027-02-01", "weeks": 16, "hours_per_week": 25},
    # best case
    {"id": "redcliff", "customer": "Redcliff Telecom", "skill": "ai-agents", "stage": "best_case",
     "start": "2027-02-01", "weeks": 16, "hours_per_week": 40},
    {"id": "ashgrove", "customer": "Ashgrove Bank", "skill": "cloud-identity", "stage": "best_case",
     "start": "2027-01-25", "weeks": 12, "hours_per_week": 25},
    {"id": "pinecrest", "customer": "Pinecrest Media", "skill": "security-automation", "stage": "best_case",
     "start": "2027-02-15", "weeks": 10, "hours_per_week": 30},
    {"id": "willow", "customer": "Willow Analytics", "skill": "ai-agents", "stage": "best_case",
     "start": "2027-03-01", "weeks": 12, "hours_per_week": 35},
    {"id": "summit", "customer": "Summit Outfitters", "skill": "ai-agents", "stage": "best_case",
     "start": "2027-02-15", "weeks": 14, "hours_per_week": 30},
    # early pipeline
    {"id": "stonebridge", "customer": "Stonebridge County", "skill": "security-automation", "stage": "pipeline",
     "start": "2027-03-08", "weeks": 16, "hours_per_week": 40},
    {"id": "marlow", "customer": "Marlow Health", "skill": "ai-agents", "stage": "pipeline",
     "start": "2027-03-15", "weeks": 12, "hours_per_week": 30},
    {"id": "elmstead", "customer": "Elmstead Retail", "skill": "it-ops", "stage": "pipeline",
     "start": "2027-02-22", "weeks": 10, "hours_per_week": 25},
]


def main() -> None:
    DATA.mkdir(exist_ok=True)
    team = {"as_of": AS_OF, "skills": SKILLS, "holidays": HOLIDAYS, "engineers": TEAM}
    (DATA / "team.json").write_text(json.dumps(team, indent=2) + "\n")
    (DATA / "pipeline.json").write_text(json.dumps({"engagements": PIPELINE}, indent=2) + "\n")
    print(f"wrote {len(TEAM)} engineers and {len(PIPELINE)} engagements to {DATA}/")


if __name__ == "__main__":
    main()
