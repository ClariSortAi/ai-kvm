# AI KVM documentation

Start with the [project README](../README.md) for the hardware path, console and MCP commands.

| Document | Purpose |
|---|---|
| [Setup and qualification](getting-started.md) | Install, flash, pair, test input, record BIOS recovery and troubleshoot. |
| [Bench contract](bench-protocol.md) | Protocol fields, action bounds, stop behavior and evidence requirements. Its firmware version header records the earlier 0.2.0 contract. |
| [Headless architecture](../ai-kvm-headless-mcp-design.md) | Architecture and proposed extensions. |
| [Dependency inventory](../THIRD_PARTY.md) | Pinned components and upstream license references. |
| [Initial readiness, 2026-10-22](readiness-2026-10-22.md) | Dated development evidence. |
| [Wireless and BIOS readiness, 2026-10-22](readiness-wireless-bios-2026-10-22.md) | Dated readiness and physical test boundaries. |

The README records the 2026-10-27 optical BIOS navigation and 2026-10-28 desktop input results. Those tests apply to the named target and installed firmware; they do not establish BIOS reboot recovery or compatibility with all targets.
