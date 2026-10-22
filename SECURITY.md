# Security

Open Scout is designed for a single trusted user. Run it on loopback by default.
Use a strong API key, TLS reverse proxy, and network controls for remote access.
The initial release has not received an independent security audit.

Report suspected vulnerabilities privately through GitHub's repository security
reporting when enabled, or contact the repository owner. Do not include credentials,
private crawl data, or exploit targets in public issues.

Important boundaries: crawler requests must stay on public IPs, redirect checks must
remain enabled, retrieved text must never become executable UI markup or trusted
agent instructions, and authenticated deployments must protect all data routes.
