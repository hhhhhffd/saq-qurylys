from typing import Any

from sqlalchemy import func

SRID = 4326


def make_point(lat: float | None, lon: float | None) -> Any:
    """SQL expression for a WGS84 point (assignable to a Geometry column), or None."""
    if lat is None or lon is None:
        return None
    return func.ST_SetSRID(func.ST_MakePoint(lon, lat), SRID)
