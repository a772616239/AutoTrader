from ib_insync import *
import yfinance as yf
from typing import Optional, Union, Dict, Any
import time

# ----------------- 价格查询函数 (免费外部数据源) -----------------

def get_external_price(symbol: str) -> Dict[str, Any]:
    """
    使用 yfinance (免费第三方，延迟数据) 获取最新的收盘价。
    
    Args:
        symbol (str): 股票代码 (如 'AAPL')。
        
    Returns:
        Dict[str, Any]: 包含价格信息的字典，如果失败则返回空字典。
    """
    try:
        # 获取股票对象
        ticker = yf.Ticker(symbol)
        
        # 获取最新的日线数据，通常包含昨收盘价
        current_data = ticker.history(period="1d")
        
        if current_data.empty:
             print(f"❌ 外部数据源未找到 {symbol} 的数据。")
             return {}
             
        # yfinance 只能提供收盘价 (Last Price)，无法提供实时 Bid/Ask
        last_price = current_data['Close'].iloc[-1]
        
        print(f"✅ 成功从 Yahoo Finance 获取 {symbol} 价格 (延迟收盘价)")
        return {
            'Symbol': symbol, 
            'Last': last_price, 
            'Bid': float('nan'), # 外部数据源无法提供 Bid/Ask
            'Ask': float('nan'), # 外部数据源无法提供 Bid/Ask
            'DataType': "Delayed (Yahoo Finance)"
        }
    except Exception as e:
        print(f"❌ 使用 yfinance 获取 {symbol} 价格失败: {e}")
        return {}


# ----------------- 交易函数封装 (使用 ib_insync) -----------------

def get_contract(ib: IB, symbol: str) -> Stock:
    """
    根据股票代码创建并鉴定合约。
    """
    contract = Stock(symbol, 'SMART', 'USD')
    # 必须使用 ib 实例来鉴定合约
    ib.qualifyContracts(contract) 
    return contract

def place_order(
    ib: IB, 
    symbol: str, 
    action: str, 
    quantity: float, 
    order_type: str = 'MKT', 
    price: Optional[float] = None
) -> Optional[Trade]:
    """
    通用订单提交函数。
    """
    if not ib.isConnected():
        print("错误：IB 连接未建立。请先连接。")
        return None
        
    try:
        contract = get_contract(ib, symbol) 
        
        if order_type == 'LMT' and price is not None:
            # 限价单：LimitOrder('BUY'/'SELL', quantity, limitPrice)
            order = LimitOrder(action, quantity, price)
        elif order_type == 'MKT':
            # 市价单：MarketOrder('BUY'/'SELL', quantity)
            order = MarketOrder(action, quantity)
        else:
            print(f"不支持的订单类型或缺少价格参数：{order_type}")
            return None

        print(f"-> 正在提交订单: {action} {quantity} 股 {symbol} ({order_type} @ {price if price else 'N/A'})...")
        
        trade = ib.placeOrder(contract, order)
        
        # 等待订单状态更新
        ib.sleep(1)
        
        print(f"-> 订单提交成功。ID: {trade.order.orderId}, 当前状态: {trade.orderStatus.status}")
        
        return trade
        
    except Exception as e:
        # 捕获资金不足等错误 (如 Error 201)，并打印
        print(f"-> 提交订单时发生错误: {e}")
        return None

def place_buy_order(ib: IB, symbol: str, quantity: float, order_type: str = 'MKT', price: Optional[float] = None) -> Optional[Trade]:
    """封装的买入订单函数。"""
    return place_order(ib, symbol, 'BUY', quantity, order_type, price)

def place_sell_order(ib: IB, symbol: str, quantity: float, order_type: str = 'MKT', price: Optional[float] = None) -> Optional[Trade]:
    """封装的卖出订单函数。"""
    return place_order(ib, symbol, 'SELL', quantity, order_type, price)


# ----------------- 主程序入口 -----------------

if __name__ == '__main__':
    ib = IB()
    
    # 连接模拟账户
    try:
        # 使用模拟账户端口 7497 或 4002
        ib.connect('127.0.0.1', 7497, clientId=1)
        print("🚀 成功连接到盈透证券模拟账户。")
    except ConnectionRefusedError:
        print("❌ 连接失败。请检查 TWS/Gateway 是否运行并登录模拟账户，端口是否为 7497。")
        exit()

    # --- 步骤 1: 使用免费数据源查看价格 ---
    print("\n" + "="*40)
    print("      市场数据查询 (免费外部源)")
    print("="*40)
    
    aapl_data = get_external_price('MSFT')
    if aapl_data:
        print(f"标的: {aapl_data['Symbol']}")
        print(f"最新收盘价 (延迟): {aapl_data['Last']:.2f}")

    # --- 步骤 2: 提交交易订单 ---
    print("\n" + "="*40)
    print("          交易订单提交 (IBKR)")
    print("="*40)
    
    # 示例 A: 市价买入 1 股 MSFT (最小测试单位)
    print("\n--- 示例 A: 市价买入 1 股 MSFT ---")
    # 建议使用小数量 1 股进行测试，以防模拟账户资金不足
    buy_trade_mkt = place_buy_order(ib, 'MSFT', 1) 
    ib.sleep(3) # 等待执行结果
    
    if buy_trade_mkt:
        print(f"最终订单状态: {buy_trade_mkt.orderStatus.status}")

    # 示例 B: 限价卖出 1 股 GOOG (假设你持有，并设置一个限价)
    print("\n--- 示例 B: 限价卖出 1 股 GOOG (LMT) ---")
    # ⚠️ 注意：这里的价格是硬编码的，你需要根据当前股价设置合理的限价
    sell_price = round(float(aapl_data['Last']), 2)
    sell_trade_lmt = place_sell_order(ib, 'MSFT', 10, 'LMT', price=sell_price)
    ib.sleep(3) 

    if sell_trade_lmt:
        print(f"最终订单状态: {sell_trade_lmt.orderStatus.status}")

    
    # 断开连接
    ib.disconnect()
    print("\n👋 任务完成，已断开连接。")