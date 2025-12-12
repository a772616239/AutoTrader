#!/usr/bin/env python3
"""
策略管理器：按股票分配策略并并行执行每个策略的分析周期
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
import queue as _queue
from typing import Dict, List
import logging

from data.data_provider import DataProvider
from trading.ib_trader import IBTrader
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
# from strategies.a19_adx_trend import A19ADXTrendStrategy    
# from strategies.a20_volume_spike import A20VolumeSpikeStrategy
# from strategies.a21_fibonacci_retracement import A21FibonacciRetracementStrategy
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


def _group_symbols_by_strategy(symbol_map: Dict[str, str], symbols: List[str]) -> Dict[str, List[str]]:
    """根据映射将 symbols 分组到各个策略名称下。"""
    grouped: Dict[str, List[str]] = {}
    for s in symbols:
        strat = symbol_map.get(s)
        if not strat:
            # 未指定策略时，默认分配为 'a1'
            strat = 'a1'
        grouped.setdefault(strat, []).append(s)
    return grouped


class StrategyManager:
    """管理多策略并行运行的简单管理器"""

    def __init__(self, data_provider: DataProvider, ib_trader: IBTrader, config: dict = None):
        self.data_provider = data_provider
        self.ib_trader = ib_trader
        self.config = config or global_config.CONFIG

    def run_once(self, symbols: List[str]) -> Dict[str, List[Dict]]:
        """对传入的 symbols 按映射并行执行各自策略的一次分析周期。

        返回合并的 signals 字典: {symbol: [signals...]}
        """
        symbol_map = self.config.get('symbol_strategy_map', {})
        grouped = _group_symbols_by_strategy(symbol_map, symbols)

        results: Dict[str, List[Dict]] = {}

        def _run_for_strategy(strategy_name: str, syms: List[str]):
            cls = STRATEGY_CLASSES.get(strategy_name)
            if not cls:
                logger.warning(f"未知策略名称: {strategy_name}，使用默认策略a1")
                cls = STRATEGY_CLASSES.get('a4')
                if not cls:
                    logger.error(f"默认策略a1也不存在")
                    return {}

            # 获取该策略在全局配置中的配置节名（如果存在）
            cfg_key = global_config.STRATEGY_CONFIG_MAP.get(strategy_name)
            strat_cfg = {}
            if cfg_key:
                strat_cfg = self.config.get(cfg_key, {})

            # 创建策略实例，但不传入 ib_trader，避免在工作线程中调用 IB
            strategy = cls(config=strat_cfg, ib_trader=None)

            # 特殊处理：为A6新闻策略设置数据提供器
            if strategy_name == 'a6' and hasattr(strategy, 'data_provider'):
                strategy.data_provider = self.data_provider

            # 对分配给该策略的每个 symbol 单独拉取数据并调用 generate_signals（不下单）
            out: Dict[str, List[Dict]] = {}
            for sym in syms:
                try:
                    # A7等策略需要更长的数据窗口 (例如SMA200)
                    df = self.data_provider.get_intraday_data(sym, interval='5m', lookback=300)
                    if df is None or df.empty:
                        continue
                    # technical indicators 可选获取，若不可用则传空
                    try:
                        indicators = self.data_provider.get_technical_indicators(sym, '1d', '5m')
                    except Exception:
                        indicators = {}

                    sigs = strategy.generate_signals(sym, df, indicators)
                    if sigs:
                        # 标注信号来源策略，便于主线程执行下单
                        for s in sigs:
                            try:
                                s['origin_strategy'] = strategy_name
                            except Exception:
                                pass
                        out[sym] = sigs
                except Exception as e:
                    logger.error(f"策略 {strategy_name} 处理 {sym} 时出错: {e}")
                    continue

            return out

        # 并行执行
        with ThreadPoolExecutor(max_workers=min(8, max(1, len(grouped)))) as ex:
            futures = {ex.submit(_run_for_strategy, name, syms): name for name, syms in grouped.items()}
            for fut in as_completed(futures):
                name = futures[fut]
                try:
                    res = fut.result()
                    # 合并结果
                    for sym, sigs in res.items():
                        results[sym] = sigs
                except Exception as e:
                    logger.error(f"策略线程 {name} 失败: {e}")

        return results

    def stream_run(self, symbols: List[str], signal_queue: _queue.Queue):
        """以流式方式运行策略分析：

        - 启动工作线程并在发现信号时将信号逐条放入 `signal_queue`（线程安全）以便主线程即时消费并下单。
        - 返回 (executor, futures) 以便调用方监控完成状态；调用方负责关闭 executor（或等待 futures 完成）。
        """
        symbol_map = self.config.get('symbol_strategy_map', {})
        grouped = _group_symbols_by_strategy(symbol_map, symbols)

        def _run_for_strategy_stream(strategy_name: str, syms: List[str]):
            cls = STRATEGY_CLASSES.get(strategy_name)
            if not cls:
                logger.warning(f"未知策略名称: {strategy_name}，使用默认策略a1")
                cls = STRATEGY_CLASSES.get('a4')
                if not cls:
                    logger.error(f"默认策略a1也不存在")
                    return {}

            cfg_key = global_config.STRATEGY_CONFIG_MAP.get(strategy_name)
            strat_cfg = {}
            if cfg_key:
                strat_cfg = self.config.get(cfg_key, {})

            strategy = cls(config=strat_cfg, ib_trader=None)

            # 特殊处理：为A6新闻策略设置数据提供器
            if strategy_name == 'a6' and hasattr(strategy, 'data_provider'):
                strategy.data_provider = self.data_provider

            for sym in syms:
                try:
                    # A7等策略需要更长的数据窗口 (例如SMA200)
                    df = self.data_provider.get_intraday_data(sym, interval='5m', lookback=300)
                    if df is None or df.empty:
                        continue
                    try:
                        indicators = self.data_provider.get_technical_indicators(sym, '1d', '5m')
                    except Exception:
                        indicators = {}

                    sigs = strategy.generate_signals(sym, df, indicators)
                    if sigs:
                        for s in sigs:
                            try:
                                s['origin_strategy'] = strategy_name
                            except Exception:
                                pass
                            # 立即推送到主线程队列，供主线程即时处理
                            try:
                                signal_queue.put_nowait((sym, s))
                            except Exception:
                                # 若队列阻塞/失败，仍继续处理其它符号
                                logger.exception('将信号放入队列失败')
                except Exception as e:
                    logger.error(f"策略 {strategy_name} 处理 {sym} 时出错: {e}")
                    continue

        ex = ThreadPoolExecutor(max_workers=min(8, max(1, len(grouped))))
        futures = []
        for name, syms in grouped.items():
            fut = ex.submit(_run_for_strategy_stream, name, syms)
            futures.append(fut)

        return ex, futures


if __name__ == '__main__':
    # 简单示例（仅在脚本直接运行时）
    dp = DataProvider(base_url=global_config.CONFIG['data_server']['base_url'])
    ib = None
    try:
        ib = IBTrader(host=global_config.CONFIG['ib_server']['host'],
                      port=global_config.CONFIG['ib_server']['port'],
                      client_id=global_config.CONFIG['ib_server']['client_id'])
        if not ib.connect():
            ib = None
    except Exception:
        ib = None

    mgr = StrategyManager(dp, ib)
    symbols = list(global_config.CONFIG['trading']['symbols'])[:10]
    out = mgr.run_once(symbols)
    print(f"运行完成，生成信号数量: {sum(len(v) for v in out.values())}")
