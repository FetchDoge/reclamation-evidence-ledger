"""Single source of pipeline defaults. Override via environment or CLI flags."""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env_flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Config:
    # Area of interest: square buffer around each site, in metres.
    aoi_buffer_m: float = 500.0

    # Growing-season discipline: only compare these months to each other.
    # Alberta snow (Nov-Mar) makes winter comparisons meaningless.
    growing_months: tuple = (5, 6, 7, 8, 9)

    # A scene is usable only if this fraction of AOI pixels is clear.
    min_clear_fraction: float = 0.6

    # Baseline = median of this many prior growing seasons.
    baseline_years: int = 3

    # Recovery signal: NDVI must rise by at least this vs baseline to flag
    # "recovering"; fall by at least this to flag "stalled".
    ndvi_recover_delta: float = 0.08
    ndvi_stall_delta: float = -0.08

    # STAC endpoint for Sentinel-2 L2A. AWS sentinel-cogs needs no key.
    stac_url: str = "https://earth-search.aws.element84.com/v1"
    collection: str = "sentinel-2-l2a"

    # TLS verification is ON by default. Some sandboxed networks terminate
    # TLS at an egress proxy whose CA GDAL's bundled OpenSSL does not trust;
    # there, and only there, an operator may opt in to GDAL_HTTP_UNSAFESSL by
    # setting LEDGER_TRUST_EGRESS_PROXY_TLS=1. Packets built while this is on
    # say so in their caveats; packets built with it off do not carry that
    # caveat. Only public satellite pixels transit this path.
    trust_egress_proxy_tls: bool = field(
        default_factory=lambda: _env_flag("LEDGER_TRUST_EGRESS_PROXY_TLS")
    )

    data_dir: str = "data"
    packets_dir: str = "packets"
    public_dir: str = "public"

    # Sentinel-2 scene classification (SCL) values to mask as unusable.
    scl_mask_values: tuple = field(default=(3, 8, 9, 10))  # shadow, cloud x2, cirrus
    scl_snow_value: int = 11  # snow: not masked, but flagged (seasonal caveat)


DEFAULT = Config()
