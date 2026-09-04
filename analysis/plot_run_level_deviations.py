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
DEVIATION_FIGURE_SIZE = (10.2, 5.6)
FINAL_PLACEMENT_FRACTION = 1.0
SOURCE_MINIMUM_TEXT_PT = 11.5
matplotlib.rcParams.update(
    {
        "pdf.fonttype": 42,
        "font.size": 11.5,
        "axes.titlesize": 11.5,
        "axes.labelsize": 11.5,
        "xtick.labelsize": 11.5,
        "ytick.labelsize": 11.5,
        "legend.fontsize": 11.5,
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
    fig, axes = plt.subplots(
        len(workloads), 2, figsize=DEVIATION_FIGURE_SIZE, squeeze=False
    )
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
                        s=13,
                        alpha=0.55,
                        color=TOPOLOGY_COLORS[topology],
                        linewidths=0,
                    )
                    axis.scatter(
                        x[overflow],
                        np.clip(y[overflow], -100.0, 100.0),
                        s=28,
                        alpha=0.85,
                        color=TOPOLOGY_COLORS[topology],
                        marker="^",
                        linewidths=0,
                    )
                else:
                    axis.scatter(
                        x,
                        y,
                        s=13,
                        alpha=0.55,
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
                            s=36,
                            color="black",
                            linewidths=1.2,
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
            axis.set_title(f"{workload}: {'absolute' if column == 0 else 'relative'}")
            centers = [2, 8, 14, 20, 26]
            axis.set_xticks(centers)
            axis.set_xticklabels(
                [BLOCKCHAIN_LABELS[item] for item in BLOCKCHAINS],
                rotation=15,
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
            markersize=6,
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
        y=0.895,
        fontsize=13.0,
    )
    fig.text(
        0.012,
        0.43,
        str(spec["absolute_label"]),
        rotation=90,
        ha="center",
        va="center",
        fontsize=11.5,
    )
    fig.text(
        0.502,
        0.43,
        "Signed deviation (%)",
        rotation=90,
        ha="center",
        va="center",
        fontsize=11.5,
    )
    fig.tight_layout(rect=(0.025, 0, 1, 0.825), h_pad=1.0, w_pad=1.0)
    output_dir.mkdir(parents=True, exist_ok=True)
    stem = f"{metric_key}_{network_size.replace(' ', '_')}_{group_name}"
    pdf = output_dir / f"{stem}.pdf"
    fig.savefig(pdf)
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
    outcome_manifest_path = output_dir / "configuration_outcome_table_manifest.csv"
    outcome_counts.to_csv(outcome_manifest_path, index=False)
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
                "retain one 3x2 deviation PDF per metric, validator size, and "
                "three-workload group; stack the two validator-size PDFs in "
                "each manuscript figure at full text width; report "
                "configuration-regime totals, execution outcomes, and "
                "metric-valid counts in one compact aggregate LaTeX table"
            ),
        },
        "plotted_execution_manifest": str(manifest_path.relative_to(REPOSITORY_ROOT)),
        "configuration_outcome_table_manifest": str(
            outcome_manifest_path.relative_to(REPOSITORY_ROOT)
        ),
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
            r"% fig:tps-added",
            r"\caption{\vd{R1.5/R2.6: Run-level throughput deviations for DDoS, FIFA, and Gaming at 10 and 40 validators. Each colored circle is one point-valued positive-service TPS execution; deterministic horizontal offsets separate runs without changing their configuration. Triangles mark relative deviations beyond $\pm100\%$, and $\times$ marks a configuration with no point-valued TPS execution. Zero-commit and no-submission executions are counted separately in Table~\ref{tab:r26_outcome_accounting}.}}",
            r"% fig:tps-main",
            r"\caption{\vd{R1.5/R2.6: Run-level throughput deviations for GAFAM, PayPal, and VISA at 10 and 40 validators. Each colored circle is one point-valued positive-service TPS execution; plotting conventions are as in Figure~\ref{fig:tps-added}, while non-positive outcomes are reported in Table~\ref{tab:r26_outcome_accounting}.}}",
            r"% fig:lat-added",
            r"\caption{\vd{R1.5/R2.6: Run-level block-latency deviations for DDoS, FIFA, and Gaming at 10 and 40 validators. Each colored circle is one metric-eligible positive-service execution; deterministic horizontal offsets separate runs without changing their configuration. Triangles mark relative deviations beyond $\pm100\%$, and $\times$ marks a configuration with no eligible latency execution. Zero-commit and no-submission executions are counted separately in Table~\ref{tab:r26_outcome_accounting}.}}",
            r"% fig:lat-main",
            r"\caption{\vd{R1.5/R2.6: Run-level block-latency deviations for GAFAM, PayPal, and VISA at 10 and 40 validators. Each colored circle is one metric-eligible positive-service execution; plotting conventions are as in Figure~\ref{fig:lat-added}, while non-positive outcomes are reported in Table~\ref{tab:r26_outcome_accounting}.}}",
            r"% fig:energy-added",
            r"\caption{\vd{R1.5/R2.6: Run-level positive-service energy deviations for DDoS, FIFA, and Gaming at 10 and 40 validators. Each colored circle is one positive-service energy execution; deterministic horizontal offsets separate runs without changing their configuration. $\times$ marks a configuration with no positive-service energy execution. Energy measurements for zero-commit and no-submission executions are not plotted here; their outcome counts are reported in Table~\ref{tab:r26_outcome_accounting}.}}",
            r"% fig:energy-main",
            r"\caption{\vd{R1.5/R2.6: Run-level positive-service energy deviations for GAFAM, PayPal, and VISA at 10 and 40 validators. Each colored circle is one positive-service energy execution; plotting conventions are as in Figure~\ref{fig:energy-added}, while non-positive outcomes are reported in Table~\ref{tab:r26_outcome_accounting}.}}",
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
