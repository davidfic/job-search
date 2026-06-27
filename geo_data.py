"""
geo_data - static geography for the jobhunt map.

Two things live here, both hand-maintained so the app needs no geocoding service
and works offline:

  GAZETTEER  -- neighborhood/town/square name -> (lat, lng). Ordered most-specific
                first so a listing in "Davis Square, Somerville" resolves to Davis
                (a precise point) rather than the Somerville centroid.
  TRANSIT    -- the rail/bus lines drawn on the map: MBTA Red Line, the Green Line
                E branch out of Medford/Tufts through Ball Square, and the key
                Davis-area bus routes (87/88/89/94/96). Coordinates are the line's
                stations/timepoints in order; the frontend connects them.

Coordinates are approximate (good to ~a block) -- plenty for placing a job pin or
sketching a transit line, not survey-grade.
"""

HOME = {"name": "Davis Square (home base)", "lat": 42.3967, "lng": -71.1218}

# Ordered most-specific -> least-specific. First substring hit wins, so squares
# and stations come before the broad city/neighborhood names.
GAZETTEER = [
    # --- Walkable squares right around Davis ---
    ("davis", 42.3967, -71.1218),
    ("teele", 42.4030, -71.1265),
    ("ball square", 42.4072, -71.1066),
    ("ball sq", 42.4072, -71.1066),
    ("magoun", 42.4039, -71.1019),
    ("powderhouse", 42.4006, -71.1142),
    ("powder house", 42.4006, -71.1142),
    ("college ave", 42.4045, -71.1190),
    ("west somerville", 42.4017, -71.1226),
    ("tufts", 42.4075, -71.1190),
    ("medford/tufts", 42.4080, -71.1186),
    # --- Nearby squares / stations ---
    ("porter", 42.3884, -71.1190),
    ("union square", 42.3793, -71.0954),
    ("union sq", 42.3793, -71.0954),
    ("inman", 42.3739, -71.1010),
    ("gilman", 42.3990, -71.0951),
    ("east somerville", 42.3920, -71.0866),
    ("assembly", 42.3927, -71.0773),
    ("sullivan", 42.3838, -71.0769),
    ("harvard", 42.3736, -71.1190),
    ("central square", 42.3654, -71.1037),
    ("central sq", 42.3654, -71.1037),
    ("kendall", 42.3625, -71.0862),
    ("mit", 42.3601, -71.0942),
    ("alewife", 42.3954, -71.1418),
    ("lechmere", 42.3706, -71.0768),
    ("east cambridge", 42.3720, -71.0780),
    ("north cambridge", 42.3960, -71.1290),
    ("charlestown", 42.3782, -71.0602),
    # --- Boston districts ---
    ("downtown crossing", 42.3555, -71.0603),
    ("financial district", 42.3559, -71.0550),
    ("south station", 42.3519, -71.0552),
    ("back bay", 42.3503, -71.0810),
    ("beacon hill", 42.3588, -71.0707),
    ("fenway", 42.3429, -71.0975),
    ("allston", 42.3539, -71.1337),
    ("brighton", 42.3464, -71.1627),
    ("downtown", 42.3559, -71.0603),
    # --- Towns / cities (broadest) ---
    ("somerville", 42.3876, -71.0995),
    ("cambridge", 42.3736, -71.1097),
    ("medford", 42.4184, -71.1062),
    ("arlington", 42.4154, -71.1565),
    ("malden", 42.4251, -71.0662),
    ("everett", 42.4084, -71.0537),
    ("chelsea", 42.3917, -71.0328),
    ("boston", 42.3601, -71.0589),
]


def resolve(*texts):
    """Resolve the first matching place from the given text fields (checked in
    order, e.g. location then title). Returns {lat, lng, matched, remote} or None
    when nothing is recognized. 'remote' is flagged but carries no coordinates."""
    blob = " ".join(t for t in texts if t).lower()
    if not blob:
        return None
    remote = "remote" in blob
    for name, lat, lng in GAZETTEER:
        if name in blob:
            return {"lat": lat, "lng": lng, "matched": name, "remote": remote}
    if remote:
        return {"lat": None, "lng": None, "matched": "remote", "remote": True}
    return None


# Each line: stations/timepoints in order. The frontend draws a polyline through
# them and a small dot per stop. Colors are official MBTA line colors.
TRANSIT = {
    "red": {
        "name": "Red Line",
        "color": "#DA291C",
        "kind": "subway",
        "stops": [
            ["Alewife", 42.3954, -71.1418],
            ["Davis", 42.3967, -71.1218],
            ["Porter", 42.3884, -71.1190],
            ["Harvard", 42.3736, -71.1190],
            ["Central", 42.3654, -71.1037],
            ["Kendall/MIT", 42.3625, -71.0862],
            ["Charles/MGH", 42.3612, -71.0707],
            ["Park Street", 42.3564, -71.0624],
            ["Downtown Crossing", 42.3555, -71.0603],
            ["South Station", 42.3519, -71.0552],
            ["Broadway", 42.3425, -71.0568],
            ["Andrew", 42.3301, -71.0573],
            ["JFK/UMass", 42.3206, -71.0524],
        ],
    },
    "green_e": {
        "name": "Green Line E (Medford/Tufts – Heath St)",
        "color": "#00843D",
        "kind": "subway",
        "stops": [
            ["Medford/Tufts", 42.4080, -71.1186],
            ["Ball Square", 42.4072, -71.1066],
            ["Magoun Square", 42.4039, -71.1019],
            ["Gilman Square", 42.3990, -71.0951],
            ["East Somerville", 42.3920, -71.0866],
            ["Lechmere", 42.3706, -71.0768],
            ["Science Park/West End", 42.3667, -71.0676],
            ["North Station", 42.3656, -71.0610],
            ["Haymarket", 42.3634, -71.0586],
            ["Government Center", 42.3596, -71.0593],
            ["Park Street", 42.3564, -71.0624],
            ["Boylston", 42.3525, -71.0644],
            ["Arlington", 42.3519, -71.0707],
            ["Copley", 42.3500, -71.0775],
            ["Prudential", 42.3454, -71.0819],
            ["Symphony", 42.3429, -71.0853],
            ["Northeastern", 42.3399, -71.0892],
            ["Museum of Fine Arts", 42.3376, -71.0950],
            ["Longwood Medical", 42.3360, -71.1006],
            ["Brigham Circle", 42.3343, -71.1046],
            ["Heath Street", 42.3282, -71.1118],
        ],
    },
    "bus_87": {
        "name": "Bus 87 · Arlington Ctr / Clarendon Hill – Lechmere",
        "color": "#FFC72C",
        "kind": "bus",
        "stops": [
            ["Arlington Center", 42.4154, -71.1565],
            ["Clarendon Hill", 42.4030, -71.1320],
            ["Davis", 42.3967, -71.1218],
            ["Somerville Ave", 42.3865, -71.1040],
            ["Union Square", 42.3793, -71.0954],
            ["Lechmere", 42.3706, -71.0768],
        ],
    },
    "bus_88": {
        "name": "Bus 88 · Clarendon Hill – Lechmere (Highland Ave)",
        "color": "#FFC72C",
        "kind": "bus",
        "stops": [
            ["Clarendon Hill", 42.4030, -71.1320],
            ["Davis", 42.3967, -71.1218],
            ["Highland Ave", 42.3905, -71.1080],
            ["Somerville City Hall", 42.3876, -71.0995],
            ["Gilman Square", 42.3990, -71.0951],
            ["Lechmere", 42.3706, -71.0768],
        ],
    },
    "bus_89": {
        "name": "Bus 89 · Clarendon Hill / Davis – Sullivan (Broadway)",
        "color": "#FFC72C",
        "kind": "bus",
        "stops": [
            ["Clarendon Hill", 42.4030, -71.1320],
            ["Davis", 42.3967, -71.1218],
            ["Ball Square", 42.4072, -71.1066],
            ["Magoun Square", 42.4039, -71.1019],
            ["Broadway", 42.3920, -71.0905],
            ["Sullivan Square", 42.3838, -71.0769],
        ],
    },
    "bus_94": {
        "name": "Bus 94 · Medford Square – Davis (Boston Ave)",
        "color": "#FFC72C",
        "kind": "bus",
        "stops": [
            ["Medford Square", 42.4184, -71.1062],
            ["Boston Ave", 42.4115, -71.1140],
            ["Tufts", 42.4075, -71.1190],
            ["College Ave", 42.4045, -71.1190],
            ["Davis", 42.3967, -71.1218],
        ],
    },
    "bus_96": {
        "name": "Bus 96 · Medford Square – Harvard (via Davis)",
        "color": "#FFC72C",
        "kind": "bus",
        "stops": [
            ["Medford Square", 42.4184, -71.1062],
            ["George St", 42.4080, -71.1160],
            ["Davis", 42.3967, -71.1218],
            ["North Cambridge", 42.3960, -71.1290],
            ["Porter", 42.3884, -71.1190],
            ["Harvard", 42.3736, -71.1190],
        ],
    },
}
