#!/usr/bin/env python3
"""
信号监控器 - 手动批量生成preselect_a2股票的信号并保存到CSV文件
注意：正常情况下，信号会在run_analysis_cycle中自动保存，此脚本仅用于手动测试或特殊情况
"""
import pandas as pd
import os
import logging
from datetime import datetime
from typing import Dict, List
from concurrent.futures import ThreadPoolExecutor, as_completed

from data.data_provider import DataProvider
import config as global_config

# 导入策略类
from strategies.a1_momentum_reversal import A1MomentumReversalStrategy
from strategies.a2_zscore import A2ZScoreStrategy
from strategies.a3_dual_ma_volume import A3DualMAVolumeStrategy
from strategies.a4_pullback import A4PullbackStrategy
from strategies.a5_multifactor_ai import A5MultiFactorAI
from strategies.a6_news_trading import A6NewsTrading
from strategies.a7_cta_trend import A7CTATrendStrategy
from strategies.a8_rsi_oscillator import A8RSIOscillatorStrategy
from strategies.a9_macd_crossover import A9MACDCrossoverStrategy
from strategies.a10_bollinger_bands import A10BollingerBandsStrategy
from strategies.a11_moving_average_crossover import A11MovingAverageCrossoverStrategy
from strategies.a12_stochastic_rsi import A12StochasticRSIStrategy
from strategies.a13_ema_crossover import A13EMACrossoverStrategy
from strategies.a14_rsi_trendline import A14RSITrendlineStrategy
from strategies.a15_pairs_trading import A15PairsTradingStrategy
from strategies.a16_roc import A16ROCStrategy
from strategies.a17_cci import A17CCIStrategy
from strategies.a18_isolation_forest import A18IsolationForestStrategy
from strategies.a22_super_trend import A22SuperTrendStrategy
from strategies.a23_aroon_oscillator import A23AroonOscillatorStrategy
from strategies.a24_ultimate_oscillator import A24UltimateOscillatorStrategy
from strategies.a25_pairs_trading import A25PairsTradingStrategy
from strategies.a26_williams_r import A26WilliamsRStrategy
from strategies.a27_minervini_trend import A27MinerviniTrendStrategy
from strategies.a28_true_strength_index import A28TrueStrengthIndexStrategy
from strategies.a29_stochastic_oscillator import A29StochasticOscillatorStrategy
from strategies.a30_ibd_rs_rating import A30IBDRSRatingStrategy
from strategies.a31_money_flow_index import A31MoneyFlowIndexStrategy
from strategies.a32_keltner_channels import A32KeltnerChannelsStrategy
from strategies.a33_pivot_points import A33PivotPointsStrategy
from strategies.a34_linear_regression import A34LinearRegressionStrategy
from strategies.a35_mlp_neural_network import A35MLPNeuralNetworkStrategy

logger = logging.getLogger(__name__)

STRATEGY_CLASSES = {
    'a1': A1MomentumReversalStrategy,
    'a2': A2ZScoreStrategy,
    'a3': A3DualMAVolumeStrategy,
    'a4': A4PullbackStrategy,
    'a5': A5MultiFactorAI,
    'a6': A6NewsTrading,
    'a7': A7CTATrendStrategy,
    'a8': A8RSIOscillatorStrategy,
    'a9': A9MACDCrossoverStrategy,
    'a10': A10BollingerBandsStrategy,
    'a11': A11MovingAverageCrossoverStrategy,
    'a12': A12StochasticRSIStrategy,
    'a13': A13EMACrossoverStrategy,
    'a14': A14RSITrendlineStrategy,
    'a15': A15PairsTradingStrategy,
    'a16': A16ROCStrategy,
    'a17': A17CCIStrategy,
    'a18': A18IsolationForestStrategy,
    'a22': A22SuperTrendStrategy,
    'a23': A23AroonOscillatorStrategy,
    'a24': A24UltimateOscillatorStrategy,
    'a25': A25PairsTradingStrategy,
    'a26': A26WilliamsRStrategy,
    'a27': A27MinerviniTrendStrategy,
    'a28': A28TrueStrengthIndexStrategy,
    'a29': A29StochasticOscillatorStrategy,
    'a30': A30IBDRSRatingStrategy,
    'a31': A31MoneyFlowIndexStrategy,
    'a32': A32KeltnerChannelsStrategy,
    'a33': A33PivotPointsStrategy,
    'a34': A34LinearRegressionStrategy,
    'a35': A35MLPNeuralNetworkStrategy,
}


class SignalMonitor:
    """信号监控器"""

    def __init__(self):
        self.data_provider = DataProvider(base_url=global_config.CONFIG['data_server']['base_url'])
        self.config = global_config.CONFIG
        self.signals_file = 'signals_monitor.csv'

    def get_preselect_a2_symbols(self) -> Dict[str, str]:
        """获取preselect_a2的股票策略映射"""
        return self.config.get('symbol_strategy_map', {})

    def generate_signals_for_symbol(self, symbol: str, strategy_name: str) -> List[Dict]:
        """为单个股票生成信号"""
        try:
            # 获取策略类
            strategy_class = STRATEGY_CLASSES.get(strategy_name)
            if not strategy_class:
                logger.warning(f"未知策略: {strategy_name} for {symbol}")
                return []

            # 获取策略配置
            cfg_key = global_config.STRATEGY_CONFIG_MAP.get(strategy_name)
            strat_cfg = {}
            if cfg_key:
                strat_cfg = self.config.get(cfg_key, {})

            # 创建策略实例
            strategy = strategy_class(config=strat_cfg, ib_trader=None)

            # 特殊处理A6新闻策略
            if strategy_name == 'a6' and hasattr(strategy, 'data_provider'):
                strategy.data_provider = self.data_provider

            # 获取数据
            df = self.data_provider.get_intraday_data(symbol, interval='5m', lookback=300)
            if df.empty:
                # 如果无法获取真实数据，生成模拟数据用于测试
                logger.info(f"无法获取{symbol}真实数据，使用模拟数据")
                df = self._generate_mock_data(symbol)

            # 获取技术指标
            indicators = self.data_provider.get_technical_indicators(symbol, '1d', '5m')
            if not indicators:
                # 如果无法获取技术指标，使用默认值
                indicators = {'RSI': 50, 'MACD': 0, 'ATR': 1.0}

            # 生成信号
            signals = strategy.generate_signals(symbol, df, indicators)

            # 为信号添加策略信息
            for signal in signals:
                signal['strategy'] = strategy_name
                signal['generated_at'] = datetime.now().isoformat()

            logger.info(f"{symbol} ({strategy_name}) 生成 {len(signals)} 个信号")
            return signals

        except Exception as e:
            logger.error(f"生成{symbol}信号时出错: {e}")
            return []

    def _generate_mock_data(self, symbol: str) -> pd.DataFrame:
        """生成模拟数据用于测试"""
        import numpy as np
        from datetime import datetime, timedelta

        # 生成最近24小时的模拟数据
        end_time = datetime.now()
        start_time = end_time - timedelta(hours=24)

        periods = 288  # 24小时 * 12个5分钟
        dates = pd.date_range(start=start_time, periods=periods, freq='5min')

        # 生成随机价格数据（基于正态随机游走）
        np.random.seed(hash(symbol) % 2**32)  # 基于股票代码的确定性种子
        base_price = {'AAPL': 150, 'MSFT': 300, 'NVDA': 400}.get(symbol, 100)
        returns = np.random.randn(periods) * 0.005  # 日波动率约1.5%
        prices = base_price * (1 + returns).cumprod()

        # 生成OHLCV数据
        df = pd.DataFrame(index=dates)
        df['Close'] = prices
        df['Open'] = prices * (1 + np.random.randn(periods) * 0.002)
        df['High'] = df[['Open', 'Close']].max(axis=1) * (1 + abs(np.random.randn(periods) * 0.003))
        df['Low'] = df[['Open', 'Close']].min(axis=1) * (1 - abs(np.random.randn(periods) * 0.003))
        df['Volume'] = np.random.randint(100000, 1000000, size=periods)

        # 确保 High >= max(Open, Close), Low <= min(Open, Close)
        df['High'] = df[['High', 'Open', 'Close']].max(axis=1)
        df['Low'] = df[['Low', 'Open', 'Close']].min(axis=1)

        return df

    def generate_all_signals(self) -> List[Dict]:
        """批量生成所有preselect_a2股票的信号"""
        symbol_map = self.get_preselect_a2_symbols()
        all_signals = []

        logger.info(f"开始生成信号，共 {len(symbol_map)} 个股票")

        # 并行处理
        with ThreadPoolExecutor(max_workers=min(8, len(symbol_map))) as executor:
            futures = {
                executor.submit(self.generate_signals_for_symbol, symbol, strategy): (symbol, strategy)
                for symbol, strategy in symbol_map.items()
            }

            for future in as_completed(futures):
                symbol, strategy = futures[future]
                try:
                    signals = future.result()
                    all_signals.extend(signals)
                    logger.info(f"完成 {symbol} ({strategy}): {len(signals)} 个信号")
                except Exception as e:
                    logger.error(f"处理 {symbol} 时出错: {e}")

        logger.info(f"信号生成完成，总共 {len(all_signals)} 个信号")
        return all_signals

    def save_signals_to_csv(self, signals: List[Dict], filename: str = None):
        """保存信号到CSV文件"""
        if not filename:
            filename = self.signals_file

        if not signals:
            logger.warning("没有信号需要保存")
            return

        try:
            # 转换为DataFrame
            df = pd.DataFrame(signals)

            # 确保必要的列存在
            required_cols = ['symbol', 'strategy', 'signal_type', 'action', 'price', 'confidence', 'generated_at']
            for col in required_cols:
                if col not in df.columns:
                    df[col] = None

            # 重新排列列顺序
            df = df[required_cols + [col for col in df.columns if col not in required_cols]]

            # 保存到CSV
            df.to_csv(filename, index=False)
            logger.info(f"信号已保存到 {filename}，共 {len(signals)} 个信号")

        except Exception as e:
            logger.error(f"保存信号到CSV失败: {e}")

    def run(self):
        """运行信号监控"""
        logger.info("开始信号监控...")

        # 生成信号
        signals = self.generate_all_signals()

        # 保存信号
        self.save_signals_to_csv(signals)

        logger.info("信号监控完成")


def main():
    """主函数"""
    # 设置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    # 创建信号监控器并运行
    monitor = SignalMonitor()
    monitor.run()


if __name__ == '__main__':
    main()