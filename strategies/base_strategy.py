#!/usr/bin/env python3
"""
策略基类
"""
import hashlib
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple
import logging

logger = logging.getLogger(__name__)

class BaseStrategy:
    """策略基类"""
    
    def __init__(self, config: Dict = None, ib_trader=None):
        self.config = self._default_config()
        if config:
            self.config.update(config)
        
        # 交易接口
        self.ib_trader = ib_trader
        
        # 交易状态
        self.positions = {}
        self.trade_history = []
        self.daily_pnl = 0.0
        
        # 资金管理
        if self.ib_trader:
            try:
                self.equity = self.ib_trader.get_net_liquidation()
            except:
                self.equity = self.config.get('initial_capital', 100000.0)
        else:
            self.equity = self.config.get('initial_capital', 100000.0)
        
        # 信号管理
        self.signal_cache = {}
        self.executed_signals = set()
        
        # 性能跟踪
        self.signals_generated = 0
        self.trades_executed = 0
        self.start_time = datetime.now()
        
        logger.info(f"策略 {self.get_strategy_name()} 初始化完成")
    
    def _default_config(self) -> Dict:
        """默认配置 - 子类应该重写此方法"""
        return {
            'initial_capital': 40000.0,
            'risk_per_trade': 0.01,
            'max_position_size': 0.05,
            'min_cash_buffer': 0.3,
            'per_trade_notional_cap': 4000.0,
            'max_position_notional': 60000.0,  # 单股总仓位上限（美元）
            'max_active_positions': 5,
        }
    
    def get_strategy_name(self) -> str:
        """获取策略名称"""
        return self.__class__.__name__
    
    def _generate_signal_hash(self, signal: Dict) -> str:
        """生成信号唯一哈希"""
        signal_str = f"{signal['symbol']}_{signal['signal_type']}_{signal['action']}_{signal.get('reason', '')}"
        price_bucket = int(signal['price'] * 100) // 5
        signal_str += f"_{price_bucket}"
        return hashlib.md5(signal_str.encode()).hexdigest()[:8]
    
    def _is_signal_cooldown(self, signal_hash: str) -> bool:
        """检查信号是否在冷却期"""
        if signal_hash in self.signal_cache:
            expiration = self.signal_cache[signal_hash]
            if datetime.now() < expiration:
                return True
        return False
    
    def _add_signal_to_cache(self, signal_hash: str, minutes: int = 5):
        """添加信号到缓存"""
        expiration = datetime.now() + timedelta(minutes=minutes)
        self.signal_cache[signal_hash] = expiration
        
        # 清理过期信号
        current_time = datetime.now()
        expired_keys = [k for k, v in self.signal_cache.items() if v < current_time]
        for key in expired_keys:
            del self.signal_cache[key]
    
    def sync_positions_from_ib(self) -> bool:
        """从IB同步持仓信息"""
        if not self.ib_trader:
            return False
        
        try:
            if not self.ib_trader.connected:
                logger.warning("IB未连接，跳过持仓同步")
                return False

            holdings = self.ib_trader.get_holdings()
            self.positions.clear()
            
            for pos in holdings:
                symbol = pos.contract.symbol
                self.positions[symbol] = {
                    'size': pos.position,
                    'avg_cost': pos.avgCost,
                    'contract': pos.contract,
                    'entry_time': datetime.now()  # 如果无法获取真实开仓时间，使用当前时间
                }
            
            # 同步净资产
            self.equity = self.ib_trader.get_net_liquidation()
            logger.info(f"✅ 持仓同步完成: {len(self.positions)} 个持仓, 净资产: ${self.equity:,.2f}")
            return True
            
        except Exception as e:
            logger.error(f"从IB同步持仓失败: {e}")
            return False
    
    def check_exit_conditions(self, symbol: str, current_price: float, 
                             current_time: datetime = None) -> Optional[Dict]:
        """
        检查卖出条件 - 子类可以重写此方法
        """
        if symbol not in self.positions:
            return None
        
        if current_time is None:
            current_time = datetime.now()
        
        position = self.positions[symbol]
        avg_cost = position['avg_cost']
        position_size = position['size']
        
        entry_time = position.get('entry_time', current_time - timedelta(minutes=60))
        
        # 计算盈亏
        if position_size > 0:
            price_change_pct = (current_price - avg_cost) / avg_cost
        else:
            price_change_pct = (avg_cost - current_price) / avg_cost
        
        # 简单的退出条件 - 使用配置或默认值
        stop_loss_pct = -self.config.get('stop_loss_pct', 0.02)
        take_profit_pct = self.config.get('take_profit_pct', 0.03)
        
        if price_change_pct <= stop_loss_pct:
            return {
                'symbol': symbol,
                'signal_type': 'STOP_LOSS',
                'action': 'SELL' if position_size > 0 else 'BUY',
                'price': current_price,
                'reason': f"触发止损: 亏损{price_change_pct*100:.1f}%",
                'position_size': abs(position_size),
                'profit_pct': price_change_pct * 100
            }
        
        if price_change_pct >= take_profit_pct:
            return {
                'symbol': symbol,
                'signal_type': 'TAKE_PROFIT',
                'action': 'SELL' if position_size > 0 else 'BUY',
                'price': current_price,
                'reason': f"触发止盈: 盈利{price_change_pct*100:.1f}%",
                'position_size': abs(position_size),
                'profit_pct': price_change_pct * 100
            }
        
        return None
    
    def calculate_position_size(self, signal: Dict, atr: float = None) -> int:
        """计算仓位大小"""
        if atr is None:
            atr = signal['price'] * 0.02
        
        # 从IB获取可用资金
        if self.ib_trader:
            try:
                available_funds = self.ib_trader.get_available_funds()
                if available_funds > 0:
                    self.equity = available_funds
            except Exception as e:
                logger.warning(f"获取IB可用资金失败: {e}")
        
        if self.config.get('max_active_positions'):
            if len(self.positions) >= int(self.config['max_active_positions']):
                return 0

        risk_amount = self.equity * self.config['risk_per_trade']
        risk_amount *= signal.get('confidence', 0.5)
        
        risk_per_share = atr * self.config.get('stop_loss_atr_multiple', 1.5)
        if risk_per_share <= 0:
            return 0
        
        shares = int(risk_amount / risk_per_share)
        shares = max(1, shares)
        
        # 最大仓位限制 - 基于$10,000美元单笔上限
        equity_buffered = self.equity * (1 - float(self.config.get('min_cash_buffer', 0.0)))
        per_trade_cap = float(self.config.get('per_trade_notional_cap', 10000.0))
        max_shares_value = min(per_trade_cap, equity_buffered)
        max_shares = int(max_shares_value / signal['price'])
        result = min(shares, max_shares)
        try:
            logger.info(
                f"仓位计算: 价格 {signal['price']:.2f}, 权益 {self.equity:,.2f}, 风险股数 {shares}, "
                f"单笔上限 ${per_trade_cap:,.2f}, 可用缓冲 ${equity_buffered:,.2f}, "
                f"上限股数 {max_shares}, 实际下单 {result}"
            )
        except Exception:
            pass
        return result
    
    def execute_signal(self, signal: Dict, current_price: float) -> Dict:
        """执行交易信号 - 子类可以重写此方法"""
        if signal['position_size'] <= 0:
            return {'status': 'REJECTED', 'reason': '无效仓位'}
        
        if 'signal_hash' in signal and self._is_signal_cooldown(signal['signal_hash']):
            return {'status': 'REJECTED', 'reason': '信号冷却期'}
        
        if not self.ib_trader:
            return {'status': 'REJECTED', 'reason': 'IB接口未初始化'}
        
        order_type_cfg = self.config.get('ib_order_type', 'MKT')
        dedupe_price = None
        if order_type_cfg == 'LMT':
            if signal['action'] == 'BUY':
                dedupe_price = current_price * (1 - self.config.get('ib_limit_offset', 0.01))
            else:
                dedupe_price = current_price * (1 + self.config.get('ib_limit_offset', 0.01))
        if self.ib_trader.has_active_order(signal['symbol'], signal['action'], signal['position_size'], dedupe_price):
            return {'status': 'REJECTED', 'reason': '存在未完成订单，避免重复下单'}

        if signal['action'] == 'SELL':
            current_pos = 0
            if signal['symbol'] in self.positions:
                try:
                    current_pos = int(self.positions[signal['symbol']].get('size', 0) or 0)
                except:
                    current_pos = 0
            try:
                ib_pos = self.ib_trader.get_holding_for_symbol(signal['symbol'])
                if ib_pos and 'position' in ib_pos:
                    current_pos = int(ib_pos['position'])
            except:
                pass
            if current_pos <= 0:
                return {'status': 'REJECTED', 'reason': '无持仓，禁止卖出'}
            if signal['position_size'] > current_pos:
                signal['position_size'] = current_pos

        # 创建交易记录
        trade = {
            'symbol': signal['symbol'],
            'action': signal['action'],
            'entry_price': current_price,
            'size': signal['position_size'],
            'timestamp': datetime.now(),
            'signal_type': signal['signal_type'],
            'confidence': signal.get('confidence', 0.5),
            'status': 'PENDING',
            'order_type': self.config.get('ib_order_type', 'MKT')
        }
        
        try:
            order_type = self.config.get('ib_order_type', 'MKT')
            
            if order_type == 'LMT' and signal['action'] == 'BUY':
                limit_price = current_price * (1 - self.config.get('ib_limit_offset', 0.01))
                ib_trade = self.ib_trader.place_buy_order(
                    signal['symbol'], signal['position_size'], 'LMT', limit_price
                )
            elif order_type == 'LMT' and signal['action'] == 'SELL':
                limit_price = current_price * (1 + self.config.get('ib_limit_offset', 0.01))
                ib_trade = self.ib_trader.place_sell_order(
                    signal['symbol'], signal['position_size'], 'LMT', limit_price
                )
            elif signal['action'] == 'BUY':
                ib_trade = self.ib_trader.place_buy_order(
                    signal['symbol'], signal['position_size'], 'MKT'
                )
            else:
                ib_trade = self.ib_trader.place_sell_order(
                    signal['symbol'], signal['position_size'], 'MKT'
                )
            
            if ib_trade:
                # 读取 IB 返回的订单状态并映射到内部状态
                ib_status = None
                try:
                    ib_status = getattr(ib_trade, 'orderStatus', None)
                    ib_status_str = ib_status.status if ib_status else None
                except Exception:
                    ib_status_str = None

                trade['order_id'] = getattr(getattr(ib_trade, 'order', None), 'orderId', None)
                trade['order_status'] = ib_status_str

                # 映射 IB 的 orderStatus 到内部 status
                status_map = {
                    'PendingSubmit': 'PENDING',
                    'PreSubmitted': 'PENDING',
                    'Submitted': 'PENDING',
                    'ApiPending': 'PENDING',
                    'Filled': 'EXECUTED',
                    'Cancelled': 'CANCELLED',
                    'Inactive': 'FAILED'
                }
                mapped = status_map.get(ib_status_str, 'PENDING')
                trade['status'] = mapped

                # 如果已执行（Filled），则更新持仓并将信号加入缓存
                if mapped == 'EXECUTED':
                    if 'signal_hash' in signal:
                        self._add_signal_to_cache(signal['signal_hash'])

                    if signal['action'] == 'BUY':
                        if signal['symbol'] not in self.positions:
                            self.positions[signal['symbol']] = {
                                'size': signal['position_size'],
                                'avg_cost': current_price,
                                'entry_time': datetime.now()
                            }
                        else:
                            old_pos = self.positions[signal['symbol']]
                            total_size = old_pos['size'] + signal['position_size']
                            total_cost = old_pos['size'] * old_pos['avg_cost'] + signal['position_size'] * current_price
                            self.positions[signal['symbol']] = {
                                'size': total_size,
                                'avg_cost': total_cost / total_size,
                                'entry_time': old_pos.get('entry_time', datetime.now())
                            }

                # 记录交易历史（包含已提交/待处理/已执行等）
                self.trade_history.append(trade)
                self.trades_executed += 1

                # 若为 PENDING，则记录警告信息
                if mapped == 'PENDING':
                    logger.warning(f"⚠️  订单状态异常或待处理 - ID: {trade.get('order_id')}, 状态: {ib_status_str}")

                return trade
            else:
                if signal['symbol'] in self.positions:
                    old_pos = self.positions[signal['symbol']]
                    remaining = max(0, int(old_pos.get('size', 0)) - int(signal['position_size']))
                    if remaining > 0:
                        self.positions[signal['symbol']] = {
                            'size': remaining,
                            'avg_cost': old_pos.get('avg_cost', current_price),
                            'entry_time': old_pos.get('entry_time', datetime.now())
                        }
                    else:
                        del self.positions[signal['symbol']]
                
                self.trade_history.append(trade)
                self.trades_executed += 1
                
                action_icon = "🟢" if signal['action'] == 'BUY' else "🔴"
                logger.info(f"{action_icon} 执行交易: {signal['symbol']} {signal['action']} "
                           f"@{current_price:.2f}, 数量: {signal['position_size']}")
                
                return trade
            # else:
            #     trade['status'] = 'FAILED'
            #     # trade['reason'] = 'IB下单失败'
            #     return trade
                
        except Exception as e:
            trade['status'] = 'ERROR'
            trade['reason'] = str(e)
            logger.error(f"执行交易时出错 {signal['symbol']}: {e}")
            return trade
    
    def generate_signals(self, symbol: str, data: pd.DataFrame, 
                        indicators: Dict) -> List[Dict]:
        """
        生成交易信号 - 子类必须重写此方法
        """
        raise NotImplementedError("子类必须实现 generate_signals 方法")
    
    def run_analysis_cycle(self, data_provider, symbols: List[str]) -> Dict[str, List[Dict]]:
        """运行分析周期"""
        all_signals = {}
        self.executed_signals.clear()
        
        # 从IB同步持仓和资金
        self.sync_positions_from_ib()
        
        logger.info(f"策略 {self.get_strategy_name()} 开始分析周期，共 {len(symbols)} 个标的")
        
        for symbol in symbols:
            try:
                # 增加数据回溯以支持长期均线 (如MA200)
                df = data_provider.get_intraday_data(symbol, interval='5m', lookback=300)
                
                if df.empty or len(df) < 30:
                    continue
                
                indicators = data_provider.get_technical_indicators(symbol, '1d', '5m')
                
                signals = self.generate_signals(symbol, df, indicators)
                
                if signals:
                    all_signals[symbol] = signals
                    logger.info(f"  {symbol} 生成 {len(signals)} 个信号")
                    
                    # 执行信号
                    for signal in signals:
                        current_price = df['Close'].iloc[-1]
                        try:
                            result = self.execute_signal(signal, current_price)
                            logger.debug(f"  信号执行结果: {result}")
                        except Exception as e:
                            logger.error(f"  执行信号时出错: {e}")
                            continue
                        
            except Exception as e:
                logger.error(f"分析 {symbol} 时出错: {e}")
                import traceback
                logger.debug(traceback.format_exc())
                continue
        
        return all_signals
    
    def generate_report(self) -> Dict:
        """生成交易报告"""
        total_trades = len(self.trade_history)
        
        self.sync_positions_from_ib()
        
        report = {
            'timestamp': datetime.now().isoformat(),
            'strategy_name': self.get_strategy_name(),
            'equity': self.equity,
            'total_trades': total_trades,
            'trades_executed': self.trades_executed,
            'signals_generated': self.signals_generated,
            'positions_open': len(self.positions),
            'open_positions': list(self.positions.keys()),
            'signal_cache_size': len(self.signal_cache),
            'ib_connected': self.ib_trader.connected if self.ib_trader else False,
        }
        
        logger.info(f"📋 {self.get_strategy_name()} 报告 - 净资产: ${self.equity:,.2f}, "
                   f"总交易: {total_trades}, 持仓: {len(self.positions)}")
        
        return report
