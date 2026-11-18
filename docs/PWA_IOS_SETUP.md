# PhoneBox auf iPhone und iPad

Diese PWA ist eine inoffizielle Erweiterung des [PhoneBox-Originalprojekts](https://github.com/ersinkoc/phonebox).
Sie läuft vom eigenen PC aus. Weder Codex noch ein Mac, Xcode oder ein Apple-Entwicklerkonto werden im Betrieb benötigt.

## Windows-Agent installieren

1. Den Branch `ios/phonebox-pwa` aus dem [Fork](https://github.com/flx63/phonebox) laden. Für den Quell-Build das [.NET-10-SDK](https://dotnet.microsoft.com/download/dotnet/10.0) installieren und PowerShell im ausgecheckten Verzeichnis öffnen.
2. Den bisherigen Agenten über das Tray beenden. Das vorhandene `%APPDATA%\PhoneBox\config.json` sichern.
3. Führe den vorhandenen Windows-Quellinstaller aus. Er baut den Windows-Agenten aus dem aktiven Branch, installiert ihn in `%LOCALAPPDATA%\PhoneBox\app` und startet ihn. `-Autostart` richtet den Start bei der Windows-Anmeldung ein. Lasse diesen Schalter weg, falls du den Agenten manuell starten willst.

   ```powershell
   .\scripts\install.ps1 -Autostart
   ```

4. In den lokalen Agent-Einstellungen auf `http://127.0.0.1:8765/` unter **Updates** automatische Updates deaktivieren, solange du diesen Entwicklungsstand nutzt. Ein Upstream-Update kann den Fork-Build ersetzen. Beende den Agenten vor der Einrichtung erneut. Der Windows-Benutzer, der den Agenten startet, benötigt Zugriff auf den privaten Zertifikatsschlüssel.

Für einen separaten, eigenständigen Entwicklungsbuild ohne Installation:

```powershell
dotnet publish agent/PhoneBox.Agent -c Release -f net10.0-windows10.0.19041.0 -r win-x64 --self-contained true -p:PublishSingleFile=true -o pwa-build
.\pwa-build\PhoneBoxAgent.exe
```

## HTTPS und eigener Hostname

Reserviere im Router die IPv4-Adresse des PCs und richte dort im lokalen DNS einen eigenen Namen ein, etwa `phonebox.home.arpa`. Der Name muss sowohl auf dem PC als auch über das WLAN des iPhones bzw. iPads zu dieser IPv4-Adresse auflösen. Eine Windows-`hosts`-Datei allein löst den Namen auf dem Mobilgerät nicht auf. Setze für den Namen einen eigenen, ausschließlich für PhoneBox verwendeten Host ein. Browser-Cookies sind an den Host gebunden und werden nicht nach TCP-Port getrennt.

Du benötigst ein TLS-Serverzertifikat mit dem exakten DNS-Namen als **Subject Alternative Name (SAN)**, Server Authentication EKU, privatem Schlüssel und einer von Safari akzeptierten Kette. Die App benutzt die normale Browser-Zertifikatsprüfung. Das Android-Zertifikat für den per Zertifikat-Pinning abgesicherten WLAN-Port ist für dieses Verfahren nicht vorgesehen.

### Windows-Zertifikatsspeicher mit bewusst eingerichteter privater CA

Verwende diese Schritte nur, wenn du die private CA auf deinen eigenen Geräten bewusst als vertrauenswürdig einrichten möchtest. Eine vertraute CA kann auch andere Namen beglaubigen. Schütze ihren privaten Schlüssel und installiere ihre öffentliche CA-Datei ausschließlich auf den Geräten, die du administrierst. Für eine weitreichende oder gemeinsam verwaltete Umgebung verwende eine vorhandene, entsprechend verwaltete CA.

In normaler PowerShell als derselbe Benutzer, der den Agenten startet:

```powershell
$phoneboxDns = 'phonebox.home.arpa'
$phoneboxCa = New-SelfSignedCertificate -Type Custom -Subject 'CN=PhoneBox Local CA' `
  -CertStoreLocation 'Cert:\CurrentUser\My' -KeyAlgorithm RSA -KeyLength 3072 `
  -HashAlgorithm SHA256 -KeyExportPolicy NonExportable -KeyUsage CertSign,CRLSign `
  -TextExtension @('2.5.29.19={critical}{text}ca=1&pathlength=0') -NotAfter (Get-Date).AddYears(3)

$phoneboxLeaf = New-SelfSignedCertificate -Type SSLServerAuthentication -DnsName $phoneboxDns `
  -Signer $phoneboxCa -CertStoreLocation 'Cert:\CurrentUser\My' -KeyAlgorithm RSA -KeyLength 2048 `
  -HashAlgorithm SHA256 -KeyExportPolicy NonExportable -NotAfter (Get-Date).AddDays(365)

Export-Certificate -Cert $phoneboxCa -FilePath .\PhoneBox-Local-CA.cer
Get-FileHash .\PhoneBox-Local-CA.cer -Algorithm SHA256
$phoneboxLeaf.Thumbprint
```

Übertrage **nur** die öffentliche Datei `PhoneBox-Local-CA.cer` auf dein Gerät. Prüfe die Datei über einen vertrauenswürdigen Kanal und vergleiche den SHA-256-Fingerabdruck. Öffne die Datei auf dem Gerät, installiere das geladene Profil in **Einstellungen → Allgemein → VPN und Geräteverwaltung** und aktiviere explizit das vollständige Vertrauen unter **Allgemein → Info → Zertifikatsvertrauenseinstellungen**. Falls du die Adresse auch im Browser des PCs öffnen willst, kannst du die öffentliche CA nach derselben Prüfung bewusst in dessen vertrauenswürdige Stammzertifizierungsstellen aufnehmen. Die beiden privaten Schlüssel bleiben im Windows-Benutzerprofil.

### Agent aktivieren

Ergänze auf oberster Ebene in `%APPDATA%\PhoneBox\config.json` den folgenden Block. Ersetze die Beispieladresse durch die reservierte IPv4-Adresse und den Platzhalter durch den Fingerabdruck des **Serverzertifikats**. Lass bestehende Seiten und Optionen in der Datei stehen.

```json
"pwa": {
  "enabled": true,
  "host": "phonebox.home.arpa",
  "bindAddress": "192.168.1.23",
  "port": 8767,
  "certificateThumbprint": "SERVERZERTIFIKAT-FINGERABDRUCK"
}
```

Falls du stattdessen bereits ein vertrauenswürdiges Zertifikat als PFX hast, verwende `certificatePath` anstelle von `certificateThumbprint`. Ein relativer Pfad bezieht sich auf die Konfigurationsdatei. Gib ein PFX-Passwort über `PHONEBOX_PWA_PFX_PASSWORD` ausschließlich an den Agentenprozess weiter. Für einen Windows-Autostart ohne Passwort-Eingabe ist der Windows-Zertifikatsspeicher der einfachere Weg. Ein von einer öffentlichen CA ausgestelltes Zertifikat für einen eigenen DNS-Namen mit privater Auflösung kann genauso verwendet werden. Tailscale ist optional. Bei Verwendung eines Tailnet-DNS-Namens müssen Zertifikat, Bind-Adresse und Zugriffsbeschränkung dazu passen. Tailscale Serve/Funnel sind hier nicht getestet und für diesen Ablauf nicht erforderlich.

Starte den Agenten. Auf der lokalen Einstellungsseite erscheint **Web app setup** mit Adresse, Zertifikatablauf, QR-Code und Geräteliste. Prüfe auf dem PC mit `Resolve-DnsName phonebox.home.arpa` die erwartete IP und mit `Get-NetTCPConnection -LocalPort 8767 -State Listen` den Listener. Falls die Firewall blockiert, erlaube in einer administrativen PowerShell **nur** das Agentenprogramm, die feste Adresse, TCP 8767, das Profil **Private** und das eigene Subnetz. Den Pfad gegebenenfalls anpassen:

```powershell
New-NetFirewallRule -DisplayName 'PhoneBox web app (private)' -Direction Inbound `
  -Program "$env:LOCALAPPDATA\PhoneBox\app\PhoneBoxAgent.exe" -LocalAddress '192.168.1.23' `
  -RemoteAddress LocalSubnet -Protocol TCP -LocalPort 8767 -Profile Private -Action Allow
```

Verwende keine Router-Portweiterleitung. Der Browser-Port ist unabhängig von USB, Android-WLAN und Webhooks.

## Auf iPhone und iPad hinzufügen

1. Öffne in Safari die in **Web app setup** angezeigte Adresse, beispielsweise `https://phonebox.home.arpa:8767/panel/`. Safari muss die Adresse ohne Zertifikatswarnung öffnen.
2. Wähle **Teilen → Zum Home-Bildschirm → Hinzufügen**. Öffne das neue Icon.
3. Wähle am PC **Create pairing code** und gib den Code in der gestarteten App ein. Gib dem Gerät einen Namen. Ein Code verfällt nach fünf Minuten oder nach der ersten erfolgreichen Verwendung. Der QR-Code kann Safari direkt mit ausgefülltem Code öffnen. Safari und die Home-Screen-App können getrennte Anmeldedaten haben. Kopple die installierte App bei Bedarf separat.
4. Wiederhole den Vorgang auf dem iPad mit einem neuen Code. Unter **Settings → General → Phones** kannst du jedem Gerät eigene Seiten zuweisen. Unter **Web app setup** kannst du die Kopplung einzeln widerrufen.
5. Für Layout, Vorlagen, Smart Stacks und Appearance öffnest du den Originaleditor **am PC**. Änderungen dort erscheinen in den verbundenen Panels. Notizen kannst du direkt auf dem Panel bearbeiten, sofern sie eigenständige Note-Widgets sind.

Auf dem iPad kannst du das Panel im Hoch- und Querformat nutzen. Bei Änderung der Fensterbreite bleibt das ursprüngliche responsive Raster maßgeblich. Öffne die Seitenübersicht und aktiviere optional **Keep screen on**. Im Hintergrund lässt iOS die App unter Umständen schlafen. Beim Zurückkehren wird die Verbindung neu geprüft.

## Fehlerbehebung

| Symptom | Prüfen und beheben |
| --- | --- |
| Name oder PC nicht erreichbar | Prüfe die genaue Adresse in **Web app setup**. Prüfe im Router den lokalen DNS-Eintrag und die DHCP-Reservierung. Gast-WLANs oder Client-Isolation können den Zugriff aufs LAN sperren. |
| Port blockiert | Prüfe `Get-NetTCPConnection -LocalPort 8767 -State Listen` am PC sowie das aktive Windows-Netzwerkprofil und die Programm-/Port-/Subnetzregel. Öffne den Port nur im privaten Netz. |
| Safari meldet einen Zertifikatsfehler | Vergleiche Hostname und SAN, Ablaufdatum und die aktivierte Vertrauenseinstellung für die richtige CA. Ein Aufruf über die IP weicht vom DNS-Zertifikat ab. Weitergehen über eine Warnseite ersetzt keine korrekte Einrichtung. |
| Kopplung schlägt fehl | Öffne die installierte App und erzeuge einen frischen Code am PC. Bei jeder neuen Code-Erzeugung wird der vorherige Code ungültig. Nach 90 Tagen ist eine neue Kopplung erforderlich. |
| Icon fehlt oder App öffnet sich in Safari | Öffne die genaue HTTPS-Paneladresse in Safari und füge sie über das Teilen-Menü hinzu. Bei einem alten Icon entferne es und füge die Adresse erneut hinzu. Dabei kann eine neue Kopplung erforderlich sein. |
| Layout lädt nicht | Öffne **Web app setup** am PC und prüfe die Kopplung. Der Verbindungsbanner kennzeichnet nicht aktuelle Daten. Die Desktop-Einstellungen bleiben über die PC-Loopback-Adresse erreichbar. |
| CPU-Temperatur fehlt auf dem i5-10400 | Der Windows-Agent liest sie aus LibreHardwareMonitor unter `http://127.0.0.1:8085/data.json`. Starte LibreHardwareMonitor mit den nötigen Treiberrechten, aktiviere dort den lokalen Webserver auf 8085 und überprüfe den Sensor **CPU Package**. Erlaube für 8085 keinen LAN-Zugriff. Ohne verfügbaren Sensor erscheint kein Temperaturwert. |
| GTX 1650 Super oder Lüfterwerte fehlen | Prüfe Device Manager und den NVIDIA-Treiber. `nvidia-smi` sollte die Karte erkennen. Der Agent nutzt NVIDIA-, Windows- und gegebenenfalls LibreHardwareMonitor-Daten. Lüfter, Board-Leistung und Takt hängen von Treiber, Karte und Sensor ab. |
| Steuerung bzw. Widget fehlt | Prüfe am PC, ob das Widget, die Integration und die jeweilige PC-Aktion aktiviert sind. Für Kamera, OBS, Home Assistant und Kalender muss der Agent selbst die Quelle erreichen. iOS-Batteriedaten und Eingriffe in die iOS-Ladesteuerung stehen nicht zur Verfügung. |
| Einstellungen bleiben unverändert | Speichere im Originaleditor. Bei einem Konflikt lade die letzte PC-Konfiguration und wende die Änderung erneut an. Für eine Notiz prüfe, ob die PWA online ist und kein paralleler Schreibvorgang die Version geändert hat. |
| PC hat eine neue IP | Aktualisiere die Reservierung, den DNS-Eintrag, die Bind-Adresse und die Firewallregel. Starte den Agenten neu. Bei gleichem Hostnamen und Port kann das Gerät die bisherige Sitzung weiterverwenden. |
| Wiederholte Abbrüche | Wechsle aus dem Gastnetz, prüfe Wi-Fi-Roaming und stell sicher, dass der PC und der Agent wach sind. Das Panel versucht bei sichtbarer App erneut zu verbinden. |
| Bildschirm geht aus | Prüfe **Keep screen on** in der Seitenübersicht. Wenn iOS den Wake Lock ablehnt oder freigibt, etwa beim Sperren oder bei Stromsparbedingungen, gelten die Systemeinstellungen. |
| Neue Version lädt nicht | Schließe alle geöffneten PhoneBox-Fenster und beende die Home-Screen-App, bevor du sie neu öffnest. Der Service Worker hält die Ressourcenversion zusammen, bis offene Instanzen beendet sind. |
| HTTPS-Zertifikat läuft ab | Erzeuge rechtzeitig ein neues Blattzertifikat für denselben SAN und dieselbe CA, aktualisiere den Fingerabdruck bzw. ersetze die PFX-Datei und starte den Agenten neu. Solange die CA gültig und der Origin gleich bleibt, ist keine neue CA-Installation erforderlich. |
| Gerät verloren oder private CA kompromittiert | Widerrufe das Gerät in **Web app setup**. Für eine kompromittierte CA entferne auf allen Geräten das installierte CA-Profil und das entsprechende Vertrauen am PC, erstelle eine neue CA und tausche das Serverzertifikat. Lösche alte private Schlüssel erst, nachdem du sie zweifelsfrei anhand des Fingerabdrucks identifiziert hast. |

Weitere technische Grenzen und Testnachweise stehen in [Implementierungsstatus](../PWA_IMPLEMENTATION_STATUS.md), [Architektur](../PWA_ARCHITECTURE.md) und [Widget-Matrix](../PWA_WIDGET_COMPATIBILITY.md).
