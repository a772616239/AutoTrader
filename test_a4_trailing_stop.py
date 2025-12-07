#!/usr/bin/env python3
"""
Test script for A4 Pullback Strategy Trailing Stop
"""
import pandas as pd
import logging
from strategies.a4_pullback import A4PullbackStrategy

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_trailing_stop_long():
    print("\n=== Testing A4 Trailing Stop (LONG) ===")
    
    # Initialize strategy with mocked config
    strategy = A4PullbackStrategy()
    strategy.config['trailing_stop_pct'] = 0.02  # 2% trailing stop
    strategy.config['take_profit_pct'] = 1.0     # 100% take profit to avoid early exit during test
    
    symbol = 'TEST_LONG'
    entry_price = 100.0
    
    # 1. Simulate Entry
    print(f"1. Opening Long Position at ${entry_price}")
    strategy.positions[symbol] = {
        'size': 100,
        'avg_cost': entry_price,
        'entry_time': pd.Timestamp.now()
    }
    
    # 2. Simulate Price Rise (New High)
    high_price = 110.0
    print(f"2. Price rises to ${high_price} (+10%) - Should update high watermark")
    # Call check_exit_conditions to trigger internal state update
    strategy.check_exit_conditions(symbol, high_price)
    
    current_high = strategy.positions[symbol].get('highest_price')
    print(f"   Current Highest Price tracked: ${current_high}")
    assert current_high == high_price, f"Expected highest_price {high_price}, got {current_high}"

    # 3. Simulate Small Drop (No Stop)
    small_drop_price = 109.0
    print(f"3. Price drops to ${small_drop_price} (-0.9%) - Should NOT trigger stop")
    signal = strategy.check_exit_conditions(symbol, small_drop_price)
    if signal:
        print(f"   ❌ Unexpected signal: {signal['signal_type']}")
    else:
        print("   ✅ No signal generated (Correct)")

    # 4. Simulate Large Drop (Trigger Stop)
    # Stop trigger price = 110 * (1 - 0.02) = 107.8
    crash_price = 107.0 
    print(f"4. Price crashes to ${crash_price} (Below $107.8) - Should TRIGGER STOP")
    signal = strategy.check_exit_conditions(symbol, crash_price)
    
    if signal and signal['signal_type'] == 'TRAILING_STOP':
        print(f"   ✅ SUCCESS: Trailing Stop Triggered!")
        print(f"   Reason: {signal['reason']}")
    else:
        print(f"   ❌ FAILED: Signal not generated or wrong type. Got: {signal}")

def test_trailing_stop_short():
    print("\n=== Testing A4 Trailing Stop (SHORT) ===")
    
    strategy = A4PullbackStrategy()
    strategy.config['trailing_stop_pct'] = 0.02
    strategy.config['take_profit_pct'] = 1.0
    
    symbol = 'TEST_SHORT'
    entry_price = 100.0
    
    # 1. Simulate Entry (Short)
    print(f"1. Opening Short Position at ${entry_price}")
    strategy.positions[symbol] = {
        'size': -100,
        'avg_cost': entry_price,
        'entry_time': pd.Timestamp.now()
    }
    
    # 2. Simulate Price Fall (New Low)
    low_price = 90.0
    print(f"2. Price falls to ${low_price} (+10% profit) - Should update low watermark")
    strategy.check_exit_conditions(symbol, low_price)
    
    current_low = strategy.positions[symbol].get('lowest_price')
    print(f"   Current Lowest Price tracked: ${current_low}")
    assert current_low == low_price, f"Expected lowest_price {low_price}, got {current_low}"

    # 3. Simulate Rebound (Trigger Stop)
    # Stop trigger price = 90 * (1 + 0.02) = 91.8
    spike_price = 92.0
    print(f"3. Price spikes to ${spike_price} (Above $91.8) - Should TRIGGER STOP")
    signal = strategy.check_exit_conditions(symbol, spike_price)
    
    if signal and signal['signal_type'] == 'TRAILING_STOP':
        print(f"   ✅ SUCCESS: Trailing Stop Triggered!")
        print(f"   Reason: {signal['reason']}")
    else:
        print(f"   ❌ FAILED: Signal not generated or wrong type. Got: {signal}")

if __name__ == "__main__":
    try:
        test_trailing_stop_long()
        test_trailing_stop_short()
    except Exception as e:
        print(f"\n❌ Test failed with error: {e}")
