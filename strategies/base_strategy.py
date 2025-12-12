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
from config import CONFIG

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
        # 检测是否在交易时间内，设置force_market_orders标志
        self.force_market_orders = not self._within_trading_hours()
        
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
            'trading_hours': {
                'start': '09:30',
                'end': '16:00'
            },
        }
    
    def get_strategy_name(self) -> str:
        """获取策略名称"""
        return self.__class__.__name__

    def _within_trading_hours(self) -> bool:
        """检查是否在交易时间内（美东时间）"""
        try:
            import pytz
            HAS_PYTZ = True
        except ImportError:
            HAS_PYTZ = False

        hours = self.config.get('trading_hours', {'start': '09:30', 'end': '16:00'})
        start = datetime.strptime(hours['start'], '%H:%M').time()
        end = datetime.strptime(hours['end'], '%H:%M').time()

        # 获取美东时间
        if HAS_PYTZ:
            try:
                eastern = pytz.timezone('US/Eastern')
                current = datetime.now(eastern).time()
            except Exception:
                current = datetime.now().time()  # 假设本地时间就是美东时间
        else:
            current = datetime.now().time()  # 假设本地时间就是美东时间

        return start <= current <= end
    
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
        logger.info(f"🔄 开始从IB同步持仓信息 - 策略: {self.get_strategy_name()}")

        if not self.ib_trader:
            logger.info("❌ IB交易接口未初始化")
            return False

        try:
            if not self.ib_trader.connected:
                logger.info("IB未连接，跳过持仓同步")
                return False

            logger.info("📡 正在获取IB持仓数据...")
            holdings = self.ib_trader.get_holdings()

            if not holdings:
                logger.info("ℹ️ IB返回空持仓列表")
                self.positions.clear()
                self.equity = self.ib_trader.get_net_liquidation()
                return True

            self.positions.clear()
            logger.info(f"📊 处理 {len(holdings)} 个IB持仓")

            for pos in holdings:
                try:
                    symbol = pos.contract.symbol
                    position_size = pos.position
                    avg_cost = pos.avgCost

                    logger.info(f"📈 同步持仓 - {symbol}: {position_size}股 @ ${avg_cost:.2f}")

                    self.positions[symbol] = {
                        'size': position_size,
                        'avg_cost': avg_cost,
                        'contract': pos.contract,
                        'entry_time': datetime.now()  # 如果无法获取真实开仓时间，使用当前时间
                    }
                except Exception as e:
                    logger.warning(f"处理持仓 {pos.contract.symbol if hasattr(pos, 'contract') else 'Unknown'} 时出错: {e}")
                    continue

            # 同步净资产
            self.equity = self.ib_trader.get_net_liquidation()
            logger.info(f"✅ 持仓同步完成: {len(self.positions)} 个持仓, 净资产: ${self.equity:,.2f}")
            return True

        except Exception as e:
            logger.error(f"从IB同步持仓失败: {e}")
            import traceback
            logger.info(f"详细错误信息: {traceback.format_exc()}")
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

        # 优先使用IB的实时持仓成本计算盈利百分比
        ib_profit_pct = None
        if self.ib_trader and self.ib_trader.connected:
            try:
                ib_holding = self.ib_trader.get_holding_for_symbol(symbol)
                if ib_holding and 'avg_cost' in ib_holding and ib_holding['avg_cost'] > 0:
                    ib_avg_cost = ib_holding['avg_cost']
                    if position_size > 0:
                        ib_profit_pct = (current_price - ib_avg_cost) / ib_avg_cost
                    else:
                        ib_profit_pct = (ib_avg_cost - current_price) / ib_avg_cost
                    logger.info(f"📊 {symbol} IB持仓成本: ${ib_avg_cost:.2f}, 当前价格: ${current_price:.2f}, 盈利百分比: {ib_profit_pct*100:.2f}%")
            except Exception as e:
                logger.info(f"获取IB持仓成本失败: {e}")

        # 计算盈亏（使用IB成本优先，否则使用本地成本）
        if ib_profit_pct is not None:
            price_change_pct = ib_profit_pct
            avg_cost = ib_holding['avg_cost']  # 更新为IB成本用于后续计算
        else:
            if position_size > 0:
                price_change_pct = (current_price - avg_cost) / avg_cost
            else:
                price_change_pct = (avg_cost - current_price) / avg_cost
        
        # 简单的退出条件 - 使用配置或默认值
        stop_loss_pct = -abs(self.config.get('stop_loss_pct', 0.015))  # 确保为负值，降低限制
        take_profit_pct = abs(self.config.get('take_profit_pct', 0.025))  # 确保为正值，降低限制
        
        # 检查最大持有时间（优先检查分钟级别，适用于日内交易）
        max_holding_minutes = self.config.get('max_holding_minutes', None)
        if max_holding_minutes:
            holding_minutes = (current_time - entry_time).total_seconds() / 60
            if holding_minutes > max_holding_minutes:
                return {
                    'symbol': symbol,
                    'signal_type': 'MAX_HOLDING_TIME',
                    'action': 'SELL' if position_size > 0 else 'BUY',
                    'price': current_price,
                    'reason': f"超过最大持有时间: {holding_minutes:.0f}分钟 > {max_holding_minutes}分钟",
                    'position_size': abs(position_size),
                    'profit_pct': price_change_pct * 100,
                    'confidence': 1.0
                }
        
        # 检查最大持有天数（适用于多日持仓策略）
        max_holding_days = self.config.get('max_holding_days', None)
        if max_holding_days:
            holding_days = (current_time - entry_time).total_seconds() / (24 * 3600)
            if holding_days > max_holding_days:
                return {
                    'symbol': symbol,
                    'signal_type': 'MAX_HOLDING_TIME',
                    'action': 'SELL' if position_size > 0 else 'BUY',
                    'price': current_price,
                    'reason': f"超过最大持有时间: {holding_days:.1f}天 > {max_holding_days}天",
                    'position_size': abs(position_size),
                    'profit_pct': price_change_pct * 100,
                    'confidence': 1.0
                }
        
        # 收盘前强制平仓检查（适用于日内交易策略）
        force_close_time = self.config.get('force_close_time', None)
        if force_close_time:
            try:
                close_time = datetime.strptime(force_close_time, '%H:%M').time()
                current_time_of_day = current_time.time()
                if current_time_of_day >= close_time and abs(position_size) > 0:
                    return {
                        'symbol': symbol,
                        'signal_type': 'FORCE_CLOSE_BEFORE_MARKET_CLOSE',
                        'action': 'SELL' if position_size > 0 else 'BUY',
                        'price': current_price,
                        'reason': f"收盘前强制平仓: 当前时间 {current_time_of_day.strftime('%H:%M')} >= {force_close_time}",
                        'position_size': abs(position_size),
                        'profit_pct': price_change_pct * 100,
                        'confidence': 1.0
                    }
            except Exception as e:
                logger.info(f"解析force_close_time失败: {e}")
        
        # 止损检查（优先检查，保护资金）
        if price_change_pct <= stop_loss_pct:
            logger.warning(f"⚠️ {symbol} 触发止损: 亏损{price_change_pct*100:.2f}% (成本: ${avg_cost:.2f}, 当前: ${current_price:.2f})")
            return {
                'symbol': symbol,
                'signal_type': 'STOP_LOSS',
                'action': 'SELL' if position_size > 0 else 'BUY',
                'price': current_price,
                'reason': f"触发止损: 亏损{price_change_pct*100:.2f}% (阈值: {abs(stop_loss_pct)*100:.1f}%)",
                'position_size': abs(position_size),
                'profit_pct': price_change_pct * 100,
                'confidence': 1.0  # 止损信号置信度最高
            }
        
        # 增强止盈检查 - 基于盈利百分比的多级判断
        take_profit_levels = self.config.get('take_profit_levels', [
            {'threshold': 0.02, 'confidence': 0.7, 'reason': '小幅盈利止盈'},
            {'threshold': 0.05, 'confidence': 0.8, 'reason': '中幅盈利止盈'},
            {'threshold': 0.10, 'confidence': 0.9, 'reason': '大幅盈利止盈'},
            {'threshold': 0.20, 'confidence': 1.0, 'reason': '巨幅盈利止盈'}
        ])

        for level in take_profit_levels:
            if price_change_pct >= level['threshold']:
                logger.info(f"✅ {symbol} 触发{level['reason']}: 盈利{price_change_pct*100:.2f}% (成本: ${avg_cost:.2f}, 当前: ${current_price:.2f})")
                return {
                    'symbol': symbol,
                    'signal_type': 'TAKE_PROFIT',
                    'action': 'SELL' if position_size > 0 else 'BUY',
                    'price': current_price,
                    'reason': f"{level['reason']}: 盈利{price_change_pct*100:.2f}% (阈值: {level['threshold']*100:.1f}%)",
                    'position_size': abs(position_size),
                    'profit_pct': price_change_pct * 100,
                    'confidence': level['confidence']
                }

        # 兼容原有单一止盈阈值
        if price_change_pct >= take_profit_pct:
            logger.info(f"✅ {symbol} 触发止盈: 盈利{price_change_pct*100:.2f}% (成本: ${avg_cost:.2f}, 当前: ${current_price:.2f})")
            return {
                'symbol': symbol,
                'signal_type': 'TAKE_PROFIT',
                'action': 'SELL' if position_size > 0 else 'BUY',
                'price': current_price,
                'reason': f"触发止盈: 盈利{price_change_pct*100:.2f}% (阈值: {take_profit_pct*100:.1f}%)",
                'position_size': abs(position_size),
                'profit_pct': price_change_pct * 100,
                'confidence': 1.0  # 止盈信号置信度最高
            }

        # 基于IB未实现盈利的止盈检查
        if self.ib_trader and self.ib_trader.connected:
            try:
                ib_holding = self.ib_trader.get_holding_for_symbol(symbol)
                if ib_holding and 'unrealized_pnl' in ib_holding:
                    unrealized_pnl = ib_holding['unrealized_pnl']
                    position_value = abs(position_size) * current_price
                    if position_value > 0:
                        pnl_pct = (unrealized_pnl / position_value) * 100
                        take_profit_pnl_threshold = self.config.get('take_profit_pnl_threshold', 300.0)  # 默认$300未实现盈利，降低限制
                        logger.info(f"📊 {symbol} IB未实现盈利检查: ${unrealized_pnl:.2f} ({pnl_pct:.2f}%), 阈值: ${take_profit_pnl_threshold:.2f}, 持仓价值: ${position_value:.2f}")
                        if unrealized_pnl >= take_profit_pnl_threshold:
                            logger.info(f"✅ {symbol} 触发IB未实现盈利止盈: ${unrealized_pnl:.2f} ({pnl_pct:.2f}%) >= ${take_profit_pnl_threshold:.2f}")
                            return {
                                'symbol': symbol,
                                'signal_type': 'TAKE_PROFIT_PNL',
                                'action': 'SELL' if position_size > 0 else 'BUY',
                                'price': current_price,
                                'reason': f"IB未实现盈利止盈: ${unrealized_pnl:.2f} ({pnl_pct:.2f}%)",
                                'position_size': abs(position_size),
                                'profit_pct': pnl_pct,
                                'confidence': 1.0
                            }
                else:
                    logger.info(f"⚠️ {symbol} 无法获取IB持仓信息进行未实现盈利检查")
            except Exception as e:
                logger.info(f"检查IB未实现盈利时出错: {e}")
        
        return None
    
    def calculate_position_size(self, signal: Dict, atr: float = None) -> int:
        """计算仓位大小"""
        if atr is None:
            atr = signal['price'] * 0.02
        
        # 从IB获取可用资金
        if self.ib_trader:
            try:
                available_funds = self.ib_trader.get_available_funds()
                logger.info(f"从IB获取可用资金: {available_funds}")
                if available_funds > 0:
                    self.equity = available_funds
                    logger.info(f"更新equity为IB可用资金: {self.equity}")
                else:
                    logger.warning(f"IB可用资金为0，使用默认equity进行模拟交易: {self.equity}")
            except Exception as e:
                logger.info(f"获取IB可用资金失败: {e}, 使用默认equity进行模拟交易: {self.equity}")
        
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
        logger.info(f"[{self.get_strategy_name()}] 计算仓位大小: 风险金额 ${risk_amount:,.2f}, 每股风险 ${risk_per_share:.2f}, 初始股数 {shares}, 最大股数 {max_shares}, 最终股数 {result} equity_buffered {equity_buffered}")
        try:
            logger.info(
                f"仓位计算: 价格 {signal['price']:.2f}, 权益 {self.equity:,.2f}, 风险股数 {shares}, "
                f"单笔上限 ${per_trade_cap:,.2f}, 可用缓冲 ${equity_buffered:,.2f}, "
                f"上限股数 {max_shares}, 实际下单 {result}"
            )
        except Exception:
            pass
        return result
    
    def execute_signal(self, signal: Dict, current_price: float, force_market_order: bool = False) -> Dict:
        """执行交易信号 - 子类可以重写此方法"""
        logger.info(f"执行交易信号: {signal['symbol']}, {signal['action']} {signal['position_size']} shares")
        if signal['position_size'] <= 0:
            logger.info(f"无效仓位: {signal['position_size']}")
            return {'status': 'REJECTED', 'reason': '无效仓位'}
        
        if 'signal_hash' in signal and self._is_signal_cooldown(signal['signal_hash']):
            logger.info(f"信号冷却期: {signal['signal_hash']}")
            return {'status': 'REJECTED', 'reason': '信号冷却期'}
        
        if not self.ib_trader:
            logger.info("IB接口未初始化")
            return {'status': 'REJECTED', 'reason': 'IB接口未初始化'}
            
        # 动态资金检查 (仅针对买入)
        if signal['action'] == 'BUY':
            # 检查当日不能重复买入限制
            # if CONFIG['trading'].get('same_day_sell_only', False):
                if signal['symbol'] in self.positions:
                    entry_time = self.positions[signal['symbol']].get('entry_time')
                    if entry_time:
                        today = datetime.now().date()
                        entry_date = entry_time.date()
                        if entry_date == today:
                            logger.info(f"当日不能重复买入限制: {signal['symbol']} 今日已买入，禁止再次买入")
                            return {'status': 'REJECTED', 'reason': "当日不能重复买入限制{signal['symbol']}"}
                        
        if signal['action'] == 'BUY':
            # 检查当日不能重复买入限制
            if CONFIG['trading'].get('same_day_sell_only', True):
                 logger.info(f"当日不能重复买入限制: {signal['symbol']} 今日已买入，禁止再次买入")
                 return {'status': 'REJECTED', 'reason': F"用完现金当日只能卖出了{signal['symbol']}"}
            try:
                available_funds = self.ib_trader.get_available_funds()
                # 1. 资金门槛检查 (< $500 则不交易，纸面账户除外)
                if available_funds < 500 and available_funds > 0:
                    msg = f"可用资金不足 $500 (${available_funds:.2f})，跳过下单"
                    logger.info(f"⚠️ {msg}")
                    return {'status': 'REJECTED', 'reason': msg}
                elif available_funds == 0:
                    logger.info(f"⚠️ IB可用资金为0，使用模拟交易模式")

                # 2. 资金充足性检查 (真实账户检查，纸面账户跳过)
                if available_funds > 0:  # 只有真实账户才有资金检查
                    estimated_cost = signal['position_size'] * current_price
                    if estimated_cost > available_funds:
                        # 计算最大可买股数
                        max_qty = int(available_funds // current_price)
                        if max_qty > 0:
                            logger.info(f"💰 资金不足全额买入 (${available_funds:.2f} < ${estimated_cost:.2f})，"
                                        f"调整仓位: {signal['position_size']} -> {max_qty} 股")
                            signal['position_size'] = max_qty
                        else:
                            msg = f"资金不足以买入 1 股 (${available_funds:.2f} < ${current_price:.2f})"
                            logger.info(f"⚠️ {msg}")
                            return {'status': 'REJECTED', 'reason': msg}
            except Exception as e:
                logger.error(f"检查可用资金时出错: {e}")
        
        order_type_cfg = self.config.get('ib_order_type', 'MKT')
        dedupe_price = None
        if order_type_cfg == 'LMT':
            if signal['action'] == 'BUY':
                dedupe_price = current_price * (1 - self.config.get('ib_limit_offset', 0.01))
            else:
                dedupe_price = current_price * (1 + self.config.get('ib_limit_offset', 0.01))
        if self.ib_trader.has_active_order(signal['symbol'], signal['action'], signal['position_size'], dedupe_price):
            logger.info(f"存在未完成订单，避免重复下单: {signal['symbol']}")
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
                if not CONFIG['trading'].get('allow_short_selling', False):
                    logger.info(f"无持仓，禁止卖出: {signal['symbol']}")
                    return {'status': 'REJECTED', 'reason': '无持仓，禁止卖出'}
            # 只有在有持仓且卖出数量超过持仓时才调整，否则保持原值（允许开空）
            elif signal['position_size'] > current_pos:
                signal['position_size'] = current_pos

            # 检查卖出名义价值上限（如果开关开启）
            if not CONFIG['trading'].get('sell_exempt_from_cap', True):
                per_trade_cap = float(self.config.get('per_trade_notional_cap', 10000.0))
                notional_value = signal['position_size'] * current_price
                if notional_value > per_trade_cap:
                    max_qty = int(per_trade_cap / current_price)
                    if max_qty > 0:
                        logger.info(f"💰 卖出名义价值超过上限 (${notional_value:.2f} > ${per_trade_cap:.2f})，"
                                    f"调整仓位: {signal['position_size']} -> {max_qty} 股")
                        signal['position_size'] = max_qty
                    else:
                        msg = f"卖出名义价值超过上限 (${notional_value:.2f} > ${per_trade_cap:.2f})，无法卖出"
                        logger.info(f"⚠️ {msg}")
                        return {'status': 'REJECTED', 'reason': msg}

        # 创建交易记录
        trade = {
            'symbol': signal['symbol'],
            'action': signal['action'],
            'entry_price': current_price,
            'price': current_price, # 兼容前端显示
            'size': signal['position_size'],
            'timestamp': datetime.now(),
            'signal_type': signal['signal_type'],
            # 'strategy': signal.get('strategy', self.name),  # 记录策略名称
            'confidence': signal.get('confidence', 0.5),
            'status': 'PENDING',
            'order_type': self.config.get('ib_order_type', 'MKT')
        }

        # 对于卖出交易，添加持仓成本信息
        if signal['action'] == 'SELL':
            # 计算平均持仓成本
            avg_cost = 0.0
            if signal['symbol'] in self.positions:
                avg_cost = self.positions[signal['symbol']].get('avg_cost', 0.0)
            elif self.ib_trader and self.ib_trader.connected:
                try:
                    ib_holding = self.ib_trader.get_holding_for_symbol(signal['symbol'])
                    if ib_holding and 'avg_cost' in ib_holding:
                        avg_cost = ib_holding['avg_cost']
                except Exception as e:
                    logger.info(f"获取IB持仓成本失败: {e}")

            trade['position_avg_cost'] = avg_cost
        
        try:
            # 清仓时或非交易时间强制使用市价单
            if signal.get('force_market_order', False) or force_market_order or self.force_market_orders:
                order_type = 'MKT'
                if force_market_order or self.force_market_orders:
                    logger.info(f"🔄 非交易时间，强制使用市价单: {signal['symbol']} {signal['action']} {signal['position_size']} 股")
                else:
                    logger.info(f"🔄 清仓订单，强制使用市价单: {signal['symbol']} {signal['action']} {signal['position_size']} 股")
            else:
                order_type = self.config.get('ib_order_type', 'MKT')

            logger.info(f"order_type: {order_type} -- action: {signal['action']} current_price: {current_price} position_size: {signal['position_size']}")

            if order_type == 'LMT' and signal['action'] == 'BUY':
                limit_price = current_price * (1 - self.config.get('ib_limit_offset', 0.01))
                logger.info(f"BUY {signal['symbol']} {signal['position_size']} 股，限价 {limit_price}--current_price {current_price}")
                ib_trade = self.ib_trader.place_buy_order(
                    signal['symbol'], signal['position_size'], 'LMT', current_price
                )
            elif order_type == 'LMT' and signal['action'] == 'SELL':
                limit_price = current_price * (1 + self.config.get('ib_limit_offset', 0.01))

                ib_trade = self.ib_trader.place_sell_order(
                    signal['symbol'], signal['position_size'], 'LMT', current_price
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
                    logger.info(f"⚠️  订单状态异常或待处理 - ID: {trade.get('order_id')}, 状态: {ib_status_str}")

                return trade
            else:
                logger.info(f"DEBUG: 模拟交易模式 - 更新本地持仓，信号: {signal['symbol']} {signal['action']} {signal['position_size']}")

                if signal['action'] == 'BUY':
                    # 买入操作：增加持仓
                    if signal['symbol'] in self.positions:
                        old_pos = self.positions[signal['symbol']]
                        old_size = int(old_pos.get('size', 0))
                        new_size = old_size + int(signal['position_size'])
                        # 计算新的平均成本
                        old_cost_total = old_size * old_pos.get('avg_cost', current_price)
                        new_cost_total = old_cost_total + int(signal['position_size']) * current_price
                        new_avg_cost = new_cost_total / new_size
                        self.positions[signal['symbol']] = {
                            'size': new_size,
                            'avg_cost': new_avg_cost,
                            'entry_time': old_pos.get('entry_time', datetime.now())
                        }
                        logger.info(f"DEBUG: 买入 - 原持仓: {old_size}股，新增: {signal['position_size']}股，总计: {new_size}股，平均成本: ${new_avg_cost:.2f}")
                    else:
                        # 新建持仓
                        self.positions[signal['symbol']] = {
                            'size': int(signal['position_size']),
                            'avg_cost': current_price,
                            'entry_time': datetime.now()
                        }
                        logger.info(f"DEBUG: 新建持仓 - {signal['symbol']}: {signal['position_size']}股 @ ${current_price:.2f}")

                elif signal['action'] == 'SELL':
                    # 卖出操作：减少持仓
                    if signal['symbol'] in self.positions:
                        old_pos = self.positions[signal['symbol']]
                        old_size = int(old_pos.get('size', 0))
                        logger.info(f"DEBUG: 原持仓: {old_size}股")
                        remaining = max(0, old_size - int(signal['position_size']))
                        logger.info(f"DEBUG: 卖出后剩余: {remaining}股")
                        if remaining > 0:
                            self.positions[signal['symbol']] = {
                                'size': remaining,
                                'avg_cost': old_pos.get('avg_cost', current_price),
                                'entry_time': old_pos.get('entry_time', datetime.now())
                            }
                        else:
                            logger.info(f"DEBUG: 持仓清空，删除 {signal['symbol']}")
                            del self.positions[signal['symbol']]
                    else:
                        logger.warning(f"DEBUG: 模拟模式卖出时无持仓记录: {signal['symbol']}")
                else:
                    logger.warning(f"DEBUG: 未知操作类型: {signal['action']}")

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
        finally:
            # 保存交易记录到文件 (供 Dashboard 使用)
            try:
                import json
                import os
                
                # 确保 data 目录存在
                data_dir = os.path.join(os.getcwd(), 'data')
                if not os.path.exists(data_dir):
                    os.makedirs(data_dir)
                    
                file_path = os.path.join(data_dir, 'trades.json')
                
                # 读取现有记录
                existing_trades = []
                if os.path.exists(file_path):
                    with open(file_path, 'r') as f:
                        try:
                            existing_trades = json.load(f)
                        except:
                            pass
                
                # 转换 datetime 为字符串
                trade_record = trade.copy()
                if isinstance(trade_record.get('timestamp'), datetime):
                    trade_record['timestamp'] = trade_record['timestamp'].isoformat()
                
                existing_trades.append(trade_record)
                
                # 写入文件
                with open(file_path, 'w') as f:
                    json.dump(existing_trades[-100:], f, indent=2) # 只保留最近100条
            except Exception as e:
                logger.error(f"保存交易记录失败: {e}")
    
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
        
        # 首先检查所有现有持仓的退出条件（即使不在当前扫描列表中）
        if self.positions:
            logger.info(f"📊 检查 {len(self.positions)} 个现有持仓的退出条件...")
            for symbol in list(self.positions.keys()):
                try:
                    # 获取当前价格数据
                    df = data_provider.get_intraday_data(symbol, interval='5m', lookback=50)
                    if df.empty or len(df) < 5:
                        # 如果无法获取数据，尝试使用IB获取价格
                        if self.ib_trader and self.ib_trader.connected:
                            try:
                                contract = self.ib_trader.get_contract(symbol)
                                ticker = self.ib_trader.ib.reqMktData(contract, '', False, False)
                                self.ib_trader.ib.sleep(0.3)
                                current_price = ticker.last if ticker.last > 0 else ticker.close
                                self.ib_trader.ib.cancelMktData(contract)
                                
                                if current_price > 0:
                                    exit_signal = self.check_exit_conditions(symbol, current_price)
                                    if exit_signal:
                                        if symbol not in all_signals:
                                            all_signals[symbol] = []
                                        all_signals[symbol].append(exit_signal)
                                        logger.info(f"  ✅ {symbol} 触发退出条件: {exit_signal.get('reason', '')}")
                            except Exception as e:
                                logger.info(f"  无法获取 {symbol} 实时价格: {e}")
                        continue
                    
                    current_price = df['Close'].iloc[-1]
                    exit_signal = self.check_exit_conditions(symbol, current_price)
                    if exit_signal:
                        if symbol not in all_signals:
                            all_signals[symbol] = []
                        all_signals[symbol].append(exit_signal)
                        logger.info(f"  ✅ {symbol} 触发退出条件: {exit_signal.get('reason', '')} (价格: ${current_price:.2f})")
                except Exception as e:
                    logger.warning(f"检查 {symbol} 退出条件时出错: {e}")
                    continue
        
        # 然后处理扫描列表中的标的
        for symbol in symbols:
            try:
                # 增加数据回溯以支持长期均线 (如MA200)
                df = data_provider.get_intraday_data(symbol, interval='5m', lookback=300)
                
                if df.empty or len(df) < 30:
                    logger.info(f"跳过 {symbol}，数据不足")
                    continue
                
                indicators = data_provider.get_technical_indicators(symbol, '1d', '5m')
                
                signals = self.generate_signals(symbol, df, indicators)
                
                if signals:
                    if symbol not in all_signals:
                        all_signals[symbol] = []
                    all_signals[symbol].extend(signals)
                    logger.info(f"  {symbol} 生成 {len(signals)} 个信号")
                    
                    # 执行信号
                    for signal in signals:
                        # 使用信号中的价格，确保与仓位计算时价格一致
                        current_price = signal.get('price', df['Close'].iloc[-1])
                        try:
                            result = self.execute_signal(signal, current_price, self.force_market_orders)
                            logger.info(f"  信号执行结果: {result}")
                        except Exception as e:
                            logger.error(f"  执行信号时出错: {e}")
                            continue
                        
            except Exception as e:
                logger.error(f"分析 {symbol} 时出错: {e}")
                import traceback
                logger.info(traceback.format_exc())
                continue
        
        return all_signals
    
    def close_all_positions(self, reason: str = "收盘前清仓") -> List[Dict]:
        """
        清仓所有持仓
        
        Args:
            reason: 清仓原因
            
        Returns:
            清仓信号列表
        """
        close_signals = []
        
        if not self.ib_trader:
            logger.warning("IB接口未初始化，无法清仓")
            return close_signals
        
        # 从IB同步最新持仓
        self.sync_positions_from_ib()
        
        if not self.positions:
            logger.info(f"当前无持仓，无需清仓")
            return close_signals
        
        logger.info(f"🔄 开始清仓所有持仓 ({reason})，共 {len(self.positions)} 个持仓")
        
        # 获取当前价格并生成卖出信号
        for symbol, position_info in list(self.positions.items()):
            try:
                position_size = position_info.get('size', 0)
                if position_size == 0:
                    continue
                
                # 获取当前价格 - 优先使用平均成本，清仓时使用市价单不需要精确价格
                current_price = position_info.get('avg_cost', 0)
                
                # 如果平均成本无效，尝试从IB获取价格
                if current_price <= 0:
                    try:
                        if hasattr(self.ib_trader, 'ib') and self.ib_trader.connected:
                            contract = self.ib_trader.get_contract(symbol)
                            ticker = self.ib_trader.ib.reqMktData(contract, '', False, False)
                            self.ib_trader.ib.sleep(0.5)  # 等待价格更新
                            current_price = ticker.last if ticker.last > 0 else ticker.close
                            self.ib_trader.ib.cancelMktData(contract)
                    except Exception as e:
                        logger.warning(f"无法获取 {symbol} 实时价格: {e}，将使用市价单")
                        current_price = 1.0  # 使用占位价格，实际会以市价执行
                
                if current_price <= 0:
                    logger.warning(f"{symbol} 价格无效，使用市价单清仓")
                    current_price = 1.0  # 占位价格
                
                # 生成卖出信号 - 清仓时强制使用市价单
                action = 'SELL' if position_size > 0 else 'BUY'  # 空头用BUY平仓
                signal = {
                    'symbol': symbol,
                    'signal_type': 'CLOSE_ALL_POSITIONS',
                    'action': action,
                    'price': current_price,
                    'quantity': abs(position_size),
                    'position_size': abs(position_size),
                    'confidence': 1.0,
                    'reason': reason,
                    'timestamp': datetime.now(),
                    'force_market_order': True  # 标记为强制市价单
                }
                
                close_signals.append(signal)
                
                logger.info(
                    f"  📤 生成清仓信号: {symbol} {action} {abs(position_size)} 股 @ ${current_price:.2f}"
                )
                
            except Exception as e:
                logger.error(f"生成 {symbol} 清仓信号时出错: {e}")
                continue
        
        # 执行清仓信号
        executed_count = 0
        for signal in close_signals:
            try:
                result = self.execute_signal(signal, signal['price'])
                if result.get('status') in ['EXECUTED', 'PENDING']:
                    executed_count += 1
                    logger.info(f"  ✅ {signal['symbol']} 清仓订单已提交")
                else:
                    logger.warning(f"  ⚠️ {signal['symbol']} 清仓订单提交失败: {result.get('reason', '未知原因')}")
            except Exception as e:
                logger.error(f"执行 {signal['symbol']} 清仓信号时出错: {e}")
        
        logger.info(f"✅ 清仓完成: 共 {len(close_signals)} 个持仓，已提交 {executed_count} 个清仓订单")
        
        return close_signals
    
    def generate_report(self) -> Dict:
        """生成交易报告"""
        total_trades = len(self.trade_history)

        self.sync_positions_from_ib()

        # 计算性能统计
        winning_trades = sum(1 for trade in self.trade_history if trade.get('status') == 'EXECUTED' and trade.get('profit_pct', 0) > 0)
        losing_trades = sum(1 for trade in self.trade_history if trade.get('status') == 'EXECUTED' and trade.get('profit_pct', 0) < 0)
        win_rate = (winning_trades / max(total_trades, 1)) * 100

        # 计算平均持有时间
        holding_times = []
        for trade in self.trade_history:
            if trade.get('status') == 'EXECUTED':
                # 这里可以计算实际持有时间，暂时使用配置的默认值
                holding_times.append(self.config.get('max_holding_minutes', 60))

        avg_holding_time = sum(holding_times) / max(len(holding_times), 1)

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
            # 性能统计
            'win_rate': win_rate,
            'winning_trades': winning_trades,
            'losing_trades': losing_trades,
            'avg_holding_time_minutes': avg_holding_time,
            'runtime_minutes': (datetime.now() - self.start_time).total_seconds() / 60,
        }

        logger.info(f"📋 {self.get_strategy_name()} 报告 - 净资产: ${self.equity:,.2f}, "
                   f"总交易: {total_trades}, 胜率: {win_rate:.1f}%, 持仓: {len(self.positions)}")
        logger.info(f"📊 性能统计 - 盈利交易: {winning_trades}, 亏损交易: {losing_trades}, "
                   f"平均持有时间: {avg_holding_time:.1f}分钟, 运行时间: {report['runtime_minutes']:.1f}分钟")

        return report
