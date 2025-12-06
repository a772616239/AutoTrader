import schedule
import time
from strategy_engine import ShortTermStrategyEngine
import requests
from llm_optimized_data import LLMDataFormatter
from datetime import datetime

def fetch_market_data(symbols):
    """从你的增强数据服务器获取数据"""
    all_data = {}
    for symbol in symbols:
        try:
            response = requests.get(f"http://localhost:8001/enhanced-data?symbol={symbol}&period=1d&interval=5m", timeout=5)
            all_data[symbol] = response.json()
        except Exception as e:
            print(f"获取{symbol}数据失败: {e}")
    return all_data

def trading_job():
    """定时执行的任务"""
    symbols_to_trade = ['AAPL', 'MSFT', 'GOOGL']  # 你的关注列表
    
    print(f"\n{'='*50}")
    print(f"执行定时扫描: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    print('='*50)
    
    # 1. 获取数据
    market_data = fetch_market_data(symbols_to_trade)
    
    # 2. 初始化策略引擎
    engine = ShortTermStrategyEngine(initial_capital=100000)
    
    # 3. 对每个标的运行策略
    for symbol, data in market_data.items():
        if 'error' in data:
            continue
        # 这里可以添加更多判断，如流动性、波动率过滤
        engine.run_daily_simulation(symbol, time.strftime('%Y-%m-%d'))
    
    # 4. (可选) 生成LLM分析报告
    generate_llm_report(market_data)

def generate_llm_report(market_data):
    """利用现有工具生成LLM可读的盘后分析"""

    
    analysis = "今日交易分析概要:\n"
    for symbol, data in market_data.items():
        llm_format = LLMDataFormatter.format_for_llm(data, style="analytical")
        # 这里可以提取关键信息或直接发送给大模型API
        analysis += f"\n{symbol}: 趋势{llm_format['多维评估']['趋势分析']['短期趋势']}, RSI状态{llm_format['多维评估']['动量分析']['RSI状态']}\n"
    
    print(analysis)
    # 保存到文件或发送通知
    with open(f"daily_report_{time.strftime('%Y%m%d')}.txt", 'w') as f:
        f.write(analysis)

def schedule_checker():
    """定时检查调度任务"""
    while True:
        schedule.run_pending()
        time.sleep(1)

def main():
    # 设置调度任务
    schedule.every().day.at("09:35").do(trading_job)  # 开盘后
    schedule.every().day.at("14:30").do(trading_job)  # 收盘前
    schedule.every().day.at("20:17").do(trading_job)  # 晚间
    
    # 添加一个测试任务，每分钟执行一次
    schedule.every(1).minutes.do(trading_job)
    
    print(f"程序启动时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("短线交易系统已启动...")
    print("计划任务:")
    for job in schedule.get_jobs():
        print(f"  - {job}")
    
    # 在主线程中运行调度检查
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == "__main__":
    # 可选：使用守护线程运行调度
    # scheduler_thread = threading.Thread(target=schedule_checker, daemon=True)
    # scheduler_thread.start()
    
    main()