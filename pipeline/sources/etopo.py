from ..core.source import Source, SourceInfo

# ETOPO 2022 (15 arc-second) via NOAA ERDDAP, every 2nd pixel: a 30″ lattice (0.93 km north-south,
# 0.65-0.70 km east-west) over the map window, lon 18.0-23.8 °E, lat 41.4-46.6 °N.
DATASET = "ETOPO_2022_v1_15s"
PIXEL = 1 / 240
STRIDE = 2
STEP = STRIDE * PIXEL
LAT_IDX = (31536, 32782)  # pixel k is centred at -90 + (k + 0.5) * PIXEL
LON_IDX = (47520, 48910)  # ... and at -180 + (k + 0.5) * PIXEL
ROWS = (LAT_IDX[1] - LAT_IDX[0]) // STRIDE + 1
COLS = (LON_IDX[1] - LON_IDX[0]) // STRIDE + 1


def _lat(k: int) -> float:
    return -90 + (k + 0.5) * PIXEL


def _lon(k: int) -> float:
    return -180 + (k + 0.5) * PIXEL


URL = (
    f"https://coastwatch.pfeg.noaa.gov/erddap/griddap/{DATASET}.esriAscii?z"
    f"%5B({_lat(LAT_IDX[0]):.6f}):{STRIDE}:({_lat(LAT_IDX[1]):.6f})%5D"
    f"%5B({_lon(LON_IDX[0]):.6f}):{STRIDE}:({_lon(LON_IDX[1]):.6f})%5D"
)
FILE = f"etopo2022_15s_lat{LAT_IDX[0]}-{LAT_IDX[1]}_lon{LON_IDX[0]}-{LON_IDX[1]}_stride{STRIDE}.asc"


class Etopo(Source):
    info = SourceInfo(
        id="etopo",
        title="ETOPO 2022 global relief model (15 arc-second)",
        publisher="NOAA National Centers for Environmental Information (via the NOAA CoastWatch ERDDAP server)",
        homepage="https://www.ncei.noaa.gov/products/etopo-global-relief-model",
        license="Public domain (U.S. Government work). NOAA NCEI, 2022: ETOPO 2022 15 Arc-Second Global Relief "
        "Model, doi:10.25921/fd45-gt74",
        description="Land elevation (EGM2008 heights, from the Copernicus GLO-30 DEM on land) and Adriatic depth, "
        "on a 30″ lattice (every 2nd 15″ pixel, about 0.9 × 0.7 km) over the map window. Each hex's relief (flat, "
        "hills, mountains, peaks) comes from the mean and spread of the land samples inside it.",
        used_for=["Relief (hills, mountains)", "Hill-shading", "Sea depth"],
    )

    def fetch(self, force=False):
        self.download(URL, FILE, force=force)

    def process(self):
        with open(self.raw_dir / FILE, encoding="ascii") as f:
            header = dict(f.readline().split() for _ in range(6))
            nodata = float(header["nodata_value"])
            alt = [None if float(v) == nodata else round(float(v)) for line in f for v in line.split()]
        rows, cols = int(header["nrows"]), int(header["ncols"])
        if (rows, cols) != (ROWS, COLS) or len(alt) != rows * cols:
            raise ValueError(f"ETOPO grid is {cols}×{rows} with {len(alt)} values, expected {COLS}×{ROWS}")
        if abs(float(header["cellsize"]) - STEP) > 1e-9 or abs(float(header["yllcenter"]) - _lat(LAT_IDX[0])) > 1e-6:
            raise ValueError(f"unexpected ETOPO grid header {header}")
        if missing := alt.count(None):
            print(f"    warning: {missing} ETOPO samples are no-data")
        return {
            "vintage": "ETOPO 2022 v1, 15 arc-second, every 2nd pixel (30″)",
            "_files": [FILE],
            # Row-major lattice of pixel centres, north-west first: sample r * cols + c lies at
            # (lat0 + r * dlat, lon0 + c * dlon); alt in metres, null for no-data.
            "lat0": _lat(LAT_IDX[1]),
            "dlat": -STEP,
            "lon0": _lon(LON_IDX[0]),
            "dlon": STEP,
            "rows": rows,
            "cols": cols,
            "alt": alt,
        }
