#!/usr/bin/env python3
"""
预选信号生成模块
负责对指定股票生成所有策略的信号
"""
import logging
from datetime import datetime
from typing import Dict, List
from config import STRATEGY_CONFIG_MAP
import config as config_module

logger = logging.getLogger(__name__)

class PreselectSignalsGenerator:
    """预选信号生成器"""

    def __init__(self, ib_trader=None):
        self.ib_trader = ib_trader

    def generate_preselect_signals(self, data_provider, all_signals: Dict[str, List[Dict]]):
        """对preselect_a2的所有股票生成信号并保存到新文件"""
        logger.info("🚀 generate_preselect_signals方法被调用")
        try:
            # 从config获取所有preselect_a2股票
            preselect_symbols = list(config_module.CONFIG.get('symbol_strategy_map', {}).keys())
            logger.info(f"📊 获取到preselect_symbols: {len(preselect_symbols)} 个")
            if not preselect_symbols:
                logger.info("⚠️ 未找到preselect_a2股票配置")
                return

            # 获取所有可用的策略
            all_strategies = list(STRATEGY_CONFIG_MAP.keys())
            logger.info(f"📊 获取到all_strategies: {len(all_strategies)} 个")
            if not all_strategies:
                logger.warning("⚠️ 未找到策略配置映射")
                return

            logger.info(f"🔍 开始生成preselect_a2信号: {len(preselect_symbols)} 个股票 × {len(all_strategies)} 个策略...")

            preselect_signals = []

            for symbol in preselect_symbols:
                try:
                    # 获取股票数据
                    df = data_provider.get_intraday_data(symbol, interval='5m', lookback=300)

                    if df.empty or len(df) < 30:
                        logger.debug(f"跳过 {symbol}，数据不足")
                        continue

                    # 获取技术指标（所有策略共享相同的indicators）
                    indicators = data_provider.get_technical_indicators(symbol, '1d', '5m')

                    # 对每个策略都生成信号
                    for strategy_name in all_strategies:
                        try:
                            # 获取策略配置
                            cfg_key = STRATEGY_CONFIG_MAP.get(strategy_name)
                            strat_cfg = config_module.CONFIG.get(cfg_key, {}) if cfg_key else {}

                            # 创建策略实例 - 直接使用strategy_manager中的STRATEGY_CLASSES
                            from strategy_manager import STRATEGY_CLASSES
                            strategy_class = STRATEGY_CLASSES.get(strategy_name)
                            if strategy_class:
                                exec_strategy = strategy_class(config=strat_cfg, ib_trader=self.ib_trader)
                            else:
                                continue

                            # 使用该策略生成信号
                            signals = exec_strategy.generate_signals(symbol, df, indicators)

                            if signals:
                                # 为每个信号添加策略信息
                                for signal in signals:
                                    signal_copy = signal.copy()
                                    signal_copy['strategy'] = strategy_name
                                    signal_copy['symbol'] = symbol
                                    signal_copy['generated_at'] = datetime.now().isoformat()
                                    preselect_signals.append(signal_copy)

                                    # 同时添加到all_signals中（用于当前周期的信号处理）
                                    if symbol not in all_signals:
                                        all_signals[symbol] = []
                                    all_signals[symbol].append(signal_copy)

                                logger.debug(f"  {symbol} + {strategy_name} 生成 {len(signals)} 个信号")

                        except Exception as e:
                            logger.debug(f"策略 {strategy_name} 处理 {symbol} 时出错: {e}")
                            continue

                except Exception as e:
                    logger.warning(f"处理 {symbol} 时出错: {e}")
                    continue

            logger.info(f"✅ preselect_a2信号生成完成，共收集 {len(preselect_signals)} 个信号")

            # 保存到新的CSV文件
            self._save_preselect_signals_to_csv(preselect_signals)

        except Exception as e:
            logger.error(f"生成preselect_a2信号失败: {e}")

    def _save_preselect_signals_to_csv(self, signals: List[Dict]):
        """保存preselect_a2信号到CSV文件"""
        try:
            import pandas as pd
            import os

            if not signals:
                logger.info("没有preselect_a2信号需要保存")
                return

            # 转换为DataFrame
            df = pd.DataFrame(signals)

            # 确保必要的列存在
            required_cols = ['symbol', 'strategy', 'signal_type', 'action', 'price', 'confidence', 'generated_at']
            for col in required_cols:
                if col not in df.columns:
                    df[col] = None

            # 重新排列列顺序
            df = df[required_cols + [col for col in df.columns if col not in required_cols]]

            # 保存到CSV文件
            filename = f'preselect_signals_{datetime.now().strftime("%Y%m%d_%H%M%S")}.csv'
            df.to_csv(filename, index=False)
            logger.info(f"preselect_a2信号已保存到 {filename}，共 {len(signals)} 个信号")

        except Exception as e:
            logger.error(f"保存preselect_a2信号到CSV失败: {e}")