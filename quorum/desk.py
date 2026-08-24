"""De desk: Strateeg -> Risk Officer -> Trader, met de Analist als dagsluiting.

Ontwerpkeuze die alles bepaalt: de LLM stelt VOOR, de code BESLIST. De Strateeg mag creatief zijn
en de Risk Officer mag zijn afwijzing in gewone taal uitleggen, maar het oordeel zelf komt uit
gates.evaluate() - deterministisch, testbaar, en niet weg te praten door een prompt-injectie of
een hallucinerend model.

De desk mag ook NIETS doen. Een desk die altijd handelt is geen desk maar een knop.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from typing import Callable, List, Optional
from .market_calendar import calendar_context
from .gates import Proposal, Limits, Verdict, evaluate, worst_case_loss, net_premium


@dataclass
class DeskState:
    account_usd: float = 100_000.0
    premium_used_usd: float = 0.0
    premium_today_usd: float = 0.0
    open_positions: int = 0
    log: List[str] = field(default_factory=list)

    def note(self, who: str, msg: str) -> None:
        line = f"[{who}] {msg}"
        self.log.append(line)
        print("  " + line)


# --- de agents -------------------------------------------------------------------------------
# Elke agent is een functie. Standaard zijn het deterministische fallbacks zodat de desk draait
# (en te testen is) zonder LLM; in productie schuif je er een LLM-call in.

def default_strategist(ctx: dict, state: DeskState) -> Optional[Proposal]:
    """Prior: koop convexiteit als de kalender meewerkt, en NIET op NFP-dag.

    De backtest zegt: TOM-dagen dragen 9.0 bp/dag tegen 1.6 bp op de rest (t=3.67, 27 jaar).
    En een straddle kopen op NFP-dag is verliesgevend (implied > realised, gem. -1.6%). Dus de
    kalender is hier een reden om te handelen EN een reden om af te blijven."""
    from .gates import Leg
    if not ctx["is_trading_day"]:
        return None
    if ctx["nfp_day"]:
        return None                     # bewust: geen premie kopen in een ingeprijsd event
    if not ctx["turn_of_month"]:
        return None
    spot = ctx.get("spot", 640.0)
    expiry = ctx.get("expiry", date(2026, 9, 4))
    prem = ctx.get("atm_premium", spot * 0.010)
    n = max(1, int(state.account_usd * 0.06 / (prem * 100)))
    strike = round(spot)
    return Proposal(
        underlying="SPY",
        legs=[Leg("call", strike, 1, prem, expiry)],
        thesis=(f"dag in TOM-venster (prior {ctx['tom_prior_bp_per_day']} bp/dag tegen 1.6 bp "
                f"buiten), {ctx['trading_days_left']} handelsdagen tot slot -> ATM-convexiteit"),
        contracts=n,
    )


def default_risk_officer(p: Proposal, state: DeskState, limits: Limits, today: date) -> Verdict:
    return evaluate(p, limits, today=today, premium_used_usd=state.premium_used_usd,
                    premium_today_usd=state.premium_today_usd,
                    open_positions=state.open_positions, account_usd=state.account_usd)


def default_trader(p: Proposal, v: Verdict, state: DeskState) -> bool:
    """In productie: Alpaca MCP / Trading API. Hier: boekhouding, zodat de loop testbaar is."""
    debit = max(net_premium(p), 0.0)
    state.premium_used_usd += debit
    state.premium_today_usd += debit
    state.open_positions += 1
    return True


# --- de loop ---------------------------------------------------------------------------------
def run_day(today: date, ctx_extra: dict, state: DeskState, limits: Limits, *,
            strategist: Callable = default_strategist,
            risk_officer: Callable = default_risk_officer,
            trader: Callable = default_trader,
            contest_end: date = date(2026, 9, 4)) -> Optional[Proposal]:
    ctx = calendar_context(today, contest_end)
    ctx.update(ctx_extra)
    state.premium_today_usd = 0.0
    print(f"\n=== {today} ===")

    p = strategist(ctx, state)
    if p is None:
        why = ("geen handelsdag" if not ctx["is_trading_day"] else
               "NFP-dag: event is ingeprijsd, wij kopen geen dure premie" if ctx["nfp_day"] else
               "buiten het TOM-venster, geen kalender-edge")
        state.note("Strateeg", f"geen voorstel - {why}")
        state.note("Desk", "vandaag NIETS doen")
        return None

    state.note("Strateeg", f"voorstel: {p.contracts}x {p.underlying} "
                           f"{p.legs[0].strike:.0f}C @ {p.legs[0].premium:.2f} | {p.thesis}")
    v = risk_officer(p, state, limits, today)
    if not v.approved:
        for r in v.reasons:
            state.note("Risk Officer", f"VETO: {r}")
        state.note("Desk", "geen quorum - geen trade")
        return None

    state.note("Risk Officer", f"akkoord - bewijsbaar maximaal verlies ${v.worst_case_usd:,.0f} "
                               f"({v.worst_case_usd/state.account_usd:.1%} van het account)")
    trader(p, v, state)
    state.note("Trader", f"uitgevoerd, premie totaal nu ${state.premium_used_usd:,.0f} "
                         f"({state.premium_used_usd/state.account_usd:.1%})")
    return p
