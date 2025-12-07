#!/usr/bin/env python3
"""
Verification script for refactored strategies.
"""
import sys
import os
import pandas as pd
import logging
from datetime import datetime

# Adjust path to import from project root
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from data.data_provider import DataProvider
from strategies.a2_zscore import A2ZScoreStrategy
from strategies.a3_dual_ma_volume import A3DualMAVolumeStrategy
from strategies.a5_multifactor_ai import A5MultiFactorAI
from strategies.a6_news_trading import A6NewsTrading
from strategies.a7_cta_trend import A7CTATrendStrategy
import config

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def verify_strategies():
    """Verify that strategies can be initialized and generate signals."""
    
    base_url = config.CONFIG.get('data_server', {}).get('base_url', 'http://localhost:8001')
    data_provider = DataProvider(base_url=base_url)
    
    # Test symbol
    symbol = 'SPY'
    
    logger.info(f"Fetching data for {symbol}...")
    try:
        # Use a longer lookback to ensure enough data for indicators
        df = data_provider.get_intraday_data(symbol, interval='5m', lookback=300)
        logger.info(f"Fetched {len(df)} rows of data.")
    except Exception as e:
        logger.error(f"Failed to fetch data: {e}")
        return

    if df.empty:
        logger.error("No data fetched.")
        return

    # Strategies to test
    strategies = [
        A2ZScoreStrategy(config.CONFIG['strategy_a2']),
        A3DualMAVolumeStrategy(config.CONFIG['strategy_a3']),
        A5MultiFactorAI(config.CONFIG['strategy_a5'])
    ]
    
    logger.info("Starting strategy verification...")
    
    for strategy in strategies:
        try:
            name = strategy.get_strategy_name()
            logger.info(f"Testing {name}...")
            
            # Helper to simulate indicator dict usually passed by main loop
            # But specific strategies might calculate their own
            indicators = {} 
            
            signals = strategy.generate_signals(symbol, df, indicators)
            logger.info(f"✅ {name} executed successfully. Generated {len(signals)} signals.")
            
        except Exception as e:
            logger.error(f"❌ {name} failed: {e}", exc_info=True)

    # 验证 A7
    try:
        a7_config = config.CONFIG.get('strategy_a7')
        a7 = A7CTATrendStrategy(config=a7_config)
        logger.info("Testing A7 CTA Trend Strategy...")
        signals = a7.generate_signals(symbol, df, {})
        if signals:
            logger.info(f"✅ A7CTATrendStrategy generated signal: {signals[0]['action']} {signals[0]['symbol']}")
        else:
            logger.info("✅ A7CTATrendStrategy executed successfully. Generated 0 signals.")
    except Exception as e:
        logger.error(f"❌ A7CTATrendStrategy verification failed: {e}")

if __name__ == "__main__":
    verify_strategies()
