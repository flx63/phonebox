# PWA implementation status

The fork implements a same-origin PhoneBox web app served by an opt-in agent listener, with the full shared widget registry and the original desktop editor. Pairing, live state, SSE, re-pairing, revocation, settings synchronization, offline shell and responsive layouts are implemented. The existing Windows source installer and autostart command install this branch. The HTTPS listener is configured explicitly in the agent settings file.

Desktop editor operations such as templates, import/export, widget sizing and Appearance remain at the Windows settings page. The mobile app receives the saved config and supports the existing narrow note update API. No mobile administrative editor is included. The local editor contains credentials and definitions for commands and integrations.

- **Platform limitations.** iOS does not expose the original Android battery, charging control, brightness or room/proximity sensor bridges. The computer switcher remains visible as a capability notice. Pair each PC under its own HTTPS origin. PhoneBox cannot force iOS orientation, manage hardware charging, or run continuously in the background. Wake Lock and speech recognition depend on the browser and OS. Speech recognition does not promise offline processing.
- **Integrations.** The shared renderer routes PC controls to their existing agent handlers. Control Deck features still depend on agent OS capabilities and the user's configured options. Internet widgets contact their existing sources directly from the browser. The local feed proxy stays local. Web Push is not included.
- **Verification boundaries.** Consult [test results](PWA_TEST_RESULTS.md) and the [per-widget matrix](PWA_WIDGET_COMPATIBILITY.md). Chromium tests against a Linux agent cannot verify native iOS, a user's Windows devices, or external services and credentials. No credentials, TLS private keys or live PC data are included.

See [Windows and iOS setup](docs/PWA_IOS_SETUP.md) and [architecture](PWA_ARCHITECTURE.md).
