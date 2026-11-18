# PhoneBox PWA test results

Tested from base `c76212555bf84994e220300094ccf8bcb1310954` with the PWA changes on `ios/phonebox-pwa`.

| Check | Result and scope |
| --- | --- |
| .NET agent suite | 1,059 passed on Linux, including two PWA unit tests for expiry, persistence, rotation and revocation |
| Existing Playwright suite | 179 passed on Chromium using the repository's browser demo fixture |
| PWA Playwright suite | 3 passed on Chromium 156 using the actual Linux agent and test CA. Verified installation metadata, static cache boundaries, offline startup, reconnect, two independent sessions, revocation, catalogue rendering, config synchronization, and editing a literal HTML-looking note |
| Widget coverage | 123 of 123 original renderers mounted from the actual agent configuration, including the original `meeting-status` alias fixed by this branch. Full interaction checks per widget and integration-specific hardware checks remain open |
| Visual coverage | Original panel and PWA widget geometry matched at 780 × 360. Captured runtime screenshots at 780 × 360, 402 × 874, 874 × 402, 820 × 1180 and 1180 × 820. This is a layout comparison, with screenshots as review artifacts |
| Real HTTPS integration | Passed on the Debug agent and the single-file Linux Release agent. Verified TLS trust and rejection of an untrusted CA, Host and Origin checks, wrong or reused codes, absent or invalid cookies, denied settings/admin/webhook routes, invalid shortcuts, two clients, live event delivery, stream termination on revoke, and persistence across restart |
| Concurrent stream soak | Passed for 90 seconds against the live Linux agent. Each TLS stream received 91 valid state frames |
| Windows agent | Windows-specific target cross-compiled from Linux. Self-contained `win-x64` single-file Release build produced. Windows certificate store, installer, firewall, hardware and interactive control execution require a Windows run |
| Android | `lintDebug`, `assembleDebug` and the existing Kotlin stream, pairing and link regression harness passed |
| Other regressions | Release/catalogue, WinGet metadata, Unix installer, autostart, uninstall and phone setup checks passed |
| Desktop WebKit, iPhone and iPad | Unrun. Chromium layout sizes do not emulate physical safe areas, Safari Home Screen storage, iOS permissions, power management, Wi-Fi behavior or device integration |

## Reproduce the real-agent checks

In a Linux checkout with .NET 10, Python 3, OpenSSL, Node.js and a trusted system Chromium:

```sh
dotnet test agent/PhoneBox.Agent.Tests --nologo
(cd tools/ui-tests && npm ci)
python3 tools/test-pwa.py agent/PhoneBox.Agent/bin/Debug/net10.0/PhoneBoxAgent --browser --soak-seconds 90
```

The TLS fixture generates a short-lived test CA and validates it via Python SSL. Browser mode uses `certutil` and an isolated NSS database. Where Chromium prioritizes a pre-existing legacy database, `bubblewrap` mounts the test database inside the test browser's namespace. It does not change the regular user or OS trust store. `PHONEBOX_TEST_CHROMIUM` can select another compatible Chromium executable. Omit `--browser` for the API-only check used by CI on the published Linux agent executable.

Tests used real CPU/RAM from the Linux test agent and controlled configuration and event fixtures. No private production machine, tokens, or certificates were used. The Windows build does not establish live GPU, CPU temperature or physical iOS compatibility. Manual Windows+iPhone and Windows+iPad acceptance still needs the actual LAN, trusted certificate and devices.
