"""
样本外验证协议模块 (P0-A)

提供因子级别的样本外验证能力：
- Walk-Forward 滚动验证：滑动窗口训练/测试，评估因子泛化能力
- Purged K-Fold CV：带清洗间隔的时间分层交叉验证，防止前视偏差
- Bootstrap IC 置信区间：非参数 Bootstrap 估计 IC 的置信区间

Author: AKShare MCP Server
Version: 2.0
"""

import math
import os
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass, field
from itertools import combinations
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
from scipy import stats


@dataclass
class ValidationResult:
    """单次验证结果"""
    train_ic: float = 0.0
    test_ic: float = 0.0
    train_rank_ic: float = 0.0
    test_rank_ic: float = 0.0
    train_size: int = 0
    test_size: int = 0
    train_start: int = 0
    train_end: int = 0
    test_start: int = 0
    test_end: int = 0
    group_returns: Optional[List[float]] = None
    long_short_return: float = 0.0


@dataclass
class ValidationSummary:
    """验证汇总统计"""
    n_folds: int = 0
    oos_ic_mean: float = 0.0
    oos_ic_std: float = 0.0
    oos_ic_ir: float = 0.0
    oos_rank_ic_mean: float = 0.0
    oos_rank_ic_std: float = 0.0
    oos_rank_ic_ir: float = 0.0
    is_ic_mean: float = 0.0
    is_ic_std: float = 0.0
    stability_ratio: float = 0.0
    degradation: float = 0.0
    oos_positive_ratio: float = 0.0
    oos_long_short_mean: float = 0.0
    fold_results: List[ValidationResult] = field(default_factory=list)
    ic_confidence_interval: Optional[Tuple[float, float]] = None
    method: str = ""


def _env_flag(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return bool(default)
    return str(raw).strip().lower() not in {"0", "false", "off", "no", "n"}


def _env_int(name: str, default: int, *, min_value: int, max_value: int) -> int:
    raw = os.getenv(name)
    try:
        val = int(str(raw).strip()) if raw is not None else int(default)
    except Exception:
        val = int(default)
    return max(min_value, min(max_value, val))


def _normalize_bootstrap_mode(mode: Optional[str]) -> str:
    val = str(mode or "").strip().lower()
    if val in {"fast", "full"}:
        return val
    return "full"


def _resolve_bootstrap_iterations(
    n_bootstrap: Optional[int],
    bootstrap_mode: Optional[str],
) -> int:
    mode = _normalize_bootstrap_mode(bootstrap_mode)
    default_n = 300 if mode == "fast" else 1000
    if n_bootstrap is None:
        n = default_n
    else:
        n = int(n_bootstrap)
    return max(50, min(20_000, n))


_CPU_COUNT = max(1, int(os.cpu_count() or 1))
_VALIDATION_PARALLEL_ENABLED = _env_flag("VALIDATION_PARALLEL_ENABLED", True)
_VALIDATION_MAX_WORKERS_DEFAULT = _env_int(
    "VALIDATION_MAX_WORKERS",
    min(_CPU_COUNT, 8),
    min_value=1,
    max_value=32,
)
_VALIDATION_PARALLEL_MIN_WORKLOAD = _env_int(
    "VALIDATION_PARALLEL_MIN_WORKLOAD",
    20_000,
    min_value=1_000,
    max_value=5_000_000,
)
_BOOTSTRAP_MODE_DEFAULT = _normalize_bootstrap_mode(os.getenv("BOOTSTRAP_MODE"))
_BOOTSTRAP_WARN_THRESHOLD = _env_int(
    "BOOTSTRAP_LARGE_SAMPLE_WARN_THRESHOLD",
    3_000,
    min_value=500,
    max_value=2_000_000,
)


def _rowwise_pearson_corr(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Compute Pearson correlation row-by-row for two 2D arrays."""
    if x.ndim != 2 or y.ndim != 2:
        raise ValueError("x and y must be 2D arrays")
    if x.shape != y.shape:
        raise ValueError("x and y must have the same shape")

    x = x.astype(np.float64, copy=False)
    y = y.astype(np.float64, copy=False)
    x_center = x - x.mean(axis=1, keepdims=True)
    y_center = y - y.mean(axis=1, keepdims=True)

    numerator = np.sum(x_center * y_center, axis=1)
    denom_x = np.sum(x_center * x_center, axis=1)
    denom_y = np.sum(y_center * y_center, axis=1)
    denominator = np.sqrt(denom_x * denom_y)

    corr = np.divide(
        numerator,
        denominator,
        out=np.zeros_like(numerator, dtype=np.float64),
        where=denominator > 0,
    )
    corr[~np.isfinite(corr)] = 0.0
    return corr


def _has_variation(arr: np.ndarray, *, tol: float = 1e-12) -> bool:
    """判断数组是否存在有效波动，避免常量输入触发相关性告警。"""
    if arr.size < 2:
        return False
    arr = arr.astype(np.float64, copy=False)
    spread = float(np.max(arr) - np.min(arr))
    return bool(np.isfinite(spread) and spread > tol)


def _safe_pearson_corr(x: np.ndarray, y: np.ndarray) -> float:
    """对常量输入安全的 Pearson 相关系数。"""
    if x.size < 3 or y.size < 3:
        return 0.0
    if not _has_variation(x) or not _has_variation(y):
        return 0.0
    corr = _rowwise_pearson_corr(
        x.astype(np.float64, copy=False).reshape(1, -1),
        y.astype(np.float64, copy=False).reshape(1, -1),
    )[0]
    return float(corr) if np.isfinite(corr) else 0.0


def _safe_spearman_corr(x: np.ndarray, y: np.ndarray) -> float:
    """对常量输入安全的 Spearman 相关系数。"""
    if x.size < 3 or y.size < 3:
        return 0.0
    if not _has_variation(x) or not _has_variation(y):
        return 0.0
    rank_x = stats.rankdata(x.astype(np.float64, copy=False), method="average")
    rank_y = stats.rankdata(y.astype(np.float64, copy=False), method="average")
    if not _has_variation(rank_x) or not _has_variation(rank_y):
        return 0.0
    corr = _rowwise_pearson_corr(rank_x.reshape(1, -1), rank_y.reshape(1, -1))[0]
    return float(corr) if np.isfinite(corr) else 0.0


def _bootstrap_chunk_size(n_sample: int, n_bootstrap: int) -> int:
    # Keep each chunk to a bounded memory footprint.
    target_elements = 3_000_000
    per_row = max(1, int(n_sample))
    chunk = max(1, target_elements // per_row)
    return max(1, min(int(n_bootstrap), chunk))


def _bootstrap_ic_vectorized(
    fv: np.ndarray,
    rv: np.ndarray,
    *,
    method: str,
    n_bootstrap: int,
    rng: np.random.RandomState,
) -> np.ndarray:
    n = len(fv)
    chunk_size = _bootstrap_chunk_size(n, n_bootstrap)
    out = np.empty(n_bootstrap, dtype=np.float64)
    m = str(method or "spearman").strip().lower()

    pos = 0
    while pos < n_bootstrap:
        size = min(chunk_size, n_bootstrap - pos)
        idx = rng.randint(0, n, size=(size, n))
        sample_fv = fv[idx]
        sample_rv = rv[idx]
        if m == "spearman":
            # Spearman = Pearson on ranks; keep tie handling with scipy rankdata.
            rank_fv = stats.rankdata(sample_fv, method="average", axis=1)
            rank_rv = stats.rankdata(sample_rv, method="average", axis=1)
            out[pos : pos + size] = _rowwise_pearson_corr(rank_fv, rank_rv)
        else:
            out[pos : pos + size] = _rowwise_pearson_corr(sample_fv, sample_rv)
        pos += size

    return out


def _bootstrap_mean_vectorized(
    values: np.ndarray,
    *,
    n_bootstrap: int,
    rng: np.random.RandomState,
) -> np.ndarray:
    n = len(values)
    chunk_size = _bootstrap_chunk_size(n, n_bootstrap)
    out = np.empty(n_bootstrap, dtype=np.float64)

    pos = 0
    while pos < n_bootstrap:
        size = min(chunk_size, n_bootstrap - pos)
        idx = rng.randint(0, n, size=(size, n))
        out[pos : pos + size] = np.mean(values[idx], axis=1)
        pos += size

    return out


def _coerce_return_series(values: Any) -> np.ndarray:
    arr = np.asarray(values if values is not None else [], dtype=np.float64).reshape(-1)
    arr = arr[np.isfinite(arr)]
    return arr


def _coerce_return_matrix(values: Any) -> np.ndarray:
    arr = np.asarray(values if values is not None else [], dtype=np.float64)
    if arr.ndim == 1:
        arr = arr.reshape(-1, 1)
    if arr.ndim != 2:
        raise ValueError("returns must be 1D or 2D")
    mask = np.all(np.isfinite(arr), axis=1)
    arr = arr[mask]
    return arr


def _safe_sharpe_ratio(returns: np.ndarray, *, periods_per_year: float = 252.0) -> float:
    arr = _coerce_return_series(returns)
    if arr.size < 3:
        return 0.0
    std = float(np.std(arr, ddof=1))
    if std <= 1e-12:
        return 0.0
    annualizer = math.sqrt(max(float(periods_per_year or 1.0), 1.0))
    return float(np.mean(arr) / std * annualizer)


def _sample_moments(returns: np.ndarray) -> tuple[float, float]:
    arr = _coerce_return_series(returns)
    if arr.size < 8:
        return 0.0, 3.0
    skewness = float(stats.skew(arr, bias=False))
    kurtosis = float(stats.kurtosis(arr, fisher=False, bias=False))
    if not np.isfinite(skewness):
        skewness = 0.0
    if not np.isfinite(kurtosis) or kurtosis <= 0:
        kurtosis = 3.0
    return skewness, kurtosis


def _estimated_sharpe_std(
    observed_sharpe: float,
    sample_size: int,
    *,
    skewness: float,
    kurtosis: float,
) -> float:
    if sample_size <= 1:
        return 0.0
    variance = (
        1.0
        - float(skewness) * float(observed_sharpe)
        + ((float(kurtosis) - 1.0) / 4.0) * float(observed_sharpe) ** 2
    ) / max(sample_size - 1, 1)
    return float(math.sqrt(max(variance, 1e-12)))


def _average_off_diagonal_correlation(correlation_matrix: np.ndarray) -> Optional[float]:
    arr = np.asarray(correlation_matrix if correlation_matrix is not None else [], dtype=np.float64)
    if arr.ndim != 2 or arr.shape[0] != arr.shape[1] or arr.shape[0] < 2:
        return None
    mask = ~np.eye(arr.shape[0], dtype=bool)
    values = arr[mask]
    values = values[np.isfinite(values)]
    if values.size == 0:
        return None
    return float(np.mean(values))


def _effective_independent_trials(
    n_trials: Optional[int],
    *,
    sharpe_trials: Optional[np.ndarray] = None,
    correlation_matrix: Optional[np.ndarray] = None,
    average_correlation: Optional[float] = None,
) -> float:
    trial_count = int(n_trials or 0)
    if trial_count <= 0 and sharpe_trials is not None:
        trial_count = int(np.asarray(sharpe_trials).size)
    trial_count = max(1, trial_count)

    rho = average_correlation
    if rho is None and correlation_matrix is not None:
        rho = _average_off_diagonal_correlation(correlation_matrix)
    if rho is None or not np.isfinite(rho):
        return float(trial_count)

    rho = float(min(1.0, max(-0.99, rho)))
    # Bailey & Lopez de Prado (2014): \hat N = \hat\rho + (1-\hat\rho) M
    effective = rho + (1.0 - rho) * float(trial_count)
    return float(max(1.0, min(float(trial_count), effective)))


def _expected_max_sharpe(mu: float, sigma: float, num_trials: float) -> float:
    sigma = max(float(sigma or 0.0), 0.0)
    num_trials = max(float(num_trials or 1.0), 1.0)
    if sigma <= 0.0 or num_trials <= 1.0:
        return float(mu)
    emc = 0.5772156649  # Euler-Mascheroni constant
    z1 = stats.norm.ppf(1.0 - 1.0 / num_trials)
    z2 = stats.norm.ppf(1.0 - 1.0 / (num_trials * math.e))
    return float(mu + sigma * ((1.0 - emc) * z1 + emc * z2))


def _stationary_bootstrap_indices(
    n_obs: int,
    *,
    restart_probability: float,
    rng: np.random.Generator,
) -> np.ndarray:
    if n_obs <= 0:
        return np.zeros(0, dtype=int)
    q = float(min(1.0, max(1e-6, restart_probability)))
    indices = np.empty(n_obs, dtype=int)
    indices[0] = int(rng.integers(0, n_obs))
    for i in range(1, n_obs):
        if float(rng.random()) < q:
            indices[i] = int(rng.integers(0, n_obs))
        else:
            indices[i] = (indices[i - 1] + 1) % n_obs
    return indices


def _autocovariance(series: np.ndarray, lag: int) -> float:
    arr = _coerce_return_series(series)
    n = arr.size
    if lag < 0 or lag >= n:
        return 0.0
    centered = arr - float(np.mean(arr))
    if lag == 0:
        return float(np.dot(centered, centered) / n)
    return float(np.dot(centered[lag:], centered[:-lag]) / n)


def _hac_long_run_variance(series: np.ndarray, max_lag: Optional[int] = None) -> float:
    arr = _coerce_return_series(series)
    n = arr.size
    if n < 3:
        return max(float(np.var(arr)) if n else 0.0, 1e-12)
    lag = int(max_lag) if max_lag is not None else int(math.floor(1.5 * n ** (1.0 / 3.0)))
    lag = max(1, min(lag, n - 1))
    gamma0 = _autocovariance(arr, 0)
    variance = gamma0
    for k in range(1, lag + 1):
        weight = 1.0 - k / float(lag + 1)
        gamma = _autocovariance(arr, k)
        variance += 2.0 * weight * gamma
    return float(max(variance, 1e-12))


def _performance_metric(
    returns: np.ndarray,
    *,
    metric: str,
    periods_per_year: float,
) -> float:
    arr = _coerce_return_series(returns)
    if arr.size < 3:
        return 0.0
    metric_name = str(metric or "sharpe").strip().lower()
    if metric_name == "mean":
        return float(np.mean(arr))
    if metric_name in {"sum", "cumulative"}:
        return float(np.sum(arr))
    return _safe_sharpe_ratio(arr, periods_per_year=periods_per_year)


def deflated_sharpe_ratio(
    returns: Optional[np.ndarray] = None,
    *,
    observed_sharpe: Optional[float] = None,
    n_trials: Optional[int] = None,
    sharpe_trials: Optional[np.ndarray] = None,
    correlation_matrix: Optional[np.ndarray] = None,
    average_correlation: Optional[float] = None,
    benchmark_sharpe: float = 0.0,
    sample_size: Optional[int] = None,
    skewness: Optional[float] = None,
    kurtosis: Optional[float] = None,
    periods_per_year: float = 252.0,
) -> Dict[str, Any]:
    """Compute Bailey & Lopez de Prado's Deflated Sharpe Ratio."""
    arr = _coerce_return_series(returns)
    n_obs = int(sample_size or arr.size)
    if observed_sharpe is None:
        observed_sharpe = _safe_sharpe_ratio(arr, periods_per_year=periods_per_year)
    observed_sharpe = float(observed_sharpe or 0.0)
    if skewness is None or kurtosis is None:
        est_skew, est_kurt = _sample_moments(arr)
        skewness = est_skew if skewness is None else float(skewness)
        kurtosis = est_kurt if kurtosis is None else float(kurtosis)
    else:
        skewness = float(skewness)
        kurtosis = float(kurtosis)

    sharpe_arr = np.asarray(sharpe_trials if sharpe_trials is not None else [], dtype=np.float64).reshape(-1)
    sharpe_arr = sharpe_arr[np.isfinite(sharpe_arr)]
    effective_trials = _effective_independent_trials(
        n_trials,
        sharpe_trials=sharpe_arr if sharpe_arr.size else None,
        correlation_matrix=correlation_matrix,
        average_correlation=average_correlation,
    )
    if sharpe_arr.size >= 2:
        mu_trials = float(np.mean(sharpe_arr))
        sigma_trials = float(np.std(sharpe_arr, ddof=1))
        reference_mode = "family_sharpes"
    else:
        mu_trials = float(benchmark_sharpe or 0.0)
        sigma_trials = _estimated_sharpe_std(
            observed_sharpe,
            n_obs,
            skewness=float(skewness),
            kurtosis=float(kurtosis),
        )
        reference_mode = "estimated_standard_error"

    sr_ref = _expected_max_sharpe(mu_trials, sigma_trials, effective_trials)
    denominator = math.sqrt(
        max(
            1e-12,
            1.0
            - float(skewness) * observed_sharpe
            + ((float(kurtosis) - 1.0) / 4.0) * observed_sharpe ** 2,
        )
    )
    z_score = ((observed_sharpe - sr_ref) * math.sqrt(max(n_obs - 1, 1))) / denominator
    dsr = float(stats.norm.cdf(z_score))
    return {
        "available": bool(n_obs >= 3),
        "sample_size": int(n_obs),
        "observed_sharpe": float(observed_sharpe),
        "benchmark_sharpe": float(benchmark_sharpe or 0.0),
        "reference_sharpe": float(sr_ref),
        "reference_mean": float(mu_trials),
        "reference_std": float(sigma_trials),
        "effective_trials": float(effective_trials),
        "skewness": float(skewness),
        "kurtosis": float(kurtosis),
        "z_score": float(z_score),
        "dsr": dsr,
        "psr_vs_benchmark": float(
            stats.norm.cdf(((observed_sharpe - float(benchmark_sharpe or 0.0)) * math.sqrt(max(n_obs - 1, 1))) / denominator)
        ),
        "reference_mode": reference_mode,
    }


def probability_of_backtest_overfitting(
    family_returns: np.ndarray,
    *,
    n_splits: int = 8,
    metric: str = "sharpe",
    periods_per_year: float = 252.0,
    max_combinations: int = 4096,
    seed: Optional[int] = 42,
) -> Dict[str, Any]:
    """Estimate PBO using CSCV (Bailey et al., 2014)."""
    matrix = _coerce_return_matrix(family_returns)
    n_obs, n_models = matrix.shape
    if n_obs < 12 or n_models < 2:
        return {
            "available": False,
            "reason": "insufficient_family_returns",
            "sample_size": int(n_obs),
            "model_count": int(n_models),
        }

    splits = int(n_splits)
    if splits % 2 != 0:
        splits -= 1
    splits = max(2, min(splits, n_obs))
    while splits > 2 and (splits % 2 != 0 or n_obs // splits < 2):
        splits -= 2
    if splits < 2:
        return {
            "available": False,
            "reason": "insufficient_split_blocks",
            "sample_size": int(n_obs),
            "model_count": int(n_models),
        }

    block_indices = [np.asarray(idx, dtype=int) for idx in np.array_split(np.arange(n_obs), splits) if len(idx) > 0]
    if len(block_indices) % 2 != 0:
        block_indices = block_indices[:-1]
    splits = len(block_indices)
    if splits < 2:
        return {
            "available": False,
            "reason": "insufficient_nonempty_blocks",
            "sample_size": int(n_obs),
            "model_count": int(n_models),
        }

    half = splits // 2
    combos = list(combinations(range(splits), half))
    sampled = False
    if len(combos) > max_combinations:
        rng = np.random.default_rng(seed)
        selected = rng.choice(len(combos), size=int(max_combinations), replace=False)
        combos = [combos[i] for i in sorted(selected.tolist())]
        sampled = True

    lambda_values: list[float] = []
    winner_indices: list[int] = []
    relative_ranks: list[float] = []

    all_blocks = set(range(splits))
    for train_combo in combos:
        train_set = set(train_combo)
        test_combo = sorted(all_blocks - train_set)
        if not test_combo:
            continue
        train_idx = np.concatenate([block_indices[i] for i in sorted(train_set)])
        test_idx = np.concatenate([block_indices[i] for i in test_combo])
        if train_idx.size < 3 or test_idx.size < 3:
            continue
        is_scores = np.asarray(
            [
                _performance_metric(matrix[train_idx, j], metric=metric, periods_per_year=periods_per_year)
                for j in range(n_models)
            ],
            dtype=np.float64,
        )
        oos_scores = np.asarray(
            [
                _performance_metric(matrix[test_idx, j], metric=metric, periods_per_year=periods_per_year)
                for j in range(n_models)
            ],
            dtype=np.float64,
        )
        if not np.any(np.isfinite(is_scores)) or not np.any(np.isfinite(oos_scores)):
            continue
        winner = int(np.nanargmax(is_scores))
        ranks = stats.rankdata(oos_scores, method="average")
        relative_rank = float(ranks[winner] / (n_models + 1.0))
        relative_rank = float(min(1.0 - 1e-8, max(1e-8, relative_rank)))
        lambda_values.append(float(math.log(relative_rank / (1.0 - relative_rank))))
        winner_indices.append(winner)
        relative_ranks.append(relative_rank)

    lambda_arr = np.asarray(lambda_values, dtype=np.float64)
    if lambda_arr.size == 0:
        return {
            "available": False,
            "reason": "no_valid_cscv_partitions",
            "sample_size": int(n_obs),
            "model_count": int(n_models),
        }

    return {
        "available": True,
        "sample_size": int(n_obs),
        "model_count": int(n_models),
        "n_splits": int(splits),
        "partition_count": int(lambda_arr.size),
        "sampled_partitions": bool(sampled),
        "metric": str(metric),
        "pbo": float(np.mean(lambda_arr <= 0.0)),
        "lambda_mean": float(np.mean(lambda_arr)),
        "lambda_median": float(np.median(lambda_arr)),
        "relative_rank_mean": float(np.mean(relative_ranks)),
        "relative_rank_median": float(np.median(relative_ranks)),
        "winner_index_mode": int(np.bincount(np.asarray(winner_indices, dtype=int)).argmax()) if winner_indices else None,
    }


def _prepare_relative_performance_matrix(
    family_returns: np.ndarray,
    benchmark_returns: Optional[np.ndarray] = None,
) -> np.ndarray:
    matrix = _coerce_return_matrix(family_returns)
    if benchmark_returns is None:
        return matrix
    benchmark = _coerce_return_series(benchmark_returns)
    if benchmark.size != matrix.shape[0]:
        raise ValueError("benchmark_returns must have the same number of periods as family_returns")
    return matrix - benchmark.reshape(-1, 1)


def white_reality_check(
    family_returns: np.ndarray,
    *,
    benchmark_returns: Optional[np.ndarray] = None,
    n_bootstrap: int = 1000,
    stationary_bootstrap_p: float = 0.1,
    seed: Optional[int] = 42,
) -> Dict[str, Any]:
    """White's Reality Check with stationary bootstrap."""
    differential = _prepare_relative_performance_matrix(family_returns, benchmark_returns)
    n_obs, n_models = differential.shape
    if n_obs < 12 or n_models < 1:
        return {
            "available": False,
            "reason": "insufficient_family_returns",
            "sample_size": int(n_obs),
            "model_count": int(n_models),
        }

    observed_means = np.mean(differential, axis=0)
    observed_stat = float(np.max(np.sqrt(n_obs) * observed_means))
    centered = differential - observed_means.reshape(1, -1)

    rng = np.random.default_rng(seed)
    draws = max(100, int(n_bootstrap or 0))
    bootstrap_stats = np.empty(draws, dtype=np.float64)
    for i in range(draws):
        idx = _stationary_bootstrap_indices(
            n_obs,
            restart_probability=stationary_bootstrap_p,
            rng=rng,
        )
        sample = centered[idx, :]
        bootstrap_stats[i] = float(np.max(np.sqrt(n_obs) * np.mean(sample, axis=0)))

    best_index = int(np.argmax(observed_means))
    return {
        "available": True,
        "sample_size": int(n_obs),
        "model_count": int(n_models),
        "observed_stat": observed_stat,
        "p_value": float(np.mean(bootstrap_stats >= observed_stat)),
        "critical_value_95": float(np.percentile(bootstrap_stats, 95)),
        "best_model_index": best_index,
        "best_model_mean": float(observed_means[best_index]),
        "bootstrap_mean": float(np.mean(bootstrap_stats)),
        "bootstrap_std": float(np.std(bootstrap_stats, ddof=1)),
        "bootstrap_draws": int(draws),
        "stationary_bootstrap_p": float(stationary_bootstrap_p),
    }


def hansen_spa_test(
    family_returns: np.ndarray,
    *,
    benchmark_returns: Optional[np.ndarray] = None,
    n_bootstrap: int = 1000,
    stationary_bootstrap_p: float = 0.1,
    seed: Optional[int] = 42,
    center: str = "consistent",
    hac_lags: Optional[int] = None,
) -> Dict[str, Any]:
    """Hansen's Superior Predictive Ability test with stationary bootstrap."""
    differential = _prepare_relative_performance_matrix(family_returns, benchmark_returns)
    n_obs, n_models = differential.shape
    if n_obs < 12 or n_models < 1:
        return {
            "available": False,
            "reason": "insufficient_family_returns",
            "sample_size": int(n_obs),
            "model_count": int(n_models),
        }

    center_mode = str(center or "consistent").strip().lower()
    if center_mode not in {"lower", "consistent", "upper"}:
        center_mode = "consistent"

    means = np.mean(differential, axis=0)
    omega = np.asarray([math.sqrt(_hac_long_run_variance(differential[:, j], max_lag=hac_lags)) for j in range(n_models)])
    omega = np.where(np.isfinite(omega) & (omega > 1e-9), omega, 1e-9)
    observed_z = np.sqrt(n_obs) * means / omega
    observed_stat = float(max(0.0, np.max(observed_z)))

    if center_mode == "upper":
        mu_hat = means
    elif center_mode == "lower":
        mu_hat = np.maximum(means, 0.0)
    else:
        loglog_n = math.log(max(math.log(max(n_obs, 3)), 1.0000001))
        threshold = -np.sqrt((omega ** 2 / max(n_obs, 1)) * 2.0 * loglog_n)
        mu_hat = means * (means >= threshold)

    centered = differential - mu_hat.reshape(1, -1)
    rng = np.random.default_rng(seed)
    draws = max(100, int(n_bootstrap or 0))
    bootstrap_stats = np.empty(draws, dtype=np.float64)
    for i in range(draws):
        idx = _stationary_bootstrap_indices(
            n_obs,
            restart_probability=stationary_bootstrap_p,
            rng=rng,
        )
        sample = centered[idx, :]
        sample_means = np.mean(sample, axis=0)
        bootstrap_stats[i] = float(max(0.0, np.max(np.sqrt(n_obs) * sample_means / omega)))

    best_index = int(np.argmax(means))
    return {
        "available": True,
        "sample_size": int(n_obs),
        "model_count": int(n_models),
        "center": center_mode,
        "observed_stat": observed_stat,
        "p_value": float(np.mean(bootstrap_stats >= observed_stat)),
        "critical_value_95": float(np.percentile(bootstrap_stats, 95)),
        "best_model_index": best_index,
        "best_model_mean": float(means[best_index]),
        "best_model_zscore": float(observed_z[best_index]),
        "bootstrap_mean": float(np.mean(bootstrap_stats)),
        "bootstrap_std": float(np.std(bootstrap_stats, ddof=1)),
        "bootstrap_draws": int(draws),
        "stationary_bootstrap_p": float(stationary_bootstrap_p),
        "hac_lags": int(hac_lags) if hac_lags is not None else None,
    }


def _calc_ic_pair(
    factor_values: np.ndarray,
    returns: np.ndarray,
) -> Tuple[float, float]:
    """计算 Pearson IC 和 Spearman Rank IC"""
    mask = np.isfinite(factor_values) & np.isfinite(returns)
    if mask.sum() < 3:
        return 0.0, 0.0
    fv = factor_values[mask]
    rv = returns[mask]
    p_ic = _safe_pearson_corr(fv, rv)
    r_ic = _safe_spearman_corr(fv, rv)
    return p_ic, r_ic


def _group_return(
    factor_values: np.ndarray,
    returns: np.ndarray,
    n_groups: int = 5,
) -> Tuple[List[float], float]:
    """计算分组收益和多空收益"""
    mask = np.isfinite(factor_values) & np.isfinite(returns)
    fv = factor_values[mask]
    rv = returns[mask]
    if len(fv) < n_groups:
        return [], 0.0
    sorted_idx = np.argsort(fv)
    group_size = len(sorted_idx) // n_groups
    group_rets = []
    for i in range(n_groups):
        start = i * group_size
        end = (i + 1) * group_size if i < n_groups - 1 else len(sorted_idx)
        group_rets.append(float(np.mean(rv[sorted_idx[start:end]])))
    ls_ret = group_rets[-1] - group_rets[0]
    return group_rets, float(ls_ret)


def bootstrap_ic_ci(
    factor_values: np.ndarray,
    returns: np.ndarray,
    method: str = "spearman",
    n_bootstrap: Optional[int] = None,
    confidence: float = 0.95,
    seed: Optional[int] = None,
    bootstrap_mode: Optional[str] = None,
    large_sample_warn_threshold: Optional[int] = None,
) -> Dict[str, Any]:
    """
    Bootstrap 非参数法估计 IC 置信区间。

    Args:
        factor_values: 因子值
        returns: 收益率
        method: 'pearson' 或 'spearman'
        n_bootstrap: 重采样次数
        confidence: 置信水平
        seed: 随机种子

    Returns:
        包含 ic, ci_lower, ci_upper, se, bootstrap_ics 的字典
    """
    mode = _normalize_bootstrap_mode(bootstrap_mode or _BOOTSTRAP_MODE_DEFAULT)
    n_bootstrap_eff = _resolve_bootstrap_iterations(n_bootstrap, mode)
    warn_threshold = (
        int(large_sample_warn_threshold)
        if large_sample_warn_threshold is not None
        else _BOOTSTRAP_WARN_THRESHOLD
    )

    mask = np.isfinite(factor_values) & np.isfinite(returns)
    fv = factor_values[mask]
    rv = returns[mask]
    n = len(fv)

    if n < 5:
        return {
            "ic": 0.0,
            "ci_lower": 0.0,
            "ci_upper": 0.0,
            "se": 0.0,
            "n_bootstrap": 0,
            "sample_size": n,
            "bootstrap_mode": mode,
        }

    rng = np.random.RandomState(seed)
    boot_ics = _bootstrap_ic_vectorized(
        fv=fv,
        rv=rv,
        method=method,
        n_bootstrap=n_bootstrap_eff,
        rng=rng,
    )

    alpha = 1.0 - confidence
    ci_lower = float(np.percentile(boot_ics, 100 * alpha / 2))
    ci_upper = float(np.percentile(boot_ics, 100 * (1 - alpha / 2)))

    # 原始 IC
    if method == "spearman":
        ic_orig = _safe_spearman_corr(fv, rv)
    else:
        ic_orig = _safe_pearson_corr(fv, rv)

    return {
        "ic": ic_orig,
        "ci_lower": ci_lower,
        "ci_upper": ci_upper,
        "se": float(np.std(boot_ics)),
        "n_bootstrap": int(n_bootstrap_eff),
        "sample_size": n,
        "confidence": confidence,
        "bootstrap_mode": mode,
        "performance_hint": (
            "Large sample with full bootstrap; consider bootstrap_mode='fast' (n_bootstrap=300)."
            if n >= warn_threshold and mode == "full"
            else None
        ),
    }


class WalkForwardValidator:
    """
    Walk-Forward 滚动验证器

    将时间序列数据按滑动窗口切分为训练集和测试集，
    在每个窗口内评估因子的样本内/样本外 IC 和分组收益，
    汇总得到因子的泛化能力指标。

    典型用法：
        validator = WalkForwardValidator(train_window=60, test_window=20, step=20)
        summary = validator.validate(factor_panel, return_panel)
    """

    def __init__(
        self,
        train_window: int = 60,
        test_window: int = 20,
        step: Optional[int] = None,
        n_groups: int = 5,
        min_samples_per_period: int = 10,
    ):
        """
        Args:
            train_window: 训练窗口（截面期数）
            test_window: 测试窗口（截面期数）
            step: 滑动步长，默认等于 test_window
            n_groups: 分组回测组数
            min_samples_per_period: 每个截面最少有效样本数
        """
        self.train_window = train_window
        self.test_window = test_window
        self.step = step or test_window
        self.n_groups = n_groups
        self.min_samples = min_samples_per_period

    def validate(
        self,
        factor_panel: np.ndarray,
        return_panel: np.ndarray,
    ) -> ValidationSummary:
        """
        执行 Walk-Forward 滚动验证。

        Args:
            factor_panel: 因子面板 shape=(n_periods, n_stocks)
            return_panel: 收益面板 shape=(n_periods, n_stocks)，
                          return_panel[t] 为 t 期因子对应的前瞻收益

        Returns:
            ValidationSummary
        """
        n_periods = factor_panel.shape[0]
        results: List[ValidationResult] = []

        i = 0
        while i + self.train_window + self.test_window <= n_periods:
            train_start = i
            train_end = i + self.train_window
            test_start = train_end
            test_end = test_start + self.test_window

            # 训练集：汇总多期截面 IC
            train_ics_p, train_ics_r = [], []
            for t in range(train_start, train_end):
                p_ic, r_ic = _calc_ic_pair(factor_panel[t], return_panel[t])
                if factor_panel[t][np.isfinite(factor_panel[t])].shape[0] >= self.min_samples:
                    train_ics_p.append(p_ic)
                    train_ics_r.append(r_ic)

            # 测试集
            test_ics_p, test_ics_r = [], []
            test_group_rets_all = []
            test_ls_all = []
            for t in range(test_start, test_end):
                p_ic, r_ic = _calc_ic_pair(factor_panel[t], return_panel[t])
                valid_n = factor_panel[t][np.isfinite(factor_panel[t])].shape[0]
                if valid_n >= self.min_samples:
                    test_ics_p.append(p_ic)
                    test_ics_r.append(r_ic)
                    gr, ls = _group_return(factor_panel[t], return_panel[t], self.n_groups)
                    if gr:
                        test_group_rets_all.append(gr)
                        test_ls_all.append(ls)

            if not train_ics_p or not test_ics_p:
                i += self.step
                continue

            vr = ValidationResult(
                train_ic=float(np.mean(train_ics_p)),
                test_ic=float(np.mean(test_ics_p)),
                train_rank_ic=float(np.mean(train_ics_r)),
                test_rank_ic=float(np.mean(test_ics_r)),
                train_size=len(train_ics_p),
                test_size=len(test_ics_p),
                train_start=train_start,
                train_end=train_end,
                test_start=test_start,
                test_end=test_end,
                long_short_return=float(np.mean(test_ls_all)) if test_ls_all else 0.0,
            )
            if test_group_rets_all:
                avg_gr = np.mean(test_group_rets_all, axis=0).tolist()
                vr.group_returns = avg_gr
            results.append(vr)
            i += self.step

        return self._build_summary(results, method="walk_forward")

    def _build_summary(
        self, results: List[ValidationResult], method: str
    ) -> ValidationSummary:
        if not results:
            return ValidationSummary(method=method)

        oos_ics = [r.test_ic for r in results]
        oos_rank_ics = [r.test_rank_ic for r in results]
        is_ics = [r.train_ic for r in results]

        oos_mean = float(np.mean(oos_ics))
        oos_std = float(np.std(oos_ics)) if len(oos_ics) > 1 else 0.0
        oos_ir = oos_mean / oos_std if oos_std > 0 else 0.0

        oos_rank_mean = float(np.mean(oos_rank_ics))
        oos_rank_std = float(np.std(oos_rank_ics)) if len(oos_rank_ics) > 1 else 0.0
        oos_rank_ir = oos_rank_mean / oos_rank_std if oos_rank_std > 0 else 0.0

        is_mean = float(np.mean(is_ics))
        is_std = float(np.std(is_ics)) if len(is_ics) > 1 else 0.0

        # 稳定性比率：OOS IC 均值 / IS IC 均值
        stability = oos_mean / is_mean if abs(is_mean) > 1e-8 else 0.0
        # 衰减：IS IC 均值 - OOS IC 均值
        degradation = is_mean - oos_mean

        oos_positive = sum(1 for ic in oos_ics if ic > 0) / len(oos_ics)
        oos_ls_mean = float(np.mean([r.long_short_return for r in results]))

        return ValidationSummary(
            n_folds=len(results),
            oos_ic_mean=oos_mean,
            oos_ic_std=oos_std,
            oos_ic_ir=oos_ir,
            oos_rank_ic_mean=oos_rank_mean,
            oos_rank_ic_std=oos_rank_std,
            oos_rank_ic_ir=oos_rank_ir,
            is_ic_mean=is_mean,
            is_ic_std=is_std,
            stability_ratio=float(stability),
            degradation=float(degradation),
            oos_positive_ratio=float(oos_positive),
            oos_long_short_mean=oos_ls_mean,
            fold_results=results,
            method=method,
        )


class PurgedKFoldCV:
    """
    Purged K-Fold 交叉验证

    时间分层 K-Fold，在训练集和测试集之间插入清洗间隔（purge gap），
    防止因子计算中的前视偏差（lookahead bias）。

    参考：de Prado, M.L. (2018) "Advances in Financial Machine Learning"
          Chapter 7: Cross-Validation in Finance

    典型用法：
        cv = PurgedKFoldCV(n_folds=5, purge_gap=5)
        summary = cv.validate(factor_panel, return_panel)
    """

    def __init__(
        self,
        n_folds: int = 5,
        purge_gap: int = 5,
        n_groups: int = 5,
        min_samples_per_period: int = 10,
    ):
        """
        Args:
            n_folds: 折数
            purge_gap: 清洗间隔（训练集末尾到测试集开头之间跳过的期数）
            n_groups: 分组回测组数
            min_samples_per_period: 每个截面最少有效样本数
        """
        self.n_folds = n_folds
        self.purge_gap = purge_gap
        self.n_groups = n_groups
        self.min_samples = min_samples_per_period

    def _generate_splits(
        self, n_periods: int
    ) -> List[Tuple[np.ndarray, np.ndarray]]:
        """生成带 purge gap 的时间分层 K-Fold 划分"""
        indices = np.arange(n_periods)
        fold_size = n_periods // self.n_folds
        splits = []

        for k in range(self.n_folds):
            test_start = k * fold_size
            test_end = (k + 1) * fold_size if k < self.n_folds - 1 else n_periods

            test_idx = indices[test_start:test_end]

            # 训练集：排除测试集及其前后 purge_gap
            purge_start = max(0, test_start - self.purge_gap)
            purge_end = min(n_periods, test_end + self.purge_gap)
            train_mask = np.ones(n_periods, dtype=bool)
            train_mask[purge_start:purge_end] = False
            train_idx = indices[train_mask]

            if len(train_idx) > 0 and len(test_idx) > 0:
                splits.append((train_idx, test_idx))

        return splits

    def validate(
        self,
        factor_panel: np.ndarray,
        return_panel: np.ndarray,
    ) -> ValidationSummary:
        """
        执行 Purged K-Fold 交叉验证。

        Args:
            factor_panel: 因子面板 shape=(n_periods, n_stocks)
            return_panel: 收益面板 shape=(n_periods, n_stocks)

        Returns:
            ValidationSummary
        """
        n_periods = factor_panel.shape[0]
        splits = self._generate_splits(n_periods)
        results: List[ValidationResult] = []

        for train_idx, test_idx in splits:
            # 训练集 IC
            train_ics_p, train_ics_r = [], []
            for t in train_idx:
                valid_n = np.isfinite(factor_panel[t]).sum()
                if valid_n >= self.min_samples:
                    p_ic, r_ic = _calc_ic_pair(factor_panel[t], return_panel[t])
                    train_ics_p.append(p_ic)
                    train_ics_r.append(r_ic)

            # 测试集 IC + 分组收益
            test_ics_p, test_ics_r = [], []
            test_ls_all = []
            test_group_rets_all = []
            for t in test_idx:
                valid_n = np.isfinite(factor_panel[t]).sum()
                if valid_n >= self.min_samples:
                    p_ic, r_ic = _calc_ic_pair(factor_panel[t], return_panel[t])
                    test_ics_p.append(p_ic)
                    test_ics_r.append(r_ic)
                    gr, ls = _group_return(factor_panel[t], return_panel[t], self.n_groups)
                    if gr:
                        test_group_rets_all.append(gr)
                        test_ls_all.append(ls)

            if not train_ics_p or not test_ics_p:
                continue

            vr = ValidationResult(
                train_ic=float(np.mean(train_ics_p)),
                test_ic=float(np.mean(test_ics_p)),
                train_rank_ic=float(np.mean(train_ics_r)),
                test_rank_ic=float(np.mean(test_ics_r)),
                train_size=len(train_ics_p),
                test_size=len(test_ics_p),
                train_start=int(train_idx[0]),
                train_end=int(train_idx[-1]),
                test_start=int(test_idx[0]),
                test_end=int(test_idx[-1]),
                long_short_return=float(np.mean(test_ls_all)) if test_ls_all else 0.0,
            )
            if test_group_rets_all:
                vr.group_returns = np.mean(test_group_rets_all, axis=0).tolist()
            results.append(vr)

        return WalkForwardValidator._build_summary(
            None, results, method="purged_kfold"
        )


def _run_walk_forward_validate_task(
    factor_panel: np.ndarray,
    return_panel: np.ndarray,
    cfg: Dict[str, Any],
) -> ValidationSummary:
    validator = WalkForwardValidator(
        train_window=int(cfg.get("train_window", 60)),
        test_window=int(cfg.get("test_window", 20)),
        step=cfg.get("step"),
        n_groups=int(cfg.get("n_groups", 5)),
        min_samples_per_period=int(cfg.get("min_samples", 10)),
    )
    return validator.validate(factor_panel, return_panel)


def _run_purged_kfold_validate_task(
    factor_panel: np.ndarray,
    return_panel: np.ndarray,
    cfg: Dict[str, Any],
) -> ValidationSummary:
    validator = PurgedKFoldCV(
        n_folds=int(cfg.get("n_folds", 5)),
        purge_gap=int(cfg.get("purge_gap", 5)),
        n_groups=int(cfg.get("n_groups", 5)),
        min_samples_per_period=int(cfg.get("min_samples", 10)),
    )
    return validator.validate(factor_panel, return_panel)


def _run_bootstrap_ic_series_task(
    ic_series: np.ndarray,
    n_bootstrap: Optional[int],
    confidence: float,
    bootstrap_mode: Optional[str],
    seed: int = 42,
) -> Dict[str, Any]:
    return FactorValidationPipeline._bootstrap_ic_series(
        ic_series=ic_series,
        n_bootstrap=n_bootstrap,
        confidence=confidence,
        seed=seed,
        bootstrap_mode=bootstrap_mode,
    )


class FactorValidationPipeline:
    """
    因子验证流水线

    整合 Walk-Forward + Purged K-Fold + Bootstrap CI，
    输出完整的因子样本外验证报告。
    """

    def __init__(
        self,
        wf_train_window: int = 60,
        wf_test_window: int = 20,
        wf_step: Optional[int] = None,
        kfold_n_folds: int = 5,
        kfold_purge_gap: int = 5,
        n_groups: int = 5,
        bootstrap_n: Optional[int] = None,
        bootstrap_confidence: float = 0.95,
        min_samples: int = 10,
        validation_parallel: bool = True,
        max_workers: int = _VALIDATION_MAX_WORKERS_DEFAULT,
        bootstrap_mode: Optional[str] = None,
    ):
        self.wf_validator = WalkForwardValidator(
            train_window=wf_train_window,
            test_window=wf_test_window,
            step=wf_step,
            n_groups=n_groups,
            min_samples_per_period=min_samples,
        )
        self.kfold_validator = PurgedKFoldCV(
            n_folds=kfold_n_folds,
            purge_gap=kfold_purge_gap,
            n_groups=n_groups,
            min_samples_per_period=min_samples,
        )
        self.bootstrap_n = int(bootstrap_n) if bootstrap_n is not None else None
        self.bootstrap_confidence = bootstrap_confidence
        self.validation_parallel = bool(validation_parallel and _VALIDATION_PARALLEL_ENABLED)
        workers = int(max_workers or _VALIDATION_MAX_WORKERS_DEFAULT)
        self.max_workers = max(1, min(workers, min(_CPU_COUNT, 8)))
        self.bootstrap_mode = _normalize_bootstrap_mode(bootstrap_mode or _BOOTSTRAP_MODE_DEFAULT)

    def run(
        self,
        factor_panel: np.ndarray,
        return_panel: np.ndarray,
        factor_name: str = "unknown",
        validation_parallel: bool = True,
        max_workers: int = _VALIDATION_MAX_WORKERS_DEFAULT,
        bootstrap_mode: Optional[str] = None,
        strategy_returns: Optional[np.ndarray] = None,
        family_returns: Optional[np.ndarray] = None,
        benchmark_returns: Optional[np.ndarray] = None,
        multiple_testing_config: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        执行完整验证流水线。

        Args:
            factor_panel: shape=(n_periods, n_stocks)
            return_panel: shape=(n_periods, n_stocks)
            factor_name: 因子名称

        Returns:
            完整验证报告字典
        """
        requested_parallel = bool(validation_parallel and self.validation_parallel and _VALIDATION_PARALLEL_ENABLED)
        workers = int(max_workers or self.max_workers)
        workers = max(1, min(workers, min(_CPU_COUNT, 8)))
        workload = int(factor_panel.shape[0] * factor_panel.shape[1])
        parallel_ready = bool(
            requested_parallel
            and workers > 1
            and workload >= _VALIDATION_PARALLEL_MIN_WORKLOAD
        )

        # 1) Build IC series for bootstrap on the full panel.
        all_ics_r: List[float] = []
        for t in range(factor_panel.shape[0]):
            _p_ic, r_ic = _calc_ic_pair(factor_panel[t], return_panel[t])
            if np.isfinite(factor_panel[t]).sum() >= 10:
                all_ics_r.append(r_ic)
        ic_array = np.array(all_ics_r, dtype=np.float64)
        selected_bootstrap_mode = _normalize_bootstrap_mode(bootstrap_mode or self.bootstrap_mode)

        wf_summary: Optional[ValidationSummary] = None
        kf_summary: Optional[ValidationSummary] = None
        boot_ci: Optional[Dict[str, Any]] = None
        execution_mode = "serial"
        fallback_reason: Optional[str] = None

        if parallel_ready:
            try:
                wf_cfg = {
                    "train_window": self.wf_validator.train_window,
                    "test_window": self.wf_validator.test_window,
                    "step": self.wf_validator.step,
                    "n_groups": self.wf_validator.n_groups,
                    "min_samples": self.wf_validator.min_samples,
                }
                kf_cfg = {
                    "n_folds": self.kfold_validator.n_folds,
                    "purge_gap": self.kfold_validator.purge_gap,
                    "n_groups": self.kfold_validator.n_groups,
                    "min_samples": self.kfold_validator.min_samples,
                }
                with ProcessPoolExecutor(max_workers=min(workers, 3)) as executor:
                    wf_future = executor.submit(
                        _run_walk_forward_validate_task,
                        factor_panel,
                        return_panel,
                        wf_cfg,
                    )
                    kf_future = executor.submit(
                        _run_purged_kfold_validate_task,
                        factor_panel,
                        return_panel,
                        kf_cfg,
                    )
                    boot_future = executor.submit(
                        _run_bootstrap_ic_series_task,
                        ic_array,
                        self.bootstrap_n,
                        self.bootstrap_confidence,
                        selected_bootstrap_mode,
                        42,
                    )
                    wf_summary = wf_future.result()
                    kf_summary = kf_future.result()
                    boot_ci = boot_future.result()
                execution_mode = "parallel"
            except Exception as exc:
                fallback_reason = f"parallel_failed:{type(exc).__name__}"

        if wf_summary is None or kf_summary is None:
            wf_summary = self.wf_validator.validate(factor_panel, return_panel)
            kf_summary = self.kfold_validator.validate(factor_panel, return_panel)
            if boot_ci is None:
                boot_ci = self._bootstrap_ic_series(
                    ic_array,
                    self.bootstrap_n,
                    self.bootstrap_confidence,
                    bootstrap_mode=selected_bootstrap_mode,
                )
            execution_mode = "serial"
        elif boot_ci is None:
            boot_ci = self._bootstrap_ic_series(
                ic_array,
                self.bootstrap_n,
                self.bootstrap_confidence,
                bootstrap_mode=selected_bootstrap_mode,
            )

        # 4. 综合评级
        rating = self._compute_rating(wf_summary, kf_summary, boot_ci)
        if strategy_returns is not None:
            strategy_returns_input = strategy_returns
        else:
            implied_returns = np.asarray(factor_panel * return_panel, dtype=np.float64)
            valid_counts = np.isfinite(implied_returns).sum(axis=1)
            row_sums = np.nansum(implied_returns, axis=1)
            strategy_returns_input = np.divide(
                row_sums,
                valid_counts,
                out=np.full(implied_returns.shape[0], np.nan, dtype=np.float64),
                where=valid_counts > 0,
            )
        strategy_returns_arr = _coerce_return_series(strategy_returns_input)
        family_returns_arr = None
        if family_returns is not None:
            try:
                family_returns_arr = _coerce_return_matrix(family_returns)
            except Exception:
                family_returns_arr = None
        mt_cfg = dict(multiple_testing_config or {})
        sharpe_trials = mt_cfg.get("trial_sharpes")
        if sharpe_trials is None and family_returns_arr is not None and family_returns_arr.shape[1] >= 1:
            sharpe_trials = np.asarray(
                [
                    _safe_sharpe_ratio(
                        family_returns_arr[:, j],
                        periods_per_year=float(mt_cfg.get("periods_per_year", 252.0) or 252.0),
                    )
                    for j in range(family_returns_arr.shape[1])
                ],
                dtype=np.float64,
            )

        multiple_testing = {
            "available": False,
            "reason": "family_returns_not_provided",
            "deflated_sharpe": deflated_sharpe_ratio(
                strategy_returns_arr,
                n_trials=int(mt_cfg.get("n_trials") or (family_returns_arr.shape[1] if family_returns_arr is not None else 1)),
                sharpe_trials=sharpe_trials,
                correlation_matrix=mt_cfg.get("trial_correlation_matrix"),
                average_correlation=mt_cfg.get("average_correlation"),
                benchmark_sharpe=float(mt_cfg.get("benchmark_sharpe", 0.0) or 0.0),
                periods_per_year=float(mt_cfg.get("periods_per_year", 252.0) or 252.0),
            ),
        }
        if family_returns_arr is not None and family_returns_arr.shape[1] >= 2:
            multiple_testing = {
                "available": True,
                "deflated_sharpe": multiple_testing["deflated_sharpe"],
                "pbo": probability_of_backtest_overfitting(
                    family_returns_arr,
                    n_splits=int(mt_cfg.get("pbo_n_splits", 8) or 8),
                    metric=str(mt_cfg.get("pbo_metric", "sharpe") or "sharpe"),
                    periods_per_year=float(mt_cfg.get("periods_per_year", 252.0) or 252.0),
                    max_combinations=int(mt_cfg.get("pbo_max_combinations", 4096) or 4096),
                    seed=mt_cfg.get("seed", 42),
                ),
                "white_reality_check": white_reality_check(
                    family_returns_arr,
                    benchmark_returns=benchmark_returns,
                    n_bootstrap=int(mt_cfg.get("n_bootstrap", self.bootstrap_n or 500) or (self.bootstrap_n or 500)),
                    stationary_bootstrap_p=float(mt_cfg.get("stationary_bootstrap_p", 0.1) or 0.1),
                    seed=mt_cfg.get("seed", 42),
                ),
                "hansen_spa": hansen_spa_test(
                    family_returns_arr,
                    benchmark_returns=benchmark_returns,
                    n_bootstrap=int(mt_cfg.get("n_bootstrap", self.bootstrap_n or 500) or (self.bootstrap_n or 500)),
                    stationary_bootstrap_p=float(mt_cfg.get("stationary_bootstrap_p", 0.1) or 0.1),
                    seed=mt_cfg.get("seed", 42),
                    center=str(mt_cfg.get("spa_center", "consistent") or "consistent"),
                    hac_lags=mt_cfg.get("spa_hac_lags"),
                ),
            }

        return {
            "factor_name": factor_name,
            "n_periods": int(factor_panel.shape[0]),
            "n_stocks": int(factor_panel.shape[1]),
            "walk_forward": self._summary_to_dict(wf_summary),
            "purged_kfold": self._summary_to_dict(kf_summary),
            "bootstrap_ci": boot_ci,
            "multiple_testing": multiple_testing,
            "rating": rating,
            "validation_execution": {
                "mode": execution_mode,
                "parallel_requested": bool(requested_parallel),
                "parallel_effective": bool(execution_mode == "parallel"),
                "max_workers": int(workers),
                "workload": int(workload),
                "fallback_reason": fallback_reason,
            },
        }

    @staticmethod
    def _bootstrap_ic_series(
        ic_series: np.ndarray,
        n_bootstrap: Optional[int],
        confidence: float,
        seed: int = 42,
        bootstrap_mode: Optional[str] = None,
    ) -> Dict[str, Any]:
        """对 IC 时间序列做 Bootstrap 置信区间"""
        mode = _normalize_bootstrap_mode(bootstrap_mode or _BOOTSTRAP_MODE_DEFAULT)
        n_bootstrap_eff = _resolve_bootstrap_iterations(n_bootstrap, mode)

        n = len(ic_series)
        if n < 5:
            return {
                "ic_mean": 0.0,
                "ci_lower": 0.0,
                "ci_upper": 0.0,
                "se": 0.0,
                "sample_size": n,
                "n_bootstrap": 0,
                "bootstrap_mode": mode,
            }

        rng = np.random.RandomState(seed)
        boot_means = _bootstrap_mean_vectorized(
            ic_series.astype(np.float64, copy=False),
            n_bootstrap=n_bootstrap_eff,
            rng=rng,
        )

        alpha = 1.0 - confidence
        return {
            "ic_mean": float(np.mean(ic_series)),
            "ic_std": float(np.std(ic_series)),
            "ic_ir": float(np.mean(ic_series) / np.std(ic_series)) if np.std(ic_series) > 0 else 0.0,
            "ci_lower": float(np.percentile(boot_means, 100 * alpha / 2)),
            "ci_upper": float(np.percentile(boot_means, 100 * (1 - alpha / 2))),
            "se": float(np.std(boot_means)),
            "sample_size": n,
            "confidence": confidence,
            "n_bootstrap": int(n_bootstrap_eff),
            "bootstrap_mode": mode,
            "performance_hint": (
                "Large sample with full bootstrap; consider bootstrap_mode='fast' (n_bootstrap=300)."
                if n >= _BOOTSTRAP_WARN_THRESHOLD and mode == "full"
                else None
            ),
        }

    @staticmethod
    def _compute_rating(
        wf: ValidationSummary,
        kf: ValidationSummary,
        boot_ci: Dict[str, Any],
    ) -> Dict[str, Any]:
        """综合评级"""
        scores = {}

        # OOS IC 均值得分（0-30分）
        avg_oos_ic = (abs(wf.oos_rank_ic_mean) + abs(kf.oos_rank_ic_mean)) / 2
        scores["oos_ic"] = min(30.0, avg_oos_ic * 600)

        # OOS IC IR 得分（0-25分）
        avg_ir = (abs(wf.oos_rank_ic_ir) + abs(kf.oos_rank_ic_ir)) / 2
        scores["oos_ir"] = min(25.0, avg_ir * 50)

        # 稳定性得分（0-20分）
        avg_stability = (wf.stability_ratio + kf.stability_ratio) / 2
        scores["stability"] = min(20.0, max(0.0, avg_stability * 20))

        # CI 不含零得分（0-15分）
        ci_lower = boot_ci.get("ci_lower", 0.0)
        ci_upper = boot_ci.get("ci_upper", 0.0)
        if ci_lower > 0 or ci_upper < 0:
            scores["ci_significance"] = 15.0
        else:
            scores["ci_significance"] = 0.0

        # OOS 正比率得分（0-10分）
        avg_pos = (wf.oos_positive_ratio + kf.oos_positive_ratio) / 2
        scores["positive_ratio"] = avg_pos * 10

        total = sum(scores.values())

        if total >= 70:
            grade = "A"
        elif total >= 55:
            grade = "B"
        elif total >= 40:
            grade = "C"
        else:
            grade = "D"

        return {
            "grade": grade,
            "total_score": float(total),
            "scores": {k: float(v) for k, v in scores.items()},
            "recommendation": (
                "Strong — 因子样本外表现稳健" if grade in ("A", "B")
                else "Weak — 因子泛化能力不足，建议审慎使用"
            ),
        }

    @staticmethod
    def _summary_to_dict(s: ValidationSummary) -> Dict[str, Any]:
        """将 ValidationSummary 转为可序列化字典"""
        return {
            "method": s.method,
            "n_folds": s.n_folds,
            "oos_ic_mean": s.oos_ic_mean,
            "oos_ic_std": s.oos_ic_std,
            "oos_ic_ir": s.oos_ic_ir,
            "oos_rank_ic_mean": s.oos_rank_ic_mean,
            "oos_rank_ic_std": s.oos_rank_ic_std,
            "oos_rank_ic_ir": s.oos_rank_ic_ir,
            "is_ic_mean": s.is_ic_mean,
            "is_ic_std": s.is_ic_std,
            "stability_ratio": s.stability_ratio,
            "degradation": s.degradation,
            "oos_positive_ratio": s.oos_positive_ratio,
            "oos_long_short_mean": s.oos_long_short_mean,
        }
