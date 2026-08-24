"""HARDE risk gates. Deze staan bewust in code en niet in een prompt.

Een LLM die zijn eigen limiet mag interpreteren is geen risk gate maar een suggestie. De Risk
Officer-agent MAG uitleggen waarom hij afwijst, maar hij kan de limieten niet verzetten - die
worden hier afgedwongen, deterministisch, voordat er ook maar iets naar Alpaca gaat.

Ontwerpregel: elke positie moet een BEWIJSBAAR maximaal verlies hebben. Daarom is naked short
categorisch verboden. Dat is niet alleen prudent, het maakt de belofte "deze agent kan nooit meer
dan $X verliezen" wiskundig hard in plaats van een intentie.
"""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import date
from typing import List, Literal

Right = Literal["call", "put"]


@dataclass(frozen=True)
class Leg:
    right: Right
    strike: float
    qty: int              # >0 = long, <0 = short
    premium: float        # per aandeel, positief (wat je betaalt/ontvangt per contract/100)
    expiry: date


@dataclass(frozen=True)
class Proposal:
    """Wat de Strateeg voorstelt. De Risk Officer keurt dit goed of af."""
    underlying: str
    legs: List[Leg]
    thesis: str
    contracts: int = 1


@dataclass
class Limits:
    max_total_premium_pct: float = 0.35   # totaal in premie, ooit, als fractie van startkapitaal
    max_daily_premium_pct: float = 0.08   # nieuwe premie per dag
    max_open_positions: int = 4
    allowed_underlyings: tuple = ("SPY", "QQQ", "IWM")
    flat_by: date = date(2026, 9, 4)      # alles plat vóór het slot
    min_days_to_expiry: int = 0


@dataclass
class Verdict:
    approved: bool
    reasons: List[str] = field(default_factory=list)
    worst_case_usd: float = 0.0


def net_premium(p: Proposal) -> float:
    """Netto betaalde premie in USD. Positief = je betaalt (debit). Negatief = credit."""
    return sum(l.qty * l.premium * 100 for l in p.legs) * p.contracts


def worst_case_loss(p: Proposal) -> float:
    """Bewijsbaar maximaal verlies in USD, positief getal.

    Voor een puur debit-pakket (alle netto long premie) is dat simpelweg de betaalde premie.
    Voor pakketten met shorts erin evalueren we de payoff op ALLE strikes plus de randen - voor
    stukgewijs-lineaire optiepayoffs ligt het extremum altijd op een knikpunt of in een staart.
    Een oneindig verlies (naked short) geeft float('inf') terug, en dat wordt hard geweigerd.
    """
    strikes = sorted({l.strike for l in p.legs})
    if not strikes:
        return 0.0
    prem = net_premium(p)

    def payoff_at(S: float) -> float:
        v = 0.0
        for l in p.legs:
            intr = max(S - l.strike, 0.0) if l.right == "call" else max(l.strike - S, 0.0)
            v += l.qty * intr * 100
        return v * p.contracts - prem

    # naked-short detectie: netto short calls -> onbeperkt omhoog; netto short puts -> tot 0
    net_calls = sum(l.qty for l in p.legs if l.right == "call")
    if net_calls < 0:
        return float("inf")

    pts = [0.0] + strikes + [strikes[-1] * 3]
    return -min(payoff_at(S) for S in pts)


def evaluate(p: Proposal, limits: Limits, *, today: date,
             premium_used_usd: float, premium_today_usd: float,
             open_positions: int, account_usd: float) -> Verdict:
    """Deterministische poortwachter. Geen LLM, geen interpretatie."""
    r: List[str] = []
    wc = worst_case_loss(p)

    if p.underlying not in limits.allowed_underlyings:
        r.append(f"onderliggende {p.underlying} staat niet op de toegestane lijst "
                 f"{limits.allowed_underlyings}")
    if wc == float("inf"):
        r.append("naked short: verlies is onbegrensd - categorisch verboden")
    if not p.legs:
        r.append("voorstel bevat geen legs")

    debit = max(net_premium(p), 0.0)
    if premium_used_usd + debit > limits.max_total_premium_pct * account_usd:
        r.append(f"totale premie zou ${premium_used_usd + debit:,.0f} worden, boven de limiet van "
                 f"{limits.max_total_premium_pct:.0%} (${limits.max_total_premium_pct*account_usd:,.0f})")
    if premium_today_usd + debit > limits.max_daily_premium_pct * account_usd:
        r.append(f"premie vandaag zou ${premium_today_usd + debit:,.0f} worden, boven de dagcap van "
                 f"{limits.max_daily_premium_pct:.0%} (${limits.max_daily_premium_pct*account_usd:,.0f})")
    if open_positions >= limits.max_open_positions:
        r.append(f"al {open_positions} posities open, limiet is {limits.max_open_positions}")
    for l in p.legs:
        if l.expiry > limits.flat_by:
            r.append(f"expiratie {l.expiry} ligt na de verplichte flat-datum {limits.flat_by}")
            break
    return Verdict(approved=not r, reasons=r, worst_case_usd=(0.0 if wc == float("inf") else wc))
