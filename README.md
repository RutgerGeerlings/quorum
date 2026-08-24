# Quorum — a trading desk that only acts when its agents agree

**Alpaca AI Trading Agents Hackathon · Aug 28 – Sep 4, 2026**

Most trading agents are a language model with a buy button. Quorum is a **desk**: four agents with
different jobs, one of whom exists purely to say no.

```
🧠 Strategist    reads the calendar + market state, proposes a thesis and an options structure
🛡️ Risk Officer  independently evaluates it, holds a veto, must give a reason
⚡ Trader        executes through Alpaca (MCP server / Trading API)
📊 Analyst       writes a plain-English post-mortem every evening
```

No quorum, no trade. **The desk is allowed to do nothing** — and on most days, it does.

---

## The one design decision that matters

**The LLM proposes. The code decides.**

Risk gates live in `quorum/gates.py` as deterministic, unit-tested functions — not in a prompt.
A model that can reinterpret its own limit isn't a risk gate, it's a suggestion. The Risk Officer
may *explain* its veto in natural language, but the verdict comes from code that can't be
talked out of it by a hallucination or a prompt injection.

That gives us a claim we can actually prove:

> **This agent cannot lose more than its premium budget.** Not "shouldn't" — *cannot*.
> Naked short positions are categorically rejected (`worst_case_loss` returns infinity → hard fail),
> so every open position has a mathematically bounded maximum loss, computed before the order is sent.

## The edge: the calendar, not the news

Everyone else will build "LLM reads headlines, buys stock". We looked at the calendar instead.

The **turn-of-month effect** on SPY, 1999–2026 (27 years):

| | mean/day | annualised | t-stat |
|---|---|---|---|
| TOM days (33% of the time) | 9.0 bp | **22.6%** | **3.67** |
| every other day | 1.6 bp | 4.0% | 0.87 |

t = 3.67 clears the Harvey/Liu/Zhu t > 3 bar for a new factor. As a standalone strategy it returns
CAGR 7.2% at 10.8% vol (Sharpe 0.67) versus buy-and-hold's 8.7% at 19.2% (Sharpe 0.45) — while
being in the market only a third of the time. The other two-thirds of the year deliver 1.4% CAGR
for a 70% drawdown.

**And 5 of the 6 trading days in this contest fall inside that window.**

```
TOM window :  Aug 26, 27, 28 · Aug 31 · Sep 1, 2, 3
contest    :          Aug 28 · Aug 31 · Sep 1, 2, 3, 4
overlap    :          Aug 28 · Aug 31 · Sep 1, 2, 3   → 5 of 6
```

## What we tested and threw away

Two of our three ideas died in backtest. We're keeping them in the write-up because the graveyard
is the interesting part.

| idea | result | verdict |
|---|---|---|
| ATM calls in the TOM window | P(+30%) 20.2%, P(+50%) 14.2% | **kept** |
| Roll winners into further OTM ("let it ride") | P(+30%) drops 20.2% → 14.8%, mean −2.6pp | **killed** |
| Long straddle into Sep 4 payrolls | P(+30%) ≈ 2%, mean negative | **killed** |

The straddle failure is the useful one: on event days the market has already priced the event, so
buying premium into NFP is paying for something you already own. Quorum therefore treats NFP day as
a reason **not** to trade — a calendar signal that says stay out.

## Honest expectations

Expected return is approximately zero. Options are fairly priced; the turn-of-month drift roughly
pays for the premium. What we're buying is **skew, not edge** — bounded downside, unbounded upside —
because a rank-based tournament rewards `P(finish first)`, not expected value. A strategy that
reliably makes 2% finishes 40th.

Backtested over 331 historical turn-of-month windows, an ATM structure at a 35% premium budget:
P(+30%) = 20.2%, P(+50%) = 14.2%, worst case = the premium budget, by construction.

## Run it

```bash
python3 tests/test_market_calendar.py   # 22 tests — calendar, TOM window, contest alignment
python3 tests/test_gates.py             # 15 tests — including "naked short must be rejected"
python3 tests/test_desk.py              # full contest week, dry
```

## Structure

```
quorum/
├── market_calendar.py   TOM / NFP / holidays. The Strategist's prior.
├── gates.py             Hard limits + provable worst case. No LLM here, on purpose.
└── desk.py              Strategist → Risk Officer → Trader loop. May decide to do nothing.
```

## Designed against the actual judging criteria

The contest scores five axes, and P&L is one of them:

| criterion | how Quorum answers it |
|---|---|
| **P&L Performance** | Turn-of-month prior (t=3.67, 27y) expressed as ATM convexity. Premium budget capped at 22% — enough for a real number, not enough to blow up. |
| **Technology Implementation** | All three surfaces: Trading API for chains and orders, **CLI** for long-running/cron sessions, **MCP** for the agent tool layer. `broker.py` is one interface, three transports. |
| **Creativity & Originality** | Four agents that are allowed to disagree, and a Risk Officer with a real veto. Risk gates live in code, not in a prompt. The desk may decide to do nothing. |
| **Presentation & Execution** | The veto *is* the demo. Watching the Risk Officer stop the Strategist mid-week is more legible than an equity curve. |
| **Social engagement** | The Analyst agent writes the daily post-mortem itself — building in public is a function of the system, not a marketing afterthought. |

A design note that follows from this: we deliberately did **not** maximise P&L variance. An earlier
draft sized the premium budget at 35–50% because that maximises `P(finish first)` in a
winner-take-most tournament. But that optimises ~20% of the available points while risking the
other 80% — an agent that blows up demonstrates nothing. The Risk Officer's caps are set so the
desk survives to show its reasoning.

## The tool surface is the safety argument

`AlpacaBroker.mcp_tools()` exposes five tools to the agents. Note what is missing: **there is no
`place_order`.** The only path to the market is `submit_proposal()`, which calls
`gates.evaluate()` before anything reaches Alpaca. An agent that decides to "just place an order
anyway" doesn't exist here, because the tool isn't there.

## Alpaca infrastructure

Alpaca MCP Server v2 (FastMCP/OpenAPI) for agent-facing tools, Trading API for execution,
Level 3 multi-leg options on a paper account. Options are commission-free, which is what makes a
defined-risk debit structure viable at this size.

---

## Build timeline (full transparency)

lablab's rules require that the **core AI-powered functionality** is built during the event window.
We're stating exactly what existed when, so a judge never has to guess.

**Before the window (Aug 24) — non-AI scaffolding only:**
- `market_calendar.py` — date arithmetic. No model, no inference.
- `gates.py` — deterministic risk limits and worst-case computation. No model.
- `desk.py` — the loop skeleton, with **placeholder** strategist/risk-officer functions that are
  plain `if` statements, deliberately built so the desk is testable without an API key.
- Backtest research on the turn-of-month effect and the option structures (Python, historical data).

**During the window (Aug 28 – Sep 4) — the actual agents:**
- LLM-backed Strategist: reasons over calendar + market state, writes its own thesis
- LLM-backed Risk Officer: argues its veto in natural language on top of the hard gates
- Alpaca MCP integration for live execution
- Analyst agent and the public post-mortems
- Live dashboard

The placeholder functions in `desk.py` exist to prove the *plumbing* works. Every one of them gets
replaced by an agent during the event — that's the whole point of the architecture: the LLM slots
in above the gates, never underneath them.

## License

MIT — see [LICENSE](LICENSE).
