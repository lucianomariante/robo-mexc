"""
crypto_bot_mexc.py
Versão específica para **MEXC Global** (Spot).
Mantém a estratégia (ATR/EMA/RSI, histerese, trailing‑stop, gestão de risco)
e troca apenas a camada de interação com a corretora.

Como usar
---------
1. `pip install httpx pandas ta websockets`  (ou adicione no requirements.txt)
2. Variáveis de ambiente obrigatórias:
   - `MEXC_API_KEY`
   - `MEXC_API_SECRET`
3. Opcional:
   - `SYMBOL`   (padrão `BTCUSDT`)
   - `INTERVAL` (padrão `1m`)  → usa WebSocket público da MEXC.
4. Start command no Render: `python crypto_bot_mexc.py`

Limitações • Roadmap
-------------------
* Ordem sempre **MARKET** (side BUY/SELL).  
* Sem testnet (MEXC não possui).  
* WebSocket reconecta automático.  
* Apenas Spot account. Para Futures, endpoints mudam.
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

# ---------------- ENV ----------------
API_KEY    = os.getenv("MEXC_API_KEY")
API_SECRET = os.getenv("MEXC_API_SECRET")
if not API_KEY or not API_SECRET:
    raise RuntimeError("MEXC_API_KEY e MEXC_API_SECRET são obrigatórias.")

SYMBOL       = os.getenv("SYMBOL", "BTCUSDT")
INTERVAL     = os.getenv("INTERVAL", "1m")
RISK_PCT     = float(os.getenv("RISK_PCT", "0.01"))
ATR_WINDOW   = int(os.getenv("ATR_WINDOW", "14"))
MA_WINDOW    = int(os.getenv("MA_WINDOW", "20"))
HYSTERESIS_K = float(os.getenv("HYSTERESIS_K", "0.2"))
MIN_BARS_POS = int(os.getenv("MIN_BARS_IN_POSITION", "3"))
MIN_VOL_PCT  = float(os.getenv("MIN_VOL_PCT", "0.0003"))
BASE_URL     = "https://api.mexc.com"  # REST
WS_URL       = "wss://stream.mexc.com/ws"

# ---------------- helper: REST signed ----------------
async def mexc_request(method: str, path: str, params: dict | None = None):
    if params is None:
        params = {}
    params["timestamp"] = int(time.time()*1000)
    query = urlencode(sorted(params.items()))
    signature = hmac.new(API_SECRET.encode(), query.encode(), hashlib.sha256).hexdigest()
    query += f"&signature={signature}"
    headers = {"X-MEXC-APIKEY": API_KEY}
    url = f"{BASE_URL}{path}?{query}"
    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.request(method, url, headers=headers)
        r.raise_for_status()
        return r.json()

# ---------------- bot ----------------
class CryptoBotMEXC:
    def __init__(self):
        self.df = pd.DataFrame()
        self.position = None  # {side, qty, entry, stop, open_bar}
        self.last_signal = None

    # ----- utils -----
    async def get_balance(self, asset: str = "USDT") -> float:
        data = await mexc_request("GET", "/api/v3/account")
        bal = next((b for b in data["balances"] if b["asset"] == asset), None)
        return float(bal["free"] if bal else 0)

    async def create_order(self, side: str, qty: float):
        params = {
            "symbol": SYMBOL,
            "side": side,
            "type": "MARKET",
            "quantity": qty,
        }
        try:
            await mexc_request("POST", "/api/v3/order", params)
            logging.info(f"ORDEM {side} {qty:.6f} enviada")
        except Exception as e:
            logging.error(f"Falha ordem: {e}")

    # ----- data frame -----
    def update_df(self, k):
        ts = pd.to_datetime(k["T"], unit="ms")
        self.df.loc[ts, ["open", "high", "low", "close", "volume"]] = [
            float(k["o"]), float(k["h"]), float(k["l"]), float(k["c"]), float(k["v"])
        ]
        if len(self.df) > 200:
            self.df = self.df.tail(200)

    def compute_indicators(self):
        if len(self.df) < MA_WINDOW:
            return
        last = self.df.iloc[-MA_WINDOW:]
        idx  = self.df.index[-1]
        self.df.at[idx, "atr"]       = average_true_range(last["high"], last["low"], last["close"], ATR_WINDOW).iloc[-1]
        self.df.at[idx, "ma20"]     = last["close"].rolling(MA_WINDOW).mean().iloc[-1]
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
            sinal = "BUY"
        elif close > ma + margem:
            sinal = "SELL"
        else:
            sinal = self.last_signal
        if sinal == "BUY" and row["ema_fast"] <= row["ema_slow"]:
            return None
        if sinal == "SELL" and row["ema_fast"] >= row["ema_slow"]:
            return None
        return sinal

    async def manage(self):
        if len(self.df) < MA_WINDOW:
            return
        row = self.df.iloc[-1]
        atr, close = row["atr"], row["close"]
        # trailing
        if self.position and atr:
            if self.position["side"] == "BUY":
                self.position["stop"] = max(self.position["stop"], close - atr*1.5)
                if close <= self.position["stop"]:
                    await self.create_order("SELL", self.position["qty"])
                    self.position = None
            else:
                self.position["stop"] = min(self.position["stop"], close + atr*1.5)
                if close >= self.position["stop"]:
                    await self.create_order("BUY", self.position["qty"])
                    self.position = None
        sinal = self.signal()
        if sinal and sinal != self.last_signal:
            logging.info(json.dumps(dict(ts=str(datetime.now(timezone.utc)), close=close, sinal=sinal, atr=atr)))
            if self.position and sinal != self.position["side"] and (len(self.df) - self.position["open_bar"]) >= MIN_BARS_POS:
                await self.create_order("SELL" if self.position["side"] == "BUY" else "BUY", self.position["qty"])
                self.position = None
            if not self.position and atr:
                stop_dist = atr*1.5
                saldo = await self.get_balance()
                qty = round((saldo * RISK_PCT) / stop_dist, 6)
                if qty > 0:
                    await self.create_order(sinal, qty)
                    stop = close - stop_dist if sinal == "BUY" else close + stop_dist
                    self.position = dict(side=sinal, qty=qty, entry=close, stop=stop, open_bar=len(self.df))
        self.last_signal = sinal

    # ----- websocket -----
    async def run(self):
        kline_channel = f"{SYMBOL.lower()}@kline_{INTERVAL}"
        while True:
            try:
                async with websockets.connect(WS_URL) as ws:
                    await ws.send(json.dumps({"method": "SUBSCRIPTION", "params": [kline_channel], "id": 1}))
                    async for msg_text in ws:
                        msg = json.loads(msg_text)
                        if "data" not in msg:
                            continue
                        kline = msg["data"]["k"]
                        if not kline["x"]:
                            continue
                        self.update_df(kline)
                        self.compute_indicators()
                        await self.manage()
            except Exception as e:
                logging.error(f"WS erro: {e} — reconecta em 5 s")
                await asyncio.sleep(5)

# ------------- entrypoint -------------
async def main():
    await CryptoBotMEXC().run()

if __name__ == "__main__":
    asyncio.run(main())


