# main.py
import asyncio
# Importa a função main() do bot
from crypto_bot_mexc import main as run_bot

if __name__ == "__main__":
    asyncio.run(run_bot())
