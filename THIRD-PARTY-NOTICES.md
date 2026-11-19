# Third-party notices

GOOD MIXX is based on an original idea by **DJ Aquarobotics**.

**djay-pro-mcp** by ckryptickunal — MIT License. https://github.com/ckryptickunal/djay-pro-mcp
The set recorder is built on it: `app/gm-recorder.mjs` loads djay-pro-mcp to read djay's MIDI controller feedback
and on-screen readouts. djay-pro-mcp is not included in this repository or in the Mac app. **SET UP RECORDER**
downloads it from GitHub at a tested commit (`d392a57`, see `MCP_COMMIT` in `app/recorder.py`) into
`~/djay-pro-mcp`, where its own LICENSE file comes with it.

**traktor-api-client** by Erik Minekus — MIT License. The files in `app/traktor-link/Api/` come from
https://github.com/ErikMinekus/traktor-api-client; `ApiClient.js` is changed to send to GOOD MIXX
(`http://localhost:8770/traktor`). See `app/traktor-link/LICENSE-traktor-api-client.txt`.
Native Instruments' own `D2.qml` is not included; the installer adds two lines to the user's own copy.

**IBM Plex Sans and IBM Plex Mono** — © IBM Corp., SIL Open Font License 1.1. Subset WOFF2 files in
`app/assets/`; license in `app/assets/OFL-IBM-Plex.txt`.

**Impact** — the GOOD MIXX title artwork and icon are images rendered with the Impact font that ships
with macOS. The font file itself is not included.

Traktor is a trademark of Native Instruments. djay is a trademark of Algoriddim. Camelot is a trademark
of Mixed In Key. GOOD MIXX is not affiliated with any of them.
