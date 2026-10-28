# Stage 3 — Basis Construction (`basis.py`, `clustering.py`)

The daily fit (stage 4) needs, for each day, a 24×(1+k) matrix
`Base = [ones(24) | b_1 … b_k]` where each `b_j` is a 24-h class shape,
**demeaned and L2-normalized** (`b = (x - mean(x)) / ||x - mean(x)||`;
note MATLAB normalizes by `norm(tmp)` AFTER demeaning — order matters).
The ones column is NOT normalized. Three source families:

## A. NYSEG source (MISO, NYISO, NEISO, FRCC)

`profiles_aggregate` (24×36×9): hour × day-type (calendar stage 2) × class.
Basis columns = slices **[2, 3, 5]** (1-based MATLAB): slice 2 = residential
shape, slices 3 & 5 = commercial/industrial shapes. So k=3 and
`Base = [ones | agg[:, daytype, 2] | agg[:, daytype, 3] | agg[:, daytype, 5]]`.
Class-role mapping used by stage 4: col 1 (index 1) = residential, cols 2–3 =
com/ind. Dead code in every script references an older 11-column scheme.

## B. NREL source (AZNM, NWPP, SPP, SRMV, SRTV, SRVC, RFCE)

Per state, one city's 17 building profiles (16 DOE reference buildings + TMY
weather-derived series ×1000) are combined into **10 frozen aggregate groups**
(`profiles_aggregate_XX(:,:,g) = mean of member profiles`, group 10 = the TMY
series ≈ "residential"). The groups were hand-derived from a one-time
hierarchical clustering — **frozen as per-region config** (decision D7).
The basis uses 3 selected group indices per state (e.g. SRVC: DE=[10 5 6],
MD=[10 2 6] — first = residential, next two = com/ind), and the day's own
24-h slice of the full-year 8760 aggregate: k=3,
`Base = [ones | agg[d24, g_res] | agg[d24, g_c1] | agg[d24, g_c2]]`.
The calendar is NOT used (dead code there).

### The clustering that produced the groups (optional analysis tool)

For each city: Y (8760×17) = per-day demeaned/normalized profile slices;
`R = (Y'Y)[1:16,1:16]` (17th excluded) is a building-type correlation matrix;
MATLAB `clusterdata(R, 9)` = agglomerative single-linkage, euclidean distance
on the ROWS of R, cut at 9 clusters ("cutoff" semantics: MaxClust=9).
Python equivalent (analysis only):
`scipy.cluster.hierarchy.linkage(R, method="single")` +
`fcluster(Z, t=9, criterion="maxclust")`. Results informed but do not equal
the hand-tuned groups; production path always uses frozen config.

## C. Utility source (CAISO, RFCW)

365×24 day-by-hour class profiles indexed by **calendar day** (not day-type):
- CAISO: PG&E rate schedules — a1-2000.csv (small commercial), a10-2000.csv
  (medium/industrial), e1-2000.csv (residential). Basis col order:
  [ones | com | ind | res] — **residential is column 4** here (config maps
  roles by name, never by position).
- RFCW: Ohio Power Co. (OPC) com/ind/res 365×24 matrices used for ALL three
  states (IN, MI, OH). CSP profiles are read but comparison-only.

## Python design

```python
class BasisSource(Protocol):
    def day_basis(self, day: int, day_type: int) -> np.ndarray  # (24, 1+k)
    @property
    def roles(self) -> tuple[Role, ...]   # semantic role of each basis column

NYSEGBasis(profiles, columns=(2,3,5), roles=(RES, CI, CI))
NRELAggregateBasis(city_profiles, groups=frozen_config, use=(10,5,6), roles=(RES, CI, CI))
UtilityBasis(profiles_by_class, roles=(CI, CI, RES))   # order per region config
```

Normalization is applied inside `day_basis` exactly as MATLAB does (demean →
L2-normalize each non-trend column, per day).
