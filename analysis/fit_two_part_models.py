"""Fit the S2/S3 two-part outcome and conditional-performance models.

The first component is a binomial GLM for an observed positive commit.  The
second component fits OLS models to log-transformed, metric-eligible TPS,
latency, and energy observations.  Every primary model contains all two-way
interactions among blockchain, topology, workload, and validator-set size.

The script records design-matrix rank before interpreting any model, reports
likelihood-ratio tests for the binomial component, HC3 Type-II tests and
partial eta squared for the linear component, Type-III sensitivity tests with
sum-to-zero contrasts, residual diagnostics, and the estimability of the two
targeted three-way interactions requested during review.
"""

from __future__ import annotations

import argparse
import json
import math
import warnings
from collections.abc import Sequence
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import scipy.stats as st
import statsmodels.api as sm
import statsmodels.formula.api as smf
from patsy import dmatrices
from statsmodels.stats.anova import anova_lm
from statsmodels.stats.diagnostic import het_breuschpagan
from statsmodels.stats.stattools import jarque_bera

try:
    from .audit_observed_runs import (
        DEFAULT_INPUT,
        PRIMARY_WORKLOADS_LEGACY,
        load_runs,
    )
    from .derive_run_outcomes import derive_outcomes, prepare_selected_runs
except ImportError:  # Direct execution
    from audit_observed_runs import (  # type: ignore[no-redef]
        DEFAULT_INPUT,
        PRIMARY_WORKLOADS_LEGACY,
        load_runs,
    )
    from derive_run_outcomes import (  # type: ignore[no-redef]
        derive_outcomes,
        prepare_selected_runs,
    )


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUTPUT_DIR = REPOSITORY_ROOT / "outputs" / "revision" / "statistical_models"
DEFAULT_TABLE_DIR = REPOSITORY_ROOT / "paper_tables"

FACTOR_EXPRESSIONS = {
    "Blockchain": "C(blockchain, Sum)",
    "Topology": "C(mode, Sum)",
    "Workload": "C(workload, Sum)",
    "Size": "C(network_size, Sum)",
}
BASE_EXPRESSION = "+".join(FACTOR_EXPRESSIONS.values())
TWO_WAY_RHS = f"({BASE_EXPRESSION})**2"
TARGETED_THREE_WAY = {
    "Blockchain $\\times$ topology $\\times$ workload": (
        "C(blockchain, Sum):C(mode, Sum):C(workload, Sum)"
    ),
    "Blockchain $\\times$ workload $\\times$ size": (
        "C(blockchain, Sum):C(workload, Sum):C(network_size, Sum)"
    ),
}

TERM_DISPLAY = {
    "C(blockchain, Sum)": "Blockchain",
    "C(mode, Sum)": "Topology",
    "C(workload, Sum)": "Workload",
    "C(network_size, Sum)": "Size",
    "C(blockchain, Sum):C(mode, Sum)": "Blockchain $\\times$ topology",
    "C(blockchain, Sum):C(workload, Sum)": "Blockchain $\\times$ workload",
    "C(blockchain, Sum):C(network_size, Sum)": "Blockchain $\\times$ size",
    "C(mode, Sum):C(workload, Sum)": "Topology $\\times$ workload",
    "C(mode, Sum):C(network_size, Sum)": "Topology $\\times$ size",
    "C(workload, Sum):C(network_size, Sum)": "Workload $\\times$ size",
}

METRIC_SPECS = {
    "TPS": ("average_throughput", "tps_point_valid_positive_commit"),
    "Latency": ("average_latency", "latency_valid_positive_commit"),
    "Energy": ("energy", "energy_valid_positive_commit"),
}


def scope_frame(derived: pd.DataFrame, scope: str) -> pd.DataFrame:
    if scope == "legacy_three_workloads":
        return derived.loc[derived["workload"].isin(PRIMARY_WORKLOADS_LEGACY)].copy()
    if scope == "six_workloads":
        return derived.copy()
    raise ValueError(f"Unknown scope: {scope}")


def design_diagnostics(formula: str, data: pd.DataFrame) -> dict[str, object]:
    _, matrix = dmatrices(formula, data, return_type="dataframe")
    rank = int(np.linalg.matrix_rank(matrix.to_numpy(float)))
    columns = int(matrix.shape[1])
    singular = np.linalg.svd(matrix.to_numpy(float), compute_uv=False)
    condition = float(singular[0] / singular[-1]) if singular[-1] > 0 else math.inf
    return {
        "observations": int(matrix.shape[0]),
        "columns": columns,
        "rank": rank,
        "rank_deficiency": columns - rank,
        "condition_number": condition,
        "full_rank": rank == columns,
    }


def model_terms(model) -> list[str]:
    return [
        term
        for term in model.model.data.design_info.term_names
        if term != "Intercept"
    ]


def fit_binomial(data: pd.DataFrame) -> tuple[object, pd.DataFrame, dict[str, object]]:
    model_data = data.copy()
    # Patsy treats a Boolean response as a two-level categorical response and
    # may choose the opposite internal level ordering.  An explicit 0/1 field
    # makes the model direction unambiguous and keeps prediction diagnostics
    # aligned with positive_commit_derived.
    model_data["positive_commit_indicator"] = model_data[
        "positive_commit_derived"
    ].astype(int)
    formula = f"positive_commit_indicator ~ {TWO_WAY_RHS}"
    model = smf.glm(formula, data=model_data, family=sm.families.Binomial()).fit(
        maxiter=200
    )
    null_model = smf.glm(
        "positive_commit_indicator ~ 1",
        data=model_data,
        family=sm.families.Binomial(),
    ).fit(maxiter=200)
    rows: list[dict[str, object]] = []
    for term in model_terms(model):
        if term in FACTOR_EXPRESSIONS.values():
            # Hierarchical omnibus test: a factor cannot be removed while its
            # interactions remain, because that leaves the same model column
            # space under sum contrasts.  Remove the factor together with all
            # interactions containing it and label the test accordingly.
            remaining = [value for value in FACTOR_EXPRESSIONS.values() if value != term]
            reduced_rhs = f"({'+'.join(remaining)})**2"
            display = f"{TERM_DISPLAY[term]} (omnibus)"
        else:
            reduced_rhs = f"{TWO_WAY_RHS} - {term}"
            display = TERM_DISPLAY.get(term, term)
        reduced = smf.glm(
            f"positive_commit_indicator ~ {reduced_rhs}",
            data=model_data,
            family=sm.families.Binomial(),
        ).fit(maxiter=200)
        statistic = max(0.0, float(reduced.deviance - model.deviance))
        df = int(model.df_model - reduced.df_model)
        rows.append(
            {
                "term": display,
                "term_formula": term,
                "test": "hierarchical likelihood-ratio chi-square"
                if term in FACTOR_EXPRESSIONS.values()
                else "likelihood-ratio chi-square",
                "statistic": statistic,
                "df": df,
                "p_value": float(st.chi2.sf(statistic, df)),
            }
        )

    probabilities = np.asarray(model.predict(), dtype=float)
    observed = model_data["positive_commit_indicator"].to_numpy()
    order = st.rankdata(probabilities)
    positives = int(observed.sum())
    negatives = int(len(observed) - positives)
    auc = (
        float((order[observed == 1].sum() - positives * (positives + 1) / 2) /
              (positives * negatives))
        if positives and negatives
        else np.nan
    )
    all_one_or_zero_cells = int(
        data.groupby(["blockchain", "mode", "workload", "network_size"], observed=True)[
            "positive_commit_derived"
        ].nunique().eq(1).sum()
    )
    diagnostics = {
        **design_diagnostics(formula, model_data),
        "converged": bool(model.converged),
        "iterations": int(model.fit_history.get("iteration", -1)),
        "deviance": float(model.deviance),
        "pearson_chi2_per_residual_df": float(model.pearson_chi2 / model.df_resid),
        "mcfadden_pseudo_r2": float(1.0 - model.llf / null_model.llf),
        "brier_score": float(np.mean((observed - probabilities) ** 2)),
        "auc": auc,
        "maximum_absolute_coefficient": float(np.max(np.abs(model.params))),
        "configuration_cells_with_single_observed_outcome": all_one_or_zero_cells,
        "quasi_separation_warning": bool(
            np.max(np.abs(model.params)) > 15
            or np.mean((probabilities < 1e-8) | (probabilities > 1 - 1e-8)) > 0.05
        ),
    }
    return model, pd.DataFrame(rows), diagnostics


def linear_term_tables(model) -> tuple[pd.DataFrame, pd.DataFrame]:
    classical_type_ii = anova_lm(model, typ=2)
    robust_type_ii = anova_lm(model, typ=2, robust="hc3")
    robust_type_iii = anova_lm(model, typ=3, robust="hc3")
    residual_ss = float(classical_type_ii.loc["Residual", "sum_sq"])

    primary_rows: list[dict[str, object]] = []
    for term in model_terms(model):
        classical_ss = float(classical_type_ii.loc[term, "sum_sq"])
        robust = robust_type_ii.loc[term]
        primary_rows.append(
            {
                "term": TERM_DISPLAY.get(term, term),
                "term_formula": term,
                "test": "HC3 Type-II F",
                "statistic": float(robust["F"]),
                "df": float(robust["df"]),
                "residual_df": float(model.df_resid),
                "p_value": float(robust["PR(>F)"]),
                "partial_eta_squared": classical_ss / (classical_ss + residual_ss),
            }
        )

    sensitivity_rows: list[dict[str, object]] = []
    for term in model_terms(model):
        robust = robust_type_iii.loc[term]
        sensitivity_rows.append(
            {
                "term": TERM_DISPLAY.get(term, term),
                "term_formula": term,
                "test": "HC3 Type-III F",
                "statistic": float(robust["F"]),
                "df": float(robust["df"]),
                "residual_df": float(model.df_resid),
                "p_value": float(robust["PR(>F)"]),
            }
        )
    return pd.DataFrame(primary_rows), pd.DataFrame(sensitivity_rows)


def fit_linear_metric(
    data: pd.DataFrame, metric: str
) -> tuple[object, pd.DataFrame, pd.DataFrame, dict[str, object]]:
    value_column, eligibility_column = METRIC_SPECS[metric]
    eligible = data.loc[data[eligibility_column]].copy()
    eligible["log_value"] = np.log(pd.to_numeric(eligible[value_column]))
    formula = f"log_value ~ {TWO_WAY_RHS}"
    diagnostics = design_diagnostics(formula, eligible)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        model = smf.ols(formula, data=eligible).fit()
        primary, sensitivity = linear_term_tables(model)
    residuals = np.asarray(model.resid, dtype=float)
    bp = het_breuschpagan(residuals, model.model.exog)
    jb = jarque_bera(residuals)
    diagnostics.update(
        {
            "r_squared": float(model.rsquared),
            "adjusted_r_squared": float(model.rsquared_adj),
            "breusch_pagan_lm": float(bp[0]),
            "breusch_pagan_p_value": float(bp[1]),
            "jarque_bera": float(jb[0]),
            "jarque_bera_p_value": float(jb[1]),
            "warnings": sorted({str(item.message) for item in caught}),
        }
    )
    return model, primary, sensitivity, diagnostics


def save_residual_diagnostics(model, path: Path, title: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fig, axes = plt.subplots(1, 2, figsize=(8.0, 3.4))
    axes[0].scatter(model.fittedvalues, model.resid, s=7, alpha=0.35)
    axes[0].axhline(0, color="black", linewidth=0.8)
    axes[0].set_xlabel("Fitted log response")
    axes[0].set_ylabel("Residual")
    axes[0].set_title("Residuals vs fitted")
    sm.qqplot(model.resid, line="45", ax=axes[1], marker=".", markersize=3)
    axes[1].set_title("Normal Q--Q")
    fig.suptitle(title)
    fig.tight_layout()
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)


def three_way_estimability(data: pd.DataFrame, metric: str) -> pd.DataFrame:
    value_column, eligibility_column = METRIC_SPECS[metric]
    eligible = data.loc[data[eligibility_column]].copy()
    eligible["log_value"] = np.log(pd.to_numeric(eligible[value_column]))
    base_formula = f"log_value ~ {TWO_WAY_RHS}"
    base = design_diagnostics(base_formula, eligible)
    rows = []
    for display, term in TARGETED_THREE_WAY.items():
        formula = f"{base_formula} + {term}"
        diag = design_diagnostics(formula, eligible)
        added_columns = int(diag["columns"]) - int(base["columns"])
        added_rank = int(diag["rank"]) - int(base["rank"])
        rows.append(
            {
                "metric": metric,
                "interaction": display,
                "observations": diag["observations"],
                "design_columns": diag["columns"],
                "design_rank": diag["rank"],
                "rank_deficiency": diag["rank_deficiency"],
                "added_columns": added_columns,
                "added_rank": added_rank,
                "fully_estimable": added_columns == added_rank and bool(diag["full_rank"]),
            }
        )
    return pd.DataFrame(rows)


def p_text(value: float) -> str:
    if not np.isfinite(value):
        return "--"
    if value < 0.001:
        return "$<0.001$"
    return f"{value:.3f}"


def render_term_table(outcome: pd.DataFrame, performance: pd.DataFrame) -> str:
    suppressed_metrics = sorted(
        {
            str(row["metric"])
            for _, row in performance.iterrows()
            if not bool(row.get("design_full_rank", True))
        }
    )
    suppression_note = (
        " Performance inferential entries marked ``--'' are not reported because "
        "the corresponding conditional log-performance design matrix is "
        "rank-deficient; the estimability audit gives the exact rank deficiency."
        if suppressed_metrics
        else ""
    )
    lines = [
        r"\begin{table*}[t]",
        r"\centering",
        r"\caption{Two-part factorial models. The outcome component reports likelihood-ratio $\chi^2$ tests; conditional log-performance models report Type-II $F$ tests with HC3 covariance and partial $\eta^2$.}",
        r"\label{tab:two_part_factorial_models}",
        r"\small",
        r"\setlength{\tabcolsep}{3.4pt}",
        r"\resizebox{\textwidth}{!}{%",
        r"\begin{tabular}{lrr|rrr|rrr|rrr}",
        r"\hline",
        r"& \multicolumn{2}{c|}{Outcome} & \multicolumn{3}{c|}{TPS} & \multicolumn{3}{c|}{Latency} & \multicolumn{3}{c}{Energy} \\",
        r"Term & $\chi^2$ & $p$ & $F_{\mathrm{HC3}}$ & $p$ & $\eta_p^2$ & $F_{\mathrm{HC3}}$ & $p$ & $\eta_p^2$ & $F_{\mathrm{HC3}}$ & $p$ & $\eta_p^2$ \\",
        r"\hline",
    ]
    for _, row in outcome.iterrows():
        pieces = [
            str(row["term"]),
            f"{row['statistic']:.2f}",
            p_text(float(row["p_value"])),
        ]
        for metric in METRIC_SPECS:
            match = performance.loc[
                (performance["metric"] == metric)
                & (performance["term_formula"] == row["term_formula"])
            ].iloc[0]
            if not bool(match.get("design_full_rank", True)):
                pieces.extend(["--", "--", "--"])
            else:
                pieces.extend(
                    [
                        f"{match['statistic']:.2f}",
                        p_text(float(match["p_value"])),
                        f"{match['partial_eta_squared']:.3f}",
                    ]
                )
        lines.append(" & ".join(pieces) + r" \\")
    lines.extend(
        [
            r"\hline",
            r"\end{tabular}",
            r"}",
            r"\vspace{1mm}",
            r"\parbox{\textwidth}{\footnotesize Outcome interactions are likelihood-ratio deletion tests; each outcome main-factor row is a hierarchical omnibus test of that factor and all interactions containing it. Performance tests are Type-II tests on log-transformed, positive-service observations with HC3 covariance; $\eta_p^2$ is partial eta squared. Degrees of freedom are provided in the machine-readable output."
            + suppression_note
            + "}",
            r"\end{table*}",
            "",
        ]
    )
    return "\n".join(lines)


def render_estimability_table(table: pd.DataFrame) -> str:
    lines = [
        r"\begin{table}[t]",
        r"\centering",
        r"\caption{Design-matrix audit for targeted three-way interaction sensitivities. A term is retained for inference only when all added columns are estimable.}",
        r"\label{tab:three_way_estimability}",
        r"\small",
        r"\begin{tabular}{llrrc}",
        r"\hline",
        r"Metric & Interaction & Added columns & Added rank & Estimable \\",
        r"\hline",
    ]
    for _, row in table.iterrows():
        interaction = str(row["interaction"]).replace("Blockchain", "B").replace(
            "topology", "T"
        ).replace("workload", "W").replace("size", "S")
        lines.append(
            f"{row['metric']} & {interaction} & {int(row['added_columns'])} & "
            f"{int(row['added_rank'])} & {'yes' if row['fully_estimable'] else 'no'} \\\\"
        )
    lines.extend([r"\hline", r"\end{tabular}", r"\end{table}", ""])
    return "\n".join(lines)


def run_models(input_path: Path, output_dir: Path, table_dir: Path) -> dict[str, object]:
    derived = derive_outcomes(prepare_selected_runs(load_runs(input_path)))
    summary: dict[str, object] = {"scopes": {}}
    for scope in ("legacy_three_workloads", "six_workloads"):
        data = scope_frame(derived, scope)
        scope_output = output_dir / scope
        scope_output.mkdir(parents=True, exist_ok=True)
        scope_tables = table_dir / scope
        scope_tables.mkdir(parents=True, exist_ok=True)

        _, outcome_tests, outcome_diag = fit_binomial(data)
        outcome_tests.to_csv(scope_output / "outcome_likelihood_ratio_tests.csv", index=False)

        primary_parts = []
        sensitivity_parts = []
        estimability_parts = []
        linear_diagnostics = {}
        for metric in METRIC_SPECS:
            model, primary, sensitivity, diagnostics = fit_linear_metric(data, metric)
            primary.insert(0, "metric", metric)
            sensitivity.insert(0, "metric", metric)
            primary["design_full_rank"] = bool(diagnostics["full_rank"])
            sensitivity["design_full_rank"] = bool(diagnostics["full_rank"])
            primary_parts.append(primary)
            sensitivity_parts.append(sensitivity)
            estimability_parts.append(three_way_estimability(data, metric))
            linear_diagnostics[metric] = diagnostics
            save_residual_diagnostics(
                model,
                scope_output / f"diagnostics_{metric.lower()}.pdf",
                f"{metric}: {scope.replace('_', ' ')}",
            )

        performance = pd.concat(primary_parts, ignore_index=True)
        sensitivity = pd.concat(sensitivity_parts, ignore_index=True)
        estimability = pd.concat(estimability_parts, ignore_index=True)
        performance.to_csv(scope_output / "performance_type_ii_hc3.csv", index=False)
        sensitivity.to_csv(scope_output / "performance_type_iii_hc3_sensitivity.csv", index=False)
        estimability.to_csv(scope_output / "three_way_estimability.csv", index=False)
        (scope_tables / "table_two_part_factorial_models.tex").write_text(
            render_term_table(outcome_tests, performance), encoding="utf-8"
        )
        (scope_tables / "table_three_way_estimability.tex").write_text(
            render_estimability_table(estimability), encoding="utf-8"
        )
        scope_summary = {
            "rows": int(len(data)),
            "outcome_model": outcome_diag,
            "conditional_models": linear_diagnostics,
            "all_two_way_models_full_rank": bool(
                outcome_diag["full_rank"]
                and all(item["full_rank"] for item in linear_diagnostics.values())
            ),
            "all_targeted_three_way_models_fully_estimable": bool(
                estimability["fully_estimable"].all()
            ),
        }
        summary["scopes"][scope] = scope_summary
        (scope_output / "model_diagnostics.json").write_text(
            json.dumps(scope_summary, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "summary.json").write_text(
        json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return summary


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--table-dir", type=Path, default=DEFAULT_TABLE_DIR)
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    summary = run_models(args.input, args.output_dir, args.table_dir)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
