# PyE_P2P - Python Encrypted Peer-to-Peer

<div align="center">

![Python](https://img.shields.io/badge/Python-3.8%2B-blue?logo=python)
![License](https://img.shields.io/badge/License-MIT-green?logo=github)
![Status](https://img.shields.io/badge/Status-Planning-yellow)
![Platform](https://img.shields.io/badge/Platform-Windows%7CmacOS%7CLinux%7CMobile-blue?logo=linux)

<h3>An end-to-end encrypted P2P communication tool for any Python environment</h3>

Layered dependencies, zero-dependency mode, single-file deployment, mobile-first, open source, and transparent design.

[English](./README.md) | [中文](./README_ZH.md)

---

</div>

## Overview

**PyE_P2P** (Python Encrypted Peer-to-Peer) is a planned lightweight and portable peer-to-peer communication project.

Its core goal is simple:

> Enable secure P2P communication in any environment where Python runs, with minimal setup and a clear layered architecture.

Current repository contents are still exploratory. The codebase already contains a few focused utilities that will later plug into the full stack:

- `tools/ip_acquirer`: fetch public IP from multiple providers with simple retries, validation, and silent fastest-provider caching.
- `tools/explorer_core`: file and directory manager for reading, writing, listing, and searching with optional base64 encoding.
- `tools/terminal_panel`: desktop-only helper to bootstrap a terminal panel process.
- `net_core/handshake/token.py`: design notes for the handshake token layer.

## Repository Layout (current)

```text
PyE_P2P/
├─ net_core/
│  └─ handshake/token.py              # handshake token design stub
├─ tools/
│  ├─ ip_acquirer/                    # public IP fetcher + providers list
│  │  ├─ acquirer.py
│  │  └─ provider.json
│  ├─ explorer_core/                  # file/directory utilities
│  │  └─ file_manager.py
│  └─ terminal_panel/                 # desktop terminal panel bootstrap
│     └─ manager.py
└─ TODO/                              # docs for layout and purpose
   ├─ files.md
   └─ purpose.md
```

## Quick Usage (utilities available today)

- Public IP: `python tools/ip_acquirer/acquirer.py` prints the detected public IP and provider source; the provider file caches a hash and the fastest 60% of providers.
- File helper: `from tools.explorer_core.file_manager import FileManager` to read/write/manage files and folders.
- Terminal panel: desktop-only helper; see docstrings in `tools/terminal_panel/manager.py` for launching a panel process.

## Design Goals

- Layered implementations for UI, encryption, and networking.
- A zero-dependency mode based on the standard library.
- An advanced mode for stronger cryptography and richer UI options.
- A single-file deployment path for easy distribution.
- Support for terminal-first and mobile-friendly usage.

## Planned Architecture

The project is designed around three main layers:

- `ui_core`: TUI, Tkinter, and Qt front ends.
- `encrypt_core`: low- and high-security encryption backends.
- `net_core`: handshake, session, and transport logic.

### Dependency Strategy

| Layer | Low Mode | High Mode |
|---|---|---|
| UI | TUI, Tkinter | Qt |
| Encryption | XOR, PBKDF2, HMAC | AES-GCM, ECDH, Argon2 |
| Network | `threading` | `asyncio` |

### Intended Flow

1. Manual secret exchange.
2. Handshake and peer verification.
3. Key exchange.
4. Session setup.
5. Message transfer and heartbeat.
6. Session close and desync handling.

## Target Features

| Feature | Description | Status |
|---|---|---|
| Layered dependencies | Switch between standard-library and advanced implementations | Planned |
| Mobile-friendly UI | Terminal-first experience for mobile terminals such as Termux | Planned |
| Single-file deployment | Merge the project into one file for easy copying and running | Planned |
| Dual crypto backends | Low mode and high mode encryption backends | Planned |
| P2P direct connection | No relay server required | Planned |
| File transfer | Chunked transfer and resume support | Planned |
| Multi-UI support | TUI, Tkinter, and Qt | Planned |
| Zero-dependency mode | Standard-library-only operation | Planned |

## Configuration

Planned environment variables:

| Variable | Default | Description |
|---|---|---|
| `PYE_MODE` | `auto` | Encryption mode: `low`, `high`, or `auto` |
| `PYE_UI` | `tui` | UI type: `tui`, `tk`, or `qt` |
| `PYE_SYNC` | `strict` | Synchronization strategy |

Example configuration file:

```json
{
  "encryption": {
    "mode": "high",
    "key_length": 32,
    "kdf_iterations": 100000
  },
  "network": {
    "bind_address": "0.0.0.0",
    "port_range": [5000, 6000],
    "timeout": 30
  },
  "security": {
    "strict_sync": true,
    "log_level": "info"
  }
}
```

## Security Statement

This project is intended for learning, prototyping, and controlled private communication scenarios.

- The code should remain fully auditable.
- The low-security backend is for compatibility and educational purposes.
- The high-security backend should be preferred for serious use.
- Users must follow applicable laws and regulations.

## Development Roadmap

### Phase 1

- Project architecture design
- Encryption interface abstraction
- Socket-based communication framework
- Finite state machine management

### Phase 2

- File transfer with resume support
- TUI improvements
- Cross-platform compatibility testing

### Phase 3

- Mobile-optimized lightweight build
- Single-file bundling workflow
- Full documentation and API reference

## Contributing

Contributions will be welcomed once the implementation is ready.

Suggested areas:

- networking and protocol design
- encryption backend implementation
- UI prototyping
- documentation and testing

## License

MIT License.

## Notes

This repository currently reflects the planning stage rather than a finished implementation.

---
