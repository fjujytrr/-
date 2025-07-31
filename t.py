import time
import hmac
import hashlib
import requests
import pandas as pd
from urllib.parse import urlencode
from ta.trend import EMAIndicator, MACD
from ta.momentum import RSIIndicator

API_KEY = "mx0vglfbfsIL7y0NOh"
SECRET_KEY = "c728de46319649c78b71f4300ba94130"

base_url = "https://api.mexc.com"
symbol = "TONUSDT"
buy_amount_usdt = 2

entry_price = None
holding = False

def create_signature(query_string, secret_key):
    return hmac.new(secret_key.encode('utf-8'), query_string.encode('utf-8'), hashlib.sha256).hexdigest()

def place_market_order(symbol, side, quote_order_qty=None, quantity=None):
    path = "/api/v3/order"
    timestamp = int(time.time() * 1000)
    params = {
        "symbol": symbol,
        "side": side,
        "type": "MARKET",
        "timestamp": timestamp
    }

    if side == "BUY":
        params["quoteOrderQty"] = quote_order_qty
    elif side == "SELL":
        params["quantity"] = quantity

    query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
    signature = create_signature(query_string, SECRET_KEY)
    headers = {"X-MEXC-APIKEY": API_KEY}
    url = f"{base_url}{path}?{query_string}&signature={signature}"
    response = requests.post(url, headers=headers)
    return response.json()

def get_price():
    url = f"{base_url}/api/v3/ticker/price"
    r = requests.get(url, params={"symbol": symbol}).json()
    return float(r["price"]) if "price" in r else None

def get_klines(symbol, interval="1m", limit=100):
    url = f"{base_url}/api/v3/klines"
    params = {"symbol": symbol, "interval": interval, "limit": limit}
    r = requests.get(url, params=params)
    data = r.json()
    if not isinstance(data, list) or len(data) < 30:
        return None
    df = pd.DataFrame(data, columns=[
        "open_time", "open", "high", "low", "close", "volume",
        "close_time", "quote_asset_volume"
    ])
    df["close"] = df["close"].astype(float)
    df["volume"] = df["volume"].astype(float)
    return df

def check_signal(df):
    close = df["close"]
    volume = df["volume"]

    ema9 = EMAIndicator(close, window=9).ema_indicator()
    ema21 = EMAIndicator(close, window=21).ema_indicator()
    macd = MACD(close)
    macd_line = macd.macd()
    macd_signal = macd.macd_signal()
    rsi = RSIIndicator(close, window=14).rsi()
    avg_vol = volume.rolling(window=20).mean()

    cond1 = close.iloc[-1] > ema9.iloc[-1] > ema21.iloc[-1]
    cond2 = macd_line.iloc[-1] > macd_signal.iloc[-1] and macd_line.iloc[-2] < macd_signal.iloc[-2]
    cond3 = 50 < rsi.iloc[-1] < 70
    cond4 = volume.iloc[-1] > avg_vol.iloc[-1]

    true_count = sum([cond1, cond2, cond3, cond4])
    print(f"📊 Совпало условий: {true_count}/4")
    return true_count >= 3

def get_balance(asset="TON"):
    timestamp = int(time.time() * 1000)
    params = {"timestamp": timestamp}
    query_string = urlencode(params)
    signature = create_signature(query_string, SECRET_KEY)
    headers = {"X-MEXC-APIKEY": API_KEY}
    url = f"{base_url}/api/v3/account?{query_string}&signature={signature}"
    r = requests.get(url, headers=headers).json()
    if "balances" not in r:
        print("❌ Ошибка получения баланса:", r)
        return 0
    for b in r["balances"]:
        if b["asset"] == asset:
            return float(b["free"])
    return 0

# 🔁 Основной цикл
while True:
    try:
        df = get_klines(symbol)
        if df is None:
            print("⚠ Нет данных. Жду...")
            time.sleep(10)
            continue

        if not holding:
            if check_signal(df):
                print("📈 Сигнал подтверждён. Покупаю TON...")
                buy = place_market_order(symbol, "BUY", quote_order_qty=buy_amount_usdt)
                if "orderId" in buy:
                    entry_price = get_price()
                    holding = True
                    print(f"✅ Куплено по цене {entry_price}")
                else:
                    print("❌ Ошибка при покупке:", buy)
        else:
            current_price = get_price()
            if current_price is None or entry_price is None:
                time.sleep(10)
                continue

            print(f"💹 Цена сейчас: {current_price:.6f} (вход: {entry_price:.6f})")

            if current_price >= entry_price * 1.007:
                print("🎯 Цена выросла на 1%. Продаю...")
                qty = round(get_balance("TON"), 4)
                sell = place_market_order(symbol, "SELL", quantity=qty)
                if "orderId" in sell:
                    print("✅ Продано по прибыли:", sell)
                else:
                    print("❌ Ошибка при продаже:", sell)
                holding = False
                entry_price = None
                time.sleep(60)

            elif current_price <= entry_price * 0.986:
                print("⚠ Цена упала на 2%. Стоп-лосс...")
                qty = round(get_balance("TON"), 4)
                sell = place_market_order(symbol, "SELL", quantity=qty)
                if "orderId" in sell:
                    print("✅ Продано по стопу:", sell)
                else:
                    print("❌ Ошибка при продаже:", sell)
                holding = False
                entry_price = None
                time.sleep(60)

        time.sleep(10)

    except Exception as e:
        print("❗ Ошибка:", e)
        time.sleep(10)








