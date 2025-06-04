# Robo MEXC

This bot connects to the MEXC websocket API using Protocol Buffers messages.

The `.proto` definitions from [mexcdevelop/websocket-proto](https://github.com/mexcdevelop/websocket-proto)
are included under `protos/` with the generated Python modules in `mexc_pb/`.
If you need to regenerate them, run:

```bash
protoc --proto_path=protos --python_out=mexc_pb protos/*.proto
```

Install requirements and run the bot:

```bash
pip install -r requirements.txt
python crypto_bot_mexc.py
```
