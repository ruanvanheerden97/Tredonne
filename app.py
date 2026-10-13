"""TreDonne Estate - Site Management app (Streamlit).

Three sections:
  * Outage Planner  - isolate minisub(s) or an MV ring section, get the
                      switching plan and the list of affected stands.
  * Reticulation    - view / download the latest site reticulation PDF.
  * Transformers    - click a transformer to see every stand on it with full
                      meter detail.

Run:  streamlit run app.py
"""
import io
import os
import glob
import datetime as dt

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Circle
import pandas as pd
import streamlit as st

try:
    import pymupdf
except ImportError:  # older installs expose it as fitz
    import fitz as pymupdf

import engine
import topology as T

NAVY = "#243f5e"; GREEN = "#1E9E4A"; RED = "#C0392B"; GREY = "#7a828b"; GOLD = "#E8860E"
HERE = os.path.dirname(os.path.abspath(__file__))
DATA_DEFAULT = os.path.join(HERE, "data", "TRD_master.xlsx")
RETIC_DIR = os.path.join(HERE, "reticulation")

st.set_page_config(page_title="TreDonne Site Management", page_icon="\u26a1", layout="wide")


@st.cache_data(show_spinner=False)
def _load(source):
    if isinstance(source, (bytes, bytearray)):
        source = io.BytesIO(source)
    return engine.load_meters(source)


@st.cache_data(show_spinner=False)
def _render_pdf(data: bytes, dpi: int = 120):
    doc = pymupdf.open(stream=data, filetype="pdf")
    pages = [doc.load_page(i).get_pixmap(dpi=dpi).tobytes("png")
             for i in range(doc.page_count)]
    doc.close()
    return pages


def latest_reticulation_pdf():
    pdfs = sorted(glob.glob(os.path.join(RETIC_DIR, "*.pdf")),
                  key=os.path.getmtime, reverse=True)
    return pdfs[0] if pdfs else None


# ------------------------------------------------------------------- ring figure
def ring_figure(dark=(), no_closed=False, open_edge=None, highlight=None):
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
            style = "-" if no_closed else (0, (2, 2)); col = GREEN if no_closed else GREY
        else:
            style = (0, (1, 2)) if (a in dark or b in dark) else "-"
            col = RED if (a in dark or b in dark) else NAVY
        ax.plot([xs[i], xs[i + 1]], [0, 0], linestyle=style, color=col, lw=2.4, zorder=1)
        if is_no:
            ax.text((xs[i] + xs[i + 1]) / 2, 0.52,
                    "break\nCLOSED" if no_closed else "break\nopen", ha="center",
                    va="bottom", fontsize=7, color=GREEN if no_closed else GREY,
                    fontweight="bold")
        if is_cut:
            ax.text((xs[i] + xs[i + 1]) / 2, 0.52, "cable\nISOLATED", ha="center",
                    va="bottom", fontsize=7, color=RED, fontweight="bold")
    for x, name in zip(xs, order):
        if name in T.SOURCES:
            fc, tc = GOLD, "white"
        elif name in dark:
            fc, tc = RED, "white"
        else:
            fc, tc = GREEN, "white"
        ec, lw = ("#1a2d44", 1.0)
        if highlight and name == highlight:
            ec, lw = (GOLD, 2.6)
        ax.add_patch(FancyBboxPatch((x - 0.42, -0.34), 0.84, 0.68,
                     boxstyle="round,pad=0.04", fc=fc, ec=ec, lw=lw, zorder=3))
        ax.text(x, 0.02, name.replace("TRX", "T"), ha="center", va="center",
                fontsize=8.5, fontweight="bold", color=tc, zorder=4)
        cnt = BY.get(name)
        if cnt:
            ax.text(x, -0.62, f"{len(cnt)}", ha="center", va="center", fontsize=7,
                    color="#333", zorder=4)
    for lx, (c, lab) in zip([n - 3.3, n - 2.2, n - 1.1],
                            [(GREEN, "live"), (RED, "dark/cut"), (GOLD, "source")]):
        ax.add_patch(Circle((lx, 1.2), 0.08, fc=c, ec="none"))
        ax.text(lx + 0.14, 1.2, lab, va="center", fontsize=7)
    fig.tight_layout()
    return fig


# ===================================================================== sidebar
st.sidebar.title("\u26a1 TreDonne")
st.sidebar.caption("Site Management")
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
        st.success(f"{len(stands)} stands \u00b7 {len(T.MINISUBS)} minisubs")
    except Exception as e:  # noqa
        st.error(f"Could not read sheet: {e}")
        st.stop()
    st.markdown("---")
    section = st.radio("Section",
                       ["Outage Planner", "Reticulation drawing", "Transformer explorer"])

BY = engine.stands_by_minisub(stands)


# ===================================================================== sections
def section_outage():
    st.title("Outage Planner")
    st.caption("Choose what to isolate; the planner keeps the rest of the estate alive "
               "where the ring allows and lists every stand that loses power.")
    st.subheader("1 \u00b7 What are you isolating?")
    mode = st.radio("Isolation type",
                    ["Minisub(s) \u2013 transformer / kiosk work",
                     "MV ring section \u2013 cable work"],
                    horizontal=True, label_visibility="collapsed")
    open_edge = None
    if mode.startswith("Minisub"):
        c1, c2 = st.columns([2, 1])
        targets = c1.multiselect("Minisub(s) to take out of service", options=T.MINISUBS,
                                 format_func=lambda m: f"{m}  ({len(BY.get(m, []))} stands)")
        lv_only = c2.checkbox("LV-side work only",
                              help="Use the 400 V isolator where fitted; transformer & ring stay live.")
        if not targets:
            st.info("Select at least one minisub to see the outage plan.")
            return
        plan = engine.plan_isolation(targets, lv_only=lv_only)
        label = ", ".join(targets) + ("  (LV-side only)"
                if lv_only and all(t in T.LV_ISOLATORS for t in targets) else "")
    else:
        sec = st.selectbox("MV ring-cable section to isolate", options=engine.ring_sections(),
                           format_func=lambda s: f"{s[0]}  \u2194  {s[1]}")
        plan = engine.plan_section(sec); open_edge = sec
        label = f"cable {sec[0]}\u2013{sec[1]}"

    rows = engine.affected_stands(plan["dark"], stands)
    summ = engine.summary(rows)

    st.subheader("2 \u00b7 Feed status")
    m = st.columns(4)
    m[0].metric("Minisubs dark", len(plan["dark"]))
    m[1].metric("Stands affected", summ["stands"])
    m[2].metric("Meters affected", summ["meters"])
    m[3].metric("Rest of estate", f"{len(T.MINISUBS) - len(plan['dark'])} live")
    st.pyplot(ring_figure(plan["dark"], plan["need_no_close"], open_edge),
              use_container_width=True)
    for w in plan["warnings"]:
        st.warning(w)

    st.subheader("3 \u00b7 Switching plan")
    if plan["need_no_close"]:
        st.markdown(f"**Ring break must be CLOSED** to keep "
                    f"**{', '.join(plan['collateral'])}** alive (back-fed from the other source).")
    for i, step in enumerate(plan["steps"], 1):
        st.markdown(f"**{i}.** {step}")
    st.caption("Planning aid only. MV switching by your authorised MV operator under your "
               "switching procedure. LV isolators drop the 400 V load only.")

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
        sc[0].caption(f"3\u00d8: **{summ['three_phase']}**")
        sc[1].caption(f"1\u00d8: **{summ['single_phase']}**")
        sc[2].caption(f"Solar: **{summ['solar']}**")
        sc[3].caption(f"Prepaid: **{summ['prepaid']}**")
        stamp = dt.date.today().isoformat()
        notice = (f"{T.ESTATE_NAME} - PLANNED ELECTRICITY INTERRUPTION\n"
                  f"Date issued: {stamp}\nWork on: {label}\n"
                  f"Minisubs affected: {', '.join(plan['dark']) or 'none'}\n"
                  f"Stands affected ({summ['stands']}):\n  "
                  + ", ".join(str(r['stand']) for r in rows) + "\n")
        tag = label.replace(" ", "").replace(",", "-")
        d1, d2 = st.columns(2)
        d1.download_button("\u2b07 Affected stands (CSV)", df.to_csv(index=False).encode(),
                           file_name=f"TRD_outage_{tag}_{stamp}.csv", use_container_width=True)
        d2.download_button("\u2b07 Outage notice (TXT)", notice.encode(),
                           file_name=f"TRD_notice_{tag}_{stamp}.txt", use_container_width=True)
    st.caption("Gate House and estate-bulk loads sit on the bulk side and are not affected.")


def section_reticulation():
    st.title("Site Reticulation Drawing")
    st.caption("The latest single-line / reticulation drawing for the estate.")
    view = st.radio("Show", ["Latest on file", "Open another PDF"], horizontal=True,
                    label_visibility="collapsed")
    data = None
    name = None
    if view == "Latest on file":
        path = latest_reticulation_pdf()
        if not path:
            st.info("No reticulation PDF on file yet. Drop the latest drawing into the "
                    "`reticulation/` folder (or run `python reticulation_pdf.py` to build "
                    "one from the master sheet), or use **Open another PDF**.")
            return
        with open(path, "rb") as fh:
            data = fh.read()
        name = os.path.basename(path)
        st.caption(f"Showing **{name}** \u00b7 updated "
                   f"{dt.datetime.fromtimestamp(os.path.getmtime(path)):%Y-%m-%d}")
    else:
        pu = st.file_uploader("Open a reticulation PDF", type=["pdf"])
        if not pu:
            st.stop()
        data, name = pu.getvalue(), pu.name

    st.download_button("\u2b07 Download PDF", data, file_name=name or "TRD_Reticulation.pdf",
                       mime="application/pdf", type="primary")
    try:
        for png in _render_pdf(data, dpi=120):
            st.image(png, use_container_width=True)
    except Exception as e:  # noqa
        st.warning(f"Could not render a preview ({e}). Use the download button above.")


def section_explorer():
    st.title("Transformer Explorer")
    st.caption("Click a transformer to see every stand connected to it, with full meter detail.")

    if "sel_trx" not in st.session_state:
        st.session_state.sel_trx = T.MINISUBS[0]

    # clickable transformer buttons (two rows)
    ov = {o["minisub"]: o for o in engine.transformer_overview(stands)}
    rowa = st.columns(5)
    rowb = st.columns(5)
    for i, trx in enumerate(T.MINISUBS):
        col = (rowa if i < 5 else rowb)[i % 5]
        if col.button(f"{trx}\n{ov[trx]['stands']} stands",
                      key=f"b_{trx}", use_container_width=True,
                      type="primary" if st.session_state.sel_trx == trx else "secondary"):
            st.session_state.sel_trx = trx

    sel = st.session_state.sel_trx
    st.pyplot(ring_figure(highlight=sel), use_container_width=True)

    o = ov[sel]
    st.subheader(f"{sel}")
    mc = st.columns(5)
    mc[0].metric("Stands", o["stands"])
    mc[1].metric("Meters", o["meters"])
    mc[2].metric("3\u00d8 / 1\u00d8", f"{o['three_phase']} / {o['single_phase']}")
    mc[3].metric("Solar PV", o["solar"])
    mc[4].metric("Prepaid", o["prepaid"])
    if o["lv_isolator"]:
        st.caption(f"LV isolator fitted: **{o['lv_isolator']}** (400 V side).")
    else:
        st.caption("No LV isolator \u2014 full isolation is by MV cable disconnection.")

    detail = engine.transformer_detail(sel, stands)
    df = pd.DataFrame(detail).rename(columns={
        "stand": "Stand", "phase": "\u00d8", "serial": "Meter serial",
        "tariff": "Tariff", "role": "Meter role", "solar": "Solar", "prepaid": "Prepaid"})
    st.dataframe(df, use_container_width=True, hide_index=True)
    st.download_button(f"\u2b07 {sel} stands (CSV)", df.to_csv(index=False).encode(),
                       file_name=f"TRD_{sel}_stands.csv")

    with st.expander("All transformers \u2014 overview"):
        ovdf = pd.DataFrame(engine.transformer_overview(stands)).rename(columns={
            "minisub": "Transformer", "stands": "Stands", "meters": "Meters",
            "three_phase": "3\u00d8", "single_phase": "1\u00d8", "solar": "Solar",
            "prepaid": "Prepaid", "lv_isolator": "LV isolator"})
        st.dataframe(ovdf, use_container_width=True, hide_index=True)


if section == "Outage Planner":
    section_outage()
elif section == "Reticulation drawing":
    section_reticulation()
else:
    section_explorer()
