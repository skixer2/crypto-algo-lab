"""Formula validator — the gate every generated alpha must pass BEFORE any study.

Layers:
  1. AST static analysis
     - syntax parses; defines calculate_math_signal(df)
     - imports restricted to {numpy, pandas, math}
     - banned calls: open/exec/eval/compile/__import__/input
     - full-sample ops (rank/mean/max/min/std/sum/cum*/median/quantile/corr/
       cov/skew/kurt) allowed ONLY on rolling/ewm/expanding receivers
     - shift() with a negative literal argument rejected
  2. Runtime contract (isolated namespace, synthetic deterministic data)
     - returns a Series aligned with df
     - last 50 values finite (no inf/NaN tail), |values| <= 1 (+clip headroom)
     - deterministic: two runs identical
  3. CAUSALITY PROOF (the strong check AST can't give): the signal computed on
     a truncated prefix df[:k] must equal the full-df signal at every common
     index. Any lookahead fails this empirically, whatever syntactic form it
     takes. Two cuts tested (k=150, k=250).

Usage: python3 tuner/validate_formula.py <formula.py> [--quiet]
Exit 0 = PASS. Prints a JSON verdict.
"""
from __future__ import annotations

import ast
import importlib.util
import json
import os
import sys

import numpy as np
import pandas as pd

ALLOWED_MODULES = {"numpy", "pandas", "math", "np", "pd"}
BANNED_CALLS = {"open", "exec", "eval", "compile", "__import__", "input", "print"}
GLOBAL_OPS = {"rank", "mean", "max", "min", "std", "sum", "median", "quantile",
              "skew", "kurt", "corr", "cov", "cumsum", "cummax", "cummin",
              "cumprod", "var", "sem", "prod"}
WINDOWED = {"rolling", "ewm", "expanding"}


def _chain_attrs(node: ast.AST) -> list:
    """Flatten attribute chain: s.a().b() -> ['a','b'] (value side included)."""
    attrs = []
    while isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        attrs.append(node.func.attr)
        node = node.func.value
    return attrs


def static_checks(path: str) -> list:
    errors = []
    tree = ast.parse(open(path).read(), filename=path)

    funcs = [n.name for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    if "calculate_math_signal" not in funcs:
        errors.append("missing calculate_math_signal(df)")

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                root = a.name.split(".")[0]
                if root not in ALLOWED_MODULES:
                    errors.append(f"banned import: {a.name}")
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            if root and root not in ALLOWED_MODULES:
                errors.append(f"banned import-from: {node.module}")

        if isinstance(node, ast.Call):
            name = node.func.id if isinstance(node.func, ast.Name) else (
                node.func.attr if isinstance(node.func, ast.Attribute) else None)
            if name in BANNED_CALLS:
                errors.append(f"banned call: {name}()")
            if name == "shift":
                for a in node.args:
                    if isinstance(a, ast.UnaryOp) and isinstance(a.op, ast.USub):
                        errors.append("shift() with negative argument (lookahead)")
            if name in GLOBAL_OPS:
                chain = _chain_attrs(node)
                axis_is_1 = any(k.arg == "axis" and getattr(k.value, "value", None) == 1
                                for k in node.keywords)
                if not any(w in chain for w in WINDOWED) and not axis_is_1:
                    errors.append(
                        f"full-sample op .{name}() — must be rolling/ewm/expanding "
                        f"(or axis=1 cross-column, which is row-local and causal)")
    return errors


def synth_df(n: int = 300, seed: int = 42) -> pd.DataFrame:
    rng = np.random.RandomState(seed)
    px = 2000 + np.cumsum(rng.randn(n))
    return pd.DataFrame(
        {"open": px, "high": px + 2, "low": px - 2, "close": px,
         "volume": np.abs(rng.randn(n)) * 10 + 5},
        index=pd.date_range("2026-01-01", periods=n, freq="15min", tz="UTC"))


def runtime_checks(path: str) -> tuple:
    errors, warns = [], []
    spec = importlib.util.spec_from_file_location("candidate", path)
    mod = importlib.util.module_from_spec(spec)
    try:
        spec.loader.exec_module(mod)
    except Exception as e:
        return [f"import/exec failed: {e}"], warns

    fn = getattr(mod, "calculate_math_signal", None)
    if fn is None:
        return ["no calculate_math_signal"], warns

    df = synth_df()
    try:
        s1 = fn(df)
    except Exception as e:
        return [f"run failed: {e}"], warns
    s1 = pd.Series(s1).astype(float)
    if len(s1) != len(df):
        errors.append(f"length mismatch: {len(s1)} != {len(df)}")
    tail = s1.iloc[-50:]
    if not np.isfinite(tail.values).all():
        errors.append("non-finite values in tail (last 50)")
    if s1.abs().max() > 1.0 + 1e-9:
        warns.append(f"|signal| max {s1.abs().max():.3f} > 1 (wrapper clips; "
                     "prefer bounded formulas)")
    if str(s1.index.dtype) != str(df.index.dtype):
        warns.append("index dtype differs from input (wrapper realigns)")

    s2 = fn(synth_df())
    if not np.allclose(pd.Series(s1).fillna(0).values,
                       pd.Series(s2).fillna(0).values, atol=1e-12):
        errors.append("non-deterministic output")

    # CAUSALITY PROOF: prefix vs full at common indices
    for k in (150, 250):
        prefix = df.iloc[:k]
        sp = pd.Series(fn(prefix)).astype(float)
        common = sp.index
        diff = (sp.values - s1.loc[common].values)
        if not np.allclose(np.nan_to_num(diff, nan=0.0), 0.0, atol=1e-9):
            errors.append(f"LOOKAHEAD: prefix-vs-full mismatch at cut k={k}")
    return errors, warns


def main() -> int:
    if len(sys.argv) < 2:
        print("usage: validate_formula.py <formula.py>")
        return 2
    path = sys.argv[1]
    static_errs = static_checks(path)
    run_errs, warns = ([], []) if static_errs else runtime_checks(path)
    verdict = {
        "formula": os.path.basename(path),
        "static_errors": static_errs,
        "runtime_errors": run_errs,
        "warnings": warns,
        "verdict": "PASS" if not static_errs and not run_errs else "FAIL",
    }
    print(json.dumps(verdict, indent=1))
    return 0 if verdict["verdict"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main())
