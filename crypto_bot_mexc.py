"""
crypto_bot_mexc.py  (fix WS URL & subscription)
• Usa WebSocket oficial V3 `wss://wbs.mexc.com/ws`.
• Canal de K‑line conforme docs: `spot@public.kline.v3.api.pb@SYMBOL@Min1`.
"""

import os, asyncio, json, hmac, hashlib, time, logging
from datetime import datetime, timezone
from urllib.parse import urlencode

import httpx
import pandas as pd
from ta.volatility import average_true_range
from ta.trend import ema_indicator
from ta.momentum import rsi
import websockets

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s")

API_KEY    = os.getenv("MEXC_API_KEY")
API_SECRET = os.getenv("MEXC_API_SECRET")
if not API_KEY or not API_SECRET:
    raise RuntimeError("MEXC_API_KEY e MEXC_API_SECRET são obrigatórias.")

SYMBOL       = os.getenv("SYMBOL", "BTCUSDT").upper()
INTERVAL     = os.getenv("INTERVAL", "1m").lower()  # ex: 1m, 5m
RISK_PCT     = float(os.getenv("RISK_PCT", "0.01"))
ATR_WINDOW   = int(os.getenv("ATR_WINDOW", "14"))
MA_WINDOW    = int(os.getenv("MA_WINDOW", "20"))
HYSTERESIS_K = float(os.getenv("HYSTERESIS_K", "0.2"))
MIN_BARS_POS = int(os.getenv("MIN_BARS_IN_POSITION", "3"))
MIN_VOL_PCT  = float(os.getenv("MIN_VOL_PCT", "0.0003"))
BASE_URL     = "https://api.mexc.com"
WS_URL       = "wss://wbs.mexc.com/ws"  # <- fix principal

# -------- util ----------
INTERVAL_MAP = {
    "1m": "Min1", "5m": "Min5", "15m": "Min15", "30m": "Min30",
    "60m": "Min60", "1h": "Min60", "4h": "Hour4", "8h": "Hour8",
    "1d": "Day1", "1w": "Week1", "1M": "Month1"
}
interval_pb = INTERVAL_MAP.get(INTERVAL, "Min1")

async def mexc_request(method: str, path: str, params: dict | None = None):
    params = params or {}
    params["timestamp"] = int(time.time()*1000)
    query = urlencode(sorted(params.items()))
    sign  = hmac.new(API_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()
    query += f"&signature={sign}"
    url = f"{BASE_URL}{path}?{query}"
    headers = {"X-MEXC-APIKEY": API_KEY}
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.request(method, url, headers=headers)
        r.raise_for_status()
        return r.json()

class CryptoBotMEXC:
    def __init__(self):
        self.df = pd.DataFrame()
        self.position = None
        self.last_signal = None

    # balance, order (mesmos de antes) ...
    async def get_balance(self, asset: str = "USDT") -> float:
        data = await mexc_request("GET", "/api/v3/account")
        bal = next((b for b in data["balances"] if b["asset"] == asset), None)
        return float(bal["free"] if bal else 0)

    async def create_order(self, side: str, qty: float):
        await mexc_request("POST", "/api/v3/order", {
            "symbol": SYMBOL, "side": side, "type": "MARKET", "quantity": qty
        })
        logging.info(f"ORDEM {side} {qty:.6f} enviada")

    # update_df, compute_indicators, signal, manage (inalterados)
    def update_df(self, k):
        ts = pd.to_datetime(int(k["windowstart"])*1000, unit="ms")
        self.df.loc[ts, ["open", "high", "low", "close", "volume"]] = [
            float(k["openingprice"]), float(k["highestprice"]), float(k["lowestprice"]),
            float(k["closingprice"]), float(k["volume"])
        ]
        if len(self.df) > 200:
            self.df = self.df.tail(200)

    def compute_indicators(self):
        if len(self.df) < MA_WINDOW:
            return
        last = self.df.iloc[-MA_WINDOW:]
        idx = self.df.index[-1]
        self.df.at[idx, "atr"] = average_true_range(last["high"], last["low"], last["close"], ATR_WINDOW).iloc[-1]
        self.df.at[idx, "ma20"] = last["close"].rolling(MA_WINDOW).mean().iloc[-1]
        self.df.at[idx, "ema_fast"] = ema_indicator(last["close"], 12).iloc[-1]
        self.df.at[idx, "ema_slow"] = ema_indicator(last["close"], 26).iloc[-1]

    def signal(self):
        if len(self.df) < MA_WINDOW:
            return None
        row = self.df.iloc[-1]
        atr, ma, close = row["atr"], row["ma20"], row["close"]
        if pd.isna(atr) or atr == 0 or atr/close < MIN_VOL_PCT:
            return None
        margem = HYSTERESIS_K * atr
        if close < ma - margem:
            sig = "BUY"
        elif close > ma + margem:
            sig = "SELL"
        else:
            sig = self.last_signal
        if sig == "BUY" and row["ema_fast"] <= row["ema_slow"]:
            return None
        if sig == "SELL" and row["ema_fast"] >= row["ema_slow"]:
            return None
        return sig

    async def manage(self):
        ...  # mantém igual (omitido aqui por brevidade)

    async def run(self):
        channel = f"spot@public.kline.v3.api.pb@{SYMBOL}@{interval_pb}"
        sub_msg = {"method": "SUBSCRIPTION", "params": [channel], "id": 1}
        while True:
            try:
                async with websockets.connect(WS_URL, ping_interval=20) as ws:
                    await ws.send(json.dumps(sub_msg))
                    async for txt in ws:
                        msg = json.loads(txt)
                        if msg.get("channel") != channel:
                            continue
                        kline = msg.get("publicspotkline")
                        if not kline:
                            continue
                        self.update_df(kline)
                        self.compute_indicators()
                        await self.manage()
            except Exception as e:
                logging.error(f"WS erro: {e} — reconecta em 5 s")
                await asyncio.sleep(5)

async def main():
    await CryptoBotMEXC().run()

if __name__ == "__main__":
    asyncio.run(main())
