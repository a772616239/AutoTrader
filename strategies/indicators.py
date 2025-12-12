"""
Technical Indicators Library
Shared implementation of common technical indicators to ensure consistency across strategies.
"""
import pandas as pd
import numpy as np
from typing import Tuple, Union, Optional

def calculate_moving_average(series: pd.Series, period: int, type: str = 'SMA') -> pd.Series:
    """
    Calculate Simple or Exponential Moving Average.
    
    Args:
        series: Price series
        period: MA period
        type: 'SMA' or 'EMA'
        
    Returns:
        pd.Series: Moving average series
    """
    if type.upper() == 'EMA':
        return series.ewm(span=period, adjust=False).mean()
    else:
        return series.rolling(window=period).mean()

def calculate_rsi(prices: pd.Series, period: int = 14) -> pd.Series:
    """
    Calculate Relative Strength Index (RSI).
    
    Args:
        prices: Price series
        period: RSI period (default 14)
        
    Returns:
        pd.Series: RSI series (0-100)
    """
    delta = prices.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    
    rs = gain / (loss + 1e-10)
    rsi = 100 - (100 / (1 + rs))
    return rsi

def calculate_macd(prices: pd.Series, fast: int = 12, slow: int = 26, 
                  signal: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    Calculate MACD (Moving Average Convergence Divergence).
    
    Args:
        prices: Price series
        fast: Fast EMA period
        slow: Slow EMA period
        signal: Signal EMA period
        
    Returns:
        Tuple[pd.Series, pd.Series, pd.Series]: (MACD line, Signal line, Histogram)
    """
    ema_fast = prices.ewm(span=fast, adjust=False).mean()
    ema_slow = prices.ewm(span=slow, adjust=False).mean()
    
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    
    return macd_line, signal_line, histogram

def calculate_zscore(series: pd.Series, window: int = 20) -> pd.Series:
    """
    Calculate Z-Score (Standard Score).
    
    Args:
        series: Data series
        window: Rolling window size
        
    Returns:
        pd.Series: Z-Score series
    """
    rolling_mean = series.rolling(window=window).mean()
    rolling_std = series.rolling(window=window).std()
    
    zscore = (series - rolling_mean) / (rolling_std + 1e-10)
    return zscore

def calculate_atr(high: pd.Series, low: pd.Series, close: pd.Series, 
                 period: int = 14) -> pd.Series:
    """
    Calculate Average True Range (ATR).
    
    Args:
        high: High price series
        low: Low price series
        close: Close price series
        period: ATR period
        
    Returns:
        pd.Series: ATR series
    """
    tr1 = high - low
    tr2 = abs(high - close.shift())
    tr3 = abs(low - close.shift())
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    return atr

def calculate_bollinger_bands(prices: pd.Series, window: int = 20, 
                             num_std: float = 2.0) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    Calculate Bollinger Bands.
    
    Args:
        prices: Price series
        window: Rolling window size
        num_std: Number of standard deviations
        
    Returns:
        Tuple[pd.Series, pd.Series, pd.Series]: (Upper Band, Middle Band, Lower Band)
    """
    middle = prices.rolling(window=window).mean()
    std = prices.rolling(window=window).std()
    
    upper = middle + (std * num_std)
    lower = middle - (std * num_std)
    
    return upper, middle, lower

def calculate_donchian_channels(high: pd.Series, low: pd.Series, window: int = 20) -> Tuple[pd.Series, pd.Series, pd.Series]:
    """
    Calculate Donchian Channels.

    Args:
        high: High price series
        low: Low price series
        window: Lookback window size

    Returns:
        Tuple[pd.Series, pd.Series, pd.Series]: (Upper Channel, Middle Channel, Lower Channel)
    """
    upper = high.rolling(window=window).max()
    lower = low.rolling(window=window).min()
    middle = (upper + lower) / 2

    return upper, middle, lower

def calculate_stochastic_rsi(prices: pd.Series, rsi_period: int = 14, stoch_period: int = 14) -> pd.Series:
    """
    Calculate Stochastic RSI.

    Args:
        prices: Price series
        rsi_period: RSI calculation period
        stoch_period: Stochastic calculation period

    Returns:
        pd.Series: Stochastic RSI series (0-1)
    """
    # First calculate RSI
    rsi = calculate_rsi(prices, rsi_period)

    # Calculate Stochastic RSI
    rsi_min = rsi.rolling(window=stoch_period).min()
    rsi_max = rsi.rolling(window=stoch_period).max()

    stoch_rsi = (rsi - rsi_min) / (rsi_max - rsi_min + 1e-10)

    return stoch_rsi

def calculate_cci(high: pd.Series, low: pd.Series, close: pd.Series, period: int = 20) -> pd.Series:
    """
    Calculate Commodity Channel Index (CCI).

    Args:
        high: High price series
        low: Low price series
        close: Close price series
        period: CCI calculation period

    Returns:
        pd.Series: CCI series
    """
    # Typical Price
    tp = (high + low + close) / 3

    # Simple Moving Average of TP
    sma_tp = tp.rolling(window=period).mean()

    # Mean Deviation
    mean_dev = tp.rolling(window=period).apply(lambda x: abs(x - x.mean()).mean())

    # CCI calculation
    cci = (tp - sma_tp) / (0.015 * mean_dev + 1e-10)

    return cci

def calculate_roc(prices: pd.Series, period: int = 12) -> pd.Series:
    """
    Calculate Rate of Change (ROC).

    Args:
        prices: Price series
        period: ROC calculation period

    Returns:
        pd.Series: ROC series (percentage change)
    """
    roc = ((prices - prices.shift(period)) / prices.shift(period)) * 100
    return roc

def calculate_super_trend(high: pd.Series, low: pd.Series, close: pd.Series,
                         atr_period: int = 14, factor: float = 3.0) -> Tuple[pd.Series, pd.Series]:
    """
    Calculate Super Trend indicator.

    Super Trend is a trend-following indicator based on ATR.
    It creates a trailing stop level that can be used to set trailing stop losses.

    Args:
        high: High price series
        low: Low price series
        close: Close price series
        atr_period: ATR calculation period
        factor: Multiplier for ATR

    Returns:
        Tuple[pd.Series, pd.Series]: (Super Trend, Trend Direction)
        Trend Direction: 1 for uptrend, -1 for downtrend
    """
    # Calculate ATR
    atr = calculate_atr(high, low, close, atr_period)

    # Calculate Basic Bands
    hl2 = (high + low) / 2
    basic_upper = hl2 + (factor * atr)
    basic_lower = hl2 - (factor * atr)

    # Initialize Final Bands
    final_upper = basic_upper.copy()
    final_lower = basic_lower.copy()

    # Calculate Final Upper and Lower bands
    for i in range(1, len(close)):
        # Final Upper Band
        if close.iloc[i-1] <= final_upper.iloc[i-1]:
            final_upper.iloc[i] = min(basic_upper.iloc[i], final_upper.iloc[i-1])
        else:
            final_upper.iloc[i] = basic_upper.iloc[i]

        # Final Lower Band
        if close.iloc[i-1] >= final_lower.iloc[i-1]:
            final_lower.iloc[i] = max(basic_lower.iloc[i], final_lower.iloc[i-1])
        else:
            final_lower.iloc[i] = basic_lower.iloc[i]

    # Calculate Super Trend
    super_trend = pd.Series(index=close.index, dtype=float)
    trend_direction = pd.Series(index=close.index, dtype=int)

    for i in range(len(close)):
        if i == 0:
            # First value
            if close.iloc[i] <= final_upper.iloc[i]:
                super_trend.iloc[i] = final_upper.iloc[i]
                trend_direction.iloc[i] = 1  # Uptrend
            else:
                super_trend.iloc[i] = final_lower.iloc[i]
                trend_direction.iloc[i] = -1  # Downtrend
        else:
            # Subsequent values
            if super_trend.iloc[i-1] == final_upper.iloc[i-1]:
                if close.iloc[i] <= final_upper.iloc[i]:
                    super_trend.iloc[i] = final_upper.iloc[i]
                    trend_direction.iloc[i] = 1
                else:
                    super_trend.iloc[i] = final_lower.iloc[i]
                    trend_direction.iloc[i] = -1
            else:  # Previous was lower band
                if close.iloc[i] >= final_lower.iloc[i]:
                    super_trend.iloc[i] = final_lower.iloc[i]
                    trend_direction.iloc[i] = -1
                else:
                    super_trend.iloc[i] = final_upper.iloc[i]
                    trend_direction.iloc[i] = 1

    return super_trend, trend_direction

def calculate_aroon_oscillator(high: pd.Series, low: pd.Series, period: int = 25) -> pd.Series:
    """
    Calculate Aroon Oscillator.

    Aroon Oscillator measures the difference between Aroon Up and Aroon Down.
    It helps identify trend strength and potential reversals.

    Args:
        high: High price series
        low: Low price series
        period: Aroon calculation period (default 25)

    Returns:
        pd.Series: Aroon Oscillator series (-100 to 100)
    """
    # Calculate days since last high
    def high_max_func(xs):
        if len(xs) < period or xs.isna().any():
            return np.nan
        return np.argmax(xs[::-1])

    def low_min_func(xs):
        if len(xs) < period or xs.isna().any():
            return np.nan
        return np.argmin(xs[::-1])

    days_since_high = (
        high.rolling(center=False, min_periods=period, window=period)
        .apply(func=high_max_func, raw=False)
    )

    days_since_low = (
        low.rolling(center=False, min_periods=period, window=period)
        .apply(func=low_min_func, raw=False)
    )

    # Calculate Aroon Up and Aroon Down
    aroon_up = ((period - days_since_high) / period) * 100
    aroon_down = ((period - days_since_low) / period) * 100

    # Calculate Aroon Oscillator
    aroon_oscillator = aroon_up - aroon_down

    return aroon_oscillator

def calculate_ultimate_oscillator(high: pd.Series, low: pd.Series, close: pd.Series,
                                 short_period: int = 7, medium_period: int = 14,
                                 long_period: int = 28) -> pd.Series:
    """
    Calculate Ultimate Oscillator.

    Ultimate Oscillator is a momentum oscillator that combines short, medium, and long-term
    buying pressure into a single oscillator. It helps identify overbought/oversold conditions
    and potential reversal points.

    Args:
        high: High price series
        low: Low price series
        close: Close price series
        short_period: Short period for calculation (default 7)
        medium_period: Medium period for calculation (default 14)
        long_period: Long period for calculation (default 28)

    Returns:
        pd.Series: Ultimate Oscillator series (0-100)
    """
    # Calculate prior close
    prior_close = close.shift(1)

    # Calculate Buying Pressure (BP)
    bp = close - pd.concat([low, prior_close], axis=1).min(axis=1)

    # Calculate True Range (TR)
    tr = pd.concat([high, prior_close], axis=1).max(axis=1) - pd.concat([low, prior_close], axis=1).min(axis=1)

    # Calculate averages for different periods
    avg_short = bp.rolling(window=short_period).sum() / tr.rolling(window=short_period).sum()
    avg_medium = bp.rolling(window=medium_period).sum() / tr.rolling(window=medium_period).sum()
    avg_long = bp.rolling(window=long_period).sum() / tr.rolling(window=long_period).sum()

    # Calculate Ultimate Oscillator
    uo = 100 * (4 * avg_short + 2 * avg_medium + avg_long) / (4 + 2 + 1)

    return uo

def calculate_chaikin_money_flow(high: pd.Series, low: pd.Series, close: pd.Series,
                                volume: pd.Series, period: int = 20) -> pd.Series:
    """
    Calculate Chaikin Money Flow (CMF).

    Chaikin Money Flow measures the amount of money flow volume over a specific period.
    It helps identify buying and selling pressure by combining price and volume data.

    Args:
        high: High price series
        low: Low price series
        close: Close price series
        volume: Volume series
        period: CMF calculation period (default 20)

    Returns:
        pd.Series: Chaikin Money Flow series (-1 to 1)
    """
    # Calculate Money Flow Multiplier
    mf_multiplier = (2 * close - low - high) / (high - low + 1e-10)

    # Calculate Money Flow Volume
    mf_volume = mf_multiplier * volume

    # Calculate Chaikin Money Flow
    cmf = mf_volume.rolling(window=period).sum() / volume.rolling(window=period).sum()

    return cmf

def calculate_ease_of_movement(high: pd.Series, low: pd.Series, volume: pd.Series,
                              period: int = 14, volume_divisor: float = 100000000) -> pd.Series:
    """
    Calculate Ease of Movement (EVM).

    Ease of Movement combines price and volume to assess the ease with which prices move.
    It helps identify periods when price movements are supported by volume.

    Args:
        high: High price series
        low: Low price series
        volume: Volume series
        period: Period for moving average (default 14)
        volume_divisor: Divisor for volume normalization (default 100000000)

    Returns:
        pd.Series: Ease of Movement series
    """
    # Calculate Distance Moved (DM)
    midpoint_current = (high + low) / 2
    midpoint_prev = midpoint_current.shift(1)
    dm = midpoint_current - midpoint_prev

    # Calculate Box Ratio (BR)
    br = (volume / volume_divisor) / (high - low + 1e-10)

    # Calculate Ease of Movement
    evm = dm / br

    # Apply moving average
    evm_ma = evm.rolling(window=period).mean()

    return evm_ma

def calculate_force_index(close: pd.Series, volume: pd.Series, period: int = 13) -> pd.Series:
    """
    Calculate Force Index.

    Force Index combines price change and volume to measure the strength of bulls and bears.
    It helps identify potential turning points and trend strength.

    Args:
        close: Close price series
        volume: Volume series
        period: Period for exponential moving average (default 13)

    Returns:
        pd.Series: Force Index series
    """
    # Calculate raw force index (1-period)
    price_change = close - close.shift(1)
    force_index_raw = price_change * volume

    # Apply exponential moving average
    force_index = force_index_raw.ewm(span=period, adjust=False).mean()

    return force_index

def calculate_williams_r(high: pd.Series, low: pd.Series, close: pd.Series,
                         period: int = 14) -> pd.Series:
    """
    Calculate Williams %R.

    Williams %R is a momentum indicator that measures overbought and oversold levels.
    Similar to Stochastic Oscillator but uses a different calculation method.

    Args:
        high: High price series
        low: Low price series
        close: Close price series
        period: Lookback period (default 14)

    Returns:
        pd.Series: Williams %R series (-100 to 0)
    """
    # Calculate highest high and lowest low over the period
    highest_high = high.rolling(window=period).max()
    lowest_low = low.rolling(window=period).min()

    # Calculate Williams %R
    williams_r = -100 * (highest_high - close) / (highest_high - lowest_low + 1e-10)

    return williams_r

def calculate_true_strength_index(close: pd.Series, r_period: int = 25,
                                 s_period: int = 13) -> pd.Series:
    """
    Calculate True Strength Index (TSI).

    True Strength Index is a momentum oscillator that ranges between -100 and +100,
    designed to identify short-term swings while filtering out longer-term trends.

    Args:
        close: Close price series
        r_period: First smoothing period (default 25)
        s_period: Second smoothing period (default 13)

    Returns:
        pd.Series: True Strength Index series (-100 to 100)
    """
    # Calculate price change
    pc = close - close.shift(1)

    # Calculate absolute price change
    abs_pc = abs(pc)

    # Double smoothing of price change
    ema_r = pc.ewm(span=r_period, adjust=False).mean()
    ema_s = ema_r.ewm(span=s_period, adjust=False).mean()

    # Double smoothing of absolute price change
    abs_ema_r = abs_pc.ewm(span=r_period, adjust=False).mean()
    abs_ema_s = abs_ema_r.ewm(span=s_period, adjust=False).mean()

    # Calculate TSI
    tsi = 100 * (ema_s / abs_ema_s)

    return tsi
