"""Outage-planning engine for the TreDonne ring.

Pure logic, no UI. Two jobs:
  1. load the meter master sheet into a stand -> minisub model, and
  2. work out, for a chosen isolation, which minisubs go dark and which
     stands are therefore affected, plus the switching sequence.

The ring is treated as a graph: sources + minisubs are nodes, the cable
runs between consecutive ring positions are edges, and the normally-open
(NO) point is an edge that is only "closed" when we choose to back-feed.
A minisub is energised if it can still reach either source.
"""
from __future__ import annotations
import re
from collections import defaultdict, OrderedDict

import openpyxl

import topology as T


# --------------------------------------------------------------------------- data
def _phase_from_tariff(tariff: str):
    t = tariff.replace(" ", "")
    if re.search(r"\d+[xX]\d+A", t):
        return 3
    if re.search(r"\b\d+A\b", tariff):
        return 1
    return None


def _role(serial: str, tariff: str):
    s, t = serial.upper(), tariff.lower()
    if s.endswith("NR") or "reverse" in t:
        return "reverse"
    if "prepaid token" in t:
        return "prepaid"
    if t.startswith("elec zero charge"):
        return "check"
    if "gridtie" in t:
        return "solar"
    return "main"


def load_meters(path: str):
    """Return (stands, specials).

    stands : OrderedDict keyed by (trx, erf) -> dict(trx, erf, meters[], phase,
             solar, prepaid).  meters is a list of dict(serial, tariff, role).
    specials : list of dict for non-ring rows (estate bulk, gate house).
    """
    wb = openpyxl.load_workbook(path, data_only=True)
    ws = wb["Elec"]
    stands: "OrderedDict[tuple, dict]" = OrderedDict()
    specials = []
    for r in range(2, ws.max_row + 1):
        vals = [ws.cell(row=r, column=c).value for c in range(1, 6)]
        if all(v is None for v in vals):
            continue
        erf, dev, tariff, trx, parent = [
            str(v).strip() if v is not None else "" for v in vals
        ]
        if trx in T.MINISUBS:
            key = (trx, erf)
            st = stands.setdefault(
                key, dict(trx=trx, erf=erf, meters=[], phase=None,
                          solar=False, prepaid=False)
            )
            role = _role(dev, tariff)
            st["meters"].append(dict(serial=dev, tariff=tariff, role=role))
            if role in ("main", "solar"):
                ph = _phase_from_tariff(tariff)
                if ph and st["phase"] is None:
                    st["phase"] = ph
            if role in ("solar", "reverse"):
                st["solar"] = True
            if role == "prepaid":
                st["prepaid"] = True
        else:
            specials.append(dict(erf=erf, serial=dev, tariff=tariff,
                                 trx=trx, parent=parent))
    return stands, specials


def stands_by_minisub(stands):
    out = defaultdict(list)
    for (trx, erf), st in stands.items():
        out[trx].append(st)
    return out


# --------------------------------------------------------------------- ring graph
def _edges(removed_nodes, no_closed, extra_open):
    """Adjacency for the ring with the given switching state."""
    adj = defaultdict(set)
    no = {T.NO_POINT[0], T.NO_POINT[1]}
    for a, b in zip(T.RING_ORDER, T.RING_ORDER[1:]):
        if {a, b} == no and not no_closed:
            continue
        if a in removed_nodes or b in removed_nodes:
            continue
        if (a, b) in extra_open or (b, a) in extra_open:
            continue
        adj[a].add(b)
        adj[b].add(a)
    return adj


def energised(removed_nodes=frozenset(), no_closed=False, extra_open=frozenset()):
    """Set of nodes still reaching a source under the given switching state."""
    adj = _edges(set(removed_nodes), no_closed, set(extra_open))
    seen = set()
    stack = [s for s in T.SOURCES if s not in removed_nodes]
    while stack:
        n = stack.pop()
        if n in seen:
            continue
        seen.add(n)
        stack.extend(m for m in adj[n] if m not in seen)
    return seen


def dark_minisubs(removed_nodes=frozenset(), no_closed=False, extra_open=frozenset()):
    live = energised(removed_nodes, no_closed, extra_open)
    return [m for m in T.MINISUBS if m not in live]


# ----------------------------------------------------------------- isolation plan
def plan_isolation(targets, lv_only=False):
    """Work out the switching plan and the full set of dark minisubs.

    targets : list of minisubs to take out of service.
    lv_only : the work is on the LV side only; use LV isolators where fitted
              (transformer and MV ring stay live, no ring reconfiguration).

    Returns a dict with: dark (list), affected_minisubs, steps (list of str),
    need_no_close (bool), collateral (minisubs that would also go dark if the
    ring break is NOT closed), method per target, and warnings.
    """
    targets = [t for t in targets if t in T.MINISUBS]
    result = dict(targets=targets, lv_only=lv_only, steps=[], warnings=[],
                  method={}, need_no_close=False, collateral=[])

    if not targets:
        result["dark"] = []
        result["affected_minisubs"] = []
        return result

    # --- Case 1: LV-side work, every target has an LV isolator -> no ring change
    all_have_lv = all(t in T.LV_ISOLATORS for t in targets)
    if lv_only and all_have_lv:
        for t in targets:
            result["method"][t] = "LV isolator"
            result["steps"].append(
                f"{t}: open the {T.LV_ISOLATORS[t]} at the back of the unit. "
                f"Transformer and 3300 V ring stay live; only {t}'s LV load drops."
            )
        result["dark"] = list(targets)
        result["affected_minisubs"] = list(targets)
        result["need_no_close"] = False
        return result

    if lv_only and not all_have_lv:
        missing = [t for t in targets if t not in T.LV_ISOLATORS]
        result["warnings"].append(
            "LV-side work selected, but no LV isolator is fitted at "
            + ", ".join(missing)
            + " - these can only be isolated by disconnecting the MV cables "
              "(full outage of the unit)."
        )

    # --- Case 2: full isolation (MV disconnect). Compare NO-open vs NO-closed.
    removed = frozenset(targets)
    dark_open = set(dark_minisubs(removed, no_closed=False))
    dark_closed = set(dark_minisubs(removed, no_closed=True))
    no_helps = dark_open > dark_closed  # closing the ring break saves units

    if no_helps:
        result["need_no_close"] = True
        result["collateral"] = sorted(dark_open - dark_closed)
        final_dark = dark_closed
    else:
        final_dark = dark_open

    for t in targets:
        has_lv = t in T.LV_ISOLATORS
        result["method"][t] = "MV disconnect" + (" (LV isolator available for LV-only work)" if has_lv else "")
        step = (f"{t}: disconnect the 3300 V incomer and outgoing ring cables "
                f"(A/B/C) at the back of the unit to isolate the transformer.")
        if has_lv:
            step += f"  [LV-only work could instead use the {T.LV_ISOLATORS[t]}.]"
        result["steps"].append(step)

    if result["need_no_close"]:
        a, b = T.NO_POINT
        result["steps"].append(
            f"Close the ring break ({a} \u2194 {b}) to back-feed "
            + ", ".join(result["collateral"])
            + " from the other source. Isolate the target(s) FIRST, then close "
              "the break (break-before-make - never parallel the two step-ups)."
        )
    else:
        result["steps"].append(
            "The ring break can stay as-is; the rest of the estate keeps its "
            "normal feed."
        )

    result["dark"] = sorted(final_dark, key=lambda m: T.MINISUBS.index(m))
    result["affected_minisubs"] = result["dark"]
    return result


# -------------------------------------------------------------- ring sections
def ring_sections():
    """Adjacent MV cable runs on the ring, excluding the NO point itself."""
    no = {T.NO_POINT[0], T.NO_POINT[1]}
    return [(a, b) for a, b in zip(T.RING_ORDER, T.RING_ORDER[1:])
            if {a, b} != no]


def plan_section(section):
    """Plan isolation of a single MV ring-cable section (a, b).

    Isolating the cable does NOT drop the two bounding units - they stay fed
    from their other side - so the only question is whether any minisub gets
    islanded, which closing the ring break almost always prevents.
    """
    a, b = section
    result = dict(section=section, steps=[], warnings=[], need_no_close=False,
                  collateral=[], method={})

    if {a, b} == {T.NO_POINT[0], T.NO_POINT[1]}:
        result["warnings"].append(
            f"{a}\u2013{b} is the normally-open ring break - it is already "
            "isolated, so there is nothing to switch.")
        result["dark"] = []
        result["affected_minisubs"] = []
        return result

    extra_open = frozenset({(a, b)})
    dark_open = set(dark_minisubs(extra_open=extra_open, no_closed=False))
    dark_closed = set(dark_minisubs(extra_open=extra_open, no_closed=True))
    no_helps = dark_open > dark_closed

    if no_helps:
        result["need_no_close"] = True
        result["collateral"] = sorted(dark_open - dark_closed,
                                      key=lambda m: T.MINISUBS.index(m))
        final_dark = dark_closed
    else:
        final_dark = dark_open

    ends = []
    if a not in T.SOURCES:
        ends.append(f"the {a} outgoing")
    else:
        ends.append(f"the {a} feeder")
    if b not in T.SOURCES:
        ends.append(f"the {b} incomer")
    else:
        ends.append(f"the {b} feeder")
    result["steps"].append(
        f"Isolate the 3300 V cable between {a} and {b}: disconnect it at "
        + " and ".join(ends) + ".")

    if result["need_no_close"]:
        x, y = T.NO_POINT
        result["steps"].append(
            f"Close the ring break ({x} \u2194 {y}) to keep "
            + ", ".join(result["collateral"])
            + " fed from the other source. Isolate the cable FIRST, then close "
              "the break (break-before-make).")
    else:
        result["steps"].append(
            "No minisub is islanded - the ring break can stay as-is; only the "
            "cable is dead.")

    result["dark"] = sorted(final_dark, key=lambda m: T.MINISUBS.index(m))
    result["affected_minisubs"] = result["dark"]
    return result


# ------------------------------------------------------------- affected stands
def affected_stands(dark, stands):
    by = stands_by_minisub(stands)
    rows = []
    for trx in sorted(dark, key=lambda m: T.MINISUBS.index(m) if m in T.MINISUBS else 99):
        for st in by.get(trx, []):
            serials = " / ".join(m["serial"] for m in st["meters"])
            tariffs = "; ".join(sorted({m["tariff"] for m in st["meters"]}))
            ph = {3: "3\u00d8", 1: "1\u00d8"}.get(st["phase"], "?")
            rows.append(dict(minisub=trx, stand=st["erf"], phase=ph,
                             meters=len(st["meters"]), serials=serials,
                             tariff=tariffs,
                             solar="yes" if st["solar"] else "",
                             prepaid="yes" if st["prepaid"] else ""))
    return rows


ROLE_LABEL = {
    "main": "Main (post-paid)",
    "solar": "Solar forward",
    "reverse": "Reverse (NR)",
    "prepaid": "Prepaid token",
    "check": "Check (zero-charge)",
}


def transformer_detail(trx, stands):
    """Every meter on a transformer, one row per meter, for the explorer view."""
    by = stands_by_minisub(stands)
    rows = []
    for st in by.get(trx, []):
        ph = {3: "3\u00d8", 1: "1\u00d8"}.get(st["phase"], "?")
        for m in st["meters"]:
            rows.append(dict(
                stand=st["erf"], phase=ph, serial=m["serial"],
                tariff=m["tariff"], role=ROLE_LABEL.get(m["role"], m["role"]),
                solar="yes" if st["solar"] else "",
                prepaid="yes" if st["prepaid"] else ""))
    return rows


def transformer_overview(stands):
    """One row per transformer: stand/meter counts and phase/solar/prepaid mix."""
    by = stands_by_minisub(stands)
    out = []
    for trx in T.MINISUBS:
        sts = by.get(trx, [])
        meters = sum(len(s["meters"]) for s in sts)
        out.append(dict(
            minisub=trx, stands=len(sts), meters=meters,
            three_phase=sum(1 for s in sts if s["phase"] == 3),
            single_phase=sum(1 for s in sts if s["phase"] == 1),
            solar=sum(1 for s in sts if s["solar"]),
            prepaid=sum(1 for s in sts if s["prepaid"]),
            lv_isolator=T.LV_ISOLATORS.get(trx, "")))
    return out


def summary(rows):
    out = dict(stands=len(rows), meters=sum(r["meters"] for r in rows),
               three_phase=sum(1 for r in rows if r["phase"] == "3\u00d8"),
               single_phase=sum(1 for r in rows if r["phase"] == "1\u00d8"),
               solar=sum(1 for r in rows if r["solar"] == "yes"),
               prepaid=sum(1 for r in rows if r["prepaid"] == "yes"))
    return out
