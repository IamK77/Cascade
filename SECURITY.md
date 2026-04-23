# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 0.2.x   | Yes                |
| < 0.2   | No                 |

## Reporting a Vulnerability

If you discover a security vulnerability in Cascade, please report it responsibly.

**Contact:** [security@autoseek.vip](mailto:security@autoseek.vip)

Please include:

- A description of the vulnerability and its potential impact
- Steps to reproduce the issue
- Affected version(s)
- Any suggested fix, if available

**Response timeline:**

- Acknowledgement within **3 business days**
- Initial assessment within **10 business days**
- Fix or mitigation communicated within **30 days** for confirmed vulnerabilities

We ask that you do not publicly disclose the vulnerability until a fix has been released.

## Security Model

Cascade is designed to run in a **trusted, single-machine environment**. The following assumptions and boundaries apply:

- **File-based storage with fcntl locking.** All graph and event data is persisted to local files (`graph.json`, `events.jsonl`). Concurrent access is coordinated via `fcntl` file locks, which are effective only on a single host.
- **No authentication on the tool API.** The 12 LLM-facing tools (`add_node`, `finish_task`, etc.) do not perform authentication or authorization. Cascade assumes all callers are trusted.
- **Token files are not access-controlled.** Any process with filesystem access to the `.cascade/` directory can read or modify stored data.
- **No encryption at rest.** Graph state and event logs are stored as plain JSON/JSONL. Sensitive data should not be placed in node descriptions, context fields, or artifacts without external encryption.

## Known Limitations

| Limitation | Details |
| --- | --- |
| Unix-only file locking | `fcntl` locks are not available on Windows. Cascade does not currently support Windows environments. |
| No distributed locking | File locks are local to a single machine. Running multiple Cascade instances against shared networked storage (e.g., NFS) is not safe. |
| No data encryption at rest | `graph.json` and `events.jsonl` are stored in plaintext. Use OS-level disk encryption if data confidentiality is required. |

## License

Cascade is licensed under the Apache License, Version 2.0.

Copyright 2026 Hangzhou Autoseek Information Technology Co., Ltd.

See [LICENSE](LICENSE) for the full license text.
