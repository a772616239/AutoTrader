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
