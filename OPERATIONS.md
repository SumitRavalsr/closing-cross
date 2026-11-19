# Operations

Run from the repository root:

```powershell
uv sync --locked
uv run --locked pytest
docker compose -f compose.dev.yaml --profile mcp config --quiet
docker compose -f compose.prod.yaml config --quiet
docker compose -f compose.dev.yaml --profile mcp build mcp
```

For a local stdio client, run `uv --directory <repository-path> run --locked angel-one-mcp`. `server_status` works without credentials. To test broker reads locally, give the process an `ANGEL_CREDENTIALS_FILE` path to a protected credential JSON file outside the checkout. On the VPS, use the encrypted bundle and forced SSH command in [MCP_SETUP.md](MCP_SETUP.md).

A local Compose client can use command `docker` with arguments `compose -f <absolute-compose.dev.yaml-path> run --rm -T mcp`. Restart the MCP process after Python source edits. If a minimal Windows client environment cannot locate the Docker Compose plugin, pass the absolute path to the user's `.docker` directory as `DOCKER_CONFIG`. Verify live tool visibility with `server_status` and `tools/list`. The tests use mocked broker requests to verify trading without placing live orders.

For a VPS release check, connect Codex and Antigravity at the same time, call `server_status` and `market_quote` from each, and confirm `docker compose -p closing-cross-prod -f compose.prod.yaml ps mcp` shows one container. Confirm an unlisted SSH key is denied.

The Windows tests exercise simultaneous MCP sessions over localhost and confirm that they reuse one mocked Angel One login. The same test uses the Unix socket on Linux. Run the VPS release check after deployment.
