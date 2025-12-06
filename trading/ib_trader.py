#!/usr/bin/env python3
"""
IB交易接口封装
"""
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any, Tuple
from ib_insync import *

logger = logging.getLogger(__name__)

class IBTrader:
    """IB交易接口封装"""
    
    def __init__(self, host='127.0.0.1', port=7497, client_id=1):
        self.host = host
        self.port = port
        self.client_id = client_id
        self.ib = IB()
        self.connected = False
        self.max_retries = 3
        
        logger.info(f"IB交易接口初始化: {host}:{port} (clientId={client_id})")
    
    def connect(self) -> bool:
        """连接IB"""
        if self.connected:
            return True
            
        for attempt in range(self.max_retries):
            try:
                logger.info(f"尝试连接IB [尝试 {attempt+1}/{self.max_retries}]")
                self.ib.connect(self.host, self.port, clientId=self.client_id)
                
                if self.ib.isConnected():
                    self.connected = True
                    logger.info("✅ IB连接成功")
                    return True
                else:
                    logger.warning(f"IB连接状态检查失败，重试中...")
                    time.sleep(2)
                    
            except Exception as e:
                logger.error(f"连接IB失败: {e}")
                if attempt < self.max_retries - 1:
                    time.sleep(3 * (attempt + 1))
                else:
                    logger.error("❌ 所有重试失败，无法连接IB")
                    return False
        
        return False
    
    def disconnect(self):
        """断开IB连接"""
        if self.connected:
            try:
                self.ib.disconnect()
                self.connected = False
                logger.info("IB连接已断开")
            except Exception as e:
                logger.error(f"断开IB连接时出错: {e}")
    
    def get_contract(self, symbol: str) -> Stock:
        """
        根据股票代码创建并鉴定合约
        """
        try:
            contract = Stock(symbol, 'SMART', 'USD')
            self.ib.qualifyContracts(contract)
            logger.info(f"✅ 合约鉴定成功: {symbol}")
            return contract
        except Exception as e:
            logger.error(f"合约鉴定失败 {symbol}: {e}")
            raise
    
    def place_order(self, symbol: str, action: str, quantity: float, 
                   order_type: str = 'MKT', price: Optional[float] = None) -> Optional[Trade]:
        """
        通用订单提交函数
        """
        if not self.connected and not self.connect():
            logger.error("IB未连接，无法提交订单")
            return None
        
        try:
            contract = self.get_contract(symbol)
            
            if order_type == 'LMT' and price is not None:
                # 规范限价到合理的 tick（以美股为例，使用到分位精度）
                try:
                    orig_price = float(price)
                    norm_price = round(orig_price, 2)
                    if norm_price != orig_price:
                        logger.debug(f"规范限价: {orig_price} -> {norm_price}")
                    price = norm_price
                except Exception:
                    price = float(price)
                order = LimitOrder(action, quantity, price)
            elif order_type == 'MKT':
                order = MarketOrder(action, quantity)
            else:
                logger.error(f"不支持的订单类型或缺少价格参数: {order_type}")
                return None
            
            logger.info(f"提交订单: {action} {quantity} 股 {symbol} "
                       f"({order_type} @ {price if price else '市价'})")
            
            trade = self.ib.placeOrder(contract, order)

            # 等待并轮询订单状态，给 TWS 一点时间处理（有时初始为 PendingSubmit）
            max_wait_seconds = 10
            waited = 0
            status_str = None
            while waited < max_wait_seconds:
                self.ib.sleep(1)
                waited += 1
                status = getattr(trade, 'orderStatus', None)
                status_str = getattr(status, 'status', None) if status else None
                # 记录 trade.log 中的条目以便诊断（例如 Warning 110）
                try:
                    if getattr(trade, 'log', None):
                        for entry in trade.log:
                            logger.debug(f"order log: time={getattr(entry,'time',None)} status={getattr(entry,'status',None)} message={getattr(entry,'message',None)} errorCode={getattr(entry,'errorCode',None)}")
                except Exception:
                    pass

                if status_str in ['Filled', 'Submitted', 'PreSubmitted']:
                    logger.info(f"✅ 订单提交成功 - ID: {getattr(getattr(trade,'order',None),'orderId',None)}, 状态: {status_str}")
                    break
                # 立即检测到被取消的情况，提前退出
                if status_str in ['Cancelled', 'Inactive']:
                    logger.warning(f"⚠️  订单被取消 - ID: {getattr(getattr(trade,'order',None),'orderId',None)}, 状态: {status_str}")
                    break

            # 最终状态处理
            if status_str in ['Filled', 'Submitted', 'PreSubmitted']:
                return trade
            else:
                logger.warning(f"⚠️  订单状态异常 - ID: {getattr(getattr(trade,'order',None),'orderId',None)}, 状态: {status_str}")
                return trade
                
        except Exception as e:
            logger.error(f"提交订单失败 {symbol}: {e}")
            return None
    
    def place_buy_order(self, symbol: str, quantity: float, 
                       order_type: str = 'MKT', price: Optional[float] = None) -> Optional[Trade]:
        """封装的买入订单函数"""
        return self.place_order(symbol, 'BUY', quantity, order_type, price)
    
    def place_sell_order(self, symbol: str, quantity: float,
                        order_type: str = 'MKT', price: Optional[float] = None) -> Optional[Trade]:
        """封装的卖出订单函数"""
        return self.place_order(symbol, 'SELL', quantity, order_type, price)
    
    def get_holdings(self, symbol: Optional[str] = None) -> List[Position]:
        """
        获取持仓信息
        """
        if not self.connected and not self.connect():
            logger.error("IB未连接，无法获取持仓")
            return []
        
        try:
            positions = self.ib.positions()
            
            if symbol:
                filtered_positions = []
                for pos in positions:
                    if hasattr(pos.contract, 'secType') and pos.contract.secType == 'STK':
                        if hasattr(pos.contract, 'symbol') and pos.contract.symbol == symbol:
                            filtered_positions.append(pos)
                return filtered_positions
            else:
                stock_positions = []
                for pos in positions:
                    if hasattr(pos.contract, 'secType') and pos.contract.secType == 'STK':
                        stock_positions.append(pos)
                return stock_positions
                
        except Exception as e:
            logger.error(f"获取持仓时发生错误: {e}")
            return []
    
    def get_holding_for_symbol(self, symbol: str) -> Optional[Dict]:
        """
        获取指定符号的持仓详情
        """
        holdings = self.get_holdings(symbol)
        
        if holdings:
            pos = holdings[0]
            return {
                'symbol': symbol,
                'position': pos.position,
                'avg_cost': pos.avgCost,
                'contract': pos.contract
            }
        return None
    
    def get_account_summary(self) -> Dict:
        """
        获取账户摘要信息
        """
        if not self.connected and not self.connect():
            logger.error("IB未连接，无法获取账户摘要")
            return {}
        
        try:
            account_summary = {}
            summary_items = self.ib.accountSummary()
            
            for item in summary_items:
                account_summary[item.tag] = {
                    'value': item.value,
                    'currency': item.currency,
                    'account': item.account
                }
            
            logger.info(f"获取账户摘要成功，共 {len(account_summary)} 项")
            return account_summary
            
        except Exception as e:
            logger.error(f"获取账户摘要时发生错误: {e}")
            return {}
    
    def get_account_value(self, tag: str = 'NetLiquidation') -> float:
        """
        获取账户净值
        """
        summary = self.get_account_summary()
        
        if tag in summary:
            try:
                value = float(summary[tag]['value'])
                logger.info(f"账户{tag}: {value:,.2f} {summary[tag]['currency']}")
                return value
            except:
                logger.error(f"无法解析账户{tag}值: {summary[tag]['value']}")
        
        logger.warning(f"未找到账户字段: {tag}")
        return 0.0
    
    def get_available_funds(self) -> float:
        """获取可用资金"""
        return self.get_account_value('AvailableFunds')
    
    def get_net_liquidation(self) -> float:
        """获取净资产"""
        return self.get_account_value('NetLiquidation')
    
    def print_holdings(self, symbol: Optional[str] = None):
        """打印持仓信息"""
        positions = self.get_holdings(symbol)
        
        if not positions:
            if symbol:
                logger.info(f"没有找到 {symbol} 的持仓")
            else:
                logger.info("当前没有任何股票持仓")
            return
        
        logger.info("\n" + "="*60)
        logger.info("当前持仓信息:")
        logger.info("="*60)
        
        for pos in positions:
            contract = pos.contract
            logger.info(f"合约: {contract.symbol} ({contract.secType})")
            logger.info(f"  数量: {pos.position}")
            logger.info(f"  平均成本: {pos.avgCost:.2f} {contract.currency}")
            if hasattr(contract, 'exchange'):
                logger.info(f"  交易所: {contract.exchange}")
            logger.info("-" * 40)

    def get_open_orders(self, symbol: Optional[str] = None) -> List[Dict]:
        """获取未完成订单列表"""
        if not self.connected and not self.connect():
            logger.error("IB未连接，无法获取未完成订单")
            return []
        try:
            trades = self.ib.openTrades()
            results: List[Dict] = []
            for t in trades:
                c = t.contract
                if hasattr(c, 'secType') and c.secType == 'STK':
                    if symbol and getattr(c, 'symbol', None) != symbol:
                        continue
                    o = t.order
                    s = t.orderStatus
                    results.append({
                        'symbol': getattr(c, 'symbol', ''),
                        'action': getattr(o, 'action', ''),
                        'quantity': int(getattr(o, 'totalQuantity', 0) or 0),
                        'order_type': getattr(o, 'orderType', ''),
                        'limit_price': getattr(o, 'lmtPrice', None),
                        'order_id': getattr(o, 'orderId', None),
                        'status': getattr(s, 'status', ''),
                        'remaining': int(getattr(s, 'remaining', 0) or 0),
                    })
            return results
        except Exception as e:
            logger.error(f"获取未完成订单时发生错误: {e}")
            return []

    def has_active_order(self, symbol: str, action: str, quantity: int,
                         price: Optional[float] = None, tolerance: float = 0.02) -> bool:
        """检查是否存在相同方向的未完成订单"""
        orders = self.get_open_orders(symbol)
        for o in orders:
            if o.get('action') != action:
                continue
            qty_match = abs(int(o.get('quantity', 0)) - int(quantity)) <= max(1, int(quantity * tolerance))
            price_match = True
            lp = o.get('limit_price')
            if price is not None and lp is not None and price > 0:
                price_match = abs(lp - price) <= price * tolerance
            if qty_match and price_match:
                logger.info(f"检测到未完成订单重复: {symbol} {action} 数量{quantity} 订单ID {o.get('order_id')}")
                return True
        return False

    def cancel_open_orders(self, symbol: Optional[str] = None) -> int:
        """取消当前未完成订单，支持按标的过滤"""
        if not self.connected and not self.connect():
            logger.error("IB未连接，无法取消订单")
            return 0
        try:
            trades = self.ib.openTrades()
            count = 0
            for t in trades:
                c = t.contract
                if hasattr(c, 'secType') and c.secType == 'STK':
                    if symbol and getattr(c, 'symbol', None) != symbol:
                        continue
                    s = t.orderStatus
                    if getattr(s, 'status', '') in ['Filled', 'Cancelled']:  # 已完成或已取消跳过
                        continue
                    self.ib.cancelOrder(t.order)
                    count += 1
            if count > 0:
                logger.info(f"已取消 {count} 个未完成订单{(' (仅 '+symbol+')' if symbol else '')}")
            else:
                logger.info("当前无需取消的未完成订单")
            return count
        except Exception as e:
            logger.error(f"取消未完成订单时发生错误: {e}")
            return 0

    def cancel_all_orders_global(self) -> None:
        """向 TWS 发送全局取消请求（若可用）"""
        if not self.connected and not self.connect():
            logger.error("IB未连接，无法全局取消订单")
            return
        try:
            # 某些配置下可能不支持全局取消，故尝试并忽略异常
            if hasattr(self.ib, 'reqGlobalCancel'):
                self.ib.reqGlobalCancel()
                logger.info("已发送全局取消请求")
            else:
                # 退化为逐个取消
                self.cancel_open_orders()
        except Exception as e:
            logger.warning(f"全局取消失败，退化为逐个取消: {e}")
            self.cancel_open_orders()
