"""TreDonne Estate ring topology and isolation hardware.

Edit this file if the network changes. The outage engine reads it directly.
All logic downstream is driven by RING_ORDER, NO_POINT, SOURCES and LV_ISOLATORS.
"""

# The two step-up transformers that feed the 3300 V ring (both normally live).
# (Labelled TRX A01 / TRX B02 on the single-line diagram.)
SOURCES = ["TX01", "TX02"]

# The ring written out as one open loop from TX01 to TX02, in physical order.
#   TX01 - TRX08 - TRX09 - TRX05 - TRX01 - TRX02 - TRX03 -//NO//- TRX04 - TRX06 - TRX07 - TX02
RING_ORDER = [
    "TX01", "TRX08", "TRX09", "TRX05", "TRX01", "TRX02", "TRX03",
    "TRX04", "TRX06", "TRX07", "TX02",
]

# The normally-open point on the ring (the "ring break").
NO_POINT = ("TRX03", "TRX04")

# The nine distribution minisubs (ring nodes that carry load).
MINISUBS = ["TRX01", "TRX02", "TRX03", "TRX04", "TRX05",
            "TRX06", "TRX07", "TRX08", "TRX09"]

# Minisubs fitted with a 400 V LV-side isolator (MCCB at the back of the unit).
# These isolate the LV load ONLY - transformer and MV ring stay live.
# Any minisub without an entry here can only be isolated by physically
# disconnecting its 3300 V A/B/C ring cables (full MV isolation).
LV_ISOLATORS = {
    "TRX01": "125 A 3-phase LV isolator",
    "TRX05": "250 A LV isolator",
    "TRX07": "125 A LV isolator",
    "TRX08": "125 A LV isolator",
}

# Special loads that do not hang off a ring minisub.
#   Gate House is fed from the estate bulk side, so ring switching never affects it.
SPECIAL_LOADS = {
    "Gate House": {"serial": "67573357", "fed_from": "Estate bulk (Bulk/TRD)"},
}

ESTATE_NAME = "TreDonne Estate"
ESTATE_BULK_SN = "83013899"
