import logging
import pandas as pd
import numpy as np
from typing import Dict

logger = logging.getLogger(__name__)

class ZScoreStrategy:
    """策略 A2: Z-Score 均值回归策略"""

    def __init__(self, ib_trader, data_provider, config: Dict = None):
        self.ib_trader = ib_trader
        self.data_provider = data_provider
        self.config = {
            'window': 20,           # 均线窗口
            'entry_std': 2.0,       # 入场标准差倍数
            'exit_std': 0.0,        # 出场标准差倍数 (回归均值)
            'stop_loss_pct': 0.03   # 硬止损
        }
        if config:
            self.config.update(config)
        
        self.positions = {}
        self.name = "Strategy_A2_ZScore"
        logger.info(f"策略引擎 {self.name} 已加载")

    def sync_positions(self):
        """同步持仓"""
        holdings = self.ib_trader.get_holdings()
        self.positions = {}
        for h in holdings:
            self.positions[h.contract.symbol] = {
                'size': h.position,
                'avg_cost': h.avgCost
            }

    def calculate_z_score(self, series: pd.Series, window: int):
        mean = series.rolling(window=window).mean()
        std = series.rolling(window=window).std()
        z_score = (series - mean) / std
        return z_score

    def run_analysis(self, symbol: str):
        """策略A2的分析逻辑"""
        # 1. 获取数据
        df = self.data_provider.get_intraday_data(symbol, lookback=self.config['window'] + 10)
        if df.empty or len(df) < self.config['window']:
            return None

        closes = df['Close']
        current_price = closes.iloc[-1]
        
        # 2. 计算 Z-Score
        z_scores = self.calculate_z_score(closes, self.config['window'])
        current_z = z_scores.iloc[-1]
        
        logger.debug(f"{symbol} Z-Score: {current_z:.2f}")

        # 3. 检查是否有持仓
        has_position = symbol in self.positions and self.positions[symbol]['size'] != 0
        
        if has_position:
            # --- 出场逻辑 ---
            pos = self.positions[symbol]
            size = pos['size']
            avg_cost = pos['avg_cost']
            
            # 计算盈亏比
            pnl_pct = (current_price - avg_cost) / avg_cost if size > 0 else (avg_cost - current_price) / avg_cost
            
            # 硬止损
            if pnl_pct < -self.config['stop_loss_pct']:
                return {
                    'symbol': symbol,
                    'action': 'SELL' if size > 0 else 'BUY',
                    'signal_type': 'ZSCORE_STOP_LOSS',
                    'price': current_price,
                    'reason': f"Z-Score止损, PnL: {pnl_pct:.2%}"
                }

            # 均值回归出场 (做多时，Z值回到0以上平仓；做空时，Z值回到0以下平仓)
            if size > 0 and current_z >= self.config['exit_std']:
                return {
                    'symbol': symbol,
                    'action': 'SELL',
                    'signal_type': 'ZSCORE_EXIT_LONG',
                    'price': current_price,
                    'reason': f"Z-Score回归 ({current_z:.2f})"
                }
            elif size < 0 and current_z <= -self.config['exit_std']:
                return {
                    'symbol': symbol,
                    'action': 'BUY',
                    'signal_type': 'ZSCORE_EXIT_SHORT',
                    'price': current_price,
                    'reason': f"Z-Score回归 ({current_z:.2f})"
                }

        else:
            # --- 入场逻辑 ---
            # Z < -2.0 做多 (超卖)
            if current_z < -self.config['entry_std']:
                return {
                    'symbol': symbol,
                    'action': 'BUY',
                    'signal_type': 'ZSCORE_ENTRY_LONG',
                    'price': current_price,
                    'reason': f"Z-Score超卖 ({current_z:.2f})"
                }
            # Z > 2.0 做空 (超买)
            elif current_z > self.config['entry_std']:
                return {
                    'symbol': symbol,
                    'action': 'SELL',
                    'signal_type': 'ZSCORE_ENTRY_SHORT',
                    'price': current_price,
                    'reason': f"Z-Score超买 ({current_z:.2f})"
                }
                
        return None