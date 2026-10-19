"""One-page HTML report from results/forecast.json. Self-contained: inline SVG, no libraries."""

from __future__ import annotations

import html
import json
from datetime import date

import forecast

E = html.escape


def _md(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.strftime('%b')} {d.day}"


def _pct(x: float) -> str:
    return f"{round(x * 100)}%"


# --- chart 1: team utilization -------------------------------------------------

def utilization_chart(r: dict) -> str:
    W, H, L, R, T, B = 860, 270, 44, 96, 16, 30
    pw, ph = W - L - R, H - T - B
    n = len(r["weeks"])
    s = r["settings"]
    ymax = 1.0
    x = lambda i: L + pw * i / max(n - 1, 1)
    y = lambda v: T + ph * (1 - v / ymax)
    u = r["utilization"]
    band = [(x(i), y(u["stretch"][i])) for i in range(n)] + [(x(i), y(u["booked"][i])) for i in reversed(range(n))]
    band_d = "M" + " L".join(f"{a:.1f},{b:.1f}" for a, b in band) + " Z"
    line_d = "M" + " L".join(f"{x(i):.1f},{y(v):.1f}" for i, v in enumerate(u["expected"]))
    grid = "".join(
        f'<line x1="{L}" x2="{L + pw}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="grid"/>'
        f'<text x="{L - 8}" y="{y(v) + 4:.1f}" class="tick" text-anchor="end">{_pct(v)}</text>'
        for v in (0, 0.25, 0.5, 0.75, 1.0))
    refs = "".join(
        f'<line x1="{L}" x2="{L + pw}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="ref"/>'
        f'<text x="{L + pw + 8}" y="{y(v) + 4:.1f}" class="reflabel">{label} {_pct(v)}</text>'
        for v, label in ((s["target_utilization"], "Target"), (s["planning_ceiling"], "Ceiling")))
    xt = "".join(
        f'<text x="{x(i):.1f}" y="{H - 8}" class="tick" text-anchor="middle">{_md(r["weeks"][i])}</text>'
        for i in range(0, n, 4))
    last = n - 1
    end_label = (f'<circle cx="{x(last):.1f}" cy="{y(u["expected"][last]):.1f}" r="4" class="dot"/>'
                 f'<text x="{x(last) + 8:.1f}" y="{y(u["expected"][last]) - 8:.1f}" class="endlabel">'
                 f'Expected {_pct(u["expected"][last])}</text>')
    return f"""
<svg viewBox="0 0 {W} {H}" class="chart" role="img" aria-labelledby="u-title" id="util">
  {grid}
  <path d="{band_d}" class="band"/>
  {refs}
  <path d="{line_d}" class="line"/>
  {end_label}
  {xt}
  <line id="u-cross" class="cross" y1="{T}" y2="{T + ph}" x1="0" x2="0" visibility="hidden"/>
  <rect x="{L}" y="{T}" width="{pw}" height="{ph}" fill="transparent" id="u-hit"
        data-left="{L}" data-width="{pw}" data-n="{n}" tabindex="0"
        aria-label="Weekly utilization; arrow keys move between weeks"/>
</svg>"""


# --- chart 2: bench heatmap ----------------------------------------------------

BINS = [(0, 2), (2, 8), (8, 14), (14, 20), (20, 27), (27, 1e9)]
BIN_LABELS = ["0–2", "2–8", "8–14", "14–20", "20–27", "27+"]


def _bin(free: float) -> int:
    for i, (lo, hi) in enumerate(BINS):
        if lo <= free < hi:
            return i
    return len(BINS) - 1


def bench_heatmap(r: dict) -> str:
    n = len(r["weeks"])
    cw, ch, gap, lw, top = 26, 26, 2, 214, 22
    W = lw + n * cw + 8
    H = top + len(r["engineers"]) * ch + 8
    rows = []
    for k, e in enumerate(r["engineers"]):
        yy = top + k * ch
        tags = " · ".join(r["skills"].get(sk, sk) for sk in e["skills"])
        rows.append(f'<text x="0" y="{yy + 11}" class="rowname">{E(e["name"])}'
                    f'<tspan class="rowregion"> {E(e["region"])}</tspan></text>'
                    f'<text x="0" y="{yy + 21}" class="rowskills">{E(tags)}</text>')
        for i, cell in enumerate(r["engineer_weeks"][e["id"]]):
            cls = "off" if cell["available"] == 0 else f"b{_bin(cell['free'])}"
            rows.append(f'<rect x="{lw + i * cw}" y="{yy}" width="{cw - gap}" height="{ch - gap}" rx="2" '
                        f'class="cell {cls}" data-e="{k}" data-w="{i}" tabindex="-1"/>')
    heads = "".join(f'<text x="{lw + i * cw + (cw - gap) / 2:.1f}" y="12" class="tick" text-anchor="middle">'
                    f'{_md(r["weeks"][i])}</text>' for i in range(0, n, 4))
    return f"""
<div class="scroll"><svg viewBox="0 0 {W} {H}" class="heat" id="heat" style="width:100%;min-width:{int(W * 0.75)}px;height:auto;display:block"
     role="img" aria-label="Free billable hours by engineer and week">{heads}{''.join(rows)}</svg></div>"""


# --- chart 3: unmet demand, small multiples -----------------------------------

def unmet_multiples(r: dict) -> str:
    s = r["settings"]
    per_fte = s["hours_per_week"] * s["target_utilization"]
    unmet = r["unmet"]["expected"]
    skills = [k for k in r["skills"] if k in unmet]
    n = len(r["weeks"])
    ymax = max(1.0, max(h / per_fte for k in skills for h in unmet[k]))
    ymax = float(int(ymax + 0.999))
    W, H, L, T, B = 400, 150, 30, 10, 22
    pw, ph = W - L - 8, H - T - B
    bw = min(12, pw / n - 2)
    out = []
    for k in skills:
        vals = [h / per_fte for h in unmet[k]]
        y = lambda v: T + ph * (1 - v / ymax)
        bars = []
        for i, v in enumerate(vals):
            if v <= 0.005:
                continue
            bx = L + i * pw / n + (pw / n - bw) / 2
            top_y, base = y(v), y(0)
            hgt = base - top_y
            r4 = min(4, hgt / 2, bw / 2)
            # rounded data-end, square at the baseline
            d = (f"M{bx:.1f},{base:.1f} V{top_y + r4:.1f} Q{bx:.1f},{top_y:.1f} {bx + r4:.1f},{top_y:.1f} "
                 f"H{bx + bw - r4:.1f} Q{bx + bw:.1f},{top_y:.1f} {bx + bw:.1f},{top_y + r4:.1f} V{base:.1f} Z")
            bars.append(f'<path d="{d}" class="bar" data-k="{k}" data-w="{i}" tabindex="-1"/>')
        thr = y(s["shortfall_fte"])
        ticks = "".join(f'<line x1="{L}" x2="{L + pw}" y1="{y(v):.1f}" y2="{y(v):.1f}" class="grid"/>'
                        f'<text x="{L - 6}" y="{y(v) + 4:.1f}" class="tick" text-anchor="end">{v:g}</text>'
                        for v in range(0, int(ymax) + 1))
        xt = "".join(f'<text x="{L + i * pw / n + pw / n / 2:.1f}" y="{H - 6}" class="tick" text-anchor="middle">'
                     f'{_md(r["weeks"][i])}</text>' for i in range(0, n, 8))
        peak = max(vals)
        note = f"peak {peak:.1f} FTE" if peak > 0.005 else "no gap"
        out.append(f"""
<figure class="mult">
  <figcaption><b>{E(r['skills'][k])}</b> <span>{note}</span></figcaption>
  <svg viewBox="0 0 {W} {H}" class="chart" role="img" aria-label="Unmet {E(r['skills'][k])} demand in FTE by week">
    {ticks}
    <line x1="{L}" x2="{L + pw}" y1="{thr:.1f}" y2="{thr:.1f}" class="ref"/>
    {''.join(bars)}
    {xt}
  </svg>
</figure>""")
    return '<div class="mults">' + "".join(out) + "</div>"


# --- page ----------------------------------------------------------------------

def _calls(r: dict) -> str:
    items = []
    for t in r["triggers"]:
        label = r["skills"].get(t["skill"], t["skill"])
        if t["late"]:
            icon, status = "critical", "Too late to hire for"
            body = (f"{E(label)} is short {t['window_fte']} FTE on average from {_md(t['need_week'])}. A req opened "
                    f"today carries full load by {_md(t['hire_productive'])}, after the gap starts. Cover it with "
                    f"a services partner or move start dates, and open the req anyway if the gap holds past then.")
        else:
            icon, status = "warning", f"Open the req by {_md(t['req_open_by'])}"
            body = (f"{E(label)} is short {t['window_fte']} FTE on average from {_md(t['need_week'])} "
                    f"(worst week {t['peak_fte']} FTE). With {r['settings']['time_to_hire_weeks']} weeks to hire and "
                    f"{r['settings']['ramp_weeks']} to ramp, that's the last date a new engineer is fully "
                    f"billable when the work lands.")
        items.append(f'<li class="call {icon}"><span class="badge"><svg viewBox="0 0 16 16" aria-hidden="true">'
                     f'<path d="M8 1.5 15 14H1z"/><rect x="7.2" y="5.5" width="1.6" height="4.6" class="glyph"/>'
                     f'<rect x="7.2" y="11.2" width="1.6" height="1.6" class="glyph"/></svg>{E(status)}</span>'
                     f'<p>{body}</p></li>')
    for skill, weeks, idle in forecast.mismatch_summary(r):
        label = r["skills"].get(skill, skill)
        leaving = {e["name"] for e in r["engineers"] if e["end"]}
        people = [(name, k) for name, k in idle if name not in leaving]
        if not people:
            continue
        who = ", ".join(f"{E(name)} ({k} wk)" for name, k in people[:3])
        items.append(f'<li class="call info"><span class="badge"><svg viewBox="0 0 16 16" aria-hidden="true">'
                     f'<circle cx="8" cy="8" r="6.5"/><rect x="7.2" y="7" width="1.6" height="5" class="glyph"/>'
                     f'<rect x="7.2" y="4" width="1.6" height="1.6" class="glyph"/></svg>Cross-train</span>'
                     f'<p>{E(label)} is short in {weeks} weeks while people without it sit on the bench. '
                     f'Most idle in those weeks: {who}. One of them picking up {E(label)} work closes part of the '
                     f'gap and the bench at once, which a hire alone doesn\'t.</p></li>')
    for b in r["bench_windows"]:
        items.append(f'<li class="call info"><span class="badge">Bench window</span><p>Team utilization stays under '
                     f'{_pct(r["settings"]["target_utilization"] - 0.10)} from {_md(b["first_week"])} to '
                     f'{_md(b["last_week"])}. Pull pipeline forward or schedule internal work there.</p></li>')
    if not items:
        items.append('<li class="call info"><p>No hiring trigger, skill gap, or bench window inside the horizon.</p></li>')
    return "<ul class=\"calls\">" + "".join(items) + "</ul>"


def _table(r: dict) -> str:
    u = r["utilization"]
    per_fte = r["settings"]["hours_per_week"] * r["settings"]["target_utilization"]
    skills = list(r["skills"])
    head = ("<tr><th>Week</th><th>Booked</th><th>Expected</th><th>Stretch</th><th>Available h</th>"
            + "".join(f"<th>Short: {E(r['skills'][k])} (FTE)</th>" for k in skills) + "<th>On the bench</th></tr>")
    rows = []
    for i, w in enumerate(r["weeks"]):
        short = "".join(f"<td>{r['unmet']['expected'][k][i] / per_fte:.1f}</td>" for k in skills)
        rows.append(f"<tr><td>{_md(w)}</td><td>{_pct(u['booked'][i])}</td><td>{_pct(u['expected'][i])}</td>"
                    f"<td>{_pct(u['stretch'][i])}</td><td>{r['team_available'][i]:g}</td>{short}"
                    f"<td>{E(', '.join(r['on_bench'][w])) or '–'}</td></tr>")
    return f'<div class="scroll"><table><thead>{head}</thead><tbody>{"".join(rows)}</tbody></table></div>'


NO_LEAD = {
    "outside_horizon": "Runs outside this horizon",
    "not_in_scenario": "Not in this scenario",
    "no_skill": "Nobody on the team has this skill",
    "no_room": "Nobody with the skill has room",
}


def _leads(r: dict) -> str:
    stage_name = {"closed": "Signed", "commit": "Commit", "best_case": "Best case", "pipeline": "Pipeline"}
    rows = []
    for g in sorted(r["engagements"], key=lambda g: (["closed", "commit", "best_case", "pipeline"].index(g["stage"]),
                                                     g["start"], g["id"])):
        lead = g["lead"] or NO_LEAD.get(g["lead_note"], "No lead")
        rows.append(f"<tr><td>{E(g['customer'])}</td><td>{stage_name[g['stage']]}</td>"
                    f"<td>{E(r['skills'].get(g['skill'], g['skill']))}</td><td>{_md(g['start'])}</td>"
                    f"<td>{g['weeks']}</td><td>{g['hours_per_week']}</td><td>{E(lead)}</td></tr>")
    return ('<div class="scroll"><table><thead><tr><th>Customer</th><th>Stage</th><th>Skill</th><th>Starts</th>'
            '<th>Weeks</th><th>Hours/wk</th><th>Lead (expected)</th></tr></thead><tbody>'
            + "".join(rows) + "</tbody></table></div>")


CSS = """
:root{color-scheme:light;--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;
--grid:#e1e0d9;--axis:#c3c2b7;--ring:rgba(11,11,11,.10);--s1:#2a78d6;--wash:rgba(42,120,214,.12);
--b0:#cde2fb;--b1:#9ec5f4;--b2:#6da7ec;--b3:#3987e5;--b4:#256abf;--b5:#104281;--off:#e9e8e2;
--warning:#fab219;--critical:#d03b3b;--info:#898781}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;
--ink:#f0efec;--ink2:#c3c2b7;--grid:#2c2c2a;--axis:#383835;--ring:rgba(255,255,255,.10);--s1:#3987e5;--wash:rgba(57,135,229,.16);
--b0:#0d366b;--b1:#104281;--b2:#1c5cab;--b3:#2a78d6;--b4:#5598e7;--b5:#9ec5f4;--off:#2a2a27}}
:root[data-theme="dark"]{color-scheme:dark;--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--grid:#2c2c2a;
--axis:#383835;--ring:rgba(255,255,255,.10);--s1:#3987e5;--wash:rgba(57,135,229,.16);--b0:#0d366b;--b1:#104281;
--b2:#1c5cab;--b3:#2a78d6;--b4:#5598e7;--b5:#9ec5f4;--off:#2a2a27}
*{box-sizing:border-box}
body{margin:0;background:var(--page);color:var(--ink);font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:940px;margin:0 auto;padding:28px 16px 48px}
h1{font-size:26px;margin:0 0 4px}h2{font-size:17px;margin:0 0 4px}
.sub{color:var(--ink2);margin:0 0 20px}.note{color:var(--ink2);font-size:13.5px;margin:2px 0 12px}
.card{background:var(--surface);border:1px solid var(--ring);border-radius:10px;padding:16px 18px;margin:0 0 16px}
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(190px,1fr));gap:10px;margin:0 0 16px}
.tile{background:var(--surface);border:1px solid var(--ring);border-radius:10px;padding:12px 14px}
.tile .label{color:var(--ink2);font-size:13px}.tile .value{font-size:28px;font-weight:600;line-height:1.2}
.tile .delta{color:var(--ink2);font-size:13px}
svg text{fill:var(--muted);font:11px system-ui,-apple-system,"Segoe UI",sans-serif}
.chart{width:100%;height:auto;display:block}
.grid{stroke:var(--grid);stroke-width:1}.ref{stroke:var(--axis);stroke-width:1}
.reflabel{fill:var(--ink2)}.band{fill:var(--wash)}
.line{fill:none;stroke:var(--s1);stroke-width:2;stroke-linejoin:round;stroke-linecap:round}
.dot{fill:var(--s1);stroke:var(--surface);stroke-width:2}.endlabel{fill:var(--ink);font-weight:600}
.cross{stroke:var(--axis);stroke-width:1}
.legend{display:flex;gap:16px;flex-wrap:wrap;font-size:13px;color:var(--ink2);margin:0 0 6px}
.legend i{display:inline-block;vertical-align:middle;margin-right:6px}
.key-line{width:16px;height:2px;background:var(--s1)}.key-band{width:14px;height:10px;background:var(--wash);border-radius:2px}
.key-ref{width:16px;height:1px;background:var(--axis)}
.scroll{overflow-x:auto}
.heat .rowname{fill:var(--ink);font-size:12px}.heat .rowregion{fill:var(--muted)}.heat .rowskills{font-size:10px}
.cell{stroke:none}.cell:hover,.cell:focus,.bar:hover,.bar:focus{opacity:.75;outline:none}
.b0{fill:var(--b0)}.b1{fill:var(--b1)}.b2{fill:var(--b2)}.b3{fill:var(--b3)}.b4{fill:var(--b4)}.b5{fill:var(--b5)}
.off{fill:var(--off)}
.swatches{display:flex;gap:2px;align-items:center;font-size:12.5px;color:var(--ink2);flex-wrap:wrap}
.swatches i{width:22px;height:12px;display:inline-block;border-radius:2px}
.swatches span{margin:0 8px 0 4px}
.mults{display:grid;grid-template-columns:repeat(auto-fit,minmax(300px,1fr));gap:8px 18px}
.mult{margin:0}.mult figcaption{font-size:13.5px;margin:0 0 2px}.mult figcaption span{color:var(--ink2);margin-left:6px}
.bar{fill:var(--s1)}
.calls{list-style:none;padding:0;margin:0}.call{display:flex;gap:12px;align-items:flex-start;padding:10px 0;border-top:1px solid var(--grid)}
.call:first-child{border-top:0}.call p{margin:0}
.badge{flex:0 0 auto;display:inline-flex;gap:6px;align-items:center;font-size:12.5px;font-weight:600;white-space:nowrap;
padding:2px 8px;border-radius:999px;border:1px solid var(--ring);min-width:150px}
.badge svg{width:14px;height:14px}.badge .glyph{fill:var(--surface)}
.warning .badge svg path{fill:var(--warning)}.critical .badge svg path{fill:var(--critical)}.info .badge svg circle{fill:var(--info)}
table{border-collapse:collapse;font-size:13px;width:100%}th,td{text-align:left;padding:5px 8px;border-bottom:1px solid var(--grid);white-space:nowrap}
th{color:var(--ink2);font-weight:600}td{font-variant-numeric:tabular-nums}
details summary{cursor:pointer;font-weight:600;margin:4px 0}
ul.assume{margin:6px 0 0;padding-left:18px}ul.assume li{margin:3px 0}
#tip{position:fixed;pointer-events:none;background:var(--surface);color:var(--ink);border:1px solid var(--ring);
border-radius:8px;padding:8px 10px;font-size:12.5px;box-shadow:0 4px 14px rgba(0,0,0,.12);display:none;z-index:5;max-width:260px}
#tip .v{font-weight:600}#tip .k{color:var(--ink2)}#tip .row{display:flex;gap:8px;justify-content:space-between}
footer{color:var(--muted);font-size:12.5px;margin-top:24px}
@media (max-width:560px){.badge{min-width:0}.call{flex-direction:column;gap:6px}}
"""

JS = """
const R = JSON.parse(document.getElementById('data').textContent);
const tip = document.getElementById('tip');
function md(iso){const d=new Date(iso+'T12:00:00');return d.toLocaleDateString('en-US',{month:'short',day:'numeric'});}
function pct(x){return Math.round(x*100)+'%';}
function show(ev, rows, title){
  tip.replaceChildren();
  const t=document.createElement('div');t.className='k';t.textContent=title;tip.appendChild(t);
  for(const [k,v] of rows){const r=document.createElement('div');r.className='row';
    const a=document.createElement('span');a.className='v';a.textContent=v;
    const b=document.createElement('span');b.className='k';b.textContent=k;r.append(a,b);tip.appendChild(r);}
  tip.style.display='block';
  const x=Math.min(ev.clientX+14, window.innerWidth-tip.offsetWidth-8), y=ev.clientY+14;
  tip.style.left=x+'px'; tip.style.top=(y+tip.offsetHeight>window.innerHeight? ev.clientY-tip.offsetHeight-10 : y)+'px';
}
function hide(){tip.style.display='none';}
// utilization crosshair
const hit=document.getElementById('u-hit'), cross=document.getElementById('u-cross'), svg=document.getElementById('util');
const L=+hit.dataset.left, PW=+hit.dataset.width, N=+hit.dataset.n;
function at(i, ev){
  const D=Math.max(N-1,1);const xx=L+PW*i/D; cross.setAttribute('x1',xx); cross.setAttribute('x2',xx); cross.setAttribute('visibility','visible');
  const u=R.utilization;
  show(ev,[['Expected',pct(u.expected[i])],['Booked',pct(u.booked[i])],['Stretch',pct(u.stretch[i])]],'Week of '+md(R.weeks[i]));
}
hit.addEventListener('pointermove',ev=>{const p=svg.createSVGPoint();p.x=ev.clientX;p.y=ev.clientY;
  const q=p.matrixTransform(svg.getScreenCTM().inverse());at(Math.max(0,Math.min(N-1,Math.round((q.x-L)/PW*Math.max(N-1,1)))),ev);});
hit.addEventListener('pointerleave',()=>{cross.setAttribute('visibility','hidden');hide();});
let ki=0;hit.addEventListener('keydown',ev=>{if(ev.key==='ArrowRight')ki=Math.min(N-1,ki+1);else if(ev.key==='ArrowLeft')ki=Math.max(0,ki-1);else return;
  const b=hit.getBoundingClientRect();at(ki,{clientX:b.left+b.width*ki/Math.max(N-1,1),clientY:b.top+20});ev.preventDefault();});
hit.addEventListener('blur',()=>{cross.setAttribute('visibility','hidden');hide();});
// heatmap
document.querySelectorAll('#heat .cell').forEach(c=>{
  const e=R.engineers[+c.dataset.e], w=+c.dataset.w, cell=R.engineer_weeks[e.id][w];
  const f=ev=>{ if(cell.available===0){show(ev,[['Off','PTO, holiday, or not on the team']],e.name+', week of '+md(R.weeks[w]));return;}
    const rows=[[cell.free+' h','free'],[cell.assigned+' of '+cell.available+' h','billed']];
    if(cell.top) rows.push([cell.top,'main engagement']);
    show(ev,rows,e.name+', week of '+md(R.weeks[w]));};
  c.addEventListener('pointermove',f);c.addEventListener('pointerleave',hide);
});
// unmet bars
const perFte=R.settings.hours_per_week*R.settings.target_utilization;
document.querySelectorAll('.bar').forEach(b=>{
  const k=b.dataset.k,w=+b.dataset.w,h=R.unmet.expected[k][w];
  b.addEventListener('pointermove',ev=>show(ev,[[(h/perFte).toFixed(2)+' FTE','short'],[h+' h','unstaffed']],R.skills[k]+', week of '+md(R.weeks[w])));
  b.addEventListener('pointerleave',hide);
});
"""


def render(r: dict) -> str:
    pipeline = r["engagements"]
    u = r["utilization"]["expected"]
    n = len(u)
    near = u[: min(13, n)]
    low_i = min(range(n), key=lambda i: u[i])
    first = r["triggers"][0] if r["triggers"] else None
    mm = forecast.mismatch_summary(r)
    s = r["settings"]
    tiles = [
        ("Expected utilization, next 13 weeks", _pct(sum(near) / len(near)), f"target {_pct(s['target_utilization'])}"),
        ("Softest week", _pct(u[low_i]), f"week of {_md(r['weeks'][low_i])}"),
        ("Next req to open",
         (_md(first["req_open_by"]) if not first["late"] else "Now") if first else "None",
         (f"{r['skills'].get(first['skill'], first['skill'])}, needed {_md(first['need_week'])}") if first else "no sustained gap"),
        ("Short while others idle", f"{mm[0][1]} wk" if mm else "0 wk",
         r["skills"].get(mm[0][0], mm[0][0]) if mm else "skill mix holds"),
    ]
    tiles_html = "".join(f'<div class="tile"><div class="label">{E(a)}</div><div class="value">{E(b)}</div>'
                         f'<div class="delta">{E(c)}</div></div>' for a, b, c in tiles)
    swatches = "".join(f'<i class="b{i}" style="background:var(--b{i})"></i><span>{lab}</span>'
                       for i, lab in enumerate(BIN_LABELS))
    data = json.dumps({k: r[k] for k in ("weeks", "utilization", "engineers", "engineer_weeks", "unmet",
                                         "skills", "settings")}).replace("</", "<\\/")
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Bench Forecast</title>
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>📅</text></svg>">
<style>{CSS}</style></head>
<body><main>
<h1>Bench forecast</h1>
<p class="sub">As of {_md(r['as_of'])}, {r['as_of'][:4]} · {n} weeks · {len(r['engineers'])} engineers ·
{len(pipeline)} engagements · synthetic data</p>

<div class="tiles">{tiles_html}</div>

<section class="card"><h2>What to do about it</h2>{_calls(r)}</section>

<section class="card">
<h2 id="u-title">Billable utilization, whole team</h2>
<p class="note">Billable hours over hours actually worked. The line weights every deal by its stage; the band runs
from signed work only up to every likely deal closing.</p>
<div class="legend"><span><i class="key-line"></i>Expected</span><span><i class="key-band"></i>Signed only to stretch</span>
<span><i class="key-ref"></i>Target and planning ceiling</span></div>
{utilization_chart(r)}
</section>

<section class="card">
<h2>Who's on the bench, week by week</h2>
<p class="note">Free billable hours per engineer in the expected case. Stronger color means more bench; hover a cell for the hours.</p>
<div class="swatches">{swatches}<i style="background:var(--off)"></i><span>off</span></div>
{bench_heatmap(r)}
</section>

<section class="card">
<h2>Unstaffed demand by skill</h2>
<p class="note">Engineers short at {_pct(s['target_utilization'])} utilization, expected case. The hairline is
{s['shortfall_fte']} FTE. A skill triggers a hire when, over any {s['shortfall_weeks']} weeks, it averages at least
that short and is that short in {round(s['shortfall_share'] * s['shortfall_weeks'])} of them.</p>
{unmet_multiples(r)}
</section>

<section class="card"><details><summary>Every week in a table</summary>{_table(r)}</details></section>
<section class="card"><details><summary>Who leads each engagement</summary>{_leads(r)}</details></section>

<section class="card"><h2>Assumptions</h2><ul class="assume">
<li>{s['hours_per_week']:g}-hour weeks, minus regional holidays and PTO. Planning stops at
{_pct(s['planning_ceiling'])} billable; the rest is internal work, enablement, and presales help.</li>
<li>Stage weights for the expected case: signed 100%, commit 80%, best case 50%, pipeline 20%.</li>
<li>One lead per engagement: someone with room, working the week it kicks off, able to carry at least
{_pct(s['lead_cover_share'])} of it, in the customer's region if it has one, in that order. Overflow goes to others
with the skill that week; anything left is unstaffed.</li>
<li>New hires ramp at {_pct(s['ramp_factor'])} for {s['ramp_weeks']} weeks. A req takes
{s['time_to_hire_weeks']} weeks to fill.</li>
<li>Demand doesn't pause for holidays, so holiday weeks look tighter than they will be. The trigger rule exists
so those weeks never hire anyone on their own.</li>
</ul></section>

<footer>Generated by forecast.py. Every person and customer here is made up.</footer>
</main>
<div id="tip" role="tooltip"></div>
<script type="application/json" id="data">{data}</script>
<script>{JS}</script>
</body></html>
"""
