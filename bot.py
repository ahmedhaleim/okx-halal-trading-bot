import ccxt
import time
import requests
import pandas as pd
import os

# ================== CONFIG ==================
OKX_API_KEY = os.getenv("OKX_API_KEY")
OKX_SECRET = os.getenv("OKX_SECRET")
OKX_PASSWORD = os.getenv("OKX_PASSWORD")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

TRADE_AMOUNT_USD = 3          # لكل صفقة
MAX_OPEN_TRADES = 5           # 3 – 7
TIMEFRAME = '5m'
RSI_PERIOD = 14
EMA_FAST = 9
EMA_SLOW = 21
CHECK_INTERVAL = 60

# ================== OKX ==================
exchange = ccxt.okx({
    'apiKey': OKX_API_KEY,
    'secret': OKX_SECRET,
    'password': OKX_PASSWORD,
    'enableRateLimit': True,
    'options': {'defaultType': 'spot'}
})

# ================== TELEGRAM ==================
def notify(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": CHAT_ID, "text": msg})

# ================== BALANCE (FIXED) ==================
def get_usdt_balance():
    balance = exchange.fetch_balance()
    for asset in balance['info']['data'][0]['details']:
        if asset['ccy'] == 'USDT':
            return float(asset['availBal'])
    return 0.0

# ================== HALAL FILTER ==================
def halal_symbols():
    markets = exchange.load_markets()
    haram_keywords = ['BTC', 'ETH', 'BNB', 'XRP', 'DOGE']  # ربا/قروض/فوائد
    halal = []
    for s in markets:
        if s.endswith('/USDT'):
            base = s.split('/')[0]
            if base not in haram_keywords:
                halal.append(s)
    return halal

# ================== INDICATORS ==================
def indicators(symbol):
    ohlcv = exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=100)
    df = pd.DataFrame(ohlcv, columns=['t','o','h','l','c','v'])
    df['ema_fast'] = df['c'].ewm(span=EMA_FAST).mean()
    df['ema_slow'] = df['c'].ewm(span=EMA_SLOW).mean()

    delta = df['c'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    rs = gain.rolling(RSI_PERIOD).mean() / loss.rolling(RSI_PERIOD).mean()
    df['rsi'] = 100 - (100 / (1 + rs))
    return df.iloc[-1]

# ================== TRADE LOGIC ==================
open_trades = {}

def can_buy(symbol):
    if symbol in open_trades:
        return False
    if len(open_trades) >= MAX_OPEN_TRADES:
        return False
    return True

def try_buy(symbol):
    ind = indicators(symbol)

    if ind['rsi'] < 30 and ind['ema_fast'] > ind['ema_slow']:
        balance = get_usdt_balance()
        if balance < TRADE_AMOUNT_USD:
            return

        price = exchange.fetch_ticker(symbol)['last']
        amount = TRADE_AMOUNT_USD / price

        order = exchange.create_market_buy_order(symbol, amount)
        open_trades[symbol] = order['price']

        notify(f"✅ شراء {symbol}\nRSI: {round(ind['rsi'],2)}")

# ================== MAIN LOOP ==================
def main():
    notify("🤖 البوت بدأ العمل (Spot + Halal + RSI/EMA)")
    symbols = halal_symbols()

    while True:
        try:
            for symbol in symbols:
                if can_buy(symbol):
                    try_buy(symbol)
                time.sleep(1)
        except Exception as e:
            notify(f"⚠️ خطأ: {str(e)}")
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
