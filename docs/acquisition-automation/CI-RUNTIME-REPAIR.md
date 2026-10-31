# CI runtime repair — October 31, 2026

Isolated repair candidate based on f793a05 (includes deterministic bot challenge test fix). No acquisition feature commits are included.

Run 41252309134 job 124688164617 completed cancelled at 23:48:26 UTC after the 25-minute job limit. Its log stopped in apt update while fetching packages from http://azure.archive.ubuntu.com/ubuntu; no database acceptance test ran. This job was not manually cancelled or restarted.

The PostgreSQL-16 setup step now replaces that specific Azure mirror with Ubuntu's HTTPS archive on the disposable runner, preserves repository signature validation, uses two retries and 30-second HTTP/HTTPS timeouts, and has a five-minute setup budget. Package versions and all acceptance steps remain intact. No production configuration changes.

APT option references: [apt.conf](https://manpages.debian.org/trixie/apt/apt.conf.5.en.html) and [HTTP transport timeouts](https://manpages.debian.org/trixie/apt/apt-transport-http.1.en.html). Local validation checks workflow parsing and shell syntax. Real Linux package install and all six jobs must pass in the successor run before any feature publication.
