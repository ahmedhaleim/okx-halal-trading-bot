import ccxt
import time
import requests
import pandas as pd
import os

# ================= CONFIG =================
OKX_API_KEY = os.getenv("OKX_API_KEY")
OKX_SECRET = os.getenv("OKX_SECRET")
OKX_PASSWORD = os.getenv("OKX_PASSWORD")

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

DASHBOARD_URL = os.getenv("DASHBOARD_URL")

TIMEFRAME = "5m"
TRADE_USD = 3
MAX_TRADES = 5

ATR_PERIOD = 14
ATR_MULTIPLIER = 1.5

# ================= EXCHANGE =================
exchange = ccxt.okx({
    "apiKey": OKX_API_KEY,
    "secret": OKX_SECRET,
    "password": OKX_PASSWORD,
    "options": {"defaultType": "spot"}
})

# ================= STATE =================
open_trades = {}
total_profit = 0.0

# ================= UTIL =================
def notify(msg):
    try:
        requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            json={"chat_id": CHAT_ID, "text": msg},
            timeout=5
        )
    except:
        pass

def push_dashboard():
    try:
        requests.post(DASHBOARD_URL, json={
            "open_trades": open_trades,
            "profit": round(total_profit, 2)
        }, timeout=5)
    except:
        pass

# ================= HALAL FILTER =================
def halal_symbols():
    haram = ["BTC", "ETH", "BNB", "XRP", "DOGE"]
    markets = exchange.load_markets()
    return [
        s for s in markets
        if s.endswith("/USDT") and s.split("/")[0] not in haram
    ]

# ================= INDICATORS =================
def indicators(symbol):
    ohlcv = exchange.fetch_ohlcv(symbol, TIMEFRAME, limit=100)
    df = pd.DataFrame(ohlcv, columns=["t","o","h","l","c","v"])

    df["ema9"] = df["c"].ewm(span=9).mean()
    df["ema21"] = df["c"].ewm(span=21).mean()

    delta = df["c"].diff()
    gain = delta.clip(lower=0).rolling(14).mean()
    loss = -delta.clip(upper=0).rolling(14).mean()
    df["rsi"] = 100 - (100 / (1 + gain / loss))

    df["tr"] = df[["h","l","c"]].max(axis=1) - df[["h","l","c"]].min(axis=1)
    df["atr"] = df["tr"].rolling(ATR_PERIOD).mean()

    return df.iloc[-1]

# ================= SAFE MARKET SELL =================
def safe_market_sell(symbol, amount):
    for attempt in range(3):
        try:
            exchange.cancel_all_orders(symbol)
            exchange.create_market_sell_order(symbol, amount)
            return True
        except Exception as e:
            time.sleep(1)
            last_error = str(e)
    notify(f"🚨 SELL FAILED {symbol}: {last_error}")
    return False

# ================= MAIN =================
notify("🤖 Bot Started (Fixed Stop Loss Logic)")
symbols = halal_symbols()

while True:
    try:
        # ===== ENTRY =====
        for s in symbols:
            if s in open_trades or len(open_trades) >= MAX_TRADES:
                continue

            ind = indicators(s)
            if ind["rsi"] < 30 and ind["ema9"] > ind["ema21"]:
                ticker = exchange.fetch_ticker(s)
                price = ticker["ask"]  # BUY at ASK
                amount = TRADE_USD / price

                exchange.create_market_buy_order(s, amount)

                open_trades[s] = {
                    "entry": price,
                    "amount": amount,
                    "highest": price,
                    "atr": ind["atr"],
                    "sl": price - (ind["atr"] * ATR_MULTIPLIER),
                    "stopped": False
                }

                notify(f"✅ BUY {s}")

        # ===== TRAILING STOP (FIXED) =====
        for s in list(open_trades):
            trade = open_trades[s]
            ticker = exchange.fetch_ticker(s)
            price = ticker["bid"]  # 🔥 BEST BID فقط

            # تحديث أعلى سعر
            if price > trade["highest"]:
                trade["highest"] = price
                trade["sl"] = price - (trade["atr"] * ATR_MULTIPLIER)

            # STOP LOSS HIT
            if price <= trade["sl"] and not trade["stopped"]:
                trade["stopped"] = True

                success = safe_market_sell(s, trade["amount"])
                if success:
                    profit = (price - trade["entry"]) * trade["amount"]
                    total_profit += profit

                    notify(f"🛑 STOP LOSS SELL {s} | P/L: {round(profit,2)}$")
                    del open_trades[s]

        push_dashboard()

    except Exception as e:
        notify(f"⚠️ {str(e)}")

    time.sleep(60)
