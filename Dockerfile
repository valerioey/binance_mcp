# Simple inspection-ready image for the Binance MCP stdio server.
FROM python:3.13-slim
WORKDIR /app
COPY binance_mcp_server.py README.md glama.json LICENSE ./
ENTRYPOINT ["python3", "/app/binance_mcp_server.py"]
