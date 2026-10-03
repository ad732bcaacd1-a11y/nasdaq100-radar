"""
技術指標運算核心模組
包含：
1. Supertrend (超級趨勢線)
2. MACD (指數平滑異同移動平均線)
3. RVOL (Relative Volume 相對成交量 / 爆量指標)
"""

import pandas as pd
import numpy as np

def calculate_supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> pd.DataFrame:
    """
    計算 Supertrend (與 Webull / TradingView 演算法完全一致)
    """
    if len(df) < period + 2:
        return df

    high = df['High']
    low = df['Low']
    close = df['Close']
    
    tr1 = high - low
    tr2 = (high - close.shift(1)).abs()
    tr3 = (low - close.shift(1)).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # Wilder's RMA / EMA ATR
    atr = tr.ewm(alpha=1/period, adjust=False).mean()
    
    hl2 = (high + low) / 2.0
    basic_upper = hl2 + (multiplier * atr)
    basic_lower = hl2 - (multiplier * atr)
    
    final_upper = pd.Series(0.0, index=df.index)
    final_lower = pd.Series(0.0, index=df.index)
    trend = pd.Series(1, index=df.index, dtype=int) # 1: 多頭(綠), -1: 空頭(紅)
    supertrend = pd.Series(0.0, index=df.index)

    # 初始第 0 筆
    final_upper.iloc[0] = basic_upper.iloc[0]
    final_lower.iloc[0] = basic_lower.iloc[0]
    supertrend.iloc[0] = basic_lower.iloc[0]

    for i in range(1, len(df)):
        curr_close = close.iloc[i]
        prev_close = close.iloc[i - 1]
        
        # 調整軌道
        if basic_lower.iloc[i] > final_lower.iloc[i - 1] or prev_close < final_lower.iloc[i - 1]:
            final_lower.iloc[i] = basic_lower.iloc[i]
        else:
            final_lower.iloc[i] = final_lower.iloc[i - 1]
            
        if basic_upper.iloc[i] < final_upper.iloc[i - 1] or prev_close > final_upper.iloc[i - 1]:
            final_upper.iloc[i] = basic_upper.iloc[i]
        else:
            final_upper.iloc[i] = final_upper.iloc[i - 1]
            
        # 判定趨勢方向
        prev_trend = trend.iloc[i - 1]
        if prev_trend == 1:
            if curr_close < final_lower.iloc[i]:
                curr_trend = -1
                curr_st = final_upper.iloc[i]
            else:
                curr_trend = 1
                curr_st = final_lower.iloc[i]
        else:
            if curr_close > final_upper.iloc[i]:
                curr_trend = 1
                curr_st = final_lower.iloc[i]
            else:
                curr_trend = -1
                curr_st = final_upper.iloc[i]
                
        trend.iloc[i] = curr_trend
        supertrend.iloc[i] = curr_st
        
    df['Supertrend'] = supertrend
    df['Supertrend_Trend'] = trend
    # 翻多買點：前一根空頭(-1)，當前翻成多頭(1)
    df['Supertrend_Buy_Flip'] = (trend == 1) & (trend.shift(1) == -1)
    return df

def calculate_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> pd.DataFrame:
    """
    計算 MACD (12, 26, 9)
    """
    if len(df) < slow + signal:
        return df

    close = df['Close']
    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    hist = macd_line - signal_line
    
    df['MACD'] = macd_line
    df['MACD_Signal'] = signal_line
    df['MACD_Hist'] = hist
    # 黃金交叉判定：前一根 DIF <= DEA，當前 DIF > DEA
    df['MACD_Golden_Cross'] = (macd_line > signal_line) & (macd_line.shift(1) <= signal_line.shift(1))
    # 多頭狀態 (DIF 在 DEA 之上)
    df['MACD_Bullish'] = macd_line > signal_line
    return df

def calculate_rvol(df: pd.DataFrame, lookback: int = 20) -> float:
    """
    計算當前 5 分鐘 K 棒的相對成交量 (RVOL)
    當前量 / 過去 20 根 K 棒的平均量
    """
    if len(df) < lookback + 1:
        return 1.0
    
    current_vol = float(df['Volume'].iloc[-1])
    # 過去 lookback 根 (排除當前這根未完結或正在走的)
    hist_vols = df['Volume'].iloc[-(lookback + 1):-1]
    avg_vol = float(hist_vols.mean())
    
    if avg_vol <= 0:
        return 1.0
    
    return round(current_vol / avg_vol, 2)

def evaluate_signals(df: pd.DataFrame, rvol_threshold: float = 1.8, lookback_bars: int = 2) -> dict:
    """
    綜合評估 3 大核心條件：
    1. Supertrend 買訊 (當前或近 1~2 根 K 棒剛翻多，或多頭啟動)
    2. MACD 黃金交叉 (當前或近 1~2 根 K 棒金叉)
    3. RVOL 大量 (>= 門檻，例如 1.8x)
    """
    if len(df) < 35:
        return {"matched": False}
        
    df = calculate_supertrend(df)
    df = calculate_macd(df)
    rvol = calculate_rvol(df)
    
    curr_idx = len(df) - 1
    
    # 檢查最近 lookback_bars 內是否有 Supertrend 翻多
    recent_st_buy = bool(df['Supertrend_Buy_Flip'].iloc[-lookback_bars:].any())
    is_st_bull = bool(df['Supertrend_Trend'].iloc[-1] == 1)
    
    # 檢查最近 lookback_bars 內是否有 MACD 金叉
    recent_macd_gold = bool(df['MACD_Golden_Cross'].iloc[-lookback_bars:].any())
    is_macd_bull = bool(df['MACD_Bullish'].iloc[-1])
    
    # 條件邏輯：
    # 完美共振 A: (Supertrend 剛翻多 或 多頭中) AND (MACD 剛金叉) AND (RVOL 放量)
    # 完美共振 B: (Supertrend 剛翻多) AND (MACD 多頭中) AND (RVOL 放量)
    condition_st = recent_st_buy or (is_st_bull and recent_macd_gold)
    condition_macd = recent_macd_gold or (is_macd_bull and recent_st_buy)
    condition_rvol = rvol >= rvol_threshold
    
    matched = (condition_st and condition_macd and condition_rvol)
    
    curr_close = float(df['Close'].iloc[-1])
    prev_close = float(df['Close'].iloc[-2]) if len(df) >= 2 else curr_close
    pct_change = round(((curr_close - prev_close) / prev_close) * 100, 2)
    
    bar_time = df.index[-1].strftime('%H:%M') if hasattr(df.index[-1], 'strftime') else str(df.index[-1])
    
    return {
        "matched": matched,
        "price": curr_close,
        "pct_change_5m": pct_change,
        "rvol": rvol,
        "rvol_pass": condition_rvol,
        "supertrend_trend": "多頭 (Bullish)" if is_st_bull else "空頭 (Bearish)",
        "supertrend_fresh_buy": recent_st_buy,
        "macd_val": round(float(df['MACD'].iloc[-1]), 3),
        "macd_signal": round(float(df['MACD_Signal'].iloc[-1]), 3),
        "macd_golden_cross": recent_macd_gold,
        "macd_is_bull": is_macd_bull,
        "bar_time": bar_time
    }
