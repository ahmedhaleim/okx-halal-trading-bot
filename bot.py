import ccxt
import time
import requests
import pandas as pd

# ================== CONFIG ==================
API_KEY = "YOUR_API_KEY"
API_SECRET = "YOUR_API_SECRET"

TELEGRAM_TOKEN = "YOUR_TELEGRAM_TOKEN"
TELEGRAM_CHAT_ID = "YOUR_CHAT_ID"

TRADE_AMOUNT_USD = 20
MAX_OPEN_TRADES = 5          # 3 – 7
TIMEFRAME = '15m'
CHECK_INTERVAL = 60

# مؤشرات
RSI_PERIOD = 14
EMA_FAST = 50
EMA_SLOW = 200

# عملات حلال (قائمة أولية)
HALAL_COINS = [
    "BTC", "ETH", "BNB", "ADA", "SOL",
    "MATIC", "AVAX", "DOT", "LINK", "XRP"
]

# كلمات محرّمة (استبعاد تلقائي)
HARAM_KEYWORDS = [
    "loan", "lend", "borrow",
    "interest", "bank",
    "leverage", "margin", "futures"
]

# ================== EXCHANGE ==================
exchange = ccxt.binance({
    "apiKey": API_KEY,
    "secret": API_SECRET,
    "enableRateLimit": True,
    "options": {"defaultType": "spot"}
})

open_trades = {}  # symbol: entry_price

# ================== HELPERS ==================
def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": TELEGRAM_CHAT_ID, "text": msg})

def get_usdt_balance():
    try:
        balance = exchange.fetch_balance()
        return float(balance.get("USDT", {}).get("free", 0))
    except Exception:
        return 0

def is_halal_symbol(symbol):
    base = symbol.split("/")[0]
    if base not in HALAL_COINS:
        return False
    for word in HARAM_KEYWORDS:
        if word.lower() in base.lower():
            return False
    return True

def fetch_indicators(symbol):
    ohlcv = exchange.fetch_ohlcv(symbol, timeframe=TIMEFRAME, limit=EMA_SLOW + 5)
    df = pd.DataFrame(ohlcv, columns=['t','o','h','l','c','v'])

    df['ema_fast'] = df['c'].ewm(span=EMA_FAST).mean()
    df['ema_slow'] = df['c'].ewm(span=EMA_SLOW).mean()

    delta = df['c'].diff()
    gain = (delta.where(delta > 0, 0)).rolling(RSI_PERIOD).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(RSI_PERIOD).mean()
    rs = gain / loss
    df['rsi'] = 100 - (100 / (1 + rs))

    return df.iloc[-1]

# ================== STRATEGY ==================
def can_enter_trade(symbol):
    if symbol in open_trades:
        return False
    if len(open_trades) >= MAX_OPEN_TRADES:
        return False

    ind = fetch_indicators(symbol)

    trend_ok = ind['ema_fast'] > ind['ema_slow']
    price_above = ind['c'] > ind['ema_slow']
    rsi_ok = 30 < ind['rsi'] < 60

    return trend_ok and price_above and rsi_ok

def open_trade(symbol):
    price = exchange.fetch_ticker(symbol)['last']
    amount = TRADE_AMOUNT_USD / price

    exchange.create_market_buy_order(symbol, amount)
    open_trades[symbol] = price

    send_telegram(f"✅ BUY {symbol}\nEntry: {price}")

def manage_trades():
    for symbol in list(open_trades.keys()):
        price = exchange.fetch_ticker(symbol)['last']
        entry = open_trades[symbol]

        tp = entry * 1.02
        sl = entry * 0.98

        if price >= tp or price <= sl:
            amount = exchange.fetch_balance()[symbol.split('/')[0]]['free']
            exchange.create_market_sell_order(symbol, amount)
            del open_trades[symbol]

            send_telegram(f"❌ CLOSE {symbol}\nPrice: {price}")

# ================== MAIN LOOP ==================
def main():
    send_telegram("🚀 Bot Started | Spot | Halal | RSI + EMA")

    markets = exchange.load_markets()
    symbols = [
        s for s in markets
        if s.endswith("/USDT") and is_halal_symbol(s)
    ]

    while True:
        usdt = get_usdt_balance()
        if usdt < TRADE_AMOUNT_USD:
            send_telegram("⚠️ رصيد USDT غير كافي")
            time.sleep(300)
            continue

        for symbol in symbols:
            try:
                if can_enter_trade(symbol):
                    open_trade(symbol)
                    time.sleep(2)
            except Exception as e:
                print(symbol, e)

        manage_trades()
        time.sleep(CHECK_INTERVAL)

if __name__ == "__main__":
    main()
