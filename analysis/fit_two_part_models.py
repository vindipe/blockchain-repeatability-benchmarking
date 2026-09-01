"""Fit the R1.10/R1.11 two-part outcome and conditional-performance models.

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
from scipy import linalg
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


def estimable_design(
    formula: str, data: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, list[dict[str, object]], dict[str, object]]:
    """Return a deterministic full-rank basis for the observed design support.

    Patsy's nominal sum-contrast design can be rank-deficient when a conditional
    positive-service cell is empty. Columns are considered in hierarchical
    formula order and retained only when they increase rank. This preserves the
    complete estimable column space without inventing observations for empty
    cells. Term membership is retained for explicit joint tests on the
    supported degrees of freedom under the fixed sum-contrast specification.
    """

    response, candidate = dmatrices(formula, data, return_type="dataframe")
    design_info = candidate.design_info
    kept: list[int] = []
    aliased: list[int] = []
    orthogonal_basis = np.empty((candidate.shape[0], 0), dtype=float)
    for term in design_info.terms:
        term_slice = design_info.slice(term)
        term_columns = list(range(term_slice.start, term_slice.stop))
        block = candidate.iloc[:, term_columns].to_numpy(float)
        if orthogonal_basis.shape[1]:
            block = block - orthogonal_basis @ (orthogonal_basis.T @ block)
        block_rank = int(np.linalg.matrix_rank(block))
        if block_rank:
            _, _, pivot = linalg.qr(block, mode="economic", pivoting=True)
            selected = sorted(term_columns[index] for index in pivot[:block_rank])
        else:
            selected = []
        kept.extend(selected)
        aliased.extend(column for column in term_columns if column not in selected)
        orthogonal_basis, _ = linalg.qr(
            candidate.iloc[:, kept].to_numpy(float), mode="economic"
        )

    design = candidate.iloc[:, kept].copy()
    original_to_reduced = {original: reduced for reduced, original in enumerate(kept)}
    terms: list[dict[str, object]] = []
    for term in design_info.terms:
        nominal_slice = design_info.slice(term)
        original_columns = list(range(nominal_slice.start, nominal_slice.stop))
        reduced_columns = [
            original_to_reduced[column]
            for column in original_columns
            if column in original_to_reduced
        ]
        terms.append(
            {
                "name": term.name(),
                "factors": frozenset(factor.name() for factor in term.factors),
                "columns": reduced_columns,
                "nominal_columns": len(original_columns),
            }
        )

    singular = np.linalg.svd(design.to_numpy(float), compute_uv=False)
    diagnostics = {
        "observations": int(design.shape[0]),
        "columns": int(design.shape[1]),
        "rank": int(np.linalg.matrix_rank(design.to_numpy(float))),
        "rank_deficiency": 0,
        "condition_number": float(singular[0] / singular[-1]),
        "full_rank": True,
        "candidate_design_columns": int(candidate.shape[1]),
        "candidate_design_rank": int(np.linalg.matrix_rank(candidate.to_numpy(float))),
        "candidate_rank_deficiency": int(candidate.shape[1] - len(kept)),
        "support_adjusted": bool(aliased),
        "aliased_columns": [str(candidate.columns[column]) for column in aliased],
    }
    return response, design, terms, diagnostics


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


def linear_term_tables(
    model, terms: list[dict[str, object]] | None = None
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Compute HC3 Type-II and Type-III tests on an estimable basis."""

    if terms is None:
        design_info = model.model.data.design_info
        terms = []
        for term in design_info.terms:
            column_slice = design_info.slice(term)
            terms.append(
                {
                    "name": term.name(),
                    "factors": frozenset(factor.name() for factor in term.factors),
                    "columns": list(range(column_slice.start, column_slice.stop)),
                    "nominal_columns": column_slice.stop - column_slice.start,
                }
            )

    terms = [term for term in terms if term["name"] != "Intercept"]
    identity = np.eye(model.model.exog.shape[1])
    robust_cov = np.asarray(model.cov_HC3)
    classical_cov = np.asarray(model.cov_params())
    residual_ss = float(model.ssr)
    primary_rows: list[dict[str, object]] = []
    sensitivity_rows: list[dict[str, object]] = []
    for term in terms:
        name = str(term["name"])
        term_factors = set(term["factors"])
        own_columns = list(term["columns"])
        higher_columns: list[int] = []
        for other in terms:
            other_factors = set(other["factors"])
            if term_factors < other_factors:
                higher_columns.extend(other["columns"])

        l1_columns = own_columns + higher_columns
        L1 = identity[l1_columns]
        L2 = identity[higher_columns]
        if L2.size:
            lvl = L1 @ robust_cov @ L2.T
            orthogonal, _ = linalg.qr(lvl, mode="full")
            df = len(own_columns)
            L12 = orthogonal[:, -df:].T @ L1
        else:
            L12 = L1
            df = len(own_columns)
        robust_test = model.f_test(L12, cov_p=robust_cov)
        classical_test = model.f_test(L12, cov_p=classical_cov)
        classical_ss = float(classical_test.fvalue) * df * residual_ss / model.df_resid
        primary_rows.append(
            {
                "term": TERM_DISPLAY.get(name, name),
                "term_formula": name,
                "test": "HC3 Type-II F",
                "statistic": float(robust_test.fvalue),
                "df": float(df),
                "nominal_df": float(term["nominal_columns"]),
                "residual_df": float(model.df_resid),
                "p_value": float(robust_test.pvalue),
                "partial_eta_squared": classical_ss / (classical_ss + residual_ss),
            }
        )
        type_iii = model.f_test(identity[own_columns], cov_p=robust_cov)
        sensitivity_rows.append(
            {
                "term": TERM_DISPLAY.get(name, name),
                "term_formula": name,
                "test": "HC3 Type-III F",
                "statistic": float(type_iii.fvalue),
                "df": float(df),
                "nominal_df": float(term["nominal_columns"]),
                "residual_df": float(model.df_resid),
                "p_value": float(type_iii.pvalue),
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
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        response, design, terms, diagnostics = estimable_design(formula, eligible)
        model = sm.OLS(response.iloc[:, 0], design).fit()
        primary, sensitivity = linear_term_tables(model, terms)
    empty_bw = (
        eligible.groupby(["blockchain", "workload"], observed=False)
        .size()
        .reindex(
            pd.MultiIndex.from_product(
                [
                    sorted(data["blockchain"].unique()),
                    sorted(data["workload"].unique()),
                ],
                names=["blockchain", "workload"],
            ),
            fill_value=0,
        )
    )
    diagnostics["empty_positive_service_blockchain_workload_cells"] = [
        f"{blockchain} / {workload}"
        for (blockchain, workload), count in empty_bw.items()
        if count == 0
    ]
    diagnostics["sparse_positive_service_blockchain_workload_cells"] = [
        f"{blockchain} / {workload}: n={int(count)}"
        for (blockchain, workload), count in empty_bw.items()
        if 0 < count < 5
    ]
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
    _, _, _, base = estimable_design(base_formula, eligible)
    rows = []
    for display, term in TARGETED_THREE_WAY.items():
        formula = f"{base_formula} + {term}"
        _, _, terms, diag = estimable_design(formula, eligible)
        added_term = next(item for item in terms if item["name"] == term)
        added_columns = int(added_term["nominal_columns"])
        added_rank = len(added_term["columns"])
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
                "estimable_on_observed_support": added_rank > 0,
            }
        )
    return pd.DataFrame(rows)


def targeted_three_way_sensitivity(data: pd.DataFrame) -> pd.DataFrame:
    """Fit targeted three-way additions when the added columns are estimable."""

    rows: list[dict[str, object]] = []
    outcome_data = data.copy()
    outcome_data["positive_commit_indicator"] = outcome_data[
        "positive_commit_derived"
    ].astype(int)
    outcome_base_formula = f"positive_commit_indicator ~ {TWO_WAY_RHS}"
    outcome_base_diag = design_diagnostics(outcome_base_formula, outcome_data)
    outcome_base_model = smf.glm(
        outcome_base_formula,
        data=outcome_data,
        family=sm.families.Binomial(),
    ).fit(maxiter=200)

    for display, term in TARGETED_THREE_WAY.items():
        formula = f"{outcome_base_formula} + {term}"
        diag = design_diagnostics(formula, outcome_data)
        added_columns = int(diag["columns"]) - int(outcome_base_diag["columns"])
        added_rank = int(diag["rank"]) - int(outcome_base_diag["rank"])
        fully_estimable = added_columns == added_rank and bool(diag["full_rank"])
        statistic = np.nan
        p_value = np.nan
        df = added_rank
        status = "not estimable"
        if fully_estimable:
            augmented = smf.glm(
                formula,
                data=outcome_data,
                family=sm.families.Binomial(),
            ).fit(maxiter=200)
            statistic = max(0.0, float(outcome_base_model.deviance - augmented.deviance))
            df = int(outcome_base_model.df_resid - augmented.df_resid)
            p_value = float(st.chi2.sf(statistic, df))
            status = "reported"
        rows.append(
            {
                "component": "Outcome",
                "metric": "Positive commit",
                "interaction": display,
                "test": "likelihood-ratio chi-square",
                "statistic": statistic,
                "df": df,
                "p_value": p_value,
                "added_columns": added_columns,
                "added_rank": added_rank,
                "fully_estimable": fully_estimable,
                "reported": fully_estimable,
                "status": status,
            }
        )

    for metric in METRIC_SPECS:
        value_column, eligibility_column = METRIC_SPECS[metric]
        eligible = data.loc[data[eligibility_column]].copy()
        eligible["log_value"] = np.log(pd.to_numeric(eligible[value_column]))
        base_formula = f"log_value ~ {TWO_WAY_RHS}"
        for display, term in TARGETED_THREE_WAY.items():
            formula = f"{base_formula} + {term}"
            response, design, terms, _ = estimable_design(formula, eligible)
            added_term = next(item for item in terms if item["name"] == term)
            added_columns = int(added_term["nominal_columns"])
            added_rank = len(added_term["columns"])
            fully_estimable = added_columns == added_rank
            statistic = np.nan
            p_value = np.nan
            df = added_rank
            residual_df = np.nan
            status = "not estimable"
            reported = added_rank > 0
            if reported:
                augmented = sm.OLS(response.iloc[:, 0], design).fit()
                restriction = np.eye(design.shape[1])[added_term["columns"]]
                robust = augmented.f_test(restriction, cov_p=augmented.cov_HC3)
                statistic = float(robust.fvalue)
                df = float(added_rank)
                residual_df = float(augmented.df_resid)
                p_value = float(robust.pvalue)
                status = "reported" if fully_estimable else "reported on observed support"
            rows.append(
                {
                    "component": "Conditional performance",
                    "metric": metric,
                    "interaction": display,
                    "test": "HC3 Type-II F",
                    "statistic": statistic,
                    "df": df,
                    "residual_df": residual_df,
                    "p_value": p_value,
                    "added_columns": added_columns,
                    "added_rank": added_rank,
                    "fully_estimable": fully_estimable,
                    "reported": reported,
                    "status": status,
                }
            )
    return pd.DataFrame(rows)


def p_text(value: float) -> str:
    if not np.isfinite(value):
        return "--"
    if value < 0.001:
        return "$<0.001$"
    return f"{value:.3f}"


def render_term_table(
    outcome: pd.DataFrame,
    performance: pd.DataFrame,
    outcome_quasi_separation: bool = False,
) -> str:
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
    support_adjusted_metrics = sorted(
        {
            str(row["metric"])
            for _, row in performance.iterrows()
            if bool(row.get("support_adjusted", False))
        }
    )
    support_note = (
        " The conditional models are fitted on a full-rank basis for the "
        "observed positive-service support. For the six-workload scope, "
        "Quorum--FIFA and Quorum--Gaming contain no positive-service "
        "observations; the blockchain--workload test consequently uses 18 "
        "estimable df rather than 20, without imputing either cell."
        if support_adjusted_metrics
        else ""
    )
    outcome_caution_note = (
        " The binomial outcome component exhibits quasi-separation in this "
        "scope; its likelihood-ratio rows are retained as model-screening "
        "evidence for service incidence, not as finite-sample causal inference."
        if outcome_quasi_separation
        else ""
    )
    lines = [
        r"\begin{table*}[t]",
        r"\centering",
        r"\caption{\vd{R1.9/R1.10: Two-part factorial models. The outcome component reports likelihood-ratio $\chi^2$ tests; conditional log-performance models report Type-II $F$ tests with HC3 covariance and partial $\eta^2$.}}",
        r"\label{tab:two_part_factorial_models}",
        r"\footnotesize",
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
            + support_note
            + outcome_caution_note
            + "}",
            r"\end{table*}",
            "",
        ]
    )
    return "\n".join(lines)


def render_estimability_table(table: pd.DataFrame) -> str:
    lines = [
        r"\begin{table*}[t]",
        r"\centering",
        r"\caption{\vd{R1.11: Design-matrix audit for targeted three-way interaction sensitivities. Added rank gives the supported degrees of freedom; a term can be tested on observed support even when empty positive-service cells reduce its nominal rank.}}",
        r"\label{tab:three_way_estimability}",
        r"\footnotesize",
        r"\begin{tabular}{llrrc}",
        r"\hline",
        r"Metric & Interaction & Added columns & Added rank & Full nominal rank \\",
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
    lines.extend([r"\hline", r"\end{tabular}", r"\end{table*}", ""])
    return "\n".join(lines)


def render_three_way_sensitivity_table(
    table: pd.DataFrame, outcome_quasi_separation: bool = False
) -> str:
    outcome_caution_note = (
        " The outcome likelihood-ratio rows are retained as model-screening "
        "evidence because the binomial component exhibits quasi-separation in "
        "this scope."
        if outcome_quasi_separation
        else ""
    )
    lines = [
        r"\begin{table*}[t]",
        r"\centering",
        r"\caption{\vd{R1.11: Targeted three-way interaction sensitivity tests. Conditional-performance terms are tested on their estimable observed-support basis; added rank over nominal columns is shown when empty positive-service cells reduce rank.}}",
        r"\label{tab:three_way_sensitivity}",
        r"\footnotesize",
        r"\resizebox{\textwidth}{!}{%",
        r"\begin{tabular}{lllrrrc}",
        r"\hline",
        r"Component & Metric & Interaction & Test statistic & df & $p$ & Status \\",
        r"\hline",
    ]
    for _, row in table.iterrows():
        interaction = str(row["interaction"]).replace("Blockchain", "B").replace(
            "topology", "T"
        ).replace("workload", "W").replace("size", "S")
        if bool(row.get("reported", row["fully_estimable"])):
            statistic = f"{row['statistic']:.2f}"
            df = (
                f"{row['df']:.0f}"
                if bool(row["fully_estimable"])
                else f"{int(row['added_rank'])}/{int(row['added_columns'])}"
            )
            p_value = p_text(float(row["p_value"]))
        else:
            statistic = "--"
            df = f"{int(row['added_rank'])}/{int(row['added_columns'])}"
            p_value = "--"
        lines.append(
            f"{row['component']} & {row['metric']} & {interaction} & "
            f"{statistic} & {df} & {p_value} & {row['status']} \\\\"
        )
    lines.extend(
        [
            r"\hline",
            r"\end{tabular}",
            r"}",
            r"\vspace{1mm}",
            r"\parbox{\textwidth}{\footnotesize Outcome rows report likelihood-ratio $\chi^2$ deletion tests comparing the two-way model with the targeted three-way augmentation. Conditional-performance rows report HC3 Type-II $F$ tests for the added highest-order term. When empty positive-service cells reduce nominal rank, df is shown as supported rank over nominal columns; no empty cell is imputed."
            + outcome_caution_note
            + "}",
            r"\end{table*}",
            "",
        ]
    )
    return "\n".join(lines)


def run_models(input_path: Path, output_dir: Path, table_dir: Path) -> dict[str, object]:
    derived = derive_outcomes(prepare_selected_runs(load_runs(input_path)))
    summary: dict[str, object] = {"scopes": {}}
    for scope in ("legacy_three_workloads", "six_workloads"):
        data = scope_frame(derived, scope)
        scope_output = output_dir / scope
        scope_output.mkdir(parents=True, exist_ok=True)
        stale_wald_output = scope_output / "outcome_wald_tests.csv"
        if stale_wald_output.exists():
            stale_wald_output.unlink()
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
            primary["support_adjusted"] = bool(diagnostics["support_adjusted"])
            sensitivity["support_adjusted"] = bool(diagnostics["support_adjusted"])
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
        three_way_sensitivity = targeted_three_way_sensitivity(data)
        performance.to_csv(scope_output / "performance_type_ii_hc3.csv", index=False)
        sensitivity.to_csv(scope_output / "performance_type_iii_hc3_sensitivity.csv", index=False)
        estimability.to_csv(scope_output / "three_way_estimability.csv", index=False)
        three_way_sensitivity.to_csv(
            scope_output / "three_way_sensitivity.csv", index=False
        )
        (scope_tables / "table_two_part_factorial_models.tex").write_text(
            render_term_table(
                outcome_tests,
                performance,
                outcome_quasi_separation=bool(
                    outcome_diag["quasi_separation_warning"]
                ),
            ),
            encoding="utf-8",
        )
        (scope_tables / "table_three_way_estimability.tex").write_text(
            render_estimability_table(estimability), encoding="utf-8"
        )
        (scope_tables / "table_three_way_sensitivity.tex").write_text(
            render_three_way_sensitivity_table(
                three_way_sensitivity,
                outcome_quasi_separation=bool(
                    outcome_diag["quasi_separation_warning"]
                ),
            ),
            encoding="utf-8",
        )
        scope_summary = {
            "rows": int(len(data)),
            "outcome_model": outcome_diag,
            "conditional_models": linear_diagnostics,
            "all_two_way_models_full_rank": bool(
                outcome_diag["full_rank"]
                and all(item["full_rank"] for item in linear_diagnostics.values())
            ),
            "all_nominal_two_way_designs_full_rank": bool(
                outcome_diag["full_rank"]
                and all(
                    not item["support_adjusted"]
                    for item in linear_diagnostics.values()
                )
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
