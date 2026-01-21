import ccxt
import time
from telegram import Bot
from config import *
from halal_pairs import HALAL_PAIRS

tg_bot = Bot(token=TELEGRAM_TOKEN)

def notify(msg):
    try:
        tg_bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=msg)
    except Exception as e:
        print("Telegram error:", e)

exchange = ccxt.okx({
    'apiKey': OKX_API_KEY,
    'secret': OKX_SECRET,
    'password': OKX_PASSPHRASE,
    'enableRateLimit': True,
    'options': {'defaultType': 'spot'}
})

def get_balance():
    balance = exchange.fetch_balance()
    return balance['USDT']['free']

def simple_signal():
    return True  # نطوره لاحقًا

def trade(pair):
    price = exchange.fetch_ticker(pair)['last']
    amount = TRADE_AMOUNT_USD / price

    exchange.create_market_buy_order(pair, amount)

    tp = price * (1 + TAKE_PROFIT_PERCENT / 100)
    sl = price * (1 - STOP_LOSS_PERCENT / 100)

    notify(f"✅ شراء {pair}\n💰 {price:.4f}\n🎯 TP {tp:.4f}\n🛑 SL {sl:.4f}")

    while True:
        current = exchange.fetch_ticker(pair)['last']
        if current >= tp or current <= sl:
            exchange.create_market_sell_order(pair, amount)
            notify(f"🔁 إغلاق الصفقة {pair} عند {current:.4f}")
            break
        time.sleep(5)

def main():
    notify("🤖 البوت يعمل الآن (Spot + Halal)")
    while True:
        if get_balance() >= TRADE_AMOUNT_USD:
            for pair in HALAL_PAIRS:
                if simple_signal():
                    trade(pair)
                    time.sleep(30)
        time.sleep(60)

main()
