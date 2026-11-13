"""Owner: M1. worst_case(playbook, rs, trials, seed) -> Trace (24h plan
section 8: "Evaluation: metrics and the worst-case search").

Optuna TPE search over fa.plans.playbooks.PARAM_RANGES, fixed seed,
objective = maximise loss_through; ties broken by fewer steps / less
waiting. random_search_baseline runs the same trial budget with uniform
random sampling instead of TPE, for the chart's baseline line.

Each trial restores a snapshot, builds a plan via the attacker/playbooks,
executes it (fa.plans.executor.execute), and scores loss_through. Coded
against M3's snapshot and M4's engine interfaces, which are still stubs.
"""
from __future__ import annotations

import random

import optuna

from fa.contracts import Plan, RuleSet, Trace
from fa.core.state import new_state
from fa.plans.executor import execute
from fa.plans.playbooks import PARAM_RANGES, build_plan

optuna.logging.set_verbosity(optuna.logging.WARNING)


def _sample_params(trial: optuna.Trial, playbook: str) -> dict:
    return {
        name: trial.suggest_float(name, lo, hi)
        for name, (lo, hi) in PARAM_RANGES[playbook].items()
    }


def _score(trace: Trace, plan: Plan) -> tuple[int, int, int]:
    # Optuna maximizes a single float; break ties by fewer steps and less
    # waiting time by folding them into the score as small penalties.
    n_steps = len(plan.steps)
    total_wait = plan.steps[-1].t - plan.steps[0].t if plan.steps else 0
    return trace.loss_through, -n_steps, -total_wait


def _run_trial(playbook: str, rs: RuleSet, seed: int, params: dict) -> tuple[Trace, Plan]:
    plan = build_plan(playbook, params, seed=seed)
    trace = execute(plan, new_state(), rs)
    return trace, plan


def worst_case(playbook: str, rs: RuleSet, trials: int, seed: int) -> Trace:
    best: tuple[Trace, Plan] | None = None
    best_score: tuple[int, int, int] | None = None

    sampler = optuna.samplers.TPESampler(seed=seed)
    study = optuna.create_study(direction="maximize", sampler=sampler)

    def objective(trial: optuna.Trial) -> float:
        nonlocal best, best_score
        params = _sample_params(trial, playbook)
        trace, plan = _run_trial(playbook, rs, seed, params)
        score = _score(trace, plan)
        if best_score is None or score > best_score:
            best, best_score = (trace, plan), score
        return float(trace.loss_through)

    study.optimize(objective, n_trials=trials, show_progress_bar=False)
    assert best is not None
    return best[0]


def random_search_baseline(playbook: str, rs: RuleSet, trials: int, seed: int) -> Trace:
    rng = random.Random(seed)
    best: tuple[Trace, Plan] | None = None
    best_score: tuple[int, int, int] | None = None

    for _ in range(trials):
        params = {name: rng.uniform(lo, hi) for name, (lo, hi) in PARAM_RANGES[playbook].items()}
        trace, plan = _run_trial(playbook, rs, seed, params)
        score = _score(trace, plan)
        if best_score is None or score > best_score:
            best, best_score = (trace, plan), score

    assert best is not None
    return best[0]
