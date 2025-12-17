#!/usr/bin/env python3
"""
Lightweight MCP-like stdio server for interacting with the Binance REST API.

The server reads JSON-RPC 2.0 requests from stdin and writes responses to stdout.
It focuses on a small tool-set that is useful for agents:
  - get_account: signed account snapshot
  - get_open_orders: signed open orders (optionally filtered by symbol)
  - get_trades: signed recent trades for a symbol
  - place_order: signed market/limit order placement (or test orders)
  - get_candles: public kline/candlestick data

Authentication is pulled from BINANCE_API_KEY and BINANCE_API_SECRET
environment variables unless explicitly provided in the request.
"""

import hmac
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional


class BinanceClient:
    """Minimal Binance REST client with signed request support."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        api_secret: Optional[str] = None,
        base_url: str = "https://api.binance.com",
        allow_public: bool = False,
    ) -> None:
        self.api_key = api_key or os.environ.get("BINANCE_API_KEY")
        self.api_secret = api_secret or os.environ.get("BINANCE_API_SECRET")
        self.base_url = base_url.rstrip("/")
        self.allow_public = allow_public
        if not self.api_key or not self.api_secret:
            if not self.allow_public:
                raise ValueError("BINANCE_API_KEY and BINANCE_API_SECRET are required")

    def _sign(self, params: Dict[str, Any]) -> Dict[str, Any]:
        if not self.api_secret:
            raise ValueError("Signing requires BINANCE_API_SECRET")
        params = {k: v for k, v in params.items() if v is not None}
        params["timestamp"] = int(time.time() * 1000)
        query = urllib.parse.urlencode(params, doseq=True)
        signature = hmac.new(
            self.api_secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256
        ).hexdigest()
        params["signature"] = signature
        return params

    def _request(
        self, method: str, path: str, params: Optional[Dict[str, Any]] = None, signed: bool = False
    ) -> Any:
        params = params or {}
        if signed and not self.api_key:
            raise ValueError("Signed request requires BINANCE_API_KEY")
        encoded_params = self._sign(params) if signed else {k: v for k, v in params.items() if v is not None}
        query = urllib.parse.urlencode(encoded_params, doseq=True)
        url = f"{self.base_url}{path}"
        data = None

        if method.upper() == "GET":
            if query:
                url = f"{url}?{query}"
        else:
            data = query.encode("utf-8")

        request = urllib.request.Request(url=url, data=data, method=method.upper())
        request.add_header("User-Agent", "binance-mcp-server/1.0")
        if signed:
            request.add_header("X-MBX-APIKEY", self.api_key)
            request.add_header("Content-Type", "application/x-www-form-urlencoded")

        try:
            with urllib.request.urlopen(request, timeout=15) as resp:
                content_type = resp.headers.get("Content-Type", "")
                payload = resp.read()
                if "application/json" in content_type or payload.startswith(b"{") or payload.startswith(b"["):
                    return json.loads(payload.decode("utf-8"))
                return payload.decode("utf-8")
        except urllib.error.HTTPError as exc:
            error_body = exc.read().decode("utf-8")
            try:
                parsed = json.loads(error_body)
            except Exception:
                parsed = {"msg": error_body}
            raise RuntimeError({"status": exc.code, "payload": parsed}) from exc
        except urllib.error.URLError as exc:
            raise RuntimeError({"status": "network_error", "payload": str(exc)}) from exc

    def get_account(self, recv_window: Optional[int] = None) -> Any:
        return self._request("GET", "/api/v3/account", {"recvWindow": recv_window}, signed=True)

    def get_open_orders(self, symbol: Optional[str] = None, recv_window: Optional[int] = None) -> Any:
        return self._request(
            "GET", "/api/v3/openOrders", {"symbol": symbol, "recvWindow": recv_window}, signed=True
        )

    def get_trades(
        self, symbol: str, limit: Optional[int] = None, recv_window: Optional[int] = None
    ) -> Any:
        return self._request(
            "GET",
            "/api/v3/myTrades",
            {"symbol": symbol, "limit": limit, "recvWindow": recv_window},
            signed=True,
        )

    def place_order(
        self,
        symbol: str,
        side: str,
        order_type: str,
        quantity: Optional[float] = None,
        price: Optional[float] = None,
        time_in_force: Optional[str] = None,
        quote_order_qty: Optional[float] = None,
        recv_window: Optional[int] = None,
        test: bool = False,
    ) -> Any:
        payload: Dict[str, Any] = {
            "symbol": symbol.upper(),
            "side": side.upper(),
            "type": order_type.upper(),
            "quantity": quantity,
            "quoteOrderQty": quote_order_qty,
            "price": price,
            "timeInForce": time_in_force,
            "recvWindow": recv_window,
        }
        path = "/api/v3/order/test" if test else "/api/v3/order"
        return self._request("POST", path, payload, signed=True)

    def get_candles(
        self,
        symbol: str,
        interval: str,
        limit: Optional[int] = None,
        start_time: Optional[int] = None,
        end_time: Optional[int] = None,
    ) -> Any:
        params = {
            "symbol": symbol.upper(),
            "interval": interval,
            "limit": limit,
            "startTime": start_time,
            "endTime": end_time,
        }
        return self._request("GET", "/api/v3/klines", params, signed=False)


class StdioMCPServer:
    """Tiny JSON-RPC 2.0 server over stdio focused on Binance operations."""

    def __init__(self) -> None:
        pass

    def _dispatch(self, request: Dict[str, Any]) -> Dict[str, Any]:
        request_id = request.get("id")
        method = request.get("method")
        params = request.get("params") or {}

        try:
            result = self._handle_method(method, params)
            return {"jsonrpc": "2.0", "id": request_id, "result": result}
        except Exception as exc:  # pylint: disable=broad-except
            error_payload = exc.args[0] if exc.args else str(exc)
            return {"jsonrpc": "2.0", "id": request_id, "error": {"code": -32000, "message": error_payload}}

    def _handle_method(self, method: str, params: Dict[str, Any]) -> Any:
        if method == "ping":
            return {"pong": True, "time": int(time.time() * 1000)}

        if method == "get_account":
            client = self._client_from_params(params)
            return client.get_account(recv_window=params.get("recvWindow"))

        if method == "get_open_orders":
            client = self._client_from_params(params)
            return client.get_open_orders(
                symbol=params.get("symbol"), recv_window=params.get("recvWindow")
            )

        if method == "get_trades":
            client = self._client_from_params(params)
            symbol = params.get("symbol")
            if not symbol:
                raise ValueError("symbol is required for get_trades")
            return client.get_trades(
                symbol=symbol,
                limit=params.get("limit"),
                recv_window=params.get("recvWindow"),
            )

        if method == "place_order":
            client = self._client_from_params(params)
            symbol = params.get("symbol")
            side = params.get("side")
            order_type = params.get("type")
            if not symbol or not side or not order_type:
                raise ValueError("symbol, side, and type are required for place_order")
            return client.place_order(
                symbol=symbol,
                side=side,
                order_type=order_type,
                quantity=params.get("quantity"),
                quote_order_qty=params.get("quoteOrderQty"),
                price=params.get("price"),
                time_in_force=params.get("timeInForce"),
                recv_window=params.get("recvWindow"),
                test=bool(params.get("test", False)),
            )

        if method == "get_candles":
            symbol = params.get("symbol")
            interval = params.get("interval")
            if not symbol or not interval:
                raise ValueError("symbol and interval are required for get_candles")
            client = self._client_from_params(params, allow_missing_keys=True)
            return client.get_candles(
                symbol=symbol,
                interval=interval,
                limit=params.get("limit"),
                start_time=params.get("startTime"),
                end_time=params.get("endTime"),
            )

        raise ValueError(f"Unknown method: {method}")

    @staticmethod
    def _client_from_params(params: Dict[str, Any], allow_missing_keys: bool = False) -> BinanceClient:
        api_key = params.get("apiKey") or os.environ.get("BINANCE_API_KEY")
        api_secret = params.get("apiSecret") or os.environ.get("BINANCE_API_SECRET")
        base_url = params.get("baseUrl") or "https://api.binance.com"
        return BinanceClient(
            api_key=api_key,
            api_secret=api_secret,
            base_url=base_url,
            allow_public=allow_missing_keys,
        )

    def serve(self) -> None:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                self._write({"jsonrpc": "2.0", "id": None, "error": {"code": -32700, "message": "invalid JSON"}})
                continue
            response = self._dispatch(payload)
            self._write(response)

    @staticmethod
    def _write(message: Dict[str, Any]) -> None:
        sys.stdout.write(json.dumps(message, separators=(",", ":")) + "\n")
        sys.stdout.flush()


def main() -> None:
    server = StdioMCPServer()
    server.serve()


if __name__ == "__main__":
    main()
