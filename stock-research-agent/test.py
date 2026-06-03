import yfinance as yf

ticker = yf.Ticker("AAPL")
info = ticker.info

print(info['longName'])
print(info['currentPrice'])
print(info['trailingPE'])
print(info['totalRevenue'])