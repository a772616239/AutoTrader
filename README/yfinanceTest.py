import yfinance as yf
import pandas as pd

def test_after_hours_data(ticker="ORCL", period="1d", interval="5m"):
    """
    测试并展示盘后交易数据
    
    参数:
        ticker: 股票代码 (默认: AAPL)
        period: 数据周期 (默认: 1d)
        interval: 数据间隔 (默认: 5m)
    """
    
    print(f"正在获取 {ticker} 的盘后数据测试...")
    print("=" * 60)
    
    # 获取包含盘前盘后的数据
    data_with_prepost = yf.download(
        ticker, 
        period=period, 
        interval=interval, 
        prepost=True,  # 包含盘前盘后
        auto_adjust=True,
        progress=False  # 不显示下载进度条
    )
    
    # 获取不包含盘前盘后的数据（用于对比）
    data_without_prepost = yf.download(
        ticker, 
        period=period, 
        interval=interval, 
        prepost=False,  # 不包含盘前盘后
        auto_adjust=True,
        progress=False
    )
    
    print(f"数据获取完成！")
    print(f"包含盘前盘后的数据形状: {data_with_prepost.shape}")
    print(f"不包含盘前盘后的数据形状: {data_without_prepost.shape}")
    print("=" * 60)
    
    # 识别盘前盘后交易时段（美东时间）
    # 常规交易时段通常为 09:30-16:00
    # 盘前交易时段通常为 04:00-09:30
    # 盘后交易时段通常为 16:00-20:00
    
    def get_trading_period(timestamp):
        """判断时间属于哪个交易时段"""
        hour = timestamp.hour
        minute = timestamp.minute
        
        # 将时间转换为分钟数便于比较
        time_in_minutes = hour * 60 + minute
        
        # 判断时段
        if time_in_minutes < 9*60 + 30:  # 09:30之前
            return "Pre-Market"
        elif time_in_minutes <= 16*60:   # 09:30-16:00
            return "Regular"
        else:                            # 16:00之后
            return "After-Hours"
    
    # 为包含盘前盘后的数据添加交易时段标记
    if not data_with_prepost.empty:
        data_with_prepost['Trading_Period'] = data_with_prepost.index.map(get_trading_period)
        
        # 统计各时段数据量
        period_counts = data_with_prepost['Trading_Period'].value_counts()
        
        print("\n📈 各交易时段数据分布:")
        for period_type, count in period_counts.items():
            percentage = count / len(data_with_prepost) * 100
            print(f"  {period_type}: {count} 条 ({percentage:.1f}%)")
        
        print("\n🔍 盘后交易数据示例 (After-Hours):")
        after_hours_data = data_with_prepost[data_with_prepost['Trading_Period'] == 'After-Hours']
        
        if not after_hours_data.empty:
            print(after_hours_data[['Open', 'High', 'Low', 'Close', 'Volume', 'Trading_Period']].head())
            
            # 分析盘后交易特征
            print("\n📊 盘后交易统计摘要:")
            print(f"  时间范围: {after_hours_data.index[0]} 到 {after_hours_data.index[-1]}")
            # print(f"  平均成交量: {after_hours_data['Volume'].mean():.0f}")
            # print(f"  价格波动范围: {after_hours_data['Close'].min():.2f} - {after_hours_data['Close'].max():.2f}")
        else:
            print("  今日无盘后交易数据")
        
        print("\n🔍 盘前交易数据示例 (Pre-Market):")
        pre_market_data = data_with_prepost[data_with_prepost['Trading_Period'] == 'Pre-Market']
        if not pre_market_data.empty:
            print(pre_market_data[['Open', 'High', 'Low', 'Close', 'Volume', 'Trading_Period']].head())
        else:
            print("  今日无盘前交易数据")
    
    # 对比数据差异
    print("\n" + "=" * 60)
    print("📊 数据对比分析:")
    print(f"包含盘前盘后比不包含多 {len(data_with_prepost) - len(data_without_prepost)} 条数据")
    
    # 保存数据到CSV以便进一步分析
    if not data_with_prepost.empty:
        filename = f"{ticker}_after_hours_test.csv"
        data_with_prepost.to_csv(filename)
        print(f"\n💾 完整数据已保存到: {filename}")
        print("   可用Excel打开查看所有交易时段数据")
    
    return data_with_prepost

# 执行测试（使用默认参数：AAPL股票，最近1天，5分钟间隔）
test_data = test_after_hours_data()

# 也可以测试其他股票或参数
# test_after_hours_data(ticker="MSFT", period="2d", interval="15m")