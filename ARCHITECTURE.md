# Angel One MCP architecture

The repository contains one Python service. Broker requests run against Angel One on demand. Session, refresh, and feed tokens live in process memory and the project has no application database.

| Path | Responsibility |
| --- | --- |
| `src/angel_one_mcp/server.py` | MCP routing, typed tools, input validation, paging, and response limits |
| `src/angel_one_mcp/smartapi/` | Credential loading, authentication, allowlisted HTTPS actions and reads, and WebSocket capture |
| src/angel_one_mcp/socket_transport.py | Private socket listener with separate MCP protocol sessions |
| 	ests/ | Mocked broker requests and MCP security checks |
| `deploy/` | SSH account policy, session wrapper, and encrypted credential provisioning |
| `pyproject.toml`, `uv.lock` | Package configuration and locked Python dependencies |
| `Dockerfile`, `compose.*.yaml` | Source-mounted development and a built, non-root production image |

The dedicated SSH account accepts a pinned Ed25519 key and runs an unprivileged socket relay. A systemd service starts one non-root Docker container and manages the decrypted runtime credential under `/run`. The container mounts the credential read-only and binds a Unix socket in a separate group-restricted directory. The SSH account can connect to the socket without Docker or sudo access. Each SSH connection gets its own MCP protocol session. The sessions share one broker client, login token, and request limiter. There are no published TCP ports.

The broker client uses fixed Angel One hosts, blocks redirects, sanitizes credential fields from tool responses, and rate-limits REST requests. It can refresh expired sessions for reads. Every authorized MCP client can call the live account tools. Each write is sent once. After an error, check broker state before attempting it again. Each WebSocket capture holds a slot for its feed and releases it when the tool returns. REST requests can run during a capture.

[Operations](OPERATIONS.md) · [VPS setup](MCP_SETUP.md)
