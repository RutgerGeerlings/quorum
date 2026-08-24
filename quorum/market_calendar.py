"""Kalender-edge. Dit is de PRIOR van de Strateeg, niet zijn dwangbuis.

Waarom dit er is: het turn-of-month-effect is de sterkste kalenderanomalie in aandelen en het is
geen folklore. SPY 1999-2026, 27 jaar:

    TOM-dagen (33% van de tijd) :  9.0 bp/dag = 22.6% geannualiseerd,  t = 3.67
    alle andere dagen           :  1.6 bp/dag =  4.0% geannualiseerd,  t = 0.87

t=3.67 haalt de Harvey/Liu/Zhu-lat van t>3 voor een nieuwe factor. Als losse strategie: CAGR 7.2%
bij 10.8% vol (Sharpe 0.67) tegen buy&hold 8.7% bij 19.2% (Sharpe 0.45) - en dat terwijl je maar
een derde van de tijd in de markt zit.

En voor deze wedstrijd in het bijzonder: 5 van de 6 handelsdagen tussen 28 aug en 4 sep 2026
vallen in het TOM-venster.
"""
from __future__ import annotations
from datetime import date, timedelta
from typing import List

# US-marktfeestdagen die in dit venster kunnen vallen. Bewust klein gehouden: alleen wat relevant
# is voor aug/sep. Een volledige kalender is hier overkill en zou stilzwijgend kunnen verouderen.
def labor_day(year: int) -> date:
    d = date(year, 9, 1)
    while d.weekday() != 0:
        d += timedelta(days=1)
    return d


def _holidays(year: int) -> set[date]:
    return {labor_day(year)}


def is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d not in _holidays(d.year)


def trading_days(year: int, month: int) -> List[date]:
    d = date(year, month, 1)
    out = []
    while d.month == month:
        if is_trading_day(d):
            out.append(d)
        d += timedelta(days=1)
    return out


def is_turn_of_month(d: date, n_before: int = 4, n_after: int = 3) -> bool:
    """True als d in het TOM-venster zit: de laatste `n_before` handelsdagen van de maand,
    of de eerste `n_after` van de volgende. Dit is exact de definitie die in productie draait."""
    tds = trading_days(d.year, d.month)
    if d not in tds:
        return False
    idx = tds.index(d)
    if idx < n_after:                       # begin van de maand
        return True
    if len(tds) - 1 - idx < n_before:       # eind van de maand
        return True
    return False


def first_friday(year: int, month: int) -> date:
    d = date(year, month, 1)
    while d.weekday() != 4:
        d += timedelta(days=1)
    return d


def is_nfp_day(d: date) -> bool:
    """Non-Farm Payrolls: eerste vrijdag van de maand, 8:30 ET.
    NB: de backtest zegt dat een straddle KOPEN op NFP verliesgevend is (implied > realised,
    gem. -1.6% op een budget van 15%). De Strateeg gebruikt dit dus als reden om GEEN premie te
    kopen op die dag, niet als koopsignaal."""
    return d == first_friday(d.year, d.month)


def days_until(d: date, target: date) -> int:
    """Handelsdagen tussen d en target (exclusief d, inclusief target)."""
    if target <= d:
        return 0
    n, cur = 0, d
    while cur < target:
        cur += timedelta(days=1)
        if is_trading_day(cur):
            n += 1
    return n


def calendar_context(d: date, contest_end: date) -> dict:
    """Alles wat de Strateeg over vandaag moet weten, in één dict."""
    return {
        "date": d.isoformat(),
        "is_trading_day": is_trading_day(d),
        "turn_of_month": is_turn_of_month(d),
        "nfp_day": is_nfp_day(d),
        "trading_days_left": days_until(d, contest_end),
        "tom_prior_bp_per_day": 9.0 if is_turn_of_month(d) else 1.6,
    }
