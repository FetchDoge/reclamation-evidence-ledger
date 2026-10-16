# Provisional footprints — READ BEFORE USE

`pilot5_provisional.geojson` holds hand-digitized disturbance footprints for
5 pilot sites. They are **interpreter estimates, not authoritative boundaries.**

## How they were made (2026-09-27)

For each site, the latest clear Sentinel-2 scene's chip was rendered as a
false-colour composite (NIR→red, red→green, blue→blue) with the DLS LSD
centroid marked — see `interpretation/<site>_<date>_falsecolour.png`.
Polygons were drawn in chip pixel coordinates and converted to WGS84 via
the chip's UTM transform. Each feature's `source_crs` names the zone.

**Correction (2026-10-08):** two sites (16-14-018-26W4, 07-30-018-26W4) were
interpreted on Sentinel-2 tile 11UQS (UTM zone 11, EPSG:32611) but converted
with EPSG:32612, which put them exactly 6° of longitude east of their sites
(~-107.4°). They were re-converted with the correct zone and now sit at their
sites; shapes and confidence classes are unchanged. See each feature's
`crs_fix` note. A test checks every footprint lies within 1 km of its site.

Interpreter rule: disturbance = a contiguous low-vegetation (dark) patch
around the centroid, distinct from surrounding fields. Where no such patch
exists, the polygon traces the field parcel containing the centroid and
`disturbance_resolved=false`.

## What the confidence classes mean

- **medium** (1 site): a distinct disturbed patch is visible, but its boundary
  is gradational and the pad itself is not resolved at 10 m.
- **low** (4 sites): no discrete disturbance is visible. The polygon is an
  area of interest, not a footprint. Do not use as ground truth.

## What supersedes these

Any of: an AER reclamation application site plan, an OWA project boundary,
a licensed high-resolution survey, or on-the-ground GPS. When one arrives,
these files are replaced, not refined.

## What they must NOT be used for

- Not inputs to the assessment pipeline (nothing in `ledger/` reads this
  directory; that is deliberate).
- Not evidence of where a wellhead is.
- Not a basis for any claim about any operator.

They exist for one purpose: a bounded, documented starting geometry for the
BACI control-site design work, to be discarded the moment real footprints
arrive.
