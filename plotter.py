#!/usr/bin/env python3
"""Create transparent overview figures from the released aggregate dataset."""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path
from typing import Iterable

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd


CONFIG_COLUMNS = [
    "blockchain",
    "mode",
    "workload",
    "cores",
    "ram",
    "secondaries",
    "dataset",
    "link_strategy",
    "network_size",
    "dynamic",
]

BASE_METRICS = [
    "average_throughput_mean",
    "average_latency_mean",
    "energy_mean",
]

DISPERSION_METRICS = [
    "average_throughput_std_perc",
    "average_latency_std_perc",
    "energy_std_perc",
]

REQUIRED_COLUMNS = CONFIG_COLUMNS + BASE_METRICS + DISPERSION_METRICS

METRIC_LABELS = {
    "average_throughput_mean": "Mean throughput (tx/s)",
    "average_latency_mean": "Mean latency (s)",
    "energy_mean": "Mean energy",
    "average_throughput_std_perc": "Throughput CV (%)",
    "average_latency_std_perc": "Latency CV (%)",
    "energy_std_perc": "Energy CV (%)",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Summarize and plot the released blockchain repeatability dataset."
    )
    parser.add_argument(
        "--dataset",
        type=Path,
        default=Path("dataset/reproducibility-dataset.csv"),
        help="Input CSV. Default: dataset/reproducibility-dataset.csv",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("img"),
        help="Output directory. Default: img",
    )
    parser.add_argument("--blockchains", nargs="+", help="Keep only these blockchains.")
    parser.add_argument("--topologies", nargs="+", help="Keep only these topology names.")
    parser.add_argument("--workloads", nargs="+", help="Keep only these workloads.")
    parser.add_argument("--network-sizes", nargs="+", help="Keep only these network sizes.")
    parser.add_argument(
        "--no-clean",
        action="store_true",
        help="Do not remove the output directory before generating files.",
    )
    return parser.parse_args()


def load_dataset(path: Path) -> pd.DataFrame:
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")

    frame = pd.read_csv(path)
    missing = sorted(set(REQUIRED_COLUMNS) - set(frame.columns))
    if missing:
        raise ValueError(f"Dataset is missing required columns: {', '.join(missing)}")

    duplicate_key = ["blockchain", "mode", "workload", "network_size"]
    duplicated = frame.duplicated(subset=duplicate_key, keep=False)
    if duplicated.any():
        raise ValueError(
            f"Found {int(duplicated.sum())} rows with duplicate configuration keys"
        )

    return frame


def keep_values(
    frame: pd.DataFrame, column: str, values: Iterable[str] | None
) -> pd.DataFrame:
    if not values:
        return frame

    requested = list(values)
    unknown = sorted(set(requested) - set(frame[column].dropna().astype(str)))
    if unknown:
        raise ValueError(f"Unknown {column} value(s): {', '.join(unknown)}")
    return frame[frame[column].isin(requested)]


def apply_filters(frame: pd.DataFrame, args: argparse.Namespace) -> pd.DataFrame:
    frame = keep_values(frame, "blockchain", args.blockchains)
    frame = keep_values(frame, "mode", args.topologies)
    frame = keep_values(frame, "workload", args.workloads)
    frame = keep_values(frame, "network_size", args.network_sizes)
    if frame.empty:
        raise ValueError("The selected filters produced an empty dataset")
    return frame.copy()


def save_figure(figure: plt.Figure, output_dir: Path, stem: str) -> None:
    figure.savefig(output_dir / f"{stem}.png", dpi=200, bbox_inches="tight")
    figure.savefig(output_dir / f"{stem}.pdf", bbox_inches="tight")
    plt.close(figure)


def grouped_summary(frame: pd.DataFrame) -> pd.DataFrame:
    aggregations = {metric: "mean" for metric in BASE_METRICS}
    aggregations.update({metric: "median" for metric in DISPERSION_METRICS})
    summary = (
        frame.groupby(["blockchain", "mode"], observed=True)
        .agg(aggregations)
        .reset_index()
    )
    counts = (
        frame.groupby(["blockchain", "mode"], observed=True)
        .size()
        .rename("configuration_rows")
        .reset_index()
    )
    return summary.merge(counts, on=["blockchain", "mode"], how="left")


def plot_mean_metrics(frame: pd.DataFrame, output_dir: Path) -> None:
    grouped = frame.groupby(["blockchain", "mode"], observed=True)[BASE_METRICS].mean()
    figure, axes = plt.subplots(3, 1, figsize=(12, 15), constrained_layout=True)

    for axis, metric in zip(axes, BASE_METRICS):
        pivot = grouped[metric].unstack("mode")
        pivot.plot(kind="bar", ax=axis, width=0.82)
        axis.set_title(METRIC_LABELS[metric])
        axis.set_xlabel("")
        axis.set_ylabel(METRIC_LABELS[metric])
        axis.grid(axis="y", linestyle="--", alpha=0.4)
        axis.tick_params(axis="x", rotation=0)
        axis.legend(title="Topology", ncol=min(5, len(pivot.columns)))

    save_figure(figure, output_dir, "mean_metrics_by_blockchain_topology")


def plot_dispersion_heatmaps(frame: pd.DataFrame, output_dir: Path) -> None:
    matrices = []
    for metric in DISPERSION_METRICS:
        matrices.append(
            frame.pivot_table(
                index="blockchain",
                columns="mode",
                values=metric,
                aggfunc="median",
                observed=True,
            )
        )

    finite_values = np.concatenate(
        [matrix.to_numpy(dtype=float)[np.isfinite(matrix.to_numpy(dtype=float))] for matrix in matrices]
    )
    color_max = float(np.nanpercentile(finite_values, 95)) if finite_values.size else 1.0
    color_max = max(color_max, 1.0)

    figure, axes = plt.subplots(1, 3, figsize=(20, 6), constrained_layout=True)
    last_image = None

    for axis, metric, matrix in zip(axes, DISPERSION_METRICS, matrices):
        values = matrix.to_numpy(dtype=float)
        masked = np.ma.masked_invalid(values)
        last_image = axis.imshow(masked, cmap="viridis", aspect="auto", vmin=0, vmax=color_max)
        axis.set_title(f"Median {METRIC_LABELS[metric]}")
        axis.set_xticks(range(len(matrix.columns)), labels=matrix.columns, rotation=35, ha="right")
        axis.set_yticks(range(len(matrix.index)), labels=matrix.index)

        for row in range(values.shape[0]):
            for column in range(values.shape[1]):
                value = values[row, column]
                label = "NA" if not np.isfinite(value) else f"{value:.1f}"
                color = "white" if np.isfinite(value) and value > color_max * 0.55 else "black"
                axis.text(column, row, label, ha="center", va="center", fontsize=8, color=color)

    if last_image is not None:
        figure.colorbar(last_image, ax=axes, label="Coefficient of variation (%)", shrink=0.8)

    save_figure(figure, output_dir, "repeatability_dispersion_heatmaps")


def main() -> None:
    args = parse_args()
    frame = apply_filters(load_dataset(args.dataset), args)

    if args.output_dir.exists() and not args.no_clean:
        shutil.rmtree(args.output_dir)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    summary = grouped_summary(frame)
    summary.to_csv(args.output_dir / "summary_by_blockchain_topology.csv", index=False)
    plot_mean_metrics(frame, args.output_dir)
    plot_dispersion_heatmaps(frame, args.output_dir)

    print(
        f"Processed {len(frame)} configuration rows; outputs written to {args.output_dir}"
    )


if __name__ == "__main__":
    main()
