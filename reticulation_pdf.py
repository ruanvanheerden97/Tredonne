"""Generate the TreDonne site reticulation PDF from the current master sheet.

Run:  python reticulation_pdf.py
Output: reticulation/TRD_Reticulation_<date>.pdf  (newest = served by the app)

This produces a clean, data-accurate reticulation reference (ring topology +
full stand schedule per transformer). Replace it with the official signed SLD
by simply dropping that PDF into the reticulation/ folder - the app serves the
newest PDF it finds there.
"""
import os
import datetime as dt

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, Circle, Rectangle
from matplotlib.backends.backend_pdf import PdfPages

import engine
import topology as T

NAVY = "#243f5e"; NAVY_D = "#1a2d44"; GREEN = "#1E9E4A"; GOLD = "#E8860E"
GREY = "#5c6570"; RED = "#C0392B"; LIGHT = "#eaf0f6"
HERE = os.path.dirname(os.path.abspath(__file__))


def ring_page(pdf, stands):
    by = engine.stands_by_minisub(stands)
    fig = plt.figure(figsize=(16.5, 11.7))      # A3 landscape
    fig.suptitle("TreDonne Estate \u2014 Electrical Reticulation",
                 fontsize=20, fontweight="bold", color=NAVY_D, y=0.95)
    ax = fig.add_axes([0.04, 0.5, 0.92, 0.33]); ax.axis("off")
    order = T.RING_ORDER; n = len(order); xs = list(range(n))
    no = {T.NO_POINT[0], T.NO_POINT[1]}
    ax.set_xlim(-0.6, n - 0.4); ax.set_ylim(-1.1, 1.0)
    for i in range(n - 1):
        a, b = order[i], order[i + 1]
        is_no = {a, b} == no
        ax.plot([xs[i], xs[i + 1]], [0, 0],
                linestyle=(0, (2, 2)) if is_no else "-",
                color=GREY if is_no else NAVY, lw=2.6, zorder=1)
        if is_no:
            ax.text((xs[i] + xs[i + 1]) / 2, 0.5, "ring\nbreak", ha="center",
                    va="bottom", fontsize=9, color=GREY, fontweight="bold")
    for x, name in zip(xs, order):
        fc = GOLD if name in T.SOURCES else GREEN
        ax.add_patch(FancyBboxPatch((x - 0.44, -0.36), 0.88, 0.72,
                     boxstyle="round,pad=0.04", fc=fc, ec=NAVY_D, lw=1.2, zorder=3))
        ax.text(x, 0.0, name.replace("TRX", "T"), ha="center", va="center",
                fontsize=12, fontweight="bold", color="white", zorder=4)
        if name in by:
            ax.text(x, -0.66, f"{len(by[name])} stands", ha="center", va="center",
                    fontsize=9, color="#333", zorder=4)
    # summary
    ov = engine.transformer_overview(stands)
    tot_s = sum(o["stands"] for o in ov); tot_m = sum(o["meters"] for o in ov)
    tot_solar = sum(o["solar"] for o in ov); tot_pp = sum(o["prepaid"] for o in ov)
    ax2 = fig.add_axes([0.04, 0.3, 0.92, 0.16]); ax2.axis("off")
    ax2.text(0, 1.0,
             f"3300 V ring fed from two 315 kVA step-ups (TX01 / TX02), normally open "
             f"between {T.NO_POINT[0]} and {T.NO_POINT[1]}.",
             fontsize=11, color=NAVY_D, va="top")
    ax2.text(0, 0.6,
             f"9 distribution minisubs \u00b7 {tot_s} stands \u00b7 {tot_m} meters \u00b7 "
             f"{tot_solar} solar PV \u00b7 {tot_pp} prepaid.",
             fontsize=11, color="#333", va="top")
    ax2.text(0, 0.2,
             "LV isolators (400 V): " + ", ".join(f"{k} {v.split(' LV')[0]}"
                                                   for k, v in T.LV_ISOLATORS.items()),
             fontsize=10, color=GREY, va="top")
    stamp = dt.date.today().isoformat()
    fig.text(0.04, 0.06, "Voltano \u2014 generated from meter master sheet",
             fontsize=9, color=GREY)
    fig.text(0.96, 0.06, f"Issued {stamp}  \u00b7  reticulation reference",
             fontsize=9, color=GREY, ha="right")
    pdf.savefig(fig); plt.close(fig)


def schedule_pages(pdf, stands):
    by = engine.stands_by_minisub(stands)
    # flat ordered rows with transformer group headers
    entries = []  # ('header', trx) or ('row', data)
    for trx in T.MINISUBS:
        sts = by.get(trx, [])
        entries.append(("header", (trx, len(sts))))
        for st in sorted(sts, key=lambda s: str(s["erf"])):
            ph = {3: "3\u00d8", 1: "1\u00d8"}.get(st["phase"], "?")
            serials = " / ".join(m["serial"] for m in st["meters"])
            tariffs = "; ".join(sorted({m["tariff"] for m in st["meters"]}))
            entries.append(("row", (st["erf"], ph, serials, tariffs)))

    rows_per_page = 46
    cols = [("Transformer / Stand", 0.14), ("\u00d8", 0.05),
            ("Meter serial(s)", 0.26), ("Tariff(s)", 0.55)]
    i = 0
    page_no = 0
    while i < len(entries):
        page_no += 1
        fig = plt.figure(figsize=(16.5, 11.7))
        ax = fig.add_axes([0.04, 0.05, 0.92, 0.9]); ax.axis("off")
        ax.set_xlim(0, 1); ax.set_ylim(0, 1)
        ax.text(0, 0.99, f"Reticulation Schedule  (page {page_no})",
                fontsize=14, fontweight="bold", color=NAVY_D, va="top")
        xe = [0.0]
        for _, f in cols:
            xe.append(xe[-1] + f)
        y = 0.95
        rh = 0.95 / rows_per_page
        # column header
        ax.add_patch(Rectangle((0, y - rh), 1, rh, fc=NAVY, ec="none"))
        for c, (nm, _) in enumerate(cols):
            ax.text(xe[c] + 0.004, y - rh / 2, nm, fontsize=9, fontweight="bold",
                    color="white", va="center")
        y -= rh
        drawn = 0
        while i < len(entries) and drawn < rows_per_page:
            kind, data = entries[i]
            if kind == "header":
                trx, ns = data
                ax.add_patch(Rectangle((0, y - rh), 1, rh, fc=LIGHT, ec="none"))
                ax.text(0.004, y - rh / 2, f"{trx}  \u2014  {ns} stands"
                        + (f"   (LV isolator {T.LV_ISOLATORS[trx].split(' LV')[0]})"
                           if trx in T.LV_ISOLATORS else ""),
                        fontsize=9.5, fontweight="bold", color=NAVY_D, va="center")
            else:
                erf, ph, serials, tariffs = data
                if drawn % 2 == 0:
                    ax.add_patch(Rectangle((0, y - rh), 1, rh, fc="#f6f8fb", ec="none"))
                ax.text(xe[0] + 0.012, y - rh / 2, str(erf), fontsize=8.5,
                        color="#222", va="center")
                ax.text(xe[1] + 0.004, y - rh / 2, ph, fontsize=8.5, va="center",
                        color="#222")
                ax.text(xe[2] + 0.004, y - rh / 2, serials, fontsize=8, va="center",
                        color="#222")
                ax.text(xe[3] + 0.004, y - rh / 2, tariffs, fontsize=8, va="center",
                        color="#222")
            y -= rh
            i += 1
            drawn += 1
        fig.text(0.96, 0.025, "TreDonne reticulation schedule \u00b7 Voltano",
                 fontsize=8, color=GREY, ha="right")
        pdf.savefig(fig); plt.close(fig)


def generate(sheet_path=None, out_dir=None):
    sheet_path = sheet_path or os.path.join(HERE, "data", "TRD_master.xlsx")
    out_dir = out_dir or os.path.join(HERE, "reticulation")
    os.makedirs(out_dir, exist_ok=True)
    stands, _ = engine.load_meters(sheet_path)
    stamp = dt.date.today().isoformat()
    out = os.path.join(out_dir, f"TRD_Reticulation_{stamp}.pdf")
    with PdfPages(out) as pdf:
        ring_page(pdf, stands)
        schedule_pages(pdf, stands)
    print("wrote", out)
    return out


if __name__ == "__main__":
    generate()
