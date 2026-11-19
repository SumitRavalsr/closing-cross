# Repository instructions

Start with [OPERATIONS.md](OPERATIONS.md) for development and verification, [MCP_SETUP.md](MCP_SETUP.md) for VPS setup and client access, and [ARCHITECTURE.md](ARCHITECTURE.md) for service boundaries.

- Keep the Python package under `src/angel_one_mcp/`, tests under `tests/`, and VPS provisioning under `deploy/`.
- Run `uv sync --locked` and `uv run --locked pytest` from the repository root. Include `uv.lock` with dependency changes.
- Keep MCP tool schemas separate from broker authentication and requests. Broker integration uses explicitly allowed read-only endpoints.
- Use `compose.dev.yaml` for source-mounted development and `compose.prod.yaml` for built production images. Validate both files and exercise MCP startup when changing container wiring.
- Keep VPS broker credentials in the encrypted bundle and mount the runtime file read-only. Keep real environment files, credentials, tokens, and generated dependency directories out of Git and image build contexts. Update `.env.example` and setup docs when configuration changes.
