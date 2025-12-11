# from ib_insync import *
# from typing import Optional, Union, List, Dict

# # ----------------- 交易函数封装 (修改版) -----------------

# def get_contract(ib: IB, symbol: str) -> Stock:
#     """
#     根据股票代码创建并鉴定合约。
#     需要传入已连接的 IB 实例。
#     """
#     contract = Stock(symbol, 'SMART', 'USD')
#     # 使用传入的 IB 实例进行合约鉴定
#     ib.qualifyContracts(contract) 
#     return contract

# def place_order(
#     ib: IB,  # <-- 新增：传入已连接的 IB 实例
#     symbol: str, 
#     action: str, 
#     quantity: float, 
#     order_type: str = 'MKT', 
#     price: Optional[float] = None
# ) -> Optional[Trade]:
#     """
#     通用订单提交函数。
#     """
#     if not ib.isConnected():
#         print("错误：IB 连接未建立。请先连接。")
#         return None
        
#     try:
#         # 使用传入的 IB 实例进行合约鉴定
#         contract = get_contract(ib, symbol) 
        
#         if order_type == 'LMT' and price is not None:
#             order = LimitOrder(action, quantity, price)
#         elif order_type == 'MKT':
#             order = MarketOrder(action, quantity)
#         else:
#             print(f"不支持的订单类型或缺少价格参数：{order_type}")
#             return None

#         print(f"正在提交订单: {action} {quantity} 股 {symbol} ({order_type} @ {price if price else 'N/A'})...")
        
#         # 使用传入的 IB 实例提交订单
#         trade = ib.placeOrder(contract, order)
        
#         # 等待订单状态更新 (非阻塞等待)
#         ib.sleep(1)
        
#         print(f"订单提交成功。ID: {trade.order.orderId}, 当前状态: {trade.orderStatus.status}")
        
#         return trade
        
#     except Exception as e:
#         # 捕获资金不足等错误，并打印
#         print(f"提交订单时发生错误: {e}")
#         return None

# def place_buy_order(ib: IB, symbol: str, quantity: float, order_type: str = 'MKT', price: Optional[float] = None) -> Optional[Trade]:
#     """
#     封装的买入订单函数。
#     """
#     return place_order(ib, symbol, 'BUY', quantity, order_type, price)

# def place_sell_order(ib: IB, symbol: str, quantity: float, order_type: str = 'MKT', price: Optional[float] = None) -> Optional[Trade]:
#     """
#     封装的卖出订单函数。
#     """
#     return place_order(ib, symbol, 'SELL', quantity, order_type, price)

# def get_holdings(ib: IB, symbol: Optional[str] = None) -> List[Position]:
#     """
#     获取持仓信息。
    
#     参数:
#         ib: 已连接的 IB 实例
#         symbol: 可选，指定要查看的股票代码。如果为None，则返回所有持仓
    
#     返回:
#         持仓列表
#     """
#     if not ib.isConnected():
#         print("错误：IB 连接未建立。请先连接。")
#         return []
    
#     try:
#         # 获取所有持仓
#         positions = ib.positions()
        
#         if symbol:
#             # 如果指定了股票代码，筛选对应持仓
#             filtered_positions = []
#             for pos in positions:
#                 # 检查合约是否是股票，并且代码匹配
#                 if pos.contract.secType == 'STK' and pos.contract.symbol == symbol:
#                     filtered_positions.append(pos)
#             return filtered_positions
#         else:
#             return positions
            
#     except Exception as e:
#         print(f"获取持仓时发生错误: {e}")
#         return []

# def print_holdings(ib: IB, symbol: Optional[str] = None):
#     """
#     打印持仓信息。
    
#     参数:
#         ib: 已连接的 IB 实例
#         symbol: 可选，指定要查看的股票代码。如果为None，则打印所有持仓
#     """
#     positions = get_holdings(ib, symbol)
    
#     if not positions:
#         if symbol:
#             print(f"没有找到 {symbol} 的持仓。")
#         else:
#             print("当前没有任何持仓。")
#         return
    
#     print("\n" + "="*60)
#     print("当前持仓信息:")
#     print("="*60)
    
#     for pos in positions:
#         contract = pos.contract
#         print(f"合约: {contract.symbol} ({contract.secType})")
#         print(f"  数量: {pos.position}")
#         print(f"  平均成本: {pos.avgCost:.2f} {contract.currency}")
#         print(f"  合约详情: {contract.exchange}, {contract.currency}")
#         print("-" * 40)

# def get_account_summary(ib: IB):
#     """
#     获取账户摘要信息。
#     """
#     if not ib.isConnected():
#         print("错误：IB 连接未建立。请先连接。")
#         return
    
#     try:
#         # 请求账户摘要
#         account = ib.accountSummary()
        
#         print("\n" + "="*60)
#         print("账户摘要:")
#         print("="*60)
        
#         # 按类别分组显示
#         categories = {}
#         for item in account:
#             category = item.tag
#             if category not in categories:
#                 categories[category] = []
#             categories[category].append(item)
        
#         for category, items in categories.items():
#             print(f"\n{category}:")
#             for item in items:
#                 print(f"  {item.tag}: {item.value} {item.currency}")
                
#     except Exception as e:
#         print(f"获取账户摘要时发生错误: {e}")

# # ----------------- 主程序示例 (添加持仓查看) -----------------
# # ----------------- 主程序示例 (调用方式修改) -----------------

# if __name__ == '__main__':
#     ib = IB()
    
#     try:
       
#         ib.connect('127.0.0.1', 7496, clientId=1)
#         print("成功连接到盈透证券模拟账户。")
#     except ConnectionRefusedError:
#         print("连接失败。请检查 TWS/Gateway 是否运行并登录，端口是否为 7496。")
#         exit()
    
#     # --- 查看当前所有持仓 ---
#     print("\n--- 查看当前所有持仓 ---")
#     print_holdings(ib)
    
#     # --- 查看账户摘要 ---
#     get_account_summary(ib)
    
#     # --- 示例 1: 市价买入 5 股 ---
#     print("\n--- 示例 1: 市价买入 (MKT) ---")
#     buy_trade_mkt = place_buy_order(ib, 'TSLA', 50)
    
#     ib.sleep(3)
#     if buy_trade_mkt:
#         print(f"市价买入最终状态: {buy_trade_mkt.orderStatus.status}")
        
#         # 查看 MSFT 持仓
#         print("\n--- 查看 MSFT 持仓 ---")
#         print_holdings(ib, 'MSFT')
    
#     # --- 示例 2: 限价卖出 10 股 ---
#     print("\n--- 示例 2: 限价卖出 (LMT) ---")
#     sell_trade_lmt = place_sell_order(ib, 'TSLA', 1, 'LMT', price=100.00)
    
#     ib.sleep(3)
#     if sell_trade_lmt:
#         print(f"限价卖出最终状态: {sell_trade_lmt.orderStatus.status}")
        
#         # 再次查看所有持仓
#         print("\n--- 查看更新后的所有持仓 ---")
#         print_holdings(ib)
    
#     # 断开连接
#     ib.disconnect()
#     print("\n已断开连接。")