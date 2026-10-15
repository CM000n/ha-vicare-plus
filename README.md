# Viessmann ViCare Plus für Home Assistant

[![hacs][hacs-badge]][hacs-url]

**ViCare Plus** ist ein Drop-in-Ersatz für die offizielle Home Assistant
Integration [Viessmann ViCare](https://www.home-assistant.io/integrations/vicare/).
Sie basiert auf dem Code der Core-Integration (Stand HA 2026.10) und ergänzt ihn
um alles, was die Viessmann API anbietet, plus einige abgeleitete Werte, die es
in der offiziellen Integration nicht gibt.

*English summary below.*

## Warum?

Die offizielle Integration bildet nur einen Teil der API ab. Ein Beispiel ist
die VScotHO1 72 (Vitodens 200-W). Dort fehlen unter anderem
der Status aller Pumpen, die Zeitprogramme, die Betriebsart der Heizkreise als
Auswahl, das Urlaubsprogramm und die Fehlerstatus des Brenners. ViCare Plus liest
den kompletten Feature-Baum der API und erzeugt **automatisch** für jeden
Datenpunkt und jeden ausführbaren Befehl eine passende Entität. Das funktioniert
auch für Geräte, die nie getestet wurden.

## Funktionen

### 1:1 Ersatz der offiziellen Integration
* Gleiche Domain (`vicare`): Die bestehende Konfiguration, das OAuth-Token und
  **alle bestehenden Entity-IDs bleiben erhalten**. Automationen, Dashboards und
  Statistiken laufen weiter.
* Alle Entitäten der Core-Integration sind unverändert enthalten.
* **Keine zusätzlichen API-Aufrufe:** Alle neuen Entitäten lesen aus demselben
  Abruf, den die Integration ohnehin macht.

### Generische Entitäten aus dem API-Featurebaum
| API-Daten | Entität |
|---|---|
| Zahlen, Texte, Zähler, Statistiken | `sensor` |
| `on`/`off`-Status (z. B. Pumpen), `active`-Flags | `binary_sensor` |
| Befehle mit einem Zahlen-Parameter (Temperaturen …) | `number` |
| Befehle mit Aufzählung (z. B. Betriebsart `setMode`) | `select` |
| Befehle mit Text-Parameter (z. B. Heizkreisname) | `text` |
| `activate`/`deactivate`-Paare (z. B. Eco, Komfort) | `switch` |
| Befehle ohne Parameter (z. B. Urlaub beenden, Zeitprogramm zurücksetzen) | `button` |

Werte, die die Core-Integration schon liefert, und selten benötigte Werte
werden zwar angelegt, sind aber standardmäßig **deaktiviert**. Sie lassen sich in
der Geräteansicht bei Bedarf aktivieren.

### Pumpen
* Status aller Pumpen: interne Kesselpumpe, Heizkreispumpen, Zirkulationspumpe,
  Speicherladepumpe und Solarkreispumpe (`binary_sensor`, Device-Class *running*).
* **Laufzeit heute** pro Pumpe (wird um Mitternacht zurückgesetzt und übersteht
  Neustarts).
* **Zirkulationspumpe steuern:** Die API erlaubt kein direktes Ein- und
  Ausschalten. ViCare Plus steuert sie deshalb über ihr Zeitprogramm:
  * `button` **Boost**: Zirkulation ab sofort für die eingestellte Dauer
    (`number` *Boost-Dauer*) einschalten, danach wird das ursprüngliche
    Programm automatisch wiederhergestellt.
  * `switch` **Dauerbetrieb**: Zirkulation rund um die Uhr. Beim Ausschalten wird das
    ursprüngliche Programm wiederhergestellt.
  * Laufende Overrides werden gespeichert und überstehen Neustarts von Home
    Assistant.
* Die Heizkreispumpen lassen sich indirekt über die **Betriebsart** des
  Heizkreises beeinflussen (`select`, z. B. *Nur Warmwasser* → Pumpe aus).

Boost und Dauerbetrieb gibt es analog für die **Warmwasserbereitung**.

### Zeitprogramme
* Ein `sensor` pro Zeitprogramm (Heizkreise, Warmwasser, Zirkulation) zeigt den
  aktuell geplanten Modus. Als Attribute kommen der nächste Wechsel mit Zeitpunkt
  und Modus, das komplette Wochenprogramm und ein eventuell aktiver Override dazu.
* Services zum Schreiben, Zurücksetzen, Boosten und Wiederherstellen (siehe unten).
  Die Programme werden vor dem Senden gegen die Gerätegrenzen geprüft, also
  maximale Einträge, 10-Minuten-Raster und erlaubte Modi.

### Abgeleitete Werte
* **Soll-Vorlauftemperatur laut Heizkurve** pro Heizkreis. Berechnet wird sie aus
  Außentemperatur, Raumsoll, Neigung und Niveau mit der Viessmann-Formel. Dazu
  kommt die **Abweichung** der gemessenen Vorlauftemperatur.
* **Brenner:** Starts in der letzten Stunde, Starts heute, Laufzeit heute,
  durchschnittliche Laufzeit pro Start, Dauer des letzten Laufs und der letzten Pause.
* **Takterkennung** (`binary_sensor` *Taktung*): Geht an, wenn der Brenner
  häufiger startet als eingestellt (Standard: 4 Starts pro Stunde).
* **Solar:** Temperaturdifferenz zwischen Kollektor und Speicher.
* **API-Aufrufe (24 h):** Zähler über ein rollierendes 24-h-Fenster. Viessmann
  erlaubt etwa 1450 Aufrufe pro Tag, der Sensor warnt also rechtzeitig.

### Optionen
Unter *Einstellungen → Geräte & Dienste → ViCare → Konfigurieren*:
* **Abfrageintervall** (60 – 3600 s, Standard 60 s, also ca. 1440 Aufrufe pro Tag).
  Mit 90 s bleibt Luft für eigene Befehle und Neustarts.
* **Schwelle für Takterkennung** (Starts pro Stunde).

## Services

| Service | Beschreibung |
|---|---|
| `vicare.execute_command` | Führt **jeden** API-Befehl aus (`feature`, `command`, `params`). Optional mit Antwort. |
| `vicare.get_features` | Liefert den kompletten Featurebaum mit allen Eigenschaften und Befehlen als Service-Antwort (optional gefiltert). |
| `vicare.set_holiday` | Urlaubsprogramm von `start` bis `end` planen. |
| `vicare.end_holiday` | Urlaubsprogramm beenden. |
| `vicare.set_schedule` | Zeitprogramm schreiben: komplette Woche (`schedule`) oder ein Tag (`day` + `entries`). |
| `vicare.reset_schedule` | Zeitprogramm (oder einen Tag) auf Werkseinstellung zurücksetzen. |
| `vicare.schedule_boost` | Zeitprogramm ab jetzt für `duration` aktivieren, danach automatisch wiederherstellen. |
| `vicare.schedule_restore` | Boost/Dauerbetrieb beenden und Originalprogramm wiederherstellen. |
| `vicare.set_vicare_mode` | (aus der Core-Integration) ViCare-Modus einer Klima-Entität setzen. |

Beispiele:

```yaml
# Zirkulation für 20 Minuten einschalten, wenn jemand ins Bad geht
action: vicare.schedule_boost
target:
  entity_id: sensor.vscotho1_72_zirkulation_zeitprogramm
data:
  duration: "00:20:00"

# Zirkulationsprogramm für Montag setzen
action: vicare.set_schedule
target:
  entity_id: sensor.vscotho1_72_zirkulation_zeitprogramm
data:
  day: mon
  entries:
    - start: "05:30"
      end: "08:00"
    - start: "17:00"
      end: "22:00"

# Heizkreis 2 auf "Heizen und Warmwasser" stellen
action: vicare.execute_command
data:
  feature: heating.circuits.2.operating.modes.active
  command: setMode
  params:
    mode: dhwAndHeating

# Alle Pumpen-Features ansehen (Entwicklerwerkzeuge → Aktionen)
action: vicare.get_features
data:
  filter: pump
```

## Installation

> [!IMPORTANT]
> ViCare Plus **ersetzt** die eingebaute Integration, weil es dieselbe Domain
> `vicare` nutzt. Eine bestehende ViCare-Konfiguration wird einfach übernommen.

### HACS (empfohlen)
1. HACS → Benutzerdefinierte Repositories → `https://github.com/CM000n/ha-vicare-plus`
   als *Integration* hinzufügen.
2. *Viessmann ViCare Plus* installieren.
3. Home Assistant neu starten.

### Manuell
1. Den Ordner `custom_components/vicare` nach `<config>/custom_components/vicare`
   kopieren.
2. Home Assistant neu starten.

Ist ViCare noch nicht eingerichtet, läuft die Einrichtung genau wie bei der
offiziellen Integration (Application Credentials mit Client-ID aus dem
Viessmann-Developer-Portal).

### Zurück zur offiziellen Integration
Ordner `custom_components/vicare` löschen und neu starten. Die Core-Entitäten
bleiben erhalten. Die Plus-Entitäten werden *nicht verfügbar* und können
gelöscht werden.

## Hinweise
* Laufende Overrides (Boost/Dauerbetrieb) liegen in
  `.storage/vicare_plus.overrides.<entry_id>`. Wird die Integration während eines
  Overrides entfernt, bleibt das geänderte Zeitprogramm am Gerät aktiv. In dem Fall
  vorher `vicare.schedule_restore` aufrufen.
* Zeitprogramme werden in der Zeitzone von Home Assistant ausgewertet. Diese
  sollte der Zeitzone der Heizung entsprechen.
* Ein Boost endet spätestens um Mitternacht.
* Nach jedem Befehl wird sofort neu abgefragt (ein zusätzlicher API-Aufruf).

## Entwicklung

```bash
# Logik-Tests (ohne Home Assistant)
python -m pytest tests/test_logic.py
# Alle Tests im Home Assistant Container
docker run --rm -v $PWD:/w -w /w --entrypoint sh homeassistant/home-assistant:2026.10.1 \
  -c "pip install pytest && python -m pytest"
```

Aufbau:
* Der Core-Code der Integration ist fast unverändert, damit Updates aus HA leicht
  nachgezogen werden können. Die Änderungen beschränken sich auf Hooks in
  `__init__.py`, den Plattformdateien, `api.py` (Aufrufzähler) und `config_flow.py`
  (Optionen).
* `plus/logic.py`: reine Logik ohne HA-Abhängigkeiten (Discovery, Namen,
  Zeitprogramme, Heizkurve).
* `plus/runtime.py`: Zustand pro Config-Entry, Befehlsausführung, Tracker.
* `plus/entity.py`: alle Plus-Entitäten.
* `plus/overrides.py`: Boost/Dauerbetrieb mit persistenter Wiederherstellung.
* `plus/services.py`: Services.

---

## English

**ViCare Plus** is a drop-in replacement for Home Assistant's built-in
Viessmann ViCare integration. It keeps the domain `vicare`, so your existing
config entry, token and entity IDs stay as they are. On top of that it:

* creates entities for **every** data point and command of the Viessmann API
  (sensor, binary_sensor, number, select, text, switch, button). Core
  duplicates start disabled.
* exposes all **pumps** with daily runtime, and lets you control the
  **circulation pump** through its time program: a boost button with
  configurable duration and a permanent switch, both restored automatically and
  persisted across restarts.
* provides time program sensors and services (`set_schedule`,
  `reset_schedule`, `schedule_boost`, `schedule_restore`), holiday services, a
  generic `execute_command` service and `get_features` for exploring the API.
* derives extra values: target supply temperature from the heating curve and
  its deviation, burner starts, cycling detection, average burner runtime, solar
  collector/tank delta, and a rolling 24 h API call counter.
* has options for the polling interval (rate-limit friendly) and the cycling
  threshold.

Install via HACS as a custom repository or copy `custom_components/vicare` into
your config folder and restart. To go back to the core integration, delete the
folder and restart.

## Lizenz

Apache 2.0, wie Home Assistant. Der Code der Core-Integration ©
Home Assistant Contributors.

[hacs-badge]: https://img.shields.io/badge/HACS-Custom-orange.svg
[hacs-url]: https://hacs.xyz/docs/faq/custom_repositories
