#!/usr/bin/env python3
"""
策略管理器：按股票分配策略并并行执行每个策略的分析周期
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List
import logging

from data.data_provider import DataProvider
from trading.ib_trader import IBTrader
import config as global_config

# 导入策略类
from strategies.a1_momentum_reversal import A1MomentumReversalStrategy
from strategies.a2_zscore import A2ZScoreStrategy
from strategies.a3_dual_ma_volume import A3DualMAVolumeStrategy

logger = logging.getLogger(__name__)

STRATEGY_CLASSES = {
    'a1': A1MomentumReversalStrategy,
    'a2': A2ZScoreStrategy,
    'a3': A3DualMAVolumeStrategy,
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
                logger.error(f"未知策略名称: {strategy_name}")
                return {}

            # 获取该策略在全局配置中的配置节名（如果存在）
            cfg_key = global_config.STRATEGY_CONFIG_MAP.get(strategy_name)
            strat_cfg = {}
            if cfg_key:
                strat_cfg = self.config.get(cfg_key, {})

            # 创建策略实例，但不传入 ib_trader，避免在工作线程中调用 IB
            strategy = cls(config=strat_cfg, ib_trader=None)

            # 对分配给该策略的每个 symbol 单独拉取数据并调用 generate_signals（不下单）
            out: Dict[str, List[Dict]] = {}
            for sym in syms:
                try:
                    df = self.data_provider.get_intraday_data(sym, interval='5m', lookback=80)
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
