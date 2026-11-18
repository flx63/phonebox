#!/usr/bin/env python3
"""Generate the PWA catalogue report from PhoneBox's canonical widget definitions."""
import argparse
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CATALOG = ROOT / "agent/PhoneBox.Agent/widgets.json"
OUTPUT = ROOT / "PWA_WIDGET_COMPATIBILITY.md"

# Each group shares a transport. The catalogue supplies the widget-specific behavior and options.
GROUPS = [
    ("analog worldclock calendar progress countdown wordclock moon", "Browser clock and locale", "—", "—"),
    ("pomodoro timer stopwatch counter checklist breathe meeting-timer", "Browser clock and local storage", "—", "—"),
    ("label quote", "Panel configuration", "config", "—"),
    ("note", "Agent configuration", "config; POST widget/{page}/{widget}/note", "Editable when outside a Smart Stack"),
    ("clock", "Browser clock, PC state, quotas and weather", "state, stream, quotas; Open-Meteo HTTPS", "Optional iOS battery readout is unavailable"),
    ("agenda nextup", "Configured iCalendar feeds via agent", "calendar", "Calendar sources must be configured on the PC"),
    ("photos", "Agent photo folder", "photos, photos/{id}", "Configured PC folder"),
    ("weather forecast sun", "Open-Meteo via browser; local astronomy", "Public HTTPS", "Provider must be reachable from Safari"),
    ("air", "Open-Meteo Air Quality via browser", "Public HTTPS", "Provider must be reachable from Safari"),
    ("battery chargecare", "Android battery/charge bridge", "Android battery API", "iOS does not expose the required hardware control or telemetry"),
    ("pcswitch", "Android list of known PCs", "Android AgentLink", "Open each PC’s separate web origin instead"),
    ("stat gauge chart meters gpu", "PC sensors through the existing agent", "state, stream", "Metrics depend on Windows sensors and drivers"),
    ("topprocs processes", "Process monitor", "procs, procs/icon, procs/detail; POST procs/kill", "Process control requires the existing settings and OS permission"),
    ("media", "PC media session and artwork", "state, stream, art; POST media/{action}, volume", "Supported PC media player and OS session"),
    ("volume", "PC audio control", "state, stream; POST volume", "Supported audio backend"),
    ("spectrum", "PC playback spectrum", "spectrum, stream", "Windows loopback capture"),
    ("shortcuts button", "Allowed agent shortcuts and pushed state", "config, push, shortcuts/icon; POST run/{id}", "Desktop-configured shortcut IDs"),
    ("docker", "Docker or Podman", "docker; POST docker/{id}/{action}", "Configured host runtime and enabled controls"),
    ("discord", "Discord desktop integration", "discord, discord/img; POST discord/{action}", "Discord desktop and configured integration"),
    ("apps", "PC application catalogue", "apps, apps/icon; POST apps/open", "Supported OS catalogue and explicit launch permission"),
    ("obs", "OBS WebSocket via the agent", "obs; POST obs/{action}", "Configured OBS connection"),
    ("app-console", "Foreground app and configured console controls", "console; POST console/{profile}/{slot}", "Supported agent OS and opted-in profiles"),
    ("dictate", "Safari speech recognition, then agent input", "Web Speech; POST dictate", "Browser permission/service and enabled desktop widget; offline recognition unavailable"),
    ("command", "Configured command on the PC", "widget/{page}/{widget}", "Only a command ID from desktop settings"),
    ("batteries", "PC and peripheral battery monitors", "batteries", "Supported PC hardware and device APIs"),
    ("onair meeting-status", "PC privacy, meeting and media state", "state, stream", "Available desktop privacy sensors"),
    ("rules", "Agent rule engine", "state, stream; POST rules/pause", "Rules set in the desktop editor"),
    ("html", "Sandboxed user HTML and panel events", "state, stream, push, work, quotas; POST run/{id}", "Browser sandbox; custom network resources must work within Safari security policies"),
    ("ha", "Home Assistant via agent", "ha/states; POST ha/toggle/{id}", "Configured Home Assistant and enabled action"),
    ("push inbox", "Agent push store and notifications", "push, state, stream", "Webhook ingestion is on the existing local or Android LAN route"),
    ("feeds", "Configured RSS/Atom sources via agent", "feeds; POST feeds/open", "Feeds must be configured on the PC"),
    ("hackernews exchange crypto image", "Public or configured remote HTTPS sources", "Browser HTTPS", "CORS and HTTPS rules apply; no agent feed proxy on the PWA listener"),
    ("camera", "Configured agent camera sources", "camera", "Compatible feed and agent configuration required"),
    ("quotas codexbar quotaring", "Agent provider and quota monitors", "quotas, state, stream", "Provider logins and data on PC"),
    ("sessions github", "Agent session and GitHub monitors", "work, stream", "Configured local sessions and GitHub authentication"),
    ("stack", "Shared Smart Stack and selected child widget", "Depends on children", "Inherits child capabilities"),
    ("pc-listen", "PC audio loopback streaming", "controls/listen, controls/state; POST controls/command/{kind}", "Compatible PC audio capture and Web Audio; requires a browser gesture"),
    ("obs-mixer obs-scenes obs-sources obs-recording obs-replay obs-transition obs-camera",
     "OBS WebSocket through Control Deck", "controls/obs; POST controls/obs/{action}", "Configured OBS and enabled PC actions"),
    ("media-queue media-favorites", "Spotify through the agent", "controls/spotify/state; POST controls/spotify/action/{action}",
     "Desktop Spotify OAuth configuration; optional artwork from Spotify"),
]
PARTIAL = {
    "clock": "Optional mobile battery status is unavailable.",
    "pomodoro": "Visual timer works; Android vibration is unavailable.",
    "timer": "Visual timer works; Android vibration is unavailable.",
    "dictate": "Requires Safari speech recognition and agent input support. Physical microphone flow untested.",
    "pcswitch": "Native in-panel PC switching is unavailable.",
}
UNAVAILABLE = {"battery", "chargecare"}
COVERAGE = {key: detail for keys, *detail in GROUPS for key in keys.split()}
DECK = ("PC Control Deck", "controls/state; POST controls/command/{kind}",
        "Native or portable desktop capability and an enabled, configured action")


def generate():
    rows = json.loads(CATALOG.read_text(encoding="utf-8"))
    lines = [
        "# PhoneBox PWA widget compatibility", "",
        f"Generated from `agent/PhoneBox.Agent/widgets.json`. **{len(rows)} widget types**.",
        "Regenerate with `python3 tools/generate-pwa-widget-matrix.py`.", "",
        "Every widget has its original renderer. The authenticated Linux-agent Chromium test mounts the entire catalogue from",
        "agent settings. ‘Mounted’ does not verify an external service, native hardware, or each control action.",
        "Every row is unverified on physical iOS/iPadOS hardware. The data sources and limitations below are based on the",
        "original catalog and code. Each API path is relative to `/agent/api/`, except browser/Android APIs.", "",
        "| ID | Name | Source | APIs | Original behavior and interactions | Dependencies or limitations | Status | Chromium evidence |",
        "| --- | --- | --- | --- | --- | --- | --- | --- |",
    ]
    for w in rows:
        key = w["type"]
        if key not in COVERAGE and w["category"] != "Control Deck":
            raise ValueError(f"Missing compatibility metadata for {key}")
        source, api, dependency = COVERAGE.get(key, DECK)
        status = "Implemented, iOS hardware untested"
        evidence = "Mounted"
        if key in PARTIAL:
            status = "Partial"
            dependency = " ".join(s for s in (dependency if dependency != "—" else "", PARTIAL[key]) if s)
        if key in UNAVAILABLE:
            status, evidence = "Unavailable in iOS browser", "Capability notice mounted"
        if key == "note":
            evidence = "Mounted; editing and persistence verified"
        elif key in {"clock", "stat"}:
            evidence = "Mounted; reference layout and live state verified"
        cells = [f"`{key}`", w["name"], source, api, w["desc"], dependency, status, evidence]
        lines.append("| " + " | ".join(value.replace("|", "\\|").replace("\n", " ") for value in cells) + " |")
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if the committed report is out of date")
    args = parser.parse_args()
    report = generate()
    if args.check:
        if OUTPUT.read_text(encoding="utf-8") != report:
            raise SystemExit("PWA widget compatibility matrix needs regeneration")
    else:
        OUTPUT.write_text(report, encoding="utf-8")


if __name__ == "__main__":
    main()
