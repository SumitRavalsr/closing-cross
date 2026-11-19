# Private Angel One MCP on the VPS

The server uses MCP over SSH stdio. It listens on no HTTP port. A dedicated OpenSSH account accepts your pinned Ed25519 key and runs one fixed command. The app runs as UID 65532 inside Docker and reads data directly from Angel One.

## 1. Deploy from the VPS administrator account

These commands assume Ubuntu, Docker Compose v2, `systemd-creds`, OpenSSH, and the existing root-owned checkout at `/root/closing-cross-git`. Publish the tested commit to the branch your VPS tracks first. Keep your current administrator SSH session open while setting up the dedicated account.

```bash
cd /root/closing-cross-git
git pull --ff-only
docker compose -p closing-cross-prod -f compose.prod.yaml --profile mcp build mcp
```

For a VPS upgrading from the retired scanner, stop its systemd timer and service if installed. Then remove the old Compose containers and the old database volume. Deleting this volume permanently removes the VPS scanner history. Check the project and volume labels before deleting it. The MCP image starts when the client connects.

```bash
if systemctl cat closing-cross-forward.timer >/dev/null 2>&1; then
  systemctl disable --now closing-cross-forward.timer
fi
if systemctl cat closing-cross-forward.service >/dev/null 2>&1; then
  systemctl stop closing-cross-forward.service
fi
docker compose -p closing-cross-prod -f compose.prod.yaml --profile mcp down --remove-orphans
if docker volume inspect closing-cross-prod_sqlite >/dev/null 2>&1; then
  owner=$(docker volume inspect --format '{{index .Labels "com.docker.compose.project"}} {{index .Labels "com.docker.compose.volume"}}' closing-cross-prod_sqlite)
  if [ "$owner" = "closing-cross-prod sqlite" ]; then
    docker volume rm closing-cross-prod_sqlite
  else
    echo "Unexpected database volume labels. Check ownership before removing the volume." >&2
  fi
fi
```

Check the retired dashboard listener with `ss -ltn 'sport = :8080'`. Disable any separate dashboard proxy or tunnel.

## 2. Provision broker credentials

Run this from an interactive VPS admin terminal. Input is hidden. The helper encrypts the API key, client code, PIN, and Authenticator **setup key** into `/etc/closing-cross/angel.json.cred` using the VPS systemd host key. At connection time, the wrapper decrypts it into a root-controlled directory under `/run`, mounts the file read-only, and removes the plaintext host file when the session ends. The broker token stays in the MCP process.

```bash
install -o root -g root -m 0755 deploy/closing-cross-mcp /usr/local/sbin/closing-cross-mcp
bash deploy/provision-angel-credentials
```

If you use an IP header in your existing SmartAPI configuration, create `/etc/closing-cross/mcp.env` with `ANGEL_PUBLIC_IP` set to your VPS's registered IP. Keep it root-owned and use it for the optional broker IP headers. Angel One receives traffic from the VPS, so register that egress IP where your SmartAPI key requires it.

Run the provisioning command again to rotate the credentials. Close the MCP client before rotating so the next session uses the new bundle. Remove the legacy broker values from `backend/.env.production` and any old deployment copies. Revoke or replace values that were shared or stored somewhere you no longer control. A root or Docker administrator can access the running workload and the VPS host key. Protect those administrative accounts and any machine backups accordingly.

## 3. Give your client a restricted SSH key

On Windows PowerShell, generate a dedicated key. Use a passphrase and load it into your SSH agent before starting the MCP client.

```powershell
ssh-keygen -t ed25519 -f "$env:USERPROFILE\.ssh\angel-one-mcp" -C "angel-one-mcp"
ssh-add "$env:USERPROFILE\.ssh\angel-one-mcp"
Get-Content "$env:USERPROFILE\.ssh\angel-one-mcp.pub"
```

If `ssh-add` reports that the Windows agent is unavailable, start the OpenSSH Authentication Agent service from an administrator PowerShell and rerun `ssh-add`. Keep the private key on the client. On the VPS, create a dedicated account with a locked password and an ordinary shell so SSH can launch its forced command. Create the key file once and put the single public key on one line, prefixed by `restrict ` (for example `restrict ssh-ed25519 AAAA... angel-one-mcp`).

```bash
id closing-mcp >/dev/null 2>&1 || useradd --system --home-dir / --no-create-home --shell /bin/sh closing-mcp
passwd -l closing-mcp
umask 077
touch /etc/ssh/closing-cross-mcp.keys
chown root:root /etc/ssh/closing-cross-mcp.keys
chmod 0644 /etc/ssh/closing-cross-mcp.keys
sudoedit /etc/ssh/closing-cross-mcp.keys

visudo -cf deploy/closing-cross-mcp.sudoers &&
install -o root -g root -m 0440 deploy/closing-cross-mcp.sudoers /etc/sudoers.d/closing-cross-mcp &&
install -o root -g root -m 0644 deploy/closing-cross-mcp.sshd.conf /etc/ssh/sshd_config.d/90-closing-cross-mcp.conf &&
sshd -t &&
systemctl reload ssh
```

Make sure the dedicated account has no administrative group memberships. Check the effective SSH policy for this account. If your VPS uses an `AllowUsers` allowlist, include `closing-mcp`.

```bash
sshd -T -C user=closing-mcp,host=localhost,addr=127.0.0.1 |
  grep -E '^(forcecommand|authenticationmethods|pubkeyacceptedalgorithms|passwordauthentication|disableforwarding|permittty|authorizedkeysfile) '
ssh-keygen -lf /etc/ssh/ssh_host_ed25519_key.pub
```

Expect the forced wrapper, public-key authentication, forwarding disabled and a custom authorized-keys file. Keep the default SSH and sudo audit policy. A host configured to capture sudo input or output can retain private MCP traffic, so account for that before using sensitive tools.

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

If your client uses a form, choose **stdio**, use command `ssh`, and enter each argument separately. Restart the client and call `server_status`, then `search_instruments` with `{"exchange":"NSE","query":"RELIANCE"}`. Use the returned equity token with `market_quote`, for example `{"mode":"LTP","exchange_tokens":{"NSE":["2885"]}}`. Only one broker session runs at once. Close the first client before switching to another. A URL-only cloud MCP client cannot connect to this setup. Connected clients may send holdings, balances, or trades to their model provider or retain them in chat history. Use a client and account whose data handling you trust.

To revoke access, remove the public-key line from `/etc/ssh/closing-cross-mcp.keys` and terminate any current session for the dedicated account. A login using an unlisted key should return `Permission denied (publickey)`. A request to open a shell or run another command still launches the fixed MCP command. SSH forwarding is disabled for the dedicated account.

## Available tools

| Area | Tools and data |
| --- | --- |
| Instruments and quotes | `search_instruments`, `instrument_master` (filtered public instrument master), `market_quote` (LTP, OHLC, full quote), `instrument_lists` (NSE/BSE intraday lists and cautionary scrips) |
| Historical and derivatives | `historical_data` (candles or historical OI), `option_greeks`, `derivatives_snapshot` (PCR, price/OI movers, OI buildup) |
| Account | `account_snapshot` (profile, funds, holdings, all holdings, positions, order book, trade book), `order_details`, `gtt_rules`, `gtt_rule_details`, `edis_transaction_status` |
| Calculators | `estimate_margin`, `estimate_charges` for hypothetical trades |
| Connectivity | `server_status` checks the MCP connection without starting a broker session |

Dates and times passed to historical tools are local IST without an offset. Historical data and selected list tools take `limit` and `offset`; their list results give `next_offset` where more rows exist. Broker entitlements and exchange segment rules still apply. The tool set covers named read-only REST operations, including live quote snapshots. Continuous broker WebSocket streams and a bulk export of the full instrument master are outside this version. Order and GTT actions, position conversion, fund movement, and eDIS authorizations are outside the read-only scope. [Angel One SmartAPI](https://smartapi.angelone.in/docs) · [MCP stdio transport](https://py.sdk.modelcontextprotocol.io/v1/)

