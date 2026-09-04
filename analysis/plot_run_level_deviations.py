"""Generate readable run-level figures and outcome tables (R1.5/R2.6)."""

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
from matplotlib.ticker import MaxNLocator

try:
    from .audit_observed_runs import DEFAULT_INPUT, load_runs
    from .derive_run_outcomes import (
        configuration_outcome_counts,
        derive_outcomes,
        prepare_selected_runs,
    )
except ImportError:  # Direct execution
    from audit_observed_runs import DEFAULT_INPUT, load_runs  # type: ignore[no-redef]
    from derive_run_outcomes import (  # type: ignore[no-redef]
        configuration_outcome_counts,
        derive_outcomes,
        prepare_selected_runs,
    )


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPOSITORY_ROOT / "outputs" / "revision" / "m1_figures"

WORKLOADS = ["DDoS", "FIFA", "Gaming", "GAFAM", "PayPal", "VISA"]
NETWORK_SIZES = ["10 nodes", "40 nodes"]
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
        "absolute_label": r"$\Delta$ TPS",
        "panel_title": "Throughput deviations",
    },
    "latency": {
        "value": "average_latency",
        "eligible": "latency_valid_positive_commit",
        "absolute_label": r"$\Delta$ Block latency (s)",
        "panel_title": "Block latency deviations",
    },
    "energy": {
        "value": "energy",
        "eligible": "energy_valid_positive_commit",
        "absolute_label": r"$\Delta$ Energy (kWh)",
        "panel_title": "Energy deviations",
    },
}
CONFIG = ["blockchain", "mode", "workload", "network_size"]
RUN_ID = ["dataset", "run", "hash"]
JITTER_HALF_WIDTH = 0.18
DEVIATION_FIGURE_SIZE = (10.8, 13.5)
FINAL_PLACEMENT_FRACTION = 1.0
SOURCE_MINIMUM_TEXT_PT = 7.5
matplotlib.rcParams.update(
    {
        "pdf.fonttype": 42,
        "font.size": 8.5,
        "axes.titlesize": 8.5,
        "axes.labelsize": 9.5,
        "xtick.labelsize": 7.5,
        "ytick.labelsize": 7.5,
        "legend.fontsize": 8.0,
    }
)


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


def plot_metric(
    derived: pd.DataFrame,
    deviations: pd.DataFrame,
    metric_key: str,
    output_dir: Path,
) -> dict[str, object]:
    spec = METRICS[metric_key]
    fig = plt.figure(figsize=DEVIATION_FIGURE_SIZE)
    grid = fig.add_gridspec(
        14,
        2,
        height_ratios=[1.0] * 6 + [0.72] + [1.0] * 6 + [0.72],
        left=0.080,
        right=0.920,
        top=0.944,
        bottom=0.018,
        hspace=0.22,
        wspace=0.10,
    )
    empty_cells = 0
    plotted_points = 0
    overflow_points = 0
    for network_index, network_size in enumerate(NETWORK_SIZES):
        for workload_index, workload in enumerate(WORKLOADS):
            grid_row = network_index * 7 + workload_index
            observed = derived.loc[
                (derived["network_size"] == network_size)
                & (derived["workload"] == workload)
            ]
            eligible = deviations.loc[
                (deviations["network_size"] == network_size)
                & (deviations["workload"] == workload)
            ]
            plotted_points += int(len(eligible))
            for column, measure in enumerate(
                ["absolute_deviation", "relative_deviation"]
            ):
                axis = fig.add_subplot(grid[grid_row, column])
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
                            s=16,
                            alpha=0.55,
                            color=TOPOLOGY_COLORS[topology],
                            linewidths=0,
                        )
                        axis.scatter(
                            x[overflow],
                            np.clip(y[overflow], -100.0, 100.0),
                            s=30,
                            alpha=0.85,
                            color=TOPOLOGY_COLORS[topology],
                            marker="^",
                            linewidths=0,
                        )
                    else:
                        axis.scatter(
                            x,
                            y,
                            s=16,
                            alpha=0.55,
                            color=TOPOLOGY_COLORS[topology],
                            linewidths=0,
                        )
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
                                s=32,
                                color="black",
                                linewidths=1.1,
                            )
                            if column == 0:
                                empty_cells += 1
                axis.axhline(0, color="black", linewidth=0.65)
                for boundary in [5.0, 11.0, 17.0, 23.0]:
                    axis.axvline(boundary - 0.5, color="#BBBBBB", linewidth=0.45)
                axis.grid(axis="y", alpha=0.20, linewidth=0.45)
                axis.set_xlim(-0.8, 28.8)
                axis.tick_params(axis="both", labelsize=7.5, pad=1.5)
                if measure == "relative_deviation":
                    axis.set_ylim(-105, 105)
                    axis.set_yticks([-100, 0, 100])
                    axis.yaxis.tick_right()
                    axis.yaxis.set_label_position("right")
                else:
                    axis.yaxis.set_major_locator(MaxNLocator(nbins=3))
                    axis.yaxis.tick_left()
                    axis.yaxis.set_label_position("left")
                    axis.set_title(
                        workload,
                        loc="left",
                        fontsize=8.5,
                        fontweight="semibold",
                        pad=1.0,
                    )
                if workload_index == len(WORKLOADS) - 1:
                    centers = [2, 8, 14, 20, 26]
                    axis.set_xticks(centers)
                    axis.set_xticklabels(
                        [BLOCKCHAIN_LABELS[item] for item in BLOCKCHAINS],
                        rotation=12,
                        ha="right",
                    )
                else:
                    axis.set_xticks([])

        title_axis = fig.add_subplot(grid[network_index * 7 + 6, :])
        title_axis.axis("off")
        panel_letter = "a" if network_index == 0 else "b"
        title_axis.text(
            0.5,
            0.20,
            rf"$\mathbf{{({panel_letter})}}$ {spec['panel_title']}, "
            rf"{network_size}, six workloads",
            ha="center",
            va="center",
            fontsize=10.5,
        )
    handles = [
        plt.Line2D(
            [0],
            [0],
            marker="o",
            linestyle="",
            color=TOPOLOGY_COLORS[topology],
            label=topology,
            markersize=6,
        )
        for topology in TOPOLOGIES
    ]
    if (deviations["relative_deviation"].abs() > 100.0).any():
        handles.append(
            plt.Line2D(
                [0],
                [0],
                marker="^",
                linestyle="",
                color="black",
                label=r"$|\Delta|>100\%$",
            )
        )
    handles.append(
        plt.Line2D(
            [0],
            [0],
            marker="x",
            linestyle="",
            color="black",
            label="no metric-eligible run",
        )
    )
    fig.legend(
        handles=handles,
        loc="upper center",
        bbox_to_anchor=(0.5, 0.995),
        ncol=len(handles),
        frameon=False,
        handletextpad=0.35,
        columnspacing=0.8,
    )
    for center in (0.724, 0.270):
        fig.text(
            0.014,
            center,
            str(spec["absolute_label"]),
            rotation=90,
            ha="center",
            va="center",
            fontsize=9.5,
        )
        fig.text(
            0.986,
            center,
            r"$\Delta$ Percentage (\%)",
            rotation=90,
            ha="center",
            va="center",
            fontsize=9.5,
        )
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{metric_key}_six_workloads"
    pdf = output_dir / f"{stem}.pdf"
    fig.savefig(pdf)
    plt.close(fig)
    return {
        "metric": metric_key,
        "network_sizes": NETWORK_SIZES,
        "workloads": WORKLOADS,
        "eligible_points": plotted_points,
        "empty_metric_cells": empty_cells,
        "relative_overflow_points": overflow_points,
        "pdf": str(pdf.relative_to(REPOSITORY_ROOT)),
        "source_figure_inches": list(DEVIATION_FIGURE_SIZE),
    }


def outcome_table_frame(derived: pd.DataFrame) -> pd.DataFrame:
    """Return the exact 300 configuration rows summarized by the merged table."""
    counts = configuration_outcome_counts(derived).copy()
    counts["display_count"] = counts.apply(
        lambda row: (
            f"{int(row['n_positive_commit'])}/"
            f"{int(row['n_zero_commit'])}/"
            f"{int(row['n_no_submission'])}"
        ),
        axis=1,
    )
    return counts


def render_outcome_table(counts: pd.DataFrame) -> str:
    grouped = (
        counts.groupby(["blockchain", "network_size"], observed=True)
        .agg(
            configurations=("n_observed", "size"),
            only_positive=(
                "service_regime_derived",
                lambda values: int((values == "all_positive_commit").sum()),
            ),
            mixed=(
                "service_regime_derived",
                lambda values: int((values == "mixed_outcomes").sum()),
            ),
            no_positive=(
                "service_regime_derived",
                lambda values: int((values == "no_positive_commit").sum()),
            ),
            observed=("n_observed", "sum"),
            submitted=("n_submitted", "sum"),
            positive=("n_positive_commit", "sum"),
            zero=("n_zero_commit", "sum"),
            no_submission=("n_no_submission", "sum"),
            tps_point=("n_tps_point_valid", "sum"),
            latency=("n_latency_valid", "sum"),
            energy_positive=("n_energy_valid_positive_commit", "sum"),
        )
        .reset_index()
    )
    if not (
        grouped["configurations"]
        == grouped[["only_positive", "mixed", "no_positive"]].sum(axis=1)
    ).all():
        raise ValueError("Configuration-regime counts do not reconcile")
    totals = grouped[
        [
            "configurations",
            "only_positive",
            "mixed",
            "no_positive",
            "observed",
            "submitted",
            "positive",
            "zero",
            "no_submission",
            "tps_point",
            "latency",
            "energy_positive",
        ]
    ].sum()
    lines = [
        r"% Auto-generated by analysis/plot_run_level_deviations.py; do not edit.",
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{\vd{R1.5/R2.6: Configuration regimes, execution outcomes, and metric-valid observations by blockchain and validator-set size. Of the $C$ configurations, All pos., Mixed, and No pos. count those with only positive commits, both positive- and non-positive outcomes, and no positive commits. Obs., Sub., Pos., Zero, and No-sub. count observed, submitted, positive-commit, zero-commit, and no-submission executions; TPS, Lat., and $E^+$ count point-valued positive-service throughput, latency, and energy observations.}}",
        r"\label{tab:r26_outcome_accounting}",
        r"\TableFont",
        r"\setlength{\tabcolsep}{2pt}",
        r"\resizebox{\columnwidth}{!}{%",
        r"\begin{tabular}{llrrrrrrrrrrrr}",
        r"\toprule",
        r" & & \multicolumn{4}{c}{\textbf{Configurations}} & \multicolumn{5}{c}{\textbf{Executions}} & \multicolumn{3}{c}{\textbf{Metric-valid}} \\",
        r"\cmidrule(lr){3-6}\cmidrule(lr){7-11}\cmidrule(lr){12-14}",
        r"\textbf{Blockchain} & \textbf{Validators} & $\mathbf{C}$ & \textbf{All pos.} & \textbf{Mixed} & \textbf{No pos.} & \textbf{Obs.} & \textbf{Sub.} & \textbf{Pos.} & \textbf{Zero} & \textbf{No-sub.} & \textbf{TPS} & \textbf{Lat.} & $\mathbf{E^+}$ \\",
        r"\midrule",
    ]
    for row_index, (_, item) in enumerate(grouped.iterrows()):
        if row_index > 0 and row_index % 2 == 0:
            lines.append(r"\midrule")
        lines.append(
            f"{BLOCKCHAIN_LABELS[str(item['blockchain'])]} & "
            f"{str(item['network_size']).split()[0]} & "
            f"{int(item['configurations'])} & {int(item['only_positive'])} & "
            f"{int(item['mixed'])} & {int(item['no_positive'])} & "
            f"{int(item['observed'])} & {int(item['submitted'])} & "
            f"{int(item['positive'])} & {int(item['zero'])} & "
            f"{int(item['no_submission'])} & {int(item['tps_point'])} & "
            f"{int(item['latency'])} & {int(item['energy_positive'])} \\\\"
        )
    lines.extend(
        [
            r"\midrule",
            r"\textbf{Total} & -- & "
            + " & ".join(str(int(totals[column])) for column in totals.index)
            + r" \\",
            r"\bottomrule",
            r"\end{tabular}",
            r"}",
            r"\end{table}",
            "",
        ]
    )
    return "\n".join(lines)


def run(input_path: Path, output_dir: Path) -> dict[str, object]:
    derived = derive_outcomes(prepare_selected_runs(load_runs(input_path)))
    outcome_counts = outcome_table_frame(derived)
    deviations_by_metric = {
        metric_key: deviation_frame(derived, metric_key) for metric_key in METRICS
    }
    output_dir.mkdir(parents=True, exist_ok=True)
    for obsolete in output_dir.glob("*_nodes_*.pdf"):
        obsolete.unlink()
    figures = [
        plot_metric(derived, deviations_by_metric[metric_key], metric_key, output_dir)
        for metric_key in METRICS
    ]
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
    manifest_path = output_dir / "plotted_execution_manifest.csv"
    manifest.to_csv(manifest_path, index=False)
    caption_path = output_dir / "m5_figure_caption_replacements.tex"
    caption_path.write_text(render_caption_replacements(), encoding="utf-8")
    outcome_table_path = (
        REPOSITORY_ROOT / "paper_tables" / "r2_6" / "table_outcome_accounting.tex"
    )
    outcome_table_path.parent.mkdir(parents=True, exist_ok=True)
    outcome_table_path.write_text(render_outcome_table(outcome_counts), encoding="utf-8")
    summary = {
        "figures": figures,
        "figure_count": len(figures),
        "pdf_count": len(figures),
        "png_count": 0,
        "plot_semantics": {
            "deviation_figures": "one circular marker per metric-eligible positive-service execution",
            "outcome_table": (
                "configuration-regime, execution-outcome, and metric-valid "
                "counts aggregated by blockchain and validator-set size"
            ),
        },
        "horizontal_offset": (
            "deterministic within-configuration offset in [-0.18, 0.18]; "
            "visual separation only"
        ),
        "layout_verification": {
            "deviation_source_inches": list(DEVIATION_FIGURE_SIZE),
            "recommended_manuscript_width_fraction": FINAL_PLACEMENT_FRACTION,
            "source_minimum_text_pt": SOURCE_MINIMUM_TEXT_PT,
            "pdf_fonttype": int(matplotlib.rcParams["pdf.fonttype"]),
            "panel_decision": (
                "use one full-width six-workload PDF per metric, with vertically "
                "stacked 10- and 40-node panels, one shared legend, absolute "
                "deviations on the left, relative deviations on the right, and "
                "node-specific titles below each panel"
            ),
        },
        "plotted_execution_manifest": str(manifest_path.relative_to(REPOSITORY_ROOT)),
        "manuscript_caption_replacements": str(caption_path.relative_to(REPOSITORY_ROOT)),
        "manuscript_outcome_table": str(
            outcome_table_path.relative_to(REPOSITORY_ROOT)
        ),
        "manifest_rows": int(len(manifest)),
        "configuration_outcome_rows": int(len(outcome_counts)),
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
            r"% Exact R1.5/R2.6 caption replacements for IEEE Access/4_Measurement_Results.tex",
            r"% fig:tps-deviations",
            r"\caption{\vd{R1.5/R2.6: Run-level throughput deviations across all six workloads at 10 and 40 nodes. Each colored circle is one point-valued positive-service TPS execution; deterministic horizontal offsets separate runs without changing their configuration. Left and right panels report $\Delta$ TPS and $\Delta$ Percentage, respectively; triangles mark relative deviations beyond $\pm100\%$, and $\times$ marks a configuration with no point-valued TPS execution. Non-positive outcomes are reported in Table~\ref{tab:r26_outcome_accounting}.}}",
            r"% fig:latency-deviations",
            r"\caption{\vd{R1.5/R2.6: Run-level block-latency deviations across all six workloads at 10 and 40 nodes. Each colored circle is one metric-eligible positive-service execution; plotting conventions are as in Figure~\ref{fig:tps-deviations}, with left panels reporting $\Delta$ Block latency (s). Non-positive outcomes are reported in Table~\ref{tab:r26_outcome_accounting}.}}",
            r"% fig:energy-deviations",
            r"\caption{\vd{R1.5/R2.6: Run-level positive-service energy deviations across all six workloads at 10 and 40 nodes. Each colored circle is one positive-service energy execution; plotting conventions are as in Figure~\ref{fig:tps-deviations}, with left panels reporting $\Delta$ Energy (kWh). Energy measurements for non-positive outcomes are not plotted; their counts are reported in Table~\ref{tab:r26_outcome_accounting}.}}",
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
