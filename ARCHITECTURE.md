# Angel One MCP architecture

The repository contains one Python service. Python reads run against Angel One on demand. The session token lives in process memory and the project has no application database.

| Path | Responsibility |
| --- | --- |
| `src/angel_one_mcp/server.py` | MCP stdio startup, typed tools, input validation, paging, and response limits |
| `src/angel_one_mcp/smartapi/` | Credential loading, authentication, and allowlisted Angel One HTTPS reads |
| `tests/` | Mocked broker requests and MCP security checks |
| `deploy/` | SSH account policy, session wrapper, and encrypted credential provisioning |
| `pyproject.toml`, `uv.lock` | Package configuration and locked Python dependencies |
| `Dockerfile`, `compose.*.yaml` | Source-mounted development and a built, non-root production image |

The dedicated SSH account accepts a pinned Ed25519 key and runs the fixed MCP wrapper. Production has no published port. The wrapper decrypts the host-bound broker bundle into a restricted runtime file under `/run`, mounts it read-only, and cleans it up when the session ends. The container mounts no data volume.

The broker client uses fixed HTTPS hosts, blocks redirects, sanitizes credential fields from tool responses, and rate-limits authenticated calls. Broker actions that modify the account are unavailable through MCP.

[Operations](OPERATIONS.md) · [VPS setup](MCP_SETUP.md)
