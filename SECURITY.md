# Security policy

## Supported version

Security fixes are applied to the latest commit on the default branch. The project is currently pre-1.0 and does not promise fixes for older revisions.

## Reporting a vulnerability

Use GitHub's **Report a vulnerability** private security-advisory form for this repository. Please do not disclose the issue publicly until a fix or mitigation is available.

Include a minimal reproduction, affected commit, expected impact, and any safe diagnostic output. Never include real search queries, credentials, proxy secrets, `.env` contents, private URLs, cookies, or unrelated local data.

Privacy-boundary bypasses, direct-egress paths, SSRF, query leakage, unsafe log persistence, prompt-injection escapes, and destructive data-deletion bugs are considered security issues.

## Scope and limitations

The project reduces exposure; it does not guarantee anonymity. The documented threat model excludes a compromised host, hostile Docker daemon, compromised dependencies, global traffic correlation, identifiable queries, authenticated destination activity, and malicious Tor exits. See [docs/THREAT_MODEL.md](docs/THREAT_MODEL.md) before deploying it for sensitive research.
