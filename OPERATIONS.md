# Operations

Run from the repository root:

```powershell
uv sync --locked
uv run --locked pytest
docker compose -f compose.dev.yaml --profile mcp config --quiet
docker compose -f compose.prod.yaml --profile mcp config --quiet
docker compose -f compose.dev.yaml --profile mcp build mcp
```

For a local stdio client, run `uv --directory <repository-path> run --locked angel-one-mcp`. `server_status` works without credentials. To test broker reads locally, give the process an `ANGEL_CREDENTIALS_FILE` path to a protected credential JSON file outside the checkout. On the VPS, use the encrypted bundle and forced SSH command in [MCP_SETUP.md](MCP_SETUP.md).

A local Compose client can use command `docker` with arguments `compose -f <absolute-compose.dev.yaml-path> run --rm -T mcp`. Restart the MCP process after Python source edits. If a minimal Windows client environment cannot locate the Docker Compose plugin, pass the absolute path to the user's `.docker` directory as `DOCKER_CONFIG`.

For a release check, initialize a stdio client, list the tools, call `server_status`, and confirm live access with `search_instruments` and `market_quote` over VPS SSH. Confirm an unlisted SSH key is denied.

The root package tests and both local Docker stdio checks passed with 15 read-only tools and no database. VPS deployment, SSH access on that host, and live SmartAPI credentials remain to be verified.
