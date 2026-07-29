# Libraries
import matplotlib
matplotlib.use("Agg")

import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import time
import os
import re
from math import pi
from io import StringIO
from matplotlib.ticker import FuncFormatter, MaxNLocator
import math
from pathlib import Path
import statsmodels.api as sm
from statsmodels.formula.api import ols

repository_root = Path(__file__).resolve().parents[1]
data_dir = repository_root / "dataset"
out_dir = repository_root / "outputs"
out_dir.mkdir(parents=True, exist_ok=True)

# -------------------------------------------------------------------
# Read joint file
# -------------------------------------------------------------------
df = pd.read_csv(data_dir / "reproducibility-runs.csv")

df['mode'] = df['mode'].str.replace(r"-l$", "", regex=True)
df['mode'] = df['mode'].replace({
    'fat-tree': 'fat-tree',
    'full-mesh': 'full mesh',
    'hypercube': 'hypercube',
    'scale-free': 'scale-free',
    'torus': 'torus'
})
df['dataset'] = df['dataset'].replace({'diablo': '2023', 'our': '2024'})
df['workload'] = df['workload'].replace({
    'dota': 'Gaming',
    'football': 'FIFA',
    'paypal': 'PayPal',
    'visa': 'VISA',
    'gafam': 'GAFAM',
    '10000': 'DDoS'
})
PRIMARY_WORKLOADS = ["GAFAM", "PayPal", "VISA"]

df['blockchain'] = df['blockchain'].replace({
    'poa': 'Ethereum',
    'diem': 'Diem',
    'algorand': 'Algorand',
    'solana': 'Solana',
    'quorum': 'Quorum'
})

df['tx_ratio'] = df['commit_number'] / df['submit_number']
df['tx_ratio'] = df['tx_ratio'].fillna(0.0)

df['latency_ratio'] = df['average_latency'] / df['median_latency']
df['latency_ratio'] = df['latency_ratio'].fillna(0.0)
df['median_latency'] = df['median_latency'].fillna(0.0)

workloads = sorted(df['workload'].unique())
blockchains = sorted(df['blockchain'].unique())
topologies = df['mode'].unique()
blockchain_number = df['blockchain'].nunique()

df['network_size'] = df['network_size'].replace({1: '10 nodes', 4: '40 nodes'})

# -------------------------------------------------------------------
# Filter reproducibility dataset
# -------------------------------------------------------------------
refined_topology_df = df[df['dataset'] == '2023']
refined_topology_df = refined_topology_df[refined_topology_df['link_strategy'] == 'hop']
refined_topology_df = refined_topology_df[refined_topology_df['secondaries'] == 10]
refined_topology_df = refined_topology_df[refined_topology_df['cores'] == 8]
refined_topology_df = refined_topology_df[refined_topology_df['ram'] == 16]
refined_topology_df = refined_topology_df[refined_topology_df['dynamic'] == 0]

# keep negative energies as NaN to avoid skewing statistics
refined_topology_df["energy"] = refined_topology_df["energy"].apply(
    lambda x: x if x >= 0 else np.nan
)

def q25(x):
    return np.percentile(x, 25)

def q75(x):
    return np.percentile(x, 75)

group_cols = [
    "blockchain", "mode", "workload", "cores", "ram", "secondaries",
    "dataset", "link_strategy", "network_size", "dynamic",
]

# -------------------------------------------------------------------
# Per-configuration aggregation + dispersion indices
# -------------------------------------------------------------------
grouped_df = refined_topology_df.groupby(group_cols).agg({
    "average_throughput": ["count", "mean", "max", "min", q25, q75, "std"],
    "average_latency":   ["count", "mean", "max", "min", q25, q75, "std"],
    "energy":            ["count", "mean", "max", "min", q25, q75, "std"],
    "commit_number":     "mean",
}).reset_index()

# flatten multi-index columns
grouped_df.columns = ["_".join(col).rstrip("_") for col in grouped_df.columns]

# compute all dispersion indices
for val in ["average_throughput", "average_latency", "energy"]:
    mean_col = grouped_df[f"{val}_mean"]
    min_col  = grouped_df[f"{val}_min"]
    max_col  = grouped_df[f"{val}_max"]
    std_col  = grouped_df[f"{val}_std"]
    q1 = grouped_df[f"{val}_q25"]
    q3 = grouped_df[f"{val}_q75"]

    # min/max in percentuale rispetto alla media (usati dai plot e per il worst-case)
    grouped_df[f"{val}_min_perc"] = np.where(
        (mean_col > 0) & (min_col > 0),
        (min_col - mean_col) / mean_col * 100.0,
        np.nan,
    )

    grouped_df[f"{val}_max_perc"] = np.where(
        mean_col > 0,
        (max_col - mean_col) / mean_col * 100.0,
        np.nan,
    )

    # IQR (absolute and %)
    grouped_df[f"{val}_iqr"] = q3 - q1
    grouped_df[f"{val}_iqr_perc"] = np.where(
        mean_col > 0,
        grouped_df[f"{val}_iqr"] / mean_col * 100.0,
        np.nan,
    )

    # Δ_abs = max - min (absolute range, ci serve per il worst-case)
    grouped_df[f"{val}_delta_abs"] = max_col - min_col

    # Std dev in % (coeff. of variation)
    grouped_df[f"{val}_std_perc"] = np.where(
        mean_col > 0,
        std_col / mean_col * 100.0,
        np.nan,
    )

# save dataset for later plots
grouped_df.to_csv(
    out_dir / "reproducibility-dataset.csv",
    index=False,
    float_format="%.4f",
)

# -------------------------------------------------------------------
# Blockchain-level summary + .tex
# -------------------------------------------------------------------
def make_blockchain_summary(grouped_df: pd.DataFrame) -> pd.DataFrame:
    metrics = {
        "TPS": "average_throughput",
        "Lat": "average_latency",
        "En":  "energy",
    }
    rows = []
    for b, g in grouped_df.groupby("blockchain"):
        row = {"blockchain": b}
        for tag, col in metrics.items():
            # median IQR% across configurations
            row[f"IQR_{tag}_perc"] = g[f"{col}_iqr_perc"].median()
            # median normalised std-dev across configurations
            row[f"STD_{tag}_perc"] = g[f"{col}_std_perc"].median()
        rows.append(row)
    return pd.DataFrame(rows)

grouped_df_primary = grouped_df[grouped_df["workload"].isin(PRIMARY_WORKLOADS)].copy()
blockchain_summary = make_blockchain_summary(grouped_df_primary)

def block_label(name: str) -> str:
    """Pretty LaTeX label for blockchain names."""
    mapping = {
        "Algorand": "Algorand",
        "Diem": "Diem",
        "Ethereum": "Ethereum Clique",
        "Quorum": "Quorum~IBFT",
        "Solana": "Solana",
        "algorand": "Algorand",
        "diem": "Diem",
        "poa": "Ethereum Clique",
        "quorum": "Quorum~IBFT",
        "solana": "Solana",
    }
    return mapping.get(name, name)

# -------------------------------------------------------------------
# Helpers for Tables 
# -------------------------------------------------------------------
def topo_label(t: str) -> str:
    mapping = {
        "fat-tree": "fat-tree",
        "full mesh": "full mesh",
        "hypercube": "hypercube",
        "scale-free": "scale-free",
        "torus": "torus",
    }
    return mapping.get(t, t)

def workload_label(w: str) -> str:
    mapping = {
        "GAFAM": "GAFAM",
        "PayPal": "PayPal",
        "VISA": "VISA",
    }
    return mapping.get(w, w)

# -------------------------------------------------------------------
# Blockchain × topology (IQR%, Std%)
# -------------------------------------------------------------------
def make_topology_summary(grouped_df_primary: pd.DataFrame) -> pd.DataFrame:
    """Group by blockchain × topology and compute IQR%, Std%, WCAD% for TPS/Lat/En."""
    metrics = {
        "TPS": "average_throughput",
        "Lat": "average_latency",
        "En":  "energy",
    }
    rows = []
    for (b, topo), g in grouped_df_primary.groupby(["blockchain", "mode"]):
        row = {
            "blockchain": b,
            "topology": topo,
        }
        for tag, col in metrics.items():
            row[f"IQR_{tag}_perc"]  = g[f"{col}_iqr_perc"].median()
            row[f"STD_{tag}_perc"]  = g[f"{col}_std_perc"].median()
        rows.append(row)
    return pd.DataFrame(rows)

def latex_table_topology(topo_summary: pd.DataFrame) -> str:
    metrics = ["TPS", "Lat", "En"]

    def fmt(x):
        if pd.isna(x):
            return "--"
        return f"{x:.2f}"

    def decorate(val, best_val, worst_val):
        if pd.isna(val):
            return "--"
        s = fmt(val)
        if (best_val is not None) and (not pd.isna(best_val)) and abs(val - best_val) < 1e-9:
            return r"\hlcell{best}" + s
        if (worst_val is not None) and (not pd.isna(worst_val)) and abs(val - worst_val) < 1e-9:
            return r"\hlcell{worst}" + s
        return s

    preferred_order = ["Algorand", "Diem", "Ethereum", "Quorum", "Solana"]
    avail = topo_summary["blockchain"].unique().tolist()
    block_order = [b for b in preferred_order if b in avail] + [
        b for b in avail if b not in preferred_order
    ]

    topo_order = ["fat-tree", "full mesh", "hypercube", "scale-free", "torus"]

    lines = []
    lines.append(r"\begin{table}[t]")
    lines.append(r"\centering")
    lines.append(
        r"\caption{Repeatability per blockchain vs.\ topology "
        r"(same convention as Table~\ref{tab:repeatability_summary}), using IQR\% and Std\%.}"
    )
    lines.append(r"\label{tab:repeatability_topology}")
    lines.append(r"\adjustbox{max width=\linewidth}{")
    lines.append(r"\begin{tabular}{l|l|rr| rr| rr}")
    lines.append(r"\toprule")
    lines.append(
        r"\textbf{Blockchain} & \textbf{Topology} "
        r"& IQR TPS & Std TPS "
        r"& IQR Lat & Std Lat "
        r"& IQR En & Std En \\"
    )
    lines.append(r"\midrule")

    for b in block_order:
        df_b = topo_summary[topo_summary["blockchain"] == b]
        if df_b.empty:
            continue

        best_b = {}
        worst_b = {}
        for m in metrics:
            iqr_col  = f"IQR_{m}_perc"
            std_col  = f"STD_{m}_perc"
            # wcad_col = f"WCAD_{m}_perc"
            best_b[iqr_col]  = df_b[iqr_col].min()
            worst_b[iqr_col] = df_b[iqr_col].max()
            best_b[std_col]  = df_b[std_col].min()
            worst_b[std_col] = df_b[std_col].max()
            # best_b[wcad_col]  = df_b[wcad_col].min()
            # worst_b[wcad_col] = df_b[wcad_col].max()

        wrote_rows = False

        for topo in topo_order:
            df_bt = df_b[df_b["topology"] == topo]
            if df_bt.empty:
                continue
            row = df_bt.iloc[0]
            cells = [block_label(b), topo_label(topo)]
            for m in metrics:
                iqr_col  = f"IQR_{m}_perc"
                std_col  = f"STD_{m}_perc"
                # wcad_col = f"WCAD_{m}_perc"
                cells.append(decorate(row[iqr_col],  best_b[iqr_col],  worst_b[iqr_col]))
                cells.append(decorate(row[std_col],  best_b[std_col],  worst_b[std_col]))
                # cells.append(decorate(row[wcad_col], best_b[wcad_col], worst_b[wcad_col]))
            lines.append(" & ".join(cells) + r" \\")
            wrote_rows = True

        for _, row in df_b.iterrows():
            if row["topology"] not in topo_order:
                cells = [block_label(row["blockchain"]), topo_label(row["topology"])]
                for m in metrics:
                    iqr_col  = f"IQR_{m}_perc"
                    std_col  = f"STD_{m}_perc"
                    # wcad_col = f"WCAD_{m}_perc"
                    cells.append(decorate(row[iqr_col],  best_b[iqr_col],  worst_b[iqr_col]))
                    cells.append(decorate(row[std_col],  best_b[std_col],  worst_b[std_col]))
                    # cells.append(decorate(row[wcad_col], best_b[wcad_col], worst_b[wcad_col]))
                lines.append(" & ".join(cells) + r" \\")
                wrote_rows = True

        if wrote_rows:
            lines.append(r"\hline")

    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    lines.append(r"}")
    lines.append(r"\end{table}")
    return "\n".join(lines)

# -------------------------------------------------------------------
# Blockchain × workload (IQR%, Std%)
# -------------------------------------------------------------------
def make_workload_summary(grouped_df_primary: pd.DataFrame) -> pd.DataFrame:
    """Group by blockchain × workload and compute IQR%, Std%, WCAD%."""
    metrics = {
        "TPS": "average_throughput",
        "Lat": "average_latency",
        "En":  "energy",
    }
    rows = []
    for (b, w), g in grouped_df_primary.groupby(["blockchain", "workload"]):
        row = {
            "blockchain": b,
            "workload": w,
        }
        for tag, col in metrics.items():
            row[f"IQR_{tag}_perc"]  = g[f"{col}_iqr_perc"].median()
            row[f"STD_{tag}_perc"]  = g[f"{col}_std_perc"].median()
        rows.append(row)
    return pd.DataFrame(rows)

def latex_table_workload(work_summary: pd.DataFrame) -> str:
    metrics = ["TPS", "Lat", "En"]

    def fmt(x):
        if pd.isna(x):
            return "--"
        return f"{x:.2f}"

    def decorate(val, best_val, worst_val):
        if pd.isna(val):
            return "--"
        s = fmt(val)
        if (best_val is not None) and (not pd.isna(best_val)) and abs(val - best_val) < 1e-9:
            return r"\hlcell{best}" + s
        if (worst_val is not None) and (not pd.isna(worst_val)) and abs(val - worst_val) < 1e-9:
            return r"\hlcell{worst}" + s
        return s

    preferred_order = ["Algorand", "Diem", "Ethereum", "Quorum", "Solana"]
    avail = work_summary["blockchain"].unique().tolist()
    block_order = [b for b in preferred_order if b in avail] + [
        b for b in avail if b not in preferred_order
    ]

    wl_order = ["GAFAM", "PayPal", "VISA"]

    lines = []
    lines.append(r"\begin{table}[t]")
    lines.append(r"\centering")
    lines.append(
        r"\caption{Repeatability per blockchain vs.\ workload "
        r"(same convention as Table~\ref{tab:repeatability_summary}), using IQR\% and Std\%.}"
    )
    lines.append(r"\label{tab:repeatability_workload}")
    lines.append(r"\adjustbox{max width=\linewidth}{")
    lines.append(r"\begin{tabular}{l|l|rr| rr| rr}")
    lines.append(r"\toprule")
    lines.append(
        r"\textbf{Blockchain} & \textbf{Workload} "
        r"& IQR TPS & Std TPS "
        r"& IQR Lat & Std Lat "
        r"& IQR En & Std En \\"
    )
    lines.append(r"\midrule")

    for b in block_order:
        df_b = work_summary[work_summary["blockchain"] == b]
        if df_b.empty:
            continue

        best_b = {}
        worst_b = {}
        for m in metrics:
            iqr_col  = f"IQR_{m}_perc"
            std_col  = f"STD_{m}_perc"
            # wcad_col = f"WCAD_{m}_perc"
            best_b[iqr_col]  = df_b[iqr_col].min()
            worst_b[iqr_col] = df_b[iqr_col].max()
            best_b[std_col]  = df_b[std_col].min()
            worst_b[std_col] = df_b[std_col].max()
            # best_b[wcad_col]  = df_b[wcad_col].min()
            # worst_b[wcad_col] = df_b[wcad_col].max()

        wrote_rows = False

        for w in wl_order:
            df_bw = df_b[df_b["workload"] == w]
            if df_bw.empty:
                continue
            row = df_bw.iloc[0]
            cells = [block_label(b), workload_label(w)]
            for m in metrics:
                iqr_col  = f"IQR_{m}_perc"
                std_col  = f"STD_{m}_perc"
                # wcad_col = f"WCAD_{m}_perc"
                cells.append(decorate(row[iqr_col],  best_b[iqr_col],  worst_b[iqr_col]))
                cells.append(decorate(row[std_col],  best_b[std_col],  worst_b[std_col]))
                # cells.append(decorate(row[wcad_col], best_b[wcad_col], worst_b[wcad_col]))
            lines.append(" & ".join(cells) + r" \\")
            wrote_rows = True

        for _, row in df_b.iterrows():
            if row["workload"] not in wl_order:
                cells = [block_label(row["blockchain"]), workload_label(row["workload"])]
                for m in metrics:
                    iqr_col  = f"IQR_{m}_perc"
                    std_col  = f"STD_{m}_perc"
                    # wcad_col = f"WCAD_{m}_perc"
                    cells.append(decorate(row[iqr_col],  best_b[iqr_col],  worst_b[iqr_col]))
                    cells.append(decorate(row[std_col],  best_b[std_col],  worst_b[std_col]))
                    # cells.append(decorate(row[wcad_col], best_b[wcad_col], worst_b[wcad_col]))
                lines.append(" & ".join(cells) + r" \\")
                wrote_rows = True

        if wrote_rows:
            lines.append(r"\hline")

    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    lines.append(r"}")
    lines.append(r"\end{table}")
    return "\n".join(lines)

# -------------------------------------------------------------------
# Scaling 10n vs 40n (IQR%, Std%)
# -------------------------------------------------------------------
def make_scaling_summary(grouped_df_primary: pd.DataFrame) -> pd.DataFrame:
    """
    Group by blockchain × {10 nodes, 40 nodes} and compute
    IQR%, Std%, WCAD% for TPS/Lat/En at both scales.
    """
    metrics = {
        "TPS": "average_throughput",
        "Lat (s)": "average_latency",
        "En (kWh)": "energy",
    }
    sizes    = ["10 nodes", "40 nodes"]
    size_tag = {"10 nodes": "10n", "40 nodes": "40n"}

    rows = []
    for b, gb in grouped_df_primary.groupby("blockchain"):
        row = {"blockchain": b}
        for size in sizes:
            gs = gb[gb["network_size"] == size]
            tag_s = size_tag[size]
            for tag, col in metrics.items():
                if gs.empty:
                    row[f"IQR_{tag}_{tag_s}"]  = np.nan
                    row[f"STD_{tag}_{tag_s}"]  = np.nan
                else:
                    row[f"IQR_{tag}_{tag_s}"]  = gs[f"{col}_iqr_perc"].median()
                    row[f"STD_{tag}_{tag_s}"]  = gs[f"{col}_std_perc"].median()
        rows.append(row)
    return pd.DataFrame(rows)

def latex_table_scaling(scale_summary: pd.DataFrame) -> str:
    metrics   = ["TPS", "Lat (s)", "En (kWh)"]
    size_tags = ["10n", "40n"]

    best = {}
    worst = {}
    for m in metrics:
        for s in size_tags:
            iqr_col  = f"IQR_{m}_{s}"
            # wcad_col = f"WCAD_{m}_{s}"
            std_col  = f"STD_{m}_{s}"
            best[iqr_col]  = scale_summary[iqr_col].min()
            worst[iqr_col] = scale_summary[iqr_col].max()
            # best[wcad_col]  = scale_summary[wcad_col].min()
            # worst[wcad_col] = scale_summary[wcad_col].max()
            best[std_col]  = scale_summary[std_col].min()
            worst[std_col] = scale_summary[std_col].max()

    def fmt(x):
        if pd.isna(x):
            return "--"
        return f"{x:.2f}"

    def decorate(val, col):
        if pd.isna(val):
            return "--"
        s = fmt(val)
        if abs(val - best[col]) < 1e-9:
            return r"\hlcell{best}" + s
        if abs(val - worst[col]) < 1e-9:
            return r"\hlcell{worst}" + s
        return s

    # ordering
    block_order_pref = ["Algorand", "Diem", "Ethereum", "Quorum", "Solana"]
    rows_ordered = []
    for b in block_order_pref:
        df_b = scale_summary[scale_summary["blockchain"] == b]
        if not df_b.empty:
            rows_ordered.append(df_b.iloc[0])
    for _, row in scale_summary.iterrows():
        if not any(row["blockchain"] == r["blockchain"] for r in rows_ordered):
            rows_ordered.append(row)

    lines = []
    lines.append(r"\begin{table*}[t]")
    lines.append(r"\centering")
    lines.append(
        r"\caption{Repeatability per blockchain with 10- and 40-node scaling "
        r"(same convention as Table~\ref{tab:repeatability_summary}), using IQR\% and Std\%.}"
    )
    lines.append(r"\label{tab:repeatability_scaling}")
    lines.append(r"\adjustbox{max width=\textwidth}{")
    lines.append(r"\begin{tabular}{lrrrr| rrrr| rrrr}")
    lines.append(r"\toprule")
    lines.append(
        r" & \multicolumn{4}{c}{TPS} "
        r"& \multicolumn{4}{c}{Lat (s)} "
        r"& \multicolumn{4}{c}{En (kWh)} \\"
    )
    lines.append(
        r"\cmidrule(lr){2-5}\cmidrule(lr){6-9}\cmidrule(lr){10-13}"
    )
    lines.append(
        r"Blockchain "
        r"& IQR 10n & Std 10n & IQR 40n & Std 40n "
        r"& IQR 10n & Std 10n & IQR 40n & Std 40n "
        r"& IQR 10n & Std 10n & IQR 40n & Std 40n \\"
    )
    lines.append(r"\midrule")

    for row in rows_ordered:
        b = row["blockchain"]
        cells = [block_label(b)]
        for m in metrics:
            for s in size_tags:
                iqr_col  = f"IQR_{m}_{s}"
                # wcad_col = f"WCAD_{m}_{s}"
                std_col  = f"STD_{m}_{s}"
                cells.append(decorate(row[iqr_col],  iqr_col))
                # cells.append(decorate(row[wcad_col], wcad_col))
                cells.append(decorate(row[std_col],  std_col))
        lines.append(" & ".join(cells) + r" \\")
    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    lines.append(r"}")
    lines.append(r"\end{table*}")
    return "\n".join(lines)


# -------------------------------------------------------------------
# Worst-case swings per blockchain (range, down/up abs, down/up %)
# -------------------------------------------------------------------
def make_blockchain_worstcase(grouped_df: pd.DataFrame) -> pd.DataFrame:
    """
    Per ciascuna blockchain e metrica (TPS, Lat, En) calcola:
      - Range_abs: massimo intervallo max - min (Δ_int)
      - Down_abs: massimo (mean - min) osservato (caduta assoluta)
      - Up_abs: massimo (max - mean) osservato (picco assoluto)
      - Down_pct: massimo -min_perc (caduta percentuale dalla media)
      - Up_pct: massimo max_perc (picco percentuale sopra la media)
    Tutti i valori sono non negativi; la direzione è codificata come down/up.
    """
    metrics = {
        "TPS": "average_throughput",
        "Lat": "average_latency",
        "En":  "energy",
    }

    rows = []
    for b, g in grouped_df.groupby("blockchain"):
        row = {"blockchain": b}

        for tag, col in metrics.items():
            mean_col = g[f"{col}_mean"]
            min_col  = g[f"{col}_min"]
            max_col  = g[f"{col}_max"]

            # Range assoluto (intervallo max - min)
            range_abs = g[f"{col}_delta_abs"].max()

            # Deviazioni assolute rispetto alla media
            down_abs = (mean_col - min_col).clip(lower=0)
            up_abs   = (max_col - mean_col).clip(lower=0)

            down_abs_max = down_abs.max() if len(down_abs) else np.nan
            up_abs_max   = up_abs.max() if len(up_abs) else np.nan

            # Deviazioni percentuali rispetto alla media (ampiezza)
            pmin = g[f"{col}_min_perc"]
            pmax = g[f"{col}_max_perc"]

            down_pct = (-pmin).clip(lower=0)    # -negativo → ampiezza positiva
            up_pct   = pmax.clip(lower=0)       # dovrebbe essere ≥0, clip per sicurezza

            down_pct_max = down_pct.max() if len(down_pct) else np.nan
            up_pct_max   = up_pct.max() if len(up_pct) else np.nan

            row[f"Range_{tag}_abs"]   = range_abs
            row[f"Down_{tag}_abs"]    = down_abs_max
            row[f"Up_{tag}_abs"]      = up_abs_max
            row[f"Down_{tag}_pct"]    = down_pct_max
            row[f"Up_{tag}_pct"]      = up_pct_max

        rows.append(row)

    return pd.DataFrame(rows)


def latex_table_blockchain_worstcase(worst_df: pd.DataFrame) -> str:
    metrics = ["TPS", "Lat", "En"]

    # Mappa (metrica, stat) → nome colonna nel DataFrame
    stat_order = ["Range", "Down", "Up", "DownPct", "UpPct"]
    col_map = {}
    for m in metrics:
        col_map[(m, "Range")]   = f"Range_{m}_abs"
        col_map[(m, "Down")]    = f"Down_{m}_abs"
        col_map[(m, "Up")]      = f"Up_{m}_abs"
        col_map[(m, "DownPct")] = f"Down_{m}_pct"
        col_map[(m, "UpPct")]   = f"Up_{m}_pct"

    # Best/worst per colonna (più basso = migliore stabilità)
    best = {}
    worst = {}
    for (_, _), col in col_map.items():
        best[col]  = worst_df[col].min()
        worst[col] = worst_df[col].max()

    def fmt(x):
        if pd.isna(x):
            return "--"
        # interi se vicino all'intero, altrimenti 2 decimali
        if abs(x - int(x)) < 1e-6:
            return f"{int(x)}"
        return f"{x:.2f}"

    def decorate_var(val, col):
        if pd.isna(val):
            return "--"
        s = fmt(val)
        if abs(val - best[col]) < 1e-9:
            return s
        if abs(val - worst[col]) < 1e-9:
            return r"\hlcell{worst}" + s
        return s

    # Ordine leggibile delle blockchain
    order = ["Algorand", "Diem", "Ethereum", "Quorum", "Solana"]
    seen = set()
    ordered_blocks = []
    for b in order:
        if b in worst_df["blockchain"].values and b not in seen:
            ordered_blocks.append(b)
            seen.add(b)
    for b in worst_df["blockchain"]:
        if b not in seen:
            ordered_blocks.append(b)
            seen.add(b)

    lines = []
    lines.append(r"\begin{table*}[t]")
    lines.append(r"\centering")
    lines.append(
        r"\caption{Worst-case run-to-run swings per blockchain. "
        r"For each metric we report: the maximum observed range "
        r"($\Delta_{\mathrm{abs}}$), the largest absolute drop "
        r"below the mean ($\Delta^{\downarrow}$), the largest absolute increase above the mean "
        r"($\Delta^{\uparrow}$), and their percentage counterparts ($\Delta^{\downarrow}\%$, $\Delta^{\uparrow}\%$) relative to "
        r"the configuration mean. "
        r"The least stable values ($\mathrm{WCD}$ and $\mathrm{WCD\%}$, depending on the column) are highlighted in \textcolor{black}{\fcolorbox{worst}{worst}{\phantom{xx}}}.}"
    )
    lines.append(r"\label{tab:repeatability_worstcase}")
    lines.append(r"\adjustbox{max width=\textwidth}{")
    lines.append(r"\begin{tabular}{lrrrrr| rrrrr| rrrrr}")
    lines.append(r"\toprule")
    lines.append(
        r" & \multicolumn{5}{c}{TPS} "
        r"& \multicolumn{5}{c}{Lat (s)} "
        r"& \multicolumn{5}{c}{En (kWh)} \\"
    )
    lines.append(
        r"\cmidrule(lr){2-6}\cmidrule(lr){7-11}\cmidrule(lr){12-16}"
    )
    lines.append(
        r"\textbf{Blockchain} "
        r"& $\Delta_{\mathrm{abs}}$ & $\Delta^{\downarrow}$ & $\Delta^{\uparrow}$ & $\Delta^{\downarrow}\%$ & $\Delta^{\uparrow}\%$ "
        r"& $\Delta_{\mathrm{abs}}$ & $\Delta^{\downarrow}$ & $\Delta^{\uparrow}$ & $\Delta^{\downarrow}\%$ & $\Delta^{\uparrow}\%$ "
        r"& $\Delta_{\mathrm{abs}}$ & $\Delta^{\downarrow}$ & $\Delta^{\uparrow}$ & $\Delta^{\downarrow}\%$ & $\Delta^{\uparrow}\%$ \\"
    )
    lines.append(r"\midrule")

    for b in ordered_blocks:
        row = worst_df[worst_df["blockchain"] == b].iloc[0]
        cells = [block_label(b)]
        for m in metrics:
            for stat in stat_order:
                col = col_map[(m, stat)]
                cells.append(decorate_var(row[col], col))
        lines.append(" & ".join(cells) + r" \\")

    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    lines.append(r"}")
    lines.append(r"\end{table*}")
    return "\n".join(lines)


# -------------------------------------------------------------------
# Generate LaTeX tables
# -------------------------------------------------------------------
topology_summary = make_topology_summary(grouped_df_primary)
workload_summary = make_workload_summary(grouped_df_primary)
scaling_summary  = make_scaling_summary(grouped_df_primary)
blockchain_worst = make_blockchain_worstcase(grouped_df_primary)

tex_topology = latex_table_topology(topology_summary)
tex_workload = latex_table_workload(workload_summary)
tex_scaling  = latex_table_scaling(scaling_summary)
tex_worst = latex_table_blockchain_worstcase(blockchain_worst)

Path(out_dir, "tab_repeatability_topology.tex").write_text(tex_topology)
Path(out_dir, "tab_repeatability_workload.tex").write_text(tex_workload)
Path(out_dir, "tab_repeatability_scaling.tex").write_text(tex_scaling)
Path(out_dir, "tab_repeatability_worstcase.tex").write_text(tex_worst)

print("Saved tables:")
print(" - tab_repeatability_topology.tex")
print(" - tab_repeatability_workload.tex")
print(" - tab_repeatability_scaling.tex")
print(" - tab_repeatability_worstcase.tex")

# -------------------------------------------------------------------
# Summary table with IQR%, Std%
# -------------------------------------------------------------------
def latex_table_repeatability(blockchain_summary: pd.DataFrame) -> str:
    # readable order
    order = ["Algorand", "Diem", "Ethereum", "Quorum", "Solana",
             "algorand", "diem", "poa", "quorum", "solana"]
    seen = set()
    ordered_blocks = []
    for b in order:
        if b in blockchain_summary["blockchain"].values and b not in seen:
            ordered_blocks.append(b)
            seen.add(b)
    for b in blockchain_summary["blockchain"]:
        if b not in seen:
            ordered_blocks.append(b)
            seen.add(b)

    metrics = ["TPS", "Lat", "En"]

    best_iqr   = {m: blockchain_summary[f"IQR_{m}_perc"].min()   for m in metrics}
    worst_iqr  = {m: blockchain_summary[f"IQR_{m}_perc"].max()   for m in metrics}
    best_std   = {m: blockchain_summary[f"STD_{m}_perc"].min()   for m in metrics}
    worst_std  = {m: blockchain_summary[f"STD_{m}_perc"].max()   for m in metrics}
    # best_wcad  = {m: blockchain_summary[f"WCAD_{m}_perc"].min()  for m in metrics}
    # worst_wcad = {m: blockchain_summary[f"WCAD_{m}_perc"].max()  for m in metrics}

    def fmt(x):
        if pd.isna(x):
            return "--"
        return f"{x:.2f}"

    def decorate(val, best_val, worst_val):
        if pd.isna(val):
            return "--"
        s = fmt(val)
        if abs(val - best_val) < 1e-9:
            return r"\hlcell{best}" + s
        if abs(val - worst_val) < 1e-9:
            return r"\hlcell{worst}" + s
        return s

    lines = []
    lines.append(r"\begin{table}[!t]")
    lines.append(r"\centering")
    lines.append(
        r"\caption{Overall blockchain-level variability. For each metric, "
        r"we report the median relative interquartile range (IQR\%), and the median "
        r"normalised standard deviation (Std\%). "
        r"The most stable blockchains (minimum values) are highlighted in "
        r"\textcolor{black}{\fcolorbox{best}{best}{\phantom{xx}}}, "
        r"the least stable ones in \textcolor{black}{\fcolorbox{worst}{worst}{\phantom{xx}}}.}"
    )
    lines.append(r"\label{tab:repeatability_summary}")
    lines.append(r"\adjustbox{max width=\linewidth}{")
    lines.append(r"\begin{tabular}{lrr| rr| rr}")
    lines.append(r"\toprule")
    lines.append(
        r" & \multicolumn{2}{c}{TPS} "
        r"& \multicolumn{2}{c}{Lat} "
        r"& \multicolumn{2}{c}{kWh} \\"
    )
    lines.append(
        r"\cmidrule(lr){2-3}\cmidrule(lr){4-5}\cmidrule(lr){6-7}"
    )
    lines.append(
        r"\textbf{Blockchain} & IQR & Std "
        r"& IQR & Std "
        r"& IQR & Std \\"
    )
    lines.append(r"\midrule")

    for b in ordered_blocks:
        row = blockchain_summary[blockchain_summary["blockchain"] == b].iloc[0]
        cells = []
        for m in metrics:
            iqr_val   = row[f"IQR_{m}_perc"]
            std_val   = row[f"STD_{m}_perc"]
            # wcad_val  = row[f"WCAD_{m}_perc"]

            cell_iqr   = decorate(iqr_val,   best_iqr[m],   worst_iqr[m])
            cell_std   = decorate(std_val,   best_std[m],   worst_std[m])
            # cell_wcad  = decorate(wcad_val,  best_wcad[m],  worst_wcad[m])

            cells.append(cell_iqr)
            cells.append(cell_std)
            # cells.append(cell_wcad)

        line = block_label(b) + " & " + " & ".join(cells) + r" \\"
        lines.append(line)

    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    lines.append(r"}")
    lines.append(r"\end{table}")
    return "\n".join(lines)

tex_table4 = latex_table_repeatability(blockchain_summary)
Path(out_dir, "tab_repeatability_summary.tex").write_text(tex_table4)

# -------------------------------------------------------------------
# Factorial ANOVA + ICC summary (unchanged)
# -------------------------------------------------------------------
def compute_icc(df_runs: pd.DataFrame, metric: str) -> float:
    """
    ICC(1,1) approx via one-way random-effects ANOVA over configurations.
    """
    cfg_cols = [
        "blockchain", "mode", "workload",
        "cores", "ram", "secondaries",
        "dataset", "link_strategy", "network_size", "dynamic",
    ]
    d = df_runs[cfg_cols + [metric]].dropna().copy()
    d["config_id"] = d[cfg_cols].astype(str).agg("|".join, axis=1)

    grand_mean = d[metric].mean()
    groups = d.groupby("config_id")
    n_g = groups.size()
    means_g = groups[metric].mean()

    ss_between = (n_g * (means_g - grand_mean) ** 2).sum()
    ss_total = ((d[metric] - grand_mean) ** 2).sum()
    ss_within = ss_total - ss_between

    G = len(n_g)
    N = len(d)
    df_between = G - 1
    df_within = N - G
    if df_between <= 0 or df_within <= 0:
        return np.nan

    ms_between = ss_between / df_between
    ms_within = ss_within / df_within

    k_bar = N / G  # average replicates per configuration
    sigma_between = max((ms_between - ms_within) / k_bar, 0.0)
    sigma_within = max(ms_within, 0.0)
    denom = sigma_between + sigma_within
    return sigma_between / denom if denom > 0 else np.nan

def compute_anova_shares(df_runs: pd.DataFrame, metric: str):
    """
    Factorial ANOVA: B + T + W + S + B×T + B×W.
    Returns dictionary of variance shares (0..1).
    """
    d = df_runs[["blockchain", "mode", "workload", "network_size", metric]].dropna().copy()
    d = d.rename(columns={
        "blockchain": "B",
        "mode": "T",
        "workload": "W",
        "network_size": "S",
        metric: "y",
    })
    for col in ["B", "T", "W", "S"]:
        d[col] = d[col].astype("category")

    formula = "y ~ C(B) + C(T) + C(W) + C(S) + C(B):C(T) + C(B):C(W)"
    model = ols(formula, data=d).fit()
    anova_table = sm.stats.anova_lm(model, typ=2)

    total_ss = anova_table["sum_sq"].sum()
    shares = {}
    mapping = [
        ("C(B)",       "blockchain"),
        ("C(T)",       "topology"),
        ("C(W)",       "workload"),
        ("C(S)",       "size"),
        ("C(B):C(T)",  "blockchain_x_topology"),
        ("C(B):C(W)",  "blockchain_x_workload"),
    ]
    for term, key in mapping:
        if term in anova_table.index:
            shares[key] = anova_table.loc[term, "sum_sq"] / total_ss
        else:
            shares[key] = np.nan

    if "Residual" in anova_table.index:
        shares["residual"] = anova_table.loc["Residual", "sum_sq"] / total_ss
    else:
        shares["residual"] = np.nan

    return shares

def build_anova_icc_summary(df_runs: pd.DataFrame) -> pd.DataFrame:
    metrics_info = [
        ("average_throughput", "TPS"),
        ("average_latency",    "Lat"),
        ("energy",             "En"),
    ]
    rows = []
    for metric, label in metrics_info:
        shares = compute_anova_shares(df_runs, metric)
        icc_val = compute_icc(df_runs, metric)
        row = {
            "Metric": label,
            "blockchain": shares.get("blockchain", np.nan),
            "topology": shares.get("topology", np.nan),
            "workload": shares.get("workload", np.nan),
            "size": shares.get("size", np.nan),
            "blockchain_x_topology": shares.get("blockchain_x_topology", np.nan),
            "blockchain_x_workload": shares.get("blockchain_x_workload", np.nan),
            "residual": shares.get("residual", np.nan),
            "ICC": icc_val,
        }
        rows.append(row)
    return pd.DataFrame(rows)

refined_topology_primary = refined_topology_df[refined_topology_df["workload"].isin(PRIMARY_WORKLOADS)].copy()
anova_icc_summary = build_anova_icc_summary(refined_topology_primary)

def latex_table_anova_icc(summary: pd.DataFrame) -> str:
    def fmt_icc(x):
        if pd.isna(x):
            return "--"
        return f"{x:.3f}"

    # Colonne dei fattori da mostrare in percentuale
    factor_cols = [
        "blockchain",
        "topology",
        "workload",
        "size",
        "blockchain_x_topology",
        "blockchain_x_workload",
        "residual",
    ]

    lines = []
    lines.append(r"\begin{table}[t]")
    lines.append(r"\centering")
    lines.append(
        r"\caption{Variance decomposition and run-to-run reliability. "
        r"Each entry reports the percentage of variance explained by the "
        r"corresponding factor or interaction in the factorial ANOVA; "
        r"$\varepsilon$ denotes the residual term (higher-order interactions "
        r"and unexplained noise). The last column reports the intraclass "
        r"correlation coefficient (ICC) for per-configuration runs. "
        r"$B$: Blockchains; $T$: Topologies; $W$: Workloads; $S$ Scales (validator-set sizes).}"
    )
    lines.append(r"\label{tab:repeatability_anova}")
    lines.append(r"\adjustbox{max width=\linewidth}{")
    lines.append(r"\begin{tabular}{lrrrrrrrr}")
    lines.append(r"\toprule")
    lines.append(
        r"\textbf{Metric} & $B$ & $T$ & $W$ & $S$ "
        r"& $B{\times}T$ & $B{\times}W$ & $\varepsilon$ & ICC \\"
    )
    lines.append(r"\midrule")

    for _, row in summary.iterrows():
        # 1) valori grezzi (0..1) dei fattori
        raw_vals = [row[col] for col in factor_cols]

        # 2) maschera per NaN
        mask = [not pd.isna(v) for v in raw_vals]

        # 3) percentuali e arrotondamento a 0.1
        perc = [
            (float(v) * 100.0) if m else np.nan
            for v, m in zip(raw_vals, mask)
        ]
        rounded = [
            round(p, 1) if m else np.nan
            for p, m in zip(perc, mask)
        ]

        # 4) errore di somma assorbito in ε (residual)
        total = np.nansum(rounded)
        diff = 100.0 - total

        try:
            residual_idx = factor_cols.index("residual")
        except ValueError:
            residual_idx = None

        if any(mask):
            if residual_idx is not None and mask[residual_idx]:
                target_idx = residual_idx
            else:
                valid_indices = [i for i, m in enumerate(mask) if m]
                target_idx = max(valid_indices, key=lambda i: rounded[i])

            rounded[target_idx] = rounded[target_idx] + diff

        # 5) formattazione percentuali
        pct_cells = []
        for v in rounded:
            if np.isnan(v):
                pct_cells.append("--")
            else:
                pct_cells.append(f"{v:.1f}")

        # QUI mettiamo ICC come ultima colonna, non toccata dal ribilanciamento
        cells = [row["Metric"]] + pct_cells + [fmt_icc(row["ICC"])]
        lines.append(" & ".join(cells) + r" \\")

    lines.append(r"\bottomrule")
    lines.append(r"\end{tabular}")
    lines.append(r"}")
    lines.append(r"\end{table}")
    return "\n".join(lines)

tex_anova = latex_table_anova_icc(anova_icc_summary)
Path(out_dir, "tab_anova_icc.tex").write_text(tex_anova)


# ==========================================================
# PLOT: run-to-run swings per blockchain / workload / size
# Use the aggregate dataset generated in outputs/reproducibility-dataset.csv.
# ==========================================================

# ---------- Load dataset ----------
df_conf = pd.read_csv(out_dir / "reproducibility-dataset.csv")
df_conf["nodes"] = pd.to_numeric(
    df_conf["network_size"].astype(str).str.extract(r"(\d+)")[0],
    errors="coerce"
)

# ---------- Metric configs ----------
METRICS = [
    {
        "key": "average_throughput",
        "label_left": "Δ TPS",
        "mean": "average_throughput_mean",
        "min":  "average_throughput_min",
        "max":  "average_throughput_max",
        "pmin": "average_throughput_min_perc",
        "pmax": "average_throughput_max_perc",
        "title": "Throughput deviation",
    },
    {
        "key": "average_latency",
        "label_left": "Δ Latency (s)",
        "mean": "average_latency_mean",
        "min":  "average_latency_min",
        "max":  "average_latency_max",
        "pmin": "average_latency_min_perc",
        "pmax": "average_latency_max_perc",
        "title": "Latency deviation",
    },
    {
        "key": "energy",
        "label_left": "Δ Energy (kWh)",
        "mean": "energy_mean",
        "min":  "energy_min",
        "max":  "energy_max",
        "pmin": "energy_min_perc",
        "pmax": "energy_max_perc",
        "title": "Energy deviation",
    },
]

# ---------- Fonts ----------
def scale(v):
    return int(round(v * 1.3))

FONT = {
    "base": scale(11),
    "ticks": scale(14),
    "labels": scale(15),
    "row_subtitle": int(round(scale(15) * 0.92)),
    "suptitle": scale(16),
    "legend": scale(14),
    "annot_bar": max(6, int(round(scale(12) * 0.90))),  # labels inside bars & NO
    "xticks_axis": max(6, int(round(scale(14) * 0.88))),  # X ticks (blockchain)
}
FONT["annot_nc"] = FONT["annot_bar"]

plt.rcParams.update({
    "font.size": FONT["base"],
    "axes.titlesize": FONT["row_subtitle"],
    "axes.labelsize": FONT["labels"],
    "xtick.labelsize": FONT["ticks"],
    "ytick.labelsize": FONT["ticks"],
    "legend.fontsize": FONT["legend"],
    "axes.titlepad": 6.0,
})

# ---------- Color palette + alpha ----------
CUSTOM_COLORS = ["#d7191c", "#fdae61", "#ffffbf", "#abdda4", "#2b83ba"]
ALPHA_BARS = 0.8  # parametro di trasparenza per tutte le barre


# ---------- Helpers ----------
def symmetric_rounded_bound(raw_min, raw_max, step=5):
    pbound = max(abs(raw_min), abs(raw_max))
    bound = math.ceil(pbound / step) * step if pbound != 0 else step
    return -bound, bound

def pad_limits(low, high, pad_rel=0.08, min_pad=1.0):
    span = high - low
    pad = max(min_pad, span * pad_rel)
    return low - pad, high + pad

def left_tick_formatter(v, pos):
    # Show "Δ=0" at zero, otherwise integer if close else 1 decimal
    if abs(v) < 1e-12:
        return "Δ=0"
    if abs(v - int(v)) < 1e-6:
        return f"{int(v)}"
    return f"{v:.1f}"

def plot_dual_halves(
    ax,
    data_slice: pd.DataFrame,
    metric: dict,
    title: str,
    tiny_gap=0.04,
    alpha_bars=ALPHA_BARS,
    bar_width=0.18,
    left_offset_rel=0.03,
    right_offset_abs=3.0
):
    # Aggregate for left half (mean/min/max across runs per config)
    g = (
        data_slice
        .groupby(["blockchain", "mode"], dropna=False, as_index=False)
        .agg(
            MEAN=(metric["mean"], "mean"),
            MIN=(metric["min"],  "mean"),
            MAX=(metric["max"],  "mean"),
        )
    )
    blockchains = sorted(g["blockchain"].unique().tolist())
    topologies  = sorted(g["mode"].unique().tolist())

    # Right-side "NO" detection (no percentage deltas)
    rc_map = {}
    for _, row in data_slice.iterrows():
        key = (row["mode"], row["blockchain"])
        rc_map.setdefault(key, {"pmin": [], "pmax": []})
        rc_map[key]["pmin"].append(row[metric["pmin"]])
        rc_map[key]["pmax"].append(row[metric["pmax"]])
    rc_nc = {
        k: (
            all([pd.isna(v) for v in vals["pmin"]])
            and all([pd.isna(v) for v in vals["pmax"]])
        )
        for k, vals in rc_map.items()
    }

    axR = ax.twinx()
    width = bar_width
    xL = np.arange(len(blockchains))
    gap = tiny_gap
    xR = np.arange(len(blockchains)) + len(blockchains) + gap

        # Assegna un colore fisso per ciascuna topology, ciclato sulla palette
    topo_colors = {
        topo: CUSTOM_COLORS[i % len(CUSTOM_COLORS)]
        for i, topo in enumerate(topologies)
    }
    topology_handles, topology_labels = [], []

    # -------- LEFT: Δ centered at 0 --------
    all_dmins, all_dmaxs = [], []
    for topo in topologies:
        sub = g[g["mode"] == topo]
        for b in blockchains:
            row = sub[sub["blockchain"] == b]
            if not row.empty:
                m  = float(row["MEAN"].squeeze())
                mn = float(row["MIN"].squeeze())
                mx = float(row["MAX"].squeeze())
                all_dmins.append(mn - m)
                all_dmaxs.append(mx - m)

    lowL, highL = symmetric_rounded_bound(
        np.nanmin(all_dmins) if len(all_dmins) else 0.0,
        np.nanmax(all_dmaxs) if len(all_dmaxs) else 0.0,
        step=5,
    )
    lowL, highL = pad_limits(lowL, highL, pad_rel=0.08, min_pad=2.0)
    ax.set_ylim(lowL, highL)

    # Dynamic offset for labels near baseline
    yspan = highL - lowL
    left_off = max(0.01 * yspan, yspan * left_offset_rel)

    for i, topo in enumerate(topologies):
        sub = g[g["mode"] == topo]
        xpos = xL + (i - len(topologies)/2)*width
        means, dmins, dmaxs = [], [], []
        for b in blockchains:
            row = sub[sub["blockchain"] == b]
            if not row.empty:
                m  = float(row["MEAN"].squeeze())
                mn = float(row["MIN"].squeeze())
                mx = float(row["MAX"].squeeze())
                means.append(m)
                dmins.append(mn - m)
                dmaxs.append(mx - m)
            else:
                means.append(np.nan)
                dmins.append(np.nan)
                dmaxs.append(np.nan)

        pos_vals = [max(0, v) if not np.isnan(v) else np.nan for v in dmaxs]
        neg_vals = [min(0, v) if not np.isnan(v) else np.nan for v in dmins]

        color = topo_colors[topo]
        bars_pos = ax.bar(xpos, pos_vals, width=width, color=color, alpha=alpha_bars)
        ax.bar(xpos, neg_vals, width=width, color=color, alpha=alpha_bars)

        # Labels "m=..." or "NO"
        for xi, mu, bname, up, down in zip(xpos, means, blockchains, pos_vals, neg_vals):
            if rc_nc.get((topo, bname), False) or np.isnan(mu):
                ax.text(
                    xi, 0, "NO", rotation=90,
                    ha='center', va='bottom', fontsize=FONT["annot_nc"]
                )
            else:
                if (not np.isnan(up) and up > 0) or (np.isnan(up) and (np.isnan(down) or down >= 0)):
                    ax.text(
                        xi, left_off, f"m={mu:.0f}", rotation=90,
                        ha='center', va='bottom', fontsize=FONT["annot_bar"]
                    )
                elif not np.isnan(down) and down < 0:
                    ax.text(
                        xi, -left_off, f"m={mu:.0f}", rotation=90,
                        ha='center', va='top', fontsize=FONT["annot_bar"]
                    )
                else:
                    ax.text(
                        xi, left_off, f"m={mu:.0f}", rotation=90,
                        ha='center', va='bottom', fontsize=FONT["annot_bar"]
                    )

        topology_handles.append(bars_pos[0])
        topology_labels.append(topo)

    ax.axhline(0, linewidth=1.0)
    ax.yaxis.set_major_locator(MaxNLocator(nbins=8))

    # Tick at zero with "Δ=0"
    ticks = ax.get_yticks()
    if 0.0 not in ticks:
        ticks = np.sort(np.append(ticks, 0.0))
        ax.set_yticks(ticks)
    ax.yaxis.set_major_formatter(FuncFormatter(left_tick_formatter))

    # Shared X ticks
    all_xticks = list(xL) + list(xR)
    ax.set_xticks(all_xticks)
    ax.set_xticklabels(blockchains + blockchains, rotation=0)
    ax.margins(x=0, y=0)
    ax.tick_params(axis='x', labelbottom=True, pad=1, labelsize=FONT["xticks_axis"])

    # Vertical separator between left/right halves
    sep_x = len(blockchains) - 0.5 + gap/2.0
    ax.axvline(sep_x, linestyle="-", linewidth=0.8)

    # -------- RIGHT: % change fixed scale [-100, 100] --------
    axR.set_ylim(-100, 100)
    ticksR = list(range(-100, 101, 25))
    axR.set_yticks(ticksR)

    for i, topo in enumerate(topologies):
        sub_raw = data_slice[data_slice["mode"] == topo]
        pmins, pmaxs = [], []
        for b in blockchains:
            sub_b = sub_raw[sub_raw["blockchain"] == b]
            if len(sub_b) == 0:
                pmins.append(np.nan)
                pmaxs.append(np.nan)
                continue
            mi_vals = sub_b[metric["pmin"]].values
            mx_vals = sub_b[metric["pmax"]].values
            mi = float(np.nanmin(mi_vals)) if not np.isnan(mi_vals).all() else np.nan
            mx = float(np.nanmax(mx_vals)) if not np.isnan(mx_vals).all() else np.nan
            pmins.append(mi)
            pmaxs.append(mx)

        xpos = xR + (i - len(topologies)/2)*width
        color = topo_colors[topo]

        pos_heights = [mx if (not np.isnan(mx) and mx > 0) else 0 for mx in pmaxs]
        neg_heights = [mi if (not np.isnan(mi) and mi < 0) else 0 for mi in pmins]

        axR.bar(xpos, pos_heights, width=width, color=color, alpha=alpha_bars)
        axR.bar(xpos, neg_heights, width=width, color=color, alpha=alpha_bars)

        # Overflow labels (|Δ%| > 100)
        for xi, mi, mx in zip(xpos, pmins, pmaxs):
            if np.isnan(mi) and np.isnan(mx):
                axR.text(
                    xi, 0, "NO", rotation=90,
                    ha='center', va='bottom', fontsize=FONT["annot_nc"]
                )
            else:
                if not np.isnan(mx) and mx > 100:
                    axR.text(
                        xi, right_offset_abs, f"{mx:.0f}%",
                        rotation=90, ha='center', va='bottom',
                        fontsize=FONT["annot_bar"]
                    )
                if not np.isnan(mi) and mi < -100:
                    axR.text(
                        xi, -right_offset_abs, f"{mi:.0f}%",
                        rotation=90, ha='center', va='top',
                        fontsize=FONT["annot_bar"]
                    )

    axR.axhline(0, linewidth=1.0)

    # Confined horizontal gridlines
    ax.grid(False)
    axR.grid(False)
    if len(xL):
        xmin_L = xL[0] - 0.6
        xmax_L = len(blockchains) - 0.5 - gap/2.0
        for y in ax.get_yticks():
            ax.hlines(y, xmin_L, xmax_L, linestyles='--', linewidth=1, alpha=0.35)
    if len(xR):
        xmin_R = len(blockchains) - 0.5 + gap/2.0
        xmax_R = xR[-1] + 0.6
        for y in ticksR:
            axR.hlines(y, xmin_R, xmax_R, linestyles='--', linewidth=1, alpha=0.35)

    ax.spines['right'].set_visible(False)
    axR.spines['left'].set_visible(False)
    ax.set_title(title, fontsize=FONT["row_subtitle"], pad=4)

    return topology_handles, topology_labels

# ---------- Figure builder (3+3 split) ----------
def build_subset_figure(nodes_value: int, metric: dict, workloads_subset, title_suffix, output_dir=out_dir):
    data = df_conf[
        (df_conf["nodes"] == nodes_value)
        & (df_conf["workload"].isin(workloads_subset))
    ].copy()
    workloads = list(dict.fromkeys(data["workload"].tolist()))
    n = len(workloads)
    if n == 0:
        return None, None, None

    fig, axes = plt.subplots(n, 1, figsize=(12.9, 2.85*n))
    if n == 1:
        axes = [axes]

    topology_handles, topology_labels = None, None
    for i, w in enumerate(workloads):
        ax = axes[i]
        sub = data[data["workload"] == w]
        handles, labels = plot_dual_halves(
            ax, sub, metric,
            f"Workload: {w}",
            tiny_gap=0.04,
            alpha_bars=ALPHA_BARS,
            bar_width=0.18,
            left_offset_rel=0.03,
            right_offset_abs=3.0,
        )
        if topology_handles is None:
            topology_handles, topology_labels = handles, labels
        if i < n-1:
            ax.set_xticklabels([])
        ax.tick_params(
            axis='x',
            labelbottom=(i == n-1),
            pad=1,
            labelsize=FONT["xticks_axis"],
        )

    # Legend and global labels
    ncol = len(topology_labels) if topology_labels else 1
    fig.legend(
        topology_handles,
        topology_labels,
        loc="upper center",
        ncol=ncol,
        bbox_to_anchor=(0.5, 1.004),
        frameon=False,
        prop={"size": FONT["legend"]},
        borderaxespad=0.0,
        handletextpad=0.25,
        columnspacing=0.5,
    )

    fig.subplots_adjust(
        left=0.113, right=0.918,
        top=0.905, bottom=0.132,
        hspace=0.28,
    )
    fig.text(
        0.033, 0.5, metric['label_left'],
        va='center', rotation='vertical',
        fontsize=FONT["labels"],
    )
    fig.text(
        0.993, 0.5, "Δ Percentage (%)",
        va='center', rotation='vertical',
        fontsize=FONT["labels"],
    )

    if nodes_value == 10:
        fig.text(
            0.5, 0.062,
            f"$\\mathbf{{(a)}}$ {nodes_value} nodes – {title_suffix} – {metric['title']}",
            ha='center', va='center',
            fontsize=FONT["suptitle"],
        )
    else:
        fig.text(
            0.5, 0.062,
            f"$\\mathbf{{(b)}}$ {nodes_value} nodes – {title_suffix} – {metric['title']}",
            ha='center', va='center',
            fontsize=FONT["suptitle"],
        )

    Path(output_dir).mkdir(parents=True, exist_ok=True)
    base = f"{metric['key']}_{nodes_value}nodes_{title_suffix.replace(' ', '_')}"
    png_path = str(Path(output_dir) / f"{base}.png")
    pdf_path = str(Path(output_dir) / f"{base}.pdf")
    fig.savefig(png_path, dpi=200, bbox_inches="tight", pad_inches=0.16)
    fig.savefig(pdf_path, bbox_inches="tight", pad_inches=0.16)
    return fig, png_path, pdf_path

# ---------- Build and SAVE all figures ----------
primary = ["GAFAM", "PayPal", "VISA"]
all_workloads = list(dict.fromkeys(df_conf["workload"].tolist()))
secondary = [w for w in all_workloads if w not in primary]

outputs = []
for metric in METRICS:
    for nodes in [10, 40]:
        fig1, png1, pdf1 = build_subset_figure(nodes, metric, primary, "GAFAM, PayPal & VISA")
        if fig1 is not None:
            outputs.append((metric["key"], nodes, "primary", png1, pdf1))

        fig2, png2, pdf2 = build_subset_figure(nodes, metric, secondary, "Other 3 workloads")
        if fig2 is not None:
            outputs.append((metric["key"], nodes, "secondary", png2, pdf2))

print("Files salvati:")
for key, nodes, which, png, pdf in outputs:
    print(f"- {key} @ {nodes} nodes [{which}] -> {png} | {pdf}")
