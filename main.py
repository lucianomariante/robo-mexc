# main.py
import asyncio
from crypto_bot import main as run_bot   # importa a função main() definida no arquivo novo

if __name__ == "__main__":
    asyncio.run(run_bot())
