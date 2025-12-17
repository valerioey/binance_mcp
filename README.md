# Binance MCP stdio server

<a href="https://glama.ai/mcp/servers/@valerioey/binance-mcp">
  <img width="380" height="200" src="https://glama.ai/mcp/servers/@valerioey/binance-mcp/badge" />
</a>

Server MCP minimale in Python che espone operazioni Binance via JSON-RPC 2.0 su `stdin`/`stdout`.

## Setup
- Richiede Python 3.8+ senza dipendenze extra.
- Esporta le chiavi prima di avviare il server:
  ```bash
  export BINANCE_API_KEY="...your key..."
  export BINANCE_API_SECRET="...your secret..."
  ```

## Avvio
```bash
python3 binance_mcp_server.py
```
Il processo resta in ascolto su `stdin` e restituisce risposte su `stdout` (una per riga).

## Metodi supportati
- `ping` → verifica con `{"pong": true, "time": ...}`
- `get_account` → snapshot account firmato
- `get_open_orders` → ordini aperti, opzionale `symbol`
- `get_trades` → ultimi trade eseguiti per `symbol`
- `place_order` → invia ordine market/limit (o test se `test: true`)
- `get_candles` → candele/klines pubbliche per `symbol` e `interval`

## Esempi di richieste
Invia un JSON per riga allo stdin del processo.

```json
{"jsonrpc":"2.0","id":1,"method":"ping","params":{}}
{"jsonrpc":"2.0","id":2,"method":"get_account","params":{}}
{"jsonrpc":"2.0","id":3,"method":"get_open_orders","params":{"symbol":"BTCUSDT"}}
{"jsonrpc":"2.0","id":4,"method":"get_trades","params":{"symbol":"ETHUSDT","limit":20}}
{"jsonrpc":"2.0","id":5,"method":"place_order","params":{"symbol":"BNBUSDT","side":"BUY","type":"MARKET","quoteOrderQty":50,"test":true}}
{"jsonrpc":"2.0","id":6,"method":"get_candles","params":{"symbol":"BTCUSDT","interval":"1h","limit":10}}
```

Le risposte seguono il formato `{"jsonrpc":"2.0","id":<id>,"result":...}` oppure `error` in caso di problemi (errori Binance inclusi).
