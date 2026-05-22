

def _eval_expr(frame: pd.DataFrame, node: dict[str, Any]) -> pd.Series:
    if "value" in node:
        return pd.Series(float(node.get("value") or 0.0), index=frame.index, dtype=float)
    indicator = str(node.get("indicator") or "").strip().lower()
    if indicator in SUPPORTED_INDICATORS:
        series = _eval_expr(frame, {"field": node.get("field") or "close"})
        window = max(1, int(node.get("window") or 14))
        if indicator == "sma":
            return series.rolling(window).mean()
        if indicator == "ema":
            return series.ewm(span=window, adjust=False).mean()
        if indicator == "roc":
            return series.pct_change(window)
        if indicator == "rsi":
            delta = series.diff()
            up = delta.clip(lower=0.0)
            down = -delta.clip(upper=0.0)
            avg_gain = up.rolling(window).mean()
            avg_loss = down.rolling(window).mean()
            rs = avg_gain / np.maximum(avg_loss, 1e-9)
            return 100.0 - (100.0 / (1.0 + rs))
        if indicator == "stddev":
            return series.rolling(window).std()
        if indicator == "zscore":
            mean = series.rolling(window).mean()
            std = series.rolling(window).std()
            return (series - mean) / np.maximum(std, 1e-9)
        if indicator == "highest":
            return series.rolling(window).max()
        if indicator == "lowest":
            return series.rolling(window).min()
        if indicator == "volume_ratio":
            volume = _eval_expr(frame, {"field": "volume"})
            return volume / np.maximum(volume.rolling(window).mean(), 1e-9)
        if indicator == "turnover_rate":
            turnover = pd.to_numeric(frame.get("turnover_rate", pd.Series(np.nan, index=frame.index)), errors="coerce")
            if turnover.notna().any():
                return turnover.fillna(0.0)
            volume = _eval_expr(frame, {"field": "volume"})
            baseline = volume.rolling(window).median()
            return volume / np.maximum(baseline, 1e-9)
        if indicator == "upper_shadow_ratio":
            high = _eval_expr(frame, {"field": "high"})
            open_ = _eval_expr(frame, {"field": "open"})
            close = _eval_expr(frame, {"field": "close"})
            low = _eval_expr(frame, {"field": "low"})
            spread = (high - low).abs().clip(lower=1e-9)
            upper_shadow = (high - pd.concat([open_, close], axis=1).max(axis=1)).clip(lower=0.0)
            return upper_shadow / spread
        if indicator == "atr":
            high = _eval_expr(frame, {"field": "high"})
            low = _eval_expr(frame, {"field": "low"})
            close = _eval_expr(frame, {"field": "close"})
            prev_close = close.shift(1)
            tr = pd.concat([
                (high - low).abs(),
                (high - prev_close).abs(),
                (low - prev_close).abs(),
            ], axis=1).max(axis=1)
            return tr.rolling(window).mean()
        if indicator == "adx":
            high = _eval_expr(frame, {"field": "high"})
            low = _eval_expr(frame, {"field": "low"})
            close = _eval_expr(frame, {"field": "close"})
            up_move = high.diff()
            down_move = -low.diff()
            plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
            minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
            prev_close = close.shift(1)
            tr = pd.concat([
                (high - low).abs(),
                (high - prev_close).abs(),
                (low - prev_close).abs(),
            ], axis=1).max(axis=1)
            atr = tr.rolling(window).mean().replace(0.0, np.nan)
            plus_di = 100.0 * plus_dm.rolling(window).sum() / atr
            minus_di = 100.0 * minus_dm.rolling(window).sum() / atr
            dx = ((plus_di - minus_di).abs() / (plus_di + minus_di).replace(0.0, np.nan)) * 100.0
            return dx.rolling(window).mean().fillna(0.0)
        if indicator == "rolling_count":
            condition = _normalize_condition(node.get("condition"))
            mask = _eval_condition(frame, condition).astype(float)
            return mask.rolling(window).sum().fillna(0.0)
        if indicator == "slope":
            smoothed = series.rolling(window).mean()
            lookback = max(1, int(node.get("lookback") or 5))
            return smoothed - smoothed.shift(lookback)
    field = str(node.get("field") or "").strip().lower()
    if field in SUPPORTED_FIELDS:
        return pd.to_numeric(frame.get(field, pd.Series(0.0, index=frame.index)), errors="coerce").fillna(0.0)
    binary = node.get("binary")
    if isinstance(binary, dict):
        left = _eval_expr(frame, dict(binary.get("left") or {}))
        right = _eval_expr(frame, dict(binary.get("right") or {}))
        op = str(binary.get("op") or "").strip().lower()
        if op == "add":
            return left + right
        if op == "sub":
            return left - right
        if op == "mul":
            return left * right
        if op == "div":
            denom = right.abs().clip(lower=1e-9)
            return left / denom
        if op == "max":
            return pd.concat([left, right], axis=1).max(axis=1)
        if op == "min":
            return pd.concat([left, right], axis=1).min(axis=1)
    return pd.Series(0.0, index=frame.index, dtype=float)
