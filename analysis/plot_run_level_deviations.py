"""Plot one point per metric-eligible execution for all six workloads (M5)."""

from __future__ import annotations

import argparse
import json
from collections.abc import Sequence
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

try:
    from .audit_observed_runs import DEFAULT_INPUT, load_runs
    from .derive_run_outcomes import derive_outcomes, prepare_selected_runs
except ImportError:  # Direct execution
    from audit_observed_runs import DEFAULT_INPUT, load_runs  # type: ignore[no-redef]
    from derive_run_outcomes import (  # type: ignore[no-redef]
        derive_outcomes,
        prepare_selected_runs,
    )


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPOSITORY_ROOT / "outputs" / "revision" / "m1_figures"

WORKLOAD_GROUPS = {
    "DDoS_FIFA_Gaming": ["DDoS", "FIFA", "Gaming"],
    "GAFAM_PayPal_VISA": ["GAFAM", "PayPal", "VISA"],
}
BLOCKCHAINS = ["Algorand", "Diem", "Ethereum", "Quorum", "Solana"]
BLOCKCHAIN_LABELS = {
    "Algorand": "Algorand",
    "Diem": "Diem",
    "Ethereum": "Ethereum Clique",
    "Quorum": "Quorum IBFT",
    "Solana": "Solana",
}
TOPOLOGIES = ["fat-tree", "full mesh", "hypercube", "scale-free", "torus"]
TOPOLOGY_COLORS = {
    "fat-tree": "#4C78A8",
    "full mesh": "#F58518",
    "hypercube": "#54A24B",
    "scale-free": "#E45756",
    "torus": "#B279A2",
}
METRICS = {
    "tps": {
        "value": "average_throughput",
        "eligible": "tps_point_valid_positive_commit",
        "absolute_label": r"Signed deviation (TPS)",
        "title": "Throughput",
    },
    "latency": {
        "value": "average_latency",
        "eligible": "latency_valid_positive_commit",
        "absolute_label": r"Signed deviation (s)",
        "title": "Block latency",
    },
    "energy": {
        "value": "energy",
        "eligible": "energy_valid_positive_commit",
        "absolute_label": r"Signed deviation (kWh)",
        "title": "Positive-service energy",
    },
}
CONFIG = ["blockchain", "mode", "workload", "network_size"]
RUN_ID = ["dataset", "run", "hash"]
JITTER_HALF_WIDTH = 0.18


def deviation_frame(derived: pd.DataFrame, metric_key: str) -> pd.DataFrame:
    spec = METRICS[metric_key]
    eligible = derived.loc[derived[str(spec["eligible"])]].copy()
    eligible["metric_value"] = pd.to_numeric(eligible[str(spec["value"])])
    eligible["configuration_mean"] = eligible.groupby(CONFIG, observed=True)[
        "metric_value"
    ].transform("mean")
    eligible["absolute_deviation"] = (
        eligible["metric_value"] - eligible["configuration_mean"]
    )
    eligible["relative_deviation"] = (
        100.0 * eligible["absolute_deviation"] / eligible["configuration_mean"]
    )
    eligible = eligible.sort_values(CONFIG + RUN_ID, kind="stable")
    groups = eligible.groupby(CONFIG, observed=True, sort=False)
    rank = groups.cumcount().astype(float)
    size = groups["metric_value"].transform("size").astype(float)
    eligible["plot_offset"] = np.where(
        size > 1,
        -JITTER_HALF_WIDTH + (2 * JITTER_HALF_WIDTH * rank / (size - 1)),
        0.0,
    )
    eligible["plot_x"] = [
        configuration_position(blockchain, topology)
        for blockchain, topology in zip(
            eligible["blockchain"], eligible["mode"], strict=True
        )
    ]
    eligible["plot_x"] += eligible["plot_offset"]
    return eligible.sort_index()


def configuration_position(blockchain: str, topology: str) -> float:
    return float(BLOCKCHAINS.index(blockchain) * 6 + TOPOLOGIES.index(topology))


def plot_group(
    derived: pd.DataFrame,
    deviations: pd.DataFrame,
    metric_key: str,
    network_size: str,
    group_name: str,
    workloads: list[str],
    output_dir: Path,
) -> dict[str, object]:
    spec = METRICS[metric_key]
    fig, axes = plt.subplots(len(workloads), 2, figsize=(13.2, 8.4), squeeze=False)
    empty_cells = 0
    plotted_points = 0
    overflow_points = 0
    for row, workload in enumerate(workloads):
        observed = derived.loc[
            (derived["network_size"] == network_size)
            & (derived["workload"] == workload)
        ]
        eligible = deviations.loc[
            (deviations["network_size"] == network_size)
            & (deviations["workload"] == workload)
        ]
        for column, measure in enumerate(["absolute_deviation", "relative_deviation"]):
            axis = axes[row, column]
            for topology in TOPOLOGIES:
                points = eligible.loc[eligible["mode"] == topology]
                x = points["plot_x"].to_numpy(float)
                y = points[measure].to_numpy(float)
                if measure == "relative_deviation":
                    overflow = np.abs(y) > 100.0
                    overflow_points += int(overflow.sum())
                    normal = ~overflow
                    axis.scatter(
                        x[normal],
                        y[normal],
                        s=9,
                        alpha=0.45,
                        color=TOPOLOGY_COLORS[topology],
                        linewidths=0,
                    )
                    axis.scatter(
                        x[overflow],
                        np.clip(y[overflow], -100.0, 100.0),
                        s=20,
                        alpha=0.8,
                        color=TOPOLOGY_COLORS[topology],
                        marker="^",
                        linewidths=0,
                    )
                else:
                    axis.scatter(
                        x,
                        y,
                        s=9,
                        alpha=0.45,
                        color=TOPOLOGY_COLORS[topology],
                        linewidths=0,
                    )
            plotted_points += int(len(eligible)) if column == 0 else 0
            for blockchain in BLOCKCHAINS:
                for topology in TOPOLOGIES:
                    cell_observed = observed.loc[
                        (observed["blockchain"] == blockchain)
                        & (observed["mode"] == topology)
                    ]
                    cell_eligible = eligible.loc[
                        (eligible["blockchain"] == blockchain)
                        & (eligible["mode"] == topology)
                    ]
                    if len(cell_observed) and cell_eligible.empty:
                        axis.scatter(
                            configuration_position(blockchain, topology),
                            0,
                            marker="x",
                            s=30,
                            color="black",
                            linewidths=1.0,
                        )
                        if column == 0:
                            empty_cells += 1
            axis.axhline(0, color="black", linewidth=0.7)
            for boundary in [5.0, 11.0, 17.0, 23.0]:
                axis.axvline(boundary - 0.5, color="#BBBBBB", linewidth=0.5)
            axis.grid(axis="y", alpha=0.2, linewidth=0.5)
            axis.set_xlim(-0.8, 28.8)
            if measure == "relative_deviation":
                axis.set_ylim(-105, 105)
                axis.set_ylabel("Signed deviation (%)")
            else:
                axis.set_ylabel(str(spec["absolute_label"]))
            axis.set_title(f"{workload}: {'absolute' if column == 0 else 'relative'}")
            centers = [2, 8, 14, 20, 26]
            axis.set_xticks(centers)
            axis.set_xticklabels(
                [BLOCKCHAIN_LABELS[item] for item in BLOCKCHAINS],
                rotation=18,
                ha="right",
            )

    handles = [
        plt.Line2D(
            [0],
            [0],
            marker="o",
            linestyle="",
            color=TOPOLOGY_COLORS[topology],
            label=topology,
            markersize=5,
        )
        for topology in TOPOLOGIES
    ]
    handles.extend(
        [
            plt.Line2D([0], [0], marker="^", linestyle="", color="black", label="|deviation| > 100%"),
            plt.Line2D([0], [0], marker="x", linestyle="", color="black", label="no metric-eligible run"),
        ]
    )
    fig.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.995),
        ncol=4,
        frameon=False,
    )
    fig.suptitle(
        f"{spec['title']} deviations, {network_size}: {', '.join(workloads)}",
        y=0.915,
        fontsize=13,
    )
    fig.tight_layout(rect=(0, 0, 1, 0.86))
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{metric_key}_{network_size.replace(' ', '_')}_{group_name}"
    pdf = output_dir / f"{stem}.pdf"
    fig.savefig(pdf, bbox_inches="tight")
    plt.close(fig)
    return {
        "metric": metric_key,
        "network_size": network_size,
        "workload_group": group_name,
        "workloads": workloads,
        "eligible_points": plotted_points,
        "empty_metric_cells": empty_cells,
        "relative_overflow_points": overflow_points,
        "pdf": str(pdf.relative_to(REPOSITORY_ROOT)),
    }


def run(input_path: Path, output_dir: Path) -> dict[str, object]:
    derived = derive_outcomes(prepare_selected_runs(load_runs(input_path)))
    deviations_by_metric = {
        metric_key: deviation_frame(derived, metric_key) for metric_key in METRICS
    }
    figures: list[dict[str, object]] = []
    for metric_key in METRICS:
        deviations = deviations_by_metric[metric_key]
        for network_size in ["10 nodes", "40 nodes"]:
            for group_name, workloads in WORKLOAD_GROUPS.items():
                figures.append(
                    plot_group(
                        derived,
                        deviations,
                        metric_key,
                        network_size,
                        group_name,
                        workloads,
                        output_dir,
                    )
                )
    manifest = pd.concat(
        [
            frame.assign(metric=metric_key)[
                [
                    "metric",
                    *RUN_ID,
                    *CONFIG,
                    "metric_value",
                    "configuration_mean",
                    "absolute_deviation",
                    "relative_deviation",
                    "plot_x",
                    "plot_offset",
                ]
            ]
            for metric_key, frame in deviations_by_metric.items()
        ],
        ignore_index=True,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = output_dir / "plotted_execution_manifest.csv"
    manifest.to_csv(manifest_path, index=False)
    caption_path = output_dir / "m5_figure_caption_replacements.tex"
    caption_path.write_text(render_caption_replacements(), encoding="utf-8")
    summary = {
        "figures": figures,
        "figure_count": len(figures),
        "pdf_count": len(figures),
        "png_count": 0,
        "plot_semantics": "one circular marker per metric-eligible execution",
        "horizontal_offset": (
            "deterministic within-configuration offset in [-0.18, 0.18]; "
            "visual separation only"
        ),
        "plotted_execution_manifest": str(manifest_path.relative_to(REPOSITORY_ROOT)),
        "manuscript_caption_replacements": str(caption_path.relative_to(REPOSITORY_ROOT)),
        "manifest_rows": int(len(manifest)),
        "metric_eligible_rows": {
            key: int(len(frame)) for key, frame in deviations_by_metric.items()
        },
    }
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def render_caption_replacements() -> str:
    return "\n".join(
        [
            r"% Exact M5 caption replacements for IEEE Access/4_Measurement_Results.tex",
            r"% fig:tps-added",
            r"\caption{\vd{M1/M3/M5: Run-level throughput deviations for DDoS, FIFA, and Gaming at 10 and 40 validators. Each colored circular marker represents one metric-eligible positive-service execution; the deterministic horizontal offsets separate executions visually without changing their blockchain--topology configuration. Triangles denote relative deviations beyond $\pm100\%$, and $\times$ denotes an observed configuration with no point-valued TPS execution.}}",
            r"% fig:tps-main",
            r"\caption{\vd{M1/M3/M5: Run-level throughput deviations for GAFAM, PayPal, and VISA at 10 and 40 validators. Each colored circular marker represents one metric-eligible positive-service execution; plotting conventions are otherwise as in Figure~\ref{fig:tps-added}.}}",
            r"% fig:lat-added",
            r"\caption{\vd{M1/M3/M5: Run-level block-latency deviations for DDoS, FIFA, and Gaming at 10 and 40 validators. Each colored circular marker represents one metric-eligible positive-service execution; the deterministic horizontal offsets separate executions visually without changing their blockchain--topology configuration. Triangles denote relative deviations beyond $\pm100\%$, and $\times$ denotes an observed configuration with no eligible latency execution.}}",
            r"% fig:lat-main",
            r"\caption{\vd{M1/M3/M5: Run-level block-latency deviations for GAFAM, PayPal, and VISA at 10 and 40 validators. Each colored circular marker represents one metric-eligible positive-service execution; plotting conventions are otherwise as in Figure~\ref{fig:lat-added}.}}",
            r"% fig:energy-added",
            r"\caption{\vd{M1/M3/M5: Run-level positive-service energy deviations for DDoS, FIFA, and Gaming at 10 and 40 validators. Each colored circular marker represents one positive-service energy execution; the deterministic horizontal offsets separate executions visually without changing their blockchain--topology configuration. $\times$ denotes an observed configuration with no positive-service energy execution.}}",
            r"% fig:energy-main",
            r"\caption{\vd{M1/M3/M5: Run-level positive-service energy deviations for GAFAM, PayPal, and VISA at 10 and 40 validators. Each colored circular marker represents one positive-service energy execution; plotting conventions are otherwise as in Figure~\ref{fig:energy-added}.}}",
            "",
        ]
    )


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    summary = run(args.input, args.output_dir)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
