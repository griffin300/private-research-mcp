# Threat model

## Protected assets

Research questions, browsing sequences, evidence, local model prompts, machine identifiers, secrets, and host files are protected. The system assumes the Windows host, Docker Desktop, and checked-in code are trusted at startup.

## Network observers

- **ISP/local network:** can observe Tor connections and timing/volume, not plaintext destinations within Tor. Tor usage itself is visible.
- **Search engines:** see a `tor-search` exit and the submitted query. They may fingerprint request behavior or present CAPTCHAs.
- **Destination sites:** see a different `tor-fetch` exit, requested path, timing, and HTTP/browser fingerprint. Authentication can identify the user.
- **Tor exits:** can observe plaintext HTTP and destinations; HTTPS protects content integrity/confidentiality from the exit. A malicious exit remains possible.
- **Global/colluding observers:** may correlate search and fetch timing despite separate gateways. Separation reduces easy linkage; it does not eliminate correlation.

## Application threats

- SSRF controls block schemes, credentials, local/internal hostnames, literal private/special IPs, unusual numeric IPs, and unsafe redirects. Tor-routed DNS means the app intentionally does not resolve public names locally; Docker network isolation and non-routability of private destinations through exits form additional layers. Allowing private destinations is development-only.
- Prompt injection is treated as untrusted page data. Scripts/styles/comments/forms/hidden content are stripped; visible override/tool/secret instructions are scored and high-risk passages are quarantined. Detection is heuristic and can have false negatives.
- Search-result poisoning and SEO spam are mitigated by engine agreement, source type, primary-source preference, page content, deduplication, and explicit coverage—not a permanent domain whitelist.
- Browser state is destroyed per page. Media, fonts, trackers, downloads, service workers, WebRTC, permissions, and persistent profiles are blocked or disabled where possible. Browser fingerprinting remains possible.
- Decompression/response abuse is limited by content-type, byte, redirect, timeout, and archive/binary rejection. Library-level decompression happens before application byte counting, so container memory limits are an additional boundary.

## Local compromise

Local malware, an administrative Docker user, Docker daemon compromise, hostile kernel, modified images, or dependency compromise can defeat controls. Containers have dropped capabilities, no Docker socket, no privileged mode, read-only roots, bounded writable mounts, and resource limits. The localhost ingress sidecar is the sole exception: it receives `NET_ADMIN` only within its own network namespace to install a default-deny egress policy, then drops to UID 10001 before proxying. Image/dependency pins reduce drift but do not replace vulnerability review or SBOM/signature verification.

## Anonymity limitations

Tor is not marketed here as perfect anonymity. Highly identifying queries, login cookies supplied by a user, browser exploits, traffic correlation, and a compromised host can reveal identity. The project improves privacy and enforces fail-closed routing; it cannot guarantee anonymity.
