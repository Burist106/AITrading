# Dependency security patch — 2026-09-09

The local-profile verification audit initially failed with two high-severity findings in existing transitive dependencies. Apply only compatible patch updates, retaining the direct package versions and supply-chain policies:

- `sharp` 0.35.3 → 0.35.4, including its matching platform packages and bundled libvips 1.3.3: [maintainer advisory](https://github.com/lovell/sharp/security/advisories/GHSA-rgj7-g3m4-5g8c).
- `js-yaml` 4.3.1 → 4.3.2: [advisory](https://github.com/advisories/GHSA-2883-xcg3-v3hh).

No audit exclusions or safety checks were disabled. After the lockfile updates, `pnpm audit --audit-level high` reported no known vulnerabilities. This is a dependency-database result at verification time, not a guarantee of vulnerability-free software.
