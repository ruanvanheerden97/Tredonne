# TreDonne Estate — Outage Planner

A small Streamlit tool for technicians planning maintenance on the TreDonne
ring-fed network. Two modes:

* **Minisub(s)** — transformer / kiosk work: pick the minisub(s) you need to
  take out of service.
* **MV ring section** — cable work: pick a 3300 V cable run between two
  minisubs.

In both cases it tells you how to isolate, whether the ring break must be
closed to keep the rest of the estate alive, and exactly which stands lose
power — ready to export as an outage notice. (For single ring-cable sections
the break can almost always be closed so **no customers go off** — only the
cable is dead.)

## Run it

```bash
cd trd_outage
pip install -r requirements.txt
streamlit run app.py
```

It opens in your browser. Technicians on site can reach it on the host's
network URL (shown when it starts) from a phone.

## How it decides who goes dark

The ring is modelled as a graph:

```
TX01 – TRX08 – TRX09 – TRX05 – TRX01 – TRX02 – TRX03 –//break//– TRX04 – TRX06 – TRX07 – TX02
```

Both `TX01` and `TX02` are live sources. A minisub is **energised** if it can
still trace a path to either source. When you isolate a minisub:

* **LV-side work** and an LV isolator is fitted (TRX01, TRX05, TRX07, TRX08) →
  open the 400 V isolator. The transformer and MV ring stay live; only that
  minisub's LV load drops.
* **Transformer / MV work** → the 3300 V ring cables are disconnected, which
  breaks the ring at that node. The app checks whether **closing the ring
  break** restores the far side from the other source, and only then are the
  affected stands limited to the isolated minisub. If closing the break is
  needed, it says so (and which units it rescues), and enforces
  **break-before-make** so the two step-ups are never paralleled.

Select several minisubs (e.g. a whole half of the estate) and it computes the
combined result the same way.

**MV ring section:** isolating a cable run opens the ring at that one point
without dropping the two bounding transformers (they stay fed from their other
side). Because the ring is a line between two live sources, closing the break
restores any islanded minisub — so a single-section isolation typically affects
**no customers at all**.

## Files

| File | Purpose |
|------|---------|
| `app.py` | Streamlit UI |
| `engine.py` | data loader + ring connectivity + switching plan (no UI) |
| `topology.py` | ring order, NO point, sources, LV isolators — **edit here** if the network changes |
| `data/TRD_master.xlsx` | meter master sheet (stand → minisub, serial, tariff). Replace via the sidebar uploader or swap this file to refresh. |

## Updating the data

The planner reads the same master sheet you already maintain
(`Erf`, `Device`, `Tariff`, `TRX`, `Parent meter`). Upload a newer version in
the sidebar, or drop it in as `data/TRD_master.xlsx`. No code changes needed as
long as the columns stay the same.

## Scope / caveats

* This is a **planning and notification aid**. Actual MV cable disconnection and
  ring switching must be carried out by your authorised MV operator under your
  switching procedure.
* LV isolators drop the 400 V load only — the transformer and MV ring stay live.
* The Gate House and estate-bulk loads sit on the bulk side and are never
  affected by ring-minisub isolation.
* Switching points reflect what's on site today: LV isolators at TRX01/05/07/08,
  otherwise isolation is by physical MV cable disconnection. Update `topology.py`
  as the network changes.
