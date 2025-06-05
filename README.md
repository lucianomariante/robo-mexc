# MEXC Crypto Bot

A simple trading bot that connects to the MEXC exchange using their HTTP and WebSocket APIs.  The bot relies on a few environment variables for configuration.

## Environment variables

| Variable               | Default  | Description                                              |
|------------------------|----------|----------------------------------------------------------|
| `MEXC_API_KEY`         | –        | Your API key from the MEXC account. **Required**.        |
| `MEXC_API_SECRET`      | –        | Secret key matching the API key. **Required**.           |
| `SYMBOL`               | BTCUSDT  | Trading pair symbol.                                     |
| `INTERVAL`             | 1m       | K‑line interval (e.g. `1m`, `5m`, `1h`).                 |
| `RISK_PCT`             | 0.01     | Fraction of balance to risk per trade.                   |
| `ATR_WINDOW`           | 14       | Window size used to compute ATR.                         |
| `MA_WINDOW`            | 20       | Moving‑average window for the trend filter.              |
| `HYSTERESIS_K`         | 0.2      | Percentage of ATR used as a hysteresis band.             |
| `MIN_BARS_IN_POSITION` | 3        | Minimum number of bars before a new position is opened.  |
| `MIN_VOL_PCT`          | 0.0003   | Minimum ATR/price ratio to consider the pair tradable.   |

Create a `.env` file or export these variables in your shell before starting the bot. Only `MEXC_API_KEY` and `MEXC_API_SECRET` are mandatory – the rest fall back to the defaults above.

## Running

Install the requirements and launch the main script:

```bash
pip install -r requirements.txt
python main.py
```
