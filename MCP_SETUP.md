# Private Angel One MCP on the VPS

One Docker container serves all Codex and Antigravity sessions. Each client uses MCP stdio over its existing SSH alias. The forced SSH command relays that connection to a private Unix socket. The service exposes no TCP port.

## 1. Prepare the VPS and stop the old clients

Run as the VPS administrator. These commands assume Ubuntu with systemd, Docker Compose v2, and the root-owned checkout at `/root/closing-cross-git`. Close the old MCP clients before upgrading. Keep your administrator SSH session open.

```bash
cd /root/closing-cross-git
git pull --ff-only
apt-get update && apt-get install -y socat
docker compose -p closing-cross-prod -f compose.prod.yaml config --quiet
docker compose -p closing-cross-prod -f compose.prod.yaml build mcp
```

Run this once when upgrading from the previous per-client containers. The filters select only this Compose project's old MCP one-off containers.

```bash
docker ps -q --filter label=com.docker.compose.project=closing-cross-prod \
  --filter label=com.docker.compose.service=mcp \
  --filter label=com.docker.compose.oneoff=True | xargs -r docker stop
```

## 2. Prepare the restricted SSH account and credentials

Keep your existing encrypted bundle at `/etc/closing-cross/angel.json.cred`. If it is missing, run the provisioning script on the VPS and enter the Angel One API key, client code, PIN, and Authenticator setup key. The input is hidden.

```bash
if [ ! -s /etc/closing-cross/angel.json.cred ]; then
  bash deploy/provision-angel-credentials
fi

getent group closing-mcp >/dev/null || groupadd --system closing-mcp
if id closing-mcp >/dev/null 2>&1; then
  usermod -aG closing-mcp closing-mcp
else
  useradd --system --gid closing-mcp --home-dir / --no-create-home --shell /bin/sh closing-mcp
fi
```

For a first-time client, create a dedicated Ed25519 key on Windows. Keep the private key on Windows and load a passphrase-protected key into the Windows SSH agent.

```powershell
ssh-keygen -t ed25519 -f "$env:USERPROFILE\.ssh\angel-one-mcp" -C "angel-one-mcp"
ssh-add "$env:USERPROFILE\.ssh\angel-one-mcp"
Get-Content "$env:USERPROFILE\.ssh\angel-one-mcp.pub"
```

The VPS reads public keys from `/etc/ssh/closing-cross-mcp.keys`. Reuse the existing file if already configured. For a new key, create the file as root with mode `0644` and add the public key on its own line with the `restrict ` prefix.

```bash
touch /etc/ssh/closing-cross-mcp.keys
chown root:root /etc/ssh/closing-cross-mcp.keys
chmod 0644 /etc/ssh/closing-cross-mcp.keys
sudoedit /etc/ssh/closing-cross-mcp.keys
```

## 3. Start the shared service

```bash
install -o root -g root -m 0755 deploy/closing-cross-mcp /usr/local/sbin/closing-cross-mcp &&
install -o root -g root -m 0644 deploy/closing-cross-mcp.service /etc/systemd/system/closing-cross-mcp.service &&
install -o root -g root -m 0644 deploy/closing-cross-mcp.sshd.conf /etc/ssh/sshd_config.d/90-closing-cross-mcp.conf &&
sshd -t &&
systemctl reload ssh &&
rm -f -- /etc/sudoers.d/closing-cross-mcp &&
systemctl daemon-reload &&
systemctl enable --now closing-cross-mcp.service
```

If your VPS uses an `AllowUsers` allowlist, include `closing-mcp`. The account needs the dedicated socket group and should have no administrative or Docker group memberships. Check the effective policy and service:

```bash
systemctl status closing-cross-mcp.service --no-pager
docker compose -p closing-cross-prod -f compose.prod.yaml ps mcp
sshd -T -C user=closing-mcp,host=localhost,addr=127.0.0.1 |
  grep -E '^(forcecommand|authenticationmethods|disableforwarding|permittty|authorizedkeysfile) '
```

Expect one healthy container, the fixed `/usr/local/sbin/closing-cross-mcp` command, public-key authentication, and forwarding disabled. If the service cannot start, use `journalctl -u closing-cross-mcp.service -n 50 --no-pager` on the VPS.

Put optional IP headers in root-owned `/etc/closing-cross/mcp.env`. For updates, rebuild the image, then run `systemctl restart closing-cross-mcp.service`. To rotate credentials, rerun the provisioning script and restart the same service. Systemd decrypts the bundle at service startup. The runtime credential is mounted read-only and removed when the service stops.

## 4. Connect a stdio MCP client

Add this to the client's `~/.ssh/config`, substituting the same verified VPS host you use for administrative SSH:

```sshconfig
Host angel-one-mcp
    HostName YOUR_VPS_IP_OR_HOST
    User closing-mcp
    IdentityFile ~/.ssh/angel-one-mcp
    IdentitiesOnly yes
    StrictHostKeyChecking yes
    BatchMode yes
    ClearAllForwardings yes
    RequestTTY no
```

Verify the VPS host fingerprint against the administrator session and establish the host entry in `known_hosts` before starting the client. When logging in for the first time from the same client, use your normal interactive admin SSH command and accept the host key only after comparing the fingerprint.

For an MCP client with a JSON `mcpServers` configuration, use:

```json
{
  "mcpServers": {
    "angel-one-private": {
      "command": "ssh",
      "args": ["-T", "angel-one-mcp"]
    }
  }
}
```

On Windows, set the command to `C:\Windows\System32\OpenSSH\ssh.exe` if the client cannot find it. If it cannot resolve the alias, add `-F` and the absolute path to your Windows SSH config before `-T` in the argument list. If your client uses a form, choose **stdio**, use command `ssh`, and enter each argument separately. Restart the client and call `server_status`, then `search_instruments` with `{"exchange":"NSE","query":"RELIANCE"}`. Use the returned equity token with `market_quote`, for example `{"mode":"LTP","exchange_tokens":{"NSE":["2885"]}}`. Codex and Antigravity can stay connected at the same time. They share the container and the Angel One login. A URL-only cloud MCP client cannot connect to this setup. Connected clients may send holdings, balances, or trades to their model provider or retain them in chat history. Use a client and account whose data handling you trust.

To revoke access, remove the public-key line from `/etc/ssh/closing-cross-mcp.keys` and terminate any active SSH connection using that key. A login using an unlisted key should return `Permission denied (publickey)`. A request to open a shell or run another command still launches the fixed MCP command. SSH forwarding is disabled for the dedicated account.

## Available tools

| Area | Tools and data |
| --- | --- |
| Instruments and quotes | `search_instruments`, `instrument_master` (filtered public instrument master), `market_quote` (LTP, OHLC, full quote), `instrument_lists` (NSE/BSE intraday lists and cautionary scrips) |
| Historical and derivatives | `historical_data` (candles or historical OI), `option_greeks`, `derivatives_snapshot` (PCR, price/OI movers, OI buildup) |
| Account | `account_snapshot` (profile, funds, holdings, all holdings, positions, order book, trade book), `order_details`, `gtt_rules`, `gtt_rule_details`, `edis_transaction_status` |
| Calculators | `estimate_margin`, `estimate_charges` for hypothetical trades |
| Connectivity | `server_status` checks the MCP connection without starting a broker session |

Dates and times passed to historical tools are local IST without an offset. Historical data and selected list tools take `limit` and `offset`; their list results give `next_offset` where more rows exist. Broker entitlements and exchange segment rules still apply. The tool set covers named read-only REST operations, including live quote snapshots. Continuous broker WebSocket streams and a bulk export of the full instrument master are outside this version. Order and GTT actions, position conversion, fund movement, and eDIS authorizations are outside the read-only scope. [Angel One SmartAPI](https://smartapi.angelone.in/docs) · [MCP stdio transport](https://py.sdk.modelcontextprotocol.io/v1/)

