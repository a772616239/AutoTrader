from ib_insync import IB

ib = IB()
ib.connect('127.0.0.1', 7497, clientId=1)

# ✅ 旧版：只能用 wrapper 回调
def historicalNews(reqId, time, providerCode, articleId, headline):
    print(f"[{time}] {providerCode} | {headline}")

def historicalNewsEnd(reqId, hasMore):
    print("=== Historical News End ===")
    ib.disconnect()

ib.wrapper.historicalNews = historicalNews
ib.wrapper.historicalNewsEnd = historicalNewsEnd

# ✅ 注意：只有 6 个参数
ib.reqHistoricalNews(
    1002,      # reqId
    265598,    # conId (AAPL)
    "",        # providerCodes（全部）
    "",        # startDateTime
    20,        # totalResults
    []         # historicalNewsOptions
)

# ✅ 必须启动事件循环
ib.run()
