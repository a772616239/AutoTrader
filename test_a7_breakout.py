#!/usr/bin/env python3
"""
Test script for A7 CTA Trend Strategy Breakout
"""
import pandas as pd
import numpy as np
import logging
from strategies.a7_cta_trend import A7CTATrendStrategy

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_a7_breakout():
    print("\n=== Testing A7 Trend Breakout (LONG) ===")
    
    # Initialize strategy
    strategy = A7CTATrendStrategy()
    
    # Create mock data: 250 bars
    # Days 0-200: Flat/Slow rise to set Trend MA
    # Days 201-240: Range bound (High=100, Low=90)
    # Day 241: Breakout to 105
    
    dates = pd.date_range(end=pd.Timestamp.now(), periods=250, freq='D')
    closes = np.linspace(80, 95, 200).tolist() # MA200 will be around 87.5
    highs = np.linspace(81, 96, 200).tolist()
    lows = np.linspace(79, 94, 200).tolist()
    
    # Range bound phase
    for i in range(40):
        closes.append(95 + np.sin(i)*4) # 91-99
        highs.append(100.0)
        lows.append(90.0)
        
    # Breakout candle
    closes.append(105.0)
    highs.append(106.0)
    lows.append(98.0)
    
    # Add dummy volume
    df = pd.DataFrame({
        'Open': closes, # Simplified
        'High': highs,
        'Low': lows,
        'Close': closes,
        'Volume': [1000000] * 241
    }, index=dates[:241])
    
    logger.info(f"Mock Data Length: {len(df)}")
    logger.info(f"Last Price: {df['Close'].iloc[-1]}, Previous High 20: {df['High'].iloc[-21:-1].max()}")
    
    # Run analysis
    symbol = 'TEST_BREAKOUT'
    signals = strategy.generate_signals(symbol, df, {})
    
    if signals:
        signal = signals[0]
        logger.info(f"✅ Signal Generated: {signal['signal_type']} {signal['action']} @ {signal['price']}")
        logger.info(f"Reason: {signal['reason']}")
        
        if signal['signal_type'] == 'CTA_BREAKOUT_LONG':
            print(">>> SUCCESS: Breakout Long Detected")
        else:
            print(f">>> FAILED: Wrong signal type {signal['signal_type']}")
    else:
        print(">>> FAILED: No signal generated on breakout")

if __name__ == "__main__":
    test_a7_breakout()
