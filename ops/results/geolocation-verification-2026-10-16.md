# How many OWA sites have a verified surveyed location? (re-verified 2026-10-16)

Command: `python -m ledger.geolocate resolve --owa owa_2026-10-01.xlsx --st37 ST_37_Excel.zip --out geo.parquet`
(current `rebuild-stage0` code, run a second time from scratch).
Inputs: OWA inventory 2026-10-01, sha256 `4e877df60c20b086ed9742abd0f3fc23e074e28a240c8577a4170f975e07bbd0`;
AER ST37 Excel package, 183,921,877 bytes, sha256 `da4918f4900d2cd45e14963b19c73b4863d9851b25e769d19ccb6e6cbc63afdb`
(AER Last-Modified 2026-10-01).

**22,057 inventory sites: 21,340 verified (96.7%), 717 location unverified.** Both runs gave identical counts.
"Verified" = the OWA licence number joins to an ST37 surface-hole coordinate inside Alberta and the ST37 location label
agrees with the OWA site name at section/township/range. It means the licensed surface hole is pinned (nominal 100 m, a
configured bound, not a measured per-site error). It does **not** mean a pad is visible at 10 m or that the site was imaged.

Unverified reasons (a site can carry several flags): ST37 label disagrees with site name 328; component is not a well 310;
no licence number 41; licence not in ST37 31; bad coordinate 7. (A further 51 verified sites carry the non-blocking flag "LSD differs within the same section".) Full counts: `geolocation-audit-all-owa-inventory-2026-10-01.json`.
All 99 pilot sites are verified; the old DLS geocoder was a median 2,405 m from them (`geolocation-audit-pilot99-2026-10-16.json`).
