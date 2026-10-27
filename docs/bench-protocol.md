# Bench implementation contract

Firmware version: `0.2.0`; wire protocol: `1`. Target: XIAO ESP32S3 8MB flash. One image selects a persisted USB profile before USB starts. `desktop` exposes CDC and keyboard/mouse/absolute reports (IDs 1/2/7). `bios` exposes only a boot keyboard with eight-byte, no-ID reports. `bios_mouse` exposes only a boot mouse, with five-byte report mode and three-byte boot mode. SET_PROTOCOL, GET_REPORT, output LEDs and keyboard SET_IDLE are handled. Actual target compatibility is accepted through the live qualification console, not inferred from descriptors.

## Wire

USB CDC at 115200 baud, or authenticated TLS over Wi-Fi: one JSON object per newline, maximum line length 1536 bytes. USB setup exists only in `desktop`. The board joins its provisioned 2.4GHz WPA network and initiates an outbound TLS 1.2 PSK connection to the paired controller. Cipher: PSK-AES128-GCM-SHA256, key: random 256 bits, identity: `aikvm-<device_id>`. No unauthenticated board listener or inference endpoint exists. Network/TLS handshakes run in a separate task so they cannot block the executor's lease checks.

Physical, disarmed USB accepts `provision` with SSID, password, controller IPv4/port, identity and PSK, or `clear_pairing`. Credentials are never returned. NVS stores the device configuration; this prototype does not enable flash encryption. The controller saves its pairing key using current-user Windows DPAPI, and does not save the Wi-Fi password. Provisioning preserves the same controller key through an acknowledgment-loss retry. The same authenticated command executor serves both transports; a live armed owner rejects another transport's handshake.

The disarmed session operation `profile` persists `desktop`, `bios` or `bios_mouse` for the next physical USB reconnection. HID-only profiles require pairing first. Profile changes do not reflash or erase NVS. Full merged-image flashing replaces all flash contents, including pairing.

`{"v":1,"op":"hello"}` releases input, disarms, invalidates any prior session and returns a random session identifier, firmware version, efuse device ID and HID readiness. This is intentionally a state-changing handshake, not an in-session status poll.

Sequenced commands carry `v`, `session`, `seq`, `op` and operation arguments. The first sequence is 1. `arm` requires enumerated HID. A session remains disarmed until that command. Subsequent sequences must increment by one; rejection consumes a valid next sequence too. The device caches the last exact JSON line/result. Repeating that exact sequence/payload returns the cached result; changed payloads and other old sequences are rejected. A new handshake, STOP, lease expiry or board restart invalidates this scope. There is no exactly-once guarantee across reset/power loss.

`ping` is unsequenced but requires the session. It refreshes the two-second input lease only while armed and returns state. The controller heartbeats independently every 250ms. `stop` is unsequenced and session-independent within physical USB or an authenticated TLS connection: release keys/buttons and invalidate the active session. The controller follows an acknowledged stop with a fresh disarmed handshake. Transport loss invalidates ownership even when disarmed; reconnect never rearms or replays input. Device hello exposes separate lease/disconnect/hold-expiry counters for diagnostics.

## Operations

| Operation | Arguments / limits |
|---|---|
| `type` | One ASCII character in `text`; printable US ASCII, newline or tab. Bridge splits bounded strings of 1–80 characters; stop can interrupt between characters. |
| `press` | `keys`: 1–6 supported names/characters, pressed as a chord and released. |
| `key_down`, `key_up` | `key`: supported name/character. Explicit holds share a 1.5s maximum lifetime from the first hold; heartbeat does not extend it. |
| `move` | `dx`, `dy`: integer HID counts, each -127..127. |
| `move_abs` | Wire `x`, `y`: integers 0..32767. MCP coordinates instead reference the observation image and are mapped by the bridge. |
| `click`, `button_down`, `button_up` | `button`: `left`, `right` or `middle`. |
| `scroll` | `ticks`: integer -127..127, positive up. |
| `release` | Release held input without disarming. |

Named keys: CTRL, SHIFT, ALT, GUI, ENTER, ESC, TAB, BACKSPACE, DELETE, UP, DOWN, LEFT, RIGHT, HOME, END, PAGEUP, PAGEDOWN, INSERT, SPACE, F1–F12. Printable one-character keys are also accepted. Unicode typing and keyboard-layout translation are outside this build.

Ordinary `press`/`type` operations release keyboard state. Do not use them to preserve an earlier explicit key hold. `release`, `stop` and expiry release both keyboard and mouse state.

Acknowledgments report `hid_submitted`: the TinyUSB input submission calls accepted the reports. Each submission waits at most 60ms for an endpoint; a submission failure faults/disarms input rather than claiming success. Queue submission cannot prove OS reception or the desired outcome. The fixture's actual host events establish host bench acceptance; saved frames with explicit operator confirmation establish target-specific BIOS acceptance. STOP acknowledgment records the release request, not measured electrical or host delivery.

Each firmware operation is bounded. Stop and lease handling run between operations; SDK HID calls can block briefly. This is not a hard-real-time stop guarantee. The host fixture tests expiry with a held Shift and a silent heartbeat, then checks rejection of the expired session. It does not measure worst-case stop latency or interrupt a process in the middle of every operation; those remain qualification tests.

## Bridge and observations

Four local stdio tools expose typed Pydantic input. Wrong targets, obsolete frames, invalid action shapes, unknown keys and concurrent actions are rejected before input. No bridge action queue or automatic input retry exists. Bounded internal transport buffers are discarded on TLS disconnect. A lost/malformed/mismatched response faults and closes the connection. Partial typing is reported with acknowledged character count, which may differ from host-received character count. A STOP arriving during a pending connection prevents that late arm from succeeding.

Frames retain native dimensions and optional crop origins. A coordinate action requires the most recent observation within five seconds, and rechecks geometry before sending. Single-monitor desktop absolute mapping is enforced. This check cannot prove screen content remains unchanged. UVC reconnect generation changes invalidate older geometry. A fresh frame after input is returned separately from the input result; capture timeout does not turn input into failure or invite replay.

UVC timestamps measure host read completion, not sensor exposure. The bridge drains continuously and rejects old host receipts. It cannot reliably distinguish dongle no-signal screens, frozen upstream content, valid black video or HDCP blanking. No full UVC or target binding acceptance was possible without hardware.

Ordinary MCP calls do not journal screenshots or typed text. The explicit BIOS qualification console saves before/after frames and operator judgments in an ignored local artifact directory. Host receipts contain fixture-generated results and device identity. Flash backups may contain previous device settings; keep them local and do not distribute them as product artifacts.

## Today's physical acceptance

1. Flash and run the Windows host fixture; retain device-specific receipts.
2. Verify disconnect during explicit holds/typing, repeated payload sequence handling on real firmware, board reboot mid-command and worst-case STOP/lease latency.
3. Run the host fixture over the actual paired Wi-Fi link, retaining its receipt.
4. Select the implemented HID-only BIOS profile and verify actual preboot navigation through the capture path.
5. Record a target reboot, reconnect, confirm another visible BIOS navigation result, and save recovered input/video evidence. Exercise capture disconnect and mode changes on that same target.
6. Verify image delivery and input tools in the user's chosen AI client. The SDK/stdio smoke test does not establish that client acceptance.

Unattended workers, messaging adapters, semantic approval policy, factory throughput and commercial packaging remain proposed work in the earlier design documents.
