"""TreDonne Estate - Outage Planner (Streamlit).

Technician tool for a ring-fed estate. Two modes:
  * isolate one or more minisubs for transformer / kiosk work, or
  * isolate an MV ring-cable section.
In both cases it gives the switching plan, shows the ring state, and lists
every stand that loses power - ready to export as an outage notice.

Run:  streamlit run app.py
"""
import io
import os
import datetime as dt

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Circle
import pandas as pd
import streamlit as st

import engine
import topology as T

NAVY = "#243f5e"; GREEN = "#1E9E4A"; RED = "#C0392B"; GREY = "#7a828b"; GOLD = "#E8860E"

st.set_page_config(page_title="TreDonne Outage Planner", page_icon="\u26a1", layout="wide")


# Default master sheet lives next to this script, so it loads no matter what
# directory Streamlit is launched from (important on Streamlit Cloud).
DATA_DEFAULT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                            "data", "TRD_master.xlsx")


@st.cache_data(show_spinner=False)
def _load(source):
    if isinstance(source, (bytes, bytearray)):
        source = io.BytesIO(source)
    return engine.load_meters(source)


# ------------------------------------------------------------------- ring figure
def ring_figure(dark, no_closed, open_edge=None):
    order = T.RING_ORDER
    n = len(order)
    fig, ax = plt.subplots(figsize=(11, 2.6))
    ax.set_xlim(-0.6, n - 0.4); ax.set_ylim(-1.1, 1.5); ax.axis("off")
    xs = list(range(n))
    no = {T.NO_POINT[0], T.NO_POINT[1]}
    oe = set(open_edge) if open_edge else None
    for i in range(n - 1):
        a, b = order[i], order[i + 1]
        is_no = {a, b} == no
        is_cut = oe is not None and {a, b} == oe
        if is_cut:
            style, col = (0, (1, 1.5)), RED
        elif is_no:
            style = "-" if no_closed else (0, (2, 2))
            col = GREEN if no_closed else GREY
        else:
            style = (0, (1, 2)) if (a in dark or b in dark) else "-"
            col = RED if (a in dark or b in dark) else NAVY
        ax.plot([xs[i], xs[i + 1]], [0, 0], linestyle=style, color=col, lw=2.4, zorder=1)
        if is_no:
            ax.text((xs[i] + xs[i + 1]) / 2, 0.52,
                    "break\nCLOSED" if no_closed else "break\nopen",
                    ha="center", va="bottom", fontsize=7,
                    color=GREEN if no_closed else GREY, fontweight="bold")
        if is_cut:
            ax.text((xs[i] + xs[i + 1]) / 2, 0.52, "cable\nISOLATED",
                    ha="center", va="bottom", fontsize=7, color=RED, fontweight="bold")
    for x, name in zip(xs, order):
        if name in T.SOURCES:
            fc, tc = GOLD, "white"
        elif name in dark:
            fc, tc = RED, "white"
        else:
            fc, tc = GREEN, "white"
        ax.add_patch(FancyBboxPatch((x - 0.42, -0.34), 0.84, 0.68,
                     boxstyle="round,pad=0.04", fc=fc, ec="#1a2d44", lw=1.0, zorder=3))
        ax.text(x, 0.02, name.replace("TRX", "T"), ha="center", va="center",
                fontsize=8.5, fontweight="bold", color=tc, zorder=4)
        cnt = BY.get(name)
        if cnt:
            ax.text(x, -0.62, f"{len(cnt)}", ha="center", va="center",
                    fontsize=7, color="#333", zorder=4)
    for lx, (c, lab) in zip([n - 3.3, n - 2.2, n - 1.1],
                            [(GREEN, "live"), (RED, "dark/cut"), (GOLD, "source")]):
        ax.add_patch(Circle((lx, 1.2), 0.08, fc=c, ec="none"))
        ax.text(lx + 0.14, 1.2, lab, va="center", fontsize=7)
    fig.tight_layout()
    return fig


# --------------------------------------------------------------------- header
st.title("\u26a1 TreDonne Estate \u2014 Outage Planner")
st.caption(
    "Ring-fed network. Choose what you need to isolate; the planner works out the "
    "switching, keeps the rest of the estate alive where the ring allows, and lists "
    "every stand that will lose power."
)

with st.sidebar:
    st.header("Data source")
    up = st.file_uploader("Meter master sheet (.xlsx)", type=["xlsx"])
    if up:
        source = up.getvalue()
    elif os.path.exists(DATA_DEFAULT):
        source = DATA_DEFAULT
    else:
        st.info("Upload the meter master sheet (.xlsx) to begin.")
        st.stop()
    try:
        stands, specials = _load(source)
        st.success(f"Loaded {len(stands)} stands across {len(T.MINISUBS)} minisubs.")
    except Exception as e:  # noqa
        st.error(f"Could not read sheet: {e}")
        st.stop()
    st.markdown("---")
    st.caption(
        f"**{T.ESTATE_NAME}** \u00b7 estate bulk SN {T.ESTATE_BULK_SN}\n\n"
        "Ring: TX01 \u2013 08 \u2013 09 \u2013 05 \u2013 01 \u2013 02 \u2013 03 "
        "\u2013//break//\u2013 04 \u2013 06 \u2013 07 \u2013 TX02"
    )
    st.caption("LV isolators (400 V side): "
               + ", ".join(f"{k} ({v.split(' LV')[0]})" for k, v in T.LV_ISOLATORS.items()))

BY = engine.stands_by_minisub(stands)

# --------------------------------------------------------------------- controls
st.subheader("1 \u00b7 What are you isolating?")
mode = st.radio("Isolation type", ["Minisub(s) \u2013 transformer / kiosk work",
                                    "MV ring section \u2013 cable work"],
                horizontal=True, label_visibility="collapsed")

plan = None
label = ""
open_edge = None

if mode.startswith("Minisub"):
    c1, c2 = st.columns([2, 1])
    targets = c1.multiselect(
        "Minisub(s) to take out of service", options=T.MINISUBS,
        format_func=lambda m: f"{m}  ({len(BY.get(m, []))} stands)",
        help="One for a single outage, or several (e.g. a whole half) to model a larger one.")
    lv_only = c2.checkbox("LV-side work only",
                          help="Use the 400 V isolator where fitted; transformer and ring stay live.")
    if not targets:
        st.info("Select at least one minisub to see the outage plan.")
        st.stop()
    plan = engine.plan_isolation(targets, lv_only=lv_only)
    label = ", ".join(targets) + ("  (LV-side only)" if lv_only and all(t in T.LV_ISOLATORS for t in targets) else "")
else:
    secs = engine.ring_sections()
    sec = st.selectbox("MV ring-cable section to isolate", options=secs,
                       format_func=lambda s: f"{s[0]}  \u2194  {s[1]}")
    plan = engine.plan_section(sec)
    open_edge = sec
    label = f"cable {sec[0]}\u2013{sec[1]}"

rows = engine.affected_stands(plan["dark"], stands)
summ = engine.summary(rows)

# --------------------------------------------------------------------- results
st.subheader("2 \u00b7 Feed status")
m1, m2, m3, m4 = st.columns(4)
m1.metric("Minisubs dark", len(plan["dark"]))
m2.metric("Stands affected", summ["stands"])
m3.metric("Meters affected", summ["meters"])
m4.metric("Rest of estate", f"{len(T.MINISUBS) - len(plan['dark'])} live")

st.pyplot(ring_figure(plan["dark"], plan["need_no_close"], open_edge), use_container_width=True)

for w in plan["warnings"]:
    st.warning(w)

st.subheader("3 \u00b7 Switching plan")
if plan["need_no_close"]:
    st.markdown(f"**Ring break must be CLOSED** to keep **{', '.join(plan['collateral'])}** "
                "alive (back-fed from the other source).")
for i, step in enumerate(plan["steps"], 1):
    st.markdown(f"**{i}.** {step}")
st.caption(
    "Planning aid only. MV cable disconnection / ring switching must be executed by your "
    "authorised MV operator under your switching procedure. LV isolators drop the 400 V load "
    "only \u2014 the transformer and MV ring remain live.")

st.subheader("4 \u00b7 Affected stands")
if summ["stands"] == 0:
    st.success("No stands lose power with this plan \u2014 only the isolated equipment is dead.")
df = pd.DataFrame(rows)
if not df.empty:
    df = df.rename(columns={"minisub": "Minisub", "stand": "Stand", "phase": "\u00d8",
                            "meters": "Meters", "serials": "Meter serial(s)",
                            "tariff": "Tariff", "solar": "Solar", "prepaid": "Prepaid"})
    st.dataframe(df, use_container_width=True, hide_index=True)
    sc = st.columns(4)
    sc[0].caption(f"3\u00d8 connections: **{summ['three_phase']}**")
    sc[1].caption(f"1\u00d8 connections: **{summ['single_phase']}**")
    sc[2].caption(f"Solar PV stands: **{summ['solar']}**")
    sc[3].caption(f"Prepaid stands: **{summ['prepaid']}**")

    stamp = dt.date.today().isoformat()
    csv = df.to_csv(index=False).encode()
    notice = io.StringIO()
    notice.write(f"{T.ESTATE_NAME} - PLANNED ELECTRICITY INTERRUPTION\n")
    notice.write(f"Date issued: {stamp}\n")
    notice.write(f"Work on: {label}\n")
    notice.write(f"Minisubs affected: {', '.join(plan['dark']) or 'none'}\n")
    notice.write(f"Stands affected ({summ['stands']}):\n  "
                 + ", ".join(str(r["stand"]) for r in rows) + "\n\n")
    notice.write("The remainder of the estate remains supplied"
                 + (" (back-fed via the ring break).\n" if plan["need_no_close"] else ".\n"))
    tag = label.replace(" ", "").replace(",", "-").replace("(", "").replace(")", "")
    d1, d2 = st.columns(2)
    d1.download_button("\u2b07 Affected stands (CSV)", csv,
                       file_name=f"TRD_outage_{tag}_{stamp}.csv", mime="text/csv",
                       use_container_width=True)
    d2.download_button("\u2b07 Outage notice (TXT)", notice.getvalue().encode(),
                       file_name=f"TRD_notice_{tag}_{stamp}.txt", mime="text/plain",
                       use_container_width=True)

st.caption("Gate House and estate-bulk loads sit on the bulk side of the ring and are not "
           "affected by minisub or ring-section isolation.")
