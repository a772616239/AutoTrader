from ib_insync import *
import time
import inspect
from datetime import datetime, timedelta

def get_ibkr_news_stable():
    """
    稳定版IBKR新闻获取
    使用动态参数适配，避免版本兼容性问题
    """
    ib = IB()
    
    try:
        print("=" * 60)
        print("IBKR新闻获取 - 动态参数适配版")
        print("=" * 60)
        
        # 1. 建立连接
        print("\n[1/4] 正在连接到TWS/IB Gateway...")
        ib.connect('127.0.0.1', 7497, clientId=1, timeout=15)
        print(f"   ✓ 连接成功! 服务器时间: {ib.reqCurrentTime()}")
        
        # 2. 设置合约
        print("\n[2/4] 设置股票合约...")
        contract = Stock('AAPL', 'SMART', 'USD')
        try:
            qualified = ib.qualifyContracts(contract)
            if qualified:
                print(f"   ✓ 合约确认: AAPL")
        except Exception as e:
            print(f"   ⚠️ 合约确认时出错: {e}")
        
        # 3. 获取新闻提供商
        print("\n[3/4] 检查新闻订阅...")
        try:
            providers = ib.reqNewsProviders()
            if providers:
                print(f"   ✓ 找到 {len(providers)} 个新闻提供商")
                provider_codes = [p.code for p in providers if hasattr(p, 'code')]
                print(f"   前3个提供商: {provider_codes[:3]}")
            else:
                print("   ⚠️  未找到新闻提供商")
                provider_codes = []
        except Exception as e:
            print(f"   ⚠️  获取提供商时出错: {e}")
            provider_codes = []
        
        # 4. 动态适配调用历史新闻请求
        print("\n[4/4] 获取历史新闻...")
        
        # 准备参数值
        req_id = 1001
        start_datetime = (datetime.now() - timedelta(days=7)).strftime('%Y%m%d %H:%M:%S')
        end_datetime = datetime.now().strftime('%Y%m%d %H:%M:%S')
        provider_to_use = provider_codes[0] if provider_codes else ""
        total_results = 10
        
        # 获取方法签名
        try:
            sig = inspect.signature(ib.reqHistoricalNews)
            params = list(sig.parameters.keys())
            print(f"   reqHistoricalNews 参数列表: {params}")
            
            # 构建参数字典
            kwargs = {}
            # 根据参数名逐个匹配
            for param in params:
                if param == 'reqId':
                    kwargs[param] = req_id
                elif param == 'contract':
                    kwargs[param] = contract
                elif param == 'providerCodes':
                    kwargs[param] = [provider_to_use] if provider_to_use else []
                elif param == 'startDateTime':
                    kwargs[param] = start_datetime
                elif param == 'endDateTime':
                    kwargs[param] = end_datetime
                elif param == 'totalResults':
                    kwargs[param] = total_results
                elif param == 'historicalNewsOptions':
                    kwargs[param] = []
                else:
                    # 对于未知参数，设置为None或空值
                    kwargs[param] = None
            
            print(f"   使用参数: {list(kwargs.keys())}")
            
            # 调用方法
            ib.reqHistoricalNews(**kwargs)
            print("   历史新闻请求已发送，等待响应...")
            
            # 等待一段时间，让数据到达
            time.sleep(3)
            
        except Exception as e:
            print(f"   动态调用历史新闻请求失败: {type(e).__name__}: {e}")
            # 如果动态调用也失败，尝试最简化的位置参数调用（基于常见顺序）
            print("   尝试使用简化位置参数调用...")
            try:
                # 清空之前的可能错误状态
                ib.reqHistoricalNews(1002, contract, [], start_datetime, end_datetime, 5, [])
                print("   简化请求已发送")
                time.sleep(3)
            except Exception as e2:
                print(f"   简化请求也失败: {e2}")
        
        # 5. 尝试从多个可能的数据源获取新闻数据
        print("\n正在检查新闻数据...")
        news_found = []
        
        # 可能存储新闻数据的属性名
        possible_attrs = ['newsBulletins', 'newsArticles', 'historicalNews', 'newsData', 'newsTicks']
        
        for attr_name in possible_attrs:
            if hasattr(ib, attr_name):
                attr = getattr(ib, attr_name)
                # 如果是可调用方法，则调用它
                if callable(attr):
                    try:
                        data = attr()
                        if data and len(data) > 0:
                            print(f"   从 {attr_name}() 找到 {len(data)} 条记录")
                            news_found.extend(data)
                    except:
                        pass
                # 如果是属性且非空
                elif attr and len(attr) > 0:
                    print(f"   从 {attr_name} 属性找到 {len(attr)} 条记录")
                    news_found.extend(attr)
        
        # 6. 显示新闻结果
        print("\n" + "=" * 60)
        print("新闻获取结果:")
        print("=" * 60)
        
        if news_found:
            print(f"✓ 总共找到 {len(news_found)} 条新闻记录")
            
            # 显示前5条新闻
            print("\n前5条新闻:")
            for i, news in enumerate(news_found[:5], 1):
                # 尝试提取标题或内容
                headline = None
                
                # 根据不同的新闻对象类型提取信息
                if hasattr(news, 'headline'):
                    headline = news.headline
                elif hasattr(news, 'message'):
                    headline = news.message
                elif hasattr(news, 'text'):
                    headline = news.text
                elif isinstance(news, tuple) and len(news) >= 4:
                    # 可能是 (time, provider, articleId, headline) 的元组
                    headline = news[3] if len(news) > 3 else str(news)
                else:
                    headline = str(news)[:100]  # 截取前100个字符
                
                if headline:
                    # 清理并截断标题
                    headline_str = str(headline).replace('\n', ' ').replace('\r', '').strip()
                    if len(headline_str) > 80:
                        headline_str = headline_str[:77] + "..."
                    print(f"  {i}. {headline_str}")
                    
                    # 如果有时间信息，也显示
                    if hasattr(news, 'time'):
                        print(f"     时间: {news.time}")
                    elif hasattr(news, 'timestamp'):
                        print(f"     时间: {news.timestamp}")
        else:
            print("⚠️  未找到任何新闻数据")
            print("\n可能原因:")
            print("  1. 当前时间段内没有新闻发布")
            print("  2. 新闻提供商不提供历史新闻API访问")
            print("  3. 需要订阅特定的新闻服务")
            print("  4. 尝试在TWS/IB Gateway中手动查看新闻功能")
        
        print("\n" + "=" * 60)
        print("完成!")
        print("=" * 60)
        
    except ConnectionError as e:
        print(f"\n❌ 连接失败: {e}")
    except Exception as e:
        print(f"\n❌ 发生错误: {type(e).__name__}: {e}")
    finally:
        # 安全断开连接
        if ib.isConnected():
            try:
                ib.disconnect()
                print("\n✅ 已安全断开连接")
            except:
                pass

if __name__ == "__main__":
    start_time = datetime.now()
    print(f"开始时间: {start_time.strftime('%Y-%m-%d %H:%M:%S')}")
    
    get_ibkr_news_stable()
    
    end_time = datetime.now()
    duration = end_time - start_time
    print(f"\n结束时间: {end_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"总耗时: {duration.total_seconds():.1f} 秒")