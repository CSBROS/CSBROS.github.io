"""Build data.json for the 3-Month Basis Portfolio tracker.

Two periods, chained:
  * Pre-launch (Oct 19 -> Nov 16 close), old account: invested positions only.
    Benchmark twin: every dollar into a buy also goes into IWM in the same hour;
    every sale takes the same dollars back out.
  * Live record (from the Nov 16 close), MCP account: whole account, cash included.
    Benchmark twin: the starting account value goes into IWM at the launch close, and
    every later deposit goes into IWM at that day's close. Trades inside the account
    don't move the twin, so cash drag counts against the portfolio.

Usage: python3 build.py   (reads inputs.json and template.html next to it; writes data.json and ../index.html)
"""
import json, sys
from collections import defaultdict, deque

import os
HERE = os.path.dirname(os.path.abspath(__file__))
IN = json.load(open(os.path.join(HERE, "inputs.json")))
INCEPTION, LAUNCH, AS_OF, BENCH = IN["inception"], IN["launch"], IN["as_of"], IN["bench"]
DATES, CLOSE, BENCH_AT, NAMES = IN["dates"], IN["close"], IN["bench_at_fill"], IN["names"]
START_CASH, DEPOSITS = IN["start_cash"], [tuple(d) for d in IN["deposits"]]
fills = [dict(f) for f in IN["fills"]]
for f in fills:
    f["date"] = f["ts"][:10]; f["notional"] = f["qty"] * f["price"]; f["bench"] = BENCH_AT[f["ts"][:13]]
    f["flow"] = (f["notional"] + f["fee"]) if f["side"] == "buy" else -(f["notional"] - f["fee"])
fills.sort(key=lambda f: f["ts"])

holdings = defaultdict(float)
def mark(i): return sum(q * CLOSE[s][i] for s, q in holdings.items() if abs(q) > 1e-9)

series = []
tw_s = tw_b = 1.0           # chained since inception
prev_v = prev_b = 0.0
shadow = 0.0                # pre-launch twin, IWM shares
cash = START_CASH; twin = 0.0; A_L = None; tl_s = tl_b = 1.0
L = DATES.index(LAUNCH)
for i, d in enumerate(DATES):
    todays = [f for f in fills if f["date"] == d]
    if i <= L:   # pre-launch: invested positions only, flows = trades
        flow = 0.0
        for f in todays:
            holdings[f["symbol"]] += f["qty"] if f["side"] == "buy" else -f["qty"]
            shadow += f["flow"] / f["bench"]; flow += f["flow"]
        v = mark(i); b = shadow * CLOSE[BENCH][i]
        if prev_v + flow > 0: tw_s *= v / (prev_v + flow)
        if prev_b + flow > 0: tw_b *= b / (prev_b + flow)
        prev_v, prev_b = v, b
        row = dict(date=d, strategy=round(100 * tw_s, 3), bench=round(100 * tw_b, 3))
        if i == L:
            A_L = v + cash; twin = A_L / CLOSE[BENCH][i]; prev_a, prev_t = A_L, A_L
            pre = dict(twr=tw_s - 1, bench_twr=tw_b - 1, positions_value=v)
            row.update(strategy_live=100.0, bench_live=100.0, value=round(A_L, 2), bench_value=round(A_L, 2))
    else:        # live: whole account, flows = deposits only
        for f in todays:
            holdings[f["symbol"]] += f["qty"] if f["side"] == "buy" else -f["qty"]
            cash -= f["flow"]
        dep = sum(a for dd, a in DEPOSITS if dd == d); cash += dep
        twin += dep / CLOSE[BENCH][i]
        a = mark(i) + cash; t = twin * CLOSE[BENCH][i]
        r_s = a / (prev_a + dep); r_b = t / (prev_t + dep)
        tl_s *= r_s; tl_b *= r_b; tw_s *= r_s; tw_b *= r_b
        prev_a, prev_t = a, t
        row = dict(date=d, strategy=round(100 * tw_s, 3), bench=round(100 * tw_b, 3),
                   strategy_live=round(100 * tl_s, 3), bench_live=round(100 * tl_b, 3),
                   value=round(a, 2), bench_value=round(t, 2))
    series.append(row)

# FIFO lots across both accounts (the transfer moved lots in-kind, cost basis intact)
lots = defaultdict(deque); closed = []
for f in fills:
    if f["side"] == "buy":
        lots[f["symbol"]].append(dict(qty=f["qty"], px=f["price"], bench=f["bench"], ts=f["ts"])); continue
    rem = f["qty"]; cost = b_cost = 0.0; first = None
    while rem > 1e-9:
        lot = lots[f["symbol"]][0]; take = min(rem, lot["qty"])
        cost += take * lot["px"]; b_cost += take * lot["px"] / lot["bench"]; first = first or lot["ts"]
        lot["qty"] -= take; rem -= take
        if lot["qty"] <= 1e-9: lots[f["symbol"]].popleft()
    proceeds = f["notional"] - f["fee"]; r = proceeds / cost - 1; r_b = b_cost * f["bench"] / cost - 1
    closed.append(dict(symbol=f["symbol"], name=NAMES[f["symbol"]], qty=round(f["qty"], 6), opened=first[:10],
                       closed=f["date"], cost=round(cost, 2), proceeds=round(proceeds, 2), pnl=round(proceeds - cost, 2),
                       ret=round(r, 5), bench_ret=round(r_b, 5), alpha=round(r - r_b, 5)))
b_now = CLOSE[BENCH][-1]; open_pos = []
for s, q in lots.items():
    if not q: continue
    qty = sum(l["qty"] for l in q); cost = sum(l["qty"] * l["px"] for l in q)
    b_cost = sum(l["qty"] * l["px"] / l["bench"] for l in q); px = CLOSE[s][-1]; val = qty * px
    r = val / cost - 1; r_b = b_cost * b_now / cost - 1
    open_pos.append(dict(symbol=s, name=NAMES[s], qty=round(qty, 6), avg_cost=round(cost / qty, 4), price=px,
                         value=round(val, 2), cost=round(cost, 2), pnl=round(val - cost, 2), ret=round(r, 5),
                         bench_ret=round(r_b, 5), alpha=round(r - r_b, 5), opened=min(l["ts"] for l in q)[:10]))
end = series[-1]
for p in open_pos: p["weight"] = round(p["value"] / end["value"], 4)
open_pos.sort(key=lambda p: -p["value"])
deposits = sum(a for _, a in DEPOSITS)

data = dict(
    meta=dict(title="3-Month Basis Portfolio", inception=INCEPTION, launch=LAUNCH, as_of=AS_OF,
              bench_name="Russell 2000", bench_ticker=BENCH, cycle=IN["cycle"]["number"],
              cycle_opened=IN["cycle"]["opened"], cycle_review=IN["cycle"]["review"],
              plan="Start with $50, add about $100 a month, hold positions on a 3-month basis and "
                   "recycle them at each review.",
              source="Robinhood fills, positions and closes; IWM (Russell 2000 ETF) prices from Robinhood market data."),
    live=dict(value=end["value"], start_value=round(A_L, 2), cash=round(cash, 2), deposits=round(deposits, 2),
              pnl=round(end["value"] - A_L - deposits, 2), bench_value=end["bench_value"],
              bench_pnl=round(end["bench_value"] - A_L - deposits, 2),
              twr=round(tl_s - 1, 5), bench_twr=round(tl_b - 1, 5), alpha=round(tl_s - tl_b, 5)),
    pre=dict(twr=round(pre["twr"], 5), bench_twr=round(pre["bench_twr"], 5), alpha=round(pre["twr"] - pre["bench_twr"], 5)),
    inception=dict(twr=round(tw_s - 1, 5), bench_twr=round(tw_b - 1, 5), alpha=round(tw_s - tw_b, 5)),
    series=series, open=open_pos, closed=closed,
    fills=[dict(ts=f["ts"], symbol=f["symbol"], side=f["side"], qty=round(f["qty"], 6), price=round(f["price"], 4),
                notional=round(f["notional"], 2), bench=f["bench"], session=f["session"], record=f["record"]) for f in fills],
)
json.dump(data, open(os.path.join(HERE, "data.json"), "w"), indent=1)
tpl = open(os.path.join(HERE, "template.html")).read()
blob = json.dumps(data, separators=(",", ":")).replace("</", "<\\/")
open(os.path.join(HERE, "..", "index.html"), "w").write(tpl.replace("/*DATA*/", blob))
print(json.dumps({k: data[k] for k in ("live", "pre", "inception")}, indent=1))
for p in open_pos: print(p)
for r in series[-5:]: print(r)
