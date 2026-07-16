# Privacy

## What stays local

Planning, ranking, coverage/contradiction analysis, evidence, SQLite, models, dashboard metrics, and final synthesis by LM Studio remain local. The system does not call a cloud LLM or commercial search API and has no intentional telemetry.

## What leaves the machine

Search queries leave through `tor-search` to enabled SearXNG engines. Selected page requests leave through `tor-fetch` to destination websites. Tor directory/relay traffic also leaves. No other container has an external network.

| Container | Internal network | Direct egress network | Purpose |
|---|---:|---:|---|
| app | yes | no | MCP, pipeline, storage |
| mcp-bridge | yes | default-deny/no-masquerade loopback bridge | localhost-only ingress |
| searxng | yes | no | URL discovery; proxy to tor-search |
| browser-service | yes | no | optional ephemeral rendering; proxy to tor-fetch |
| tor-search | yes | egress_search | search traffic only |
| tor-fetch | yes | egress_fetch | page traffic only |

The `internal_private` network has `internal: true`. A minimal TCP sidecar exposes port 8088 only on `127.0.0.1`; it installs a default-deny OUTPUT policy, permits only the app and established replies, and then drops to UID 10001. Its second bridge also has IP masquerading disabled. SOCKS proxy hostnames keep public DNS resolution inside Tor.

## Storage and logs

The `research-data` volume contains SQLite caches/evidence. Default retention is seven days. Search history and raw query logs are off. URL-bearing HTTP client logs are suppressed, and SearXNG's Docker logging driver is disabled because engine failures can otherwise render the query URL. Normal request records contain a short SHA-256 fingerprint and opaque request ID. Browser profiles/cookies are never persisted.

Use MCP `clear_local_data(confirm=true)` for selective deletion. To delete the entire volume, stop Compose and explicitly remove `private-research-mcp_research-data`.

## Verification

Run `.\scripts\privacy-test.ps1`. It checks topology, loopback publication, configuration, direct app egress, query logging, and forbidden cloud endpoints. To inspect manually:

```powershell
docker network inspect private-research-mcp_internal_private
docker inspect private-research-mcp-app-1
docker compose config
```

Stopping either Tor gateway must make its traffic fail. The release test records this behavior; no code path enables direct fallback.

## External observations

Search engines can observe query text and a search exit IP. Destination sites observe fetch paths and a different exit IP. Timing correlation is possible. Plain HTTP is visible to exits. See the threat model for ISP, exit-node, fingerprinting, and host-compromise limitations.
