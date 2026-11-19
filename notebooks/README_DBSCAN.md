# DBSCAN Baseline — Dubai Metro Station Profiling

## Overview

This document describes the density-based clustering baseline implemented in [`04_dbscan.ipynb`](04_dbscan.ipynb) for the **Dubai Metro Station Profiling** project.

The notebook applies **DBSCAN (Density-Based Spatial Clustering of Applications with Noise)** to station usage profiles. Unlike methods requiring a predefined number of clusters, DBSCAN groups observations in dense regions and assigns the label `-1` to observations that do not belong to a dense group.

The method is a **behavioural baseline** for comparison with K-means, hierarchical clustering, spectral clustering and the proposed ST-GRSC method. It does **not** cluster physical station coordinates or use the planned spatio-temporal graph.

## Dataset and input

- **Unit of analysis:** one Dubai Metro station in one study window (a *station-window observation*).
- **Input data:** standardized features exported from the project's AWS Athena `dubai_metro.features` table.
- **Sample used in the current run:** 244 station-window observations.
- **Clustering inputs:** 17 numerical features, divided into:
  - 5 check-in time-band shares;
  - 5 check-out time-band shares;
  - 5 time-band net-flow features;
  - 1 weekend share;
  - 1 volume share.

Station names, IDs, study windows and passenger totals are retained for interpretation but **not used as clustering features**.

The upstream feature table has already been standardized. The notebook **does not standardize it again**.

### Expected input location

From the repository root:

```text
results/aws_features_export.csv
```

The CSV is a **local input** and is not included in the DBSCAN commit. Export the standardized `features` table from the project's existing AWS/Athena pipeline before running the notebook. Once the CSV is available, the notebook runs locally without making AWS API calls or requiring credentials.

## Requirements

- Python with Jupyter notebook support (`ipykernel`)
- `numpy`
- `pandas`
- `scikit-learn`
- `matplotlib`

Use an existing Python environment with these packages installed. No additional virtual environment is needed specifically for this notebook.

## Running the notebook

1. Open the **repository root** in VS Code or Jupyter.
2. Confirm that `results/aws_features_export.csv` exists.
3. Open `notebooks/04_dbscan.ipynb`.
4. Select a Python kernel containing the required packages.
5. Run all cells in order.

The notebook can locate the CSV whether the Jupyter working directory is the repository root or the `notebooks/` directory. Its generated files are saved under `results/dbscan/`.

## Methodology

### 1. Feature validation

The notebook loads the CSV, selects the specified 17 features, verifies that the numerical values are finite and checks for duplicate `(win, location_id)` observations.

### 2. DBSCAN parameters

DBSCAN uses **Euclidean distance** over the 17 standardized behavioural features.

- **`eps`:** maximum neighbourhood radius. Very small values may mark many observations as noise; very large values may merge distinct groups.
- **`min_samples` (minPts):** minimum number of observations in an `eps` neighbourhood, including the observation itself, needed to identify a core point.
- **Noise (`-1`):** observations that are not density-reachable from any core point.

The initial parameter heuristic uses `min_samples = number_of_features + 1`, giving **18** for this dataset. The sensitivity search also tests **8** and **34**.

A sorted **k-distance plot** estimates a candidate `eps` using a heuristic knee in the curve. This is a practical starting point, **not a mathematical guarantee of optimality**.

### 3. Parameter sensitivity analysis

For each candidate `min_samples`, the notebook searches multiple `eps` values based on the corresponding k-distance knee and distance quantiles.

A candidate is treated as **usable** when it produces:

- at least two non-noise clusters; and
- no more than 40% noise observations.

Among usable candidates, the notebook chooses the model with the largest:

```text
coverage-adjusted silhouette = non-noise silhouette × (1 − noise_fraction)
```

It breaks ties using lower noise fraction and then smaller `eps`. If the search does not meet the usable criteria, the notebook marks the result as exploratory or degenerate rather than claiming a successful clustering solution.

### 4. Evaluation

The notebook records:

- number of clusters (excluding noise);
- cluster sizes;
- number and percentage of noise observations;
- non-noise coverage;
- silhouette score;
- Davies–Bouldin index; and
- Calinski–Harabasz index.

**Important:** The three cluster-quality scores are computed only for non-noise observations, so they must be interpreted together with coverage. Since the parameter search and evaluation use the same observations, these are **descriptive scores**, not held-out validation estimates.

### 5. Visualization and interpretation

The notebook uses **PCA** to display station-window observations on two axes. DBSCAN itself is fitted on the **original 17-dimensional feature matrix**, not on the two-dimensional PCA projection.

Cluster numbers have no predetermined meaning. Any descriptions such as business, residential or leisure must be justified by feature patterns and external evidence rather than inferred from cluster IDs.

## Results from the initial run

The initial run on 244 station-window observations produced the following preliminary result:

| Assignment | Observations |
|---|---:|
| Cluster 0 | 206 |
| Cluster 1 | 5 |
| Noise (`-1`) | 33 |
| **Total** | **244** |

**Noise fraction:** approximately **13.5%**. The result identifies **two non-noise clusters**, but they are highly imbalanced. In particular, the five-observation cluster needs further examination before assigning it a meaningful station-profile category. These results are a **baseline**, not a final validation of station types.

The chosen `eps`, `min_samples` and evaluation scores are captured by the notebook's generated `summary.json`; inspect that file for the exact values from your run.

## Generated outputs

Running the notebook creates the following files under `results/dbscan/`:

| File | Purpose |
|---|---|
| `k_distance.png` | k-distance curve with heuristic `eps` reference |
| `parameter_sweep.csv` | Tested `eps`/`min_samples` combinations and diagnostic metrics |
| `dbscan_labels.csv` | Station-window records with DBSCAN labels and noise indicators |
| `cluster_sizes.csv` | Number of observations per cluster, including noise |
| `window_cluster_counts.csv` | Assignment counts for each study window |
| `cluster_feature_means_standardized.csv` | Mean standardized feature values per non-noise cluster |
| `pca_clusters.png` | Two-dimensional PCA display of assignments |
| `summary.json` | Selected parameters, selection rule, metrics and run metadata |

These are **generated local artifacts**; the original input CSV is not modified.

## Limitations and next steps

1. **High-dimensional distances:** Euclidean neighbourhoods in 17 dimensions may be less discriminative than in lower-dimensional data.
2. **Imbalanced groups:** Most observations currently belong to one cluster, and the smaller cluster must be interpreted carefully.
3. **Noise sensitivity:** The number of noise observations and cluster count depend on `eps`, `min_samples` and the input feature distribution.
4. **No geographic constraints:** This baseline captures passenger behaviour, not network adjacency or geographic proximity.
5. **Comparative evaluation:** Report clustering quality, noise coverage and interpretability alongside K-means, Ward, spectral clustering and ST-GRSC results on the same station-window feature table.

## Project references

- [Main project README](../README.md)
- [DBSCAN implementation notebook](04_dbscan.ipynb)
