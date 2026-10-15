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

### Boost und Dauerbetrieb im Detail

#### Grundprinzip: Steuerung über das Zeitprogramm
Die Viessmann-API kennt für Zirkulations-, Heizkreis- und Speicherladepumpen
**keinen Ein/Aus-Befehl**. Die Pumpen werden ausschließlich vom Regler der Anlage
geschaltet. Schreiben lassen sich aber die **Zeitprogramme**, nach denen der
Regler arbeitet. Darauf bauen Boost und Dauerbetrieb auf:

1. Das aktuelle Wochenprogramm wird gelesen und als **Original** in Home Assistant
   gespeichert (`.storage/vicare_plus.overrides.<entry_id>`).
2. Ein **verändertes Programm** wird an die Anlage gesendet.
3. Danach wird das Original **automatisch zurückgeschrieben**: beim Boost nach
   Ablauf der Zeit, beim Dauerbetrieb beim Ausschalten.

Pro Zeitprogramm gibt es diese Entitäten:

| Entität | Typ | Wirkung |
|---|---|---|
| *Boost* | `button` | Fügt ab jetzt ein aktives Zeitfenster für die *Boost-Dauer* ein |
| *Boost-Dauer* | `number` | Länge des Boosts, 10–360 min, Standard 30 min, wird gespeichert |
| *Dauerbetrieb* | `switch` | Programm 00:00–24:00 an allen Tagen aktiv, beim Ausschalten zurück zum Original |
| *Zeitprogramm* | `sensor` | Geplanter Modus, nächster Wechsel, Wochenprogramm und aktiver Override als Attribut |

#### Ablauf eines Boosts
* **Start und Ende** werden auf das 10-Minuten-Raster der Anlage ausgerichtet.
  Der Start wird abgerundet, das Ende aufgerundet. Ein Boost um 14:07 für
  30 Minuten wird also zu **14:00–14:40**.
* **Ein Boost endet spätestens um Mitternacht**, denn ein Zeitfenster kann nicht
  über den Tageswechsel hinaus reichen.
* **Überlappungen:** Das Boost-Fenster wird mit den vorhandenen Fenstern des Tages
  zusammengeführt. Liegt es in einem ohnehin aktiven Zeitraum, ändert sich
  praktisch nichts.
* **Volle Tage:** Die Anlage erlaubt **maximal 4 Zeitfenster pro Tag**. Sind alle
  vier belegt und das Boost-Fenster lässt sich nicht anfügen oder zusammenführen,
  wird der Boost mit einer Fehlermeldung abgelehnt.
* **Erneuter Boost:** Ein zweiter Boost während eines laufenden Boosts geht
  wieder vom gespeicherten **Original** aus und setzt eine neue Endzeit. Boosts
  addieren sich nicht.
* **Boost bei Dauerbetrieb** wird abgelehnt, denn dort läuft ohnehin alles.
* **Wiederherstellung:** Ein Timer stellt das Original zur Endzeit wieder her.
  Das gilt auch nach einem Neustart von Home Assistant; war die Endzeit währenddessen
  schon erreicht, wird sofort wiederhergestellt. Scheitert das Zurückschreiben,
  etwa weil das API-Limit erreicht ist, folgt alle 10 Minuten ein neuer Versuch.
* Mit dem Service `vicare.schedule_restore` lässt sich ein Override jederzeit
  vorzeitig beenden.

#### Dauerbetrieb
* Das Programm wird an allen Tagen durch **ein Fenster 00:00–24:00** im aktiven
  Modus ersetzt:
  * Zirkulation und Warmwasser: `on`
  * Heizkreis: `normal`
* Beim Ausschalten wird das gespeicherte Original zurückgeschrieben. Auch das
  übersteht Neustarts.

#### Zusammenspiel mit den Betriebsarten
Ein Zeitprogramm wirkt **nur, wenn die Betriebsart es auswertet**. Boost und
Dauerbetrieb ändern ausschließlich das Zeitprogramm, **nie die Betriebsart**. Bei
der VScotHO1 72 hat jeder Heizkreis eine eigene **Betriebsart** (`select`):

| Betriebsart | Heizkreis-Zeitprogramm | Warmwasser- und Zirkulationsprogramm | Heizkreispumpe |
|---|---|---|---|
| `dhwAndHeating` – Heizen und Warmwasser | **wirksam**: im Fenster *Normal*, sonst *Reduziert* | wirksam | läuft bei Wärmebedarf |
| `dhw` – Nur Warmwasser | wirkungslos, der Heizkreis ist aus (nur Frostschutz) | wirksam | aus, außer bei Frostschutz |
| `forcedNormal` – Dauernd Normal | wirkungslos, immer *Normal* | wirksam | läuft bei Wärmebedarf |
| `forcedReduced` – Dauernd Reduziert | wirkungslos, immer *Reduziert* | wirksam | läuft bei Wärmebedarf |
| `standby` – Abschaltbetrieb | wirkungslos | in der Regel wirkungslos, da die Warmwasserbereitung ruht | aus, außer bei Frostschutz |

Daraus folgt:
* **Heizkreis-Boost:** Er hat nur in der Betriebsart *Heizen und Warmwasser* eine
  Wirkung. Er schaltet dann für die Boost-Dauer von der reduzierten auf die
  normale Raumsolltemperatur. Steht der Heizkreis auf *Nur Warmwasser* oder
  *Dauernd Normal*, wird das Programm zwar geschrieben, an der Heizung ändert
  sich aber nichts.
* **Heizkreispumpe:** Es gibt keinen Pumpenbefehl. Ob die Pumpe läuft,
  entscheidet der Regler aus der Betriebsart, dem Heizkreisprogramm und dem
  Wärmebedarf (Heizkurve, Außentemperatur, Heizgrenze/Sparfunktion). Wer die
  Pumpe sicher ausschalten will, stellt die Betriebsart auf *Nur Warmwasser*;
  der Frostschutz bleibt dabei aktiv. Für „Heizen jetzt“ eignet sich *Dauernd
  Normal* oder ein Boost bei *Heizen und Warmwasser*.
* **Zirkulationspumpe:** Sie folgt ihrem eigenen Zeitprogramm, unabhängig vom
  Heizkreisprogramm, solange die Warmwasserbereitung aktiv ist. Boost und
  Dauerbetrieb wirken also auch bei *Nur Warmwasser*, nicht aber im Standby
  oder im Urlaubsprogramm.
* **Warmwasser-Boost:** Das Warmwasserprogramm legt nur fest, *wann* die Anlage
  den Speicher auf die Solltemperatur hält; außerhalb der Fenster wird nicht
  nachgeladen. Ein Boost startet die **Speicherladepumpe und den Brenner nur,
  wenn der Speicher unter Soll minus Hysterese liegt** (typisch ca. 2,5 K). Ist der
  Speicher warm genug, passiert nichts. Eine einmalige Zwangsladung
  (`oneTimeCharge`) bietet die API für diese Anlage nicht an. Wer heißeres Wasser
  will, kombiniert den Boost mit einer höheren *Warmwasser-Solltemperatur*.
* **Urlaubsprogramm:** Es hat Vorrang vor allen Zeitprogrammen. Heizkreise laufen
  reduziert bzw. im Frostschutz, Warmwasser und Zirkulation ruhen. Boost und
  Dauerbetrieb haben in dieser Zeit keine Wirkung, die Wiederherstellung des
  Originals läuft trotzdem planmäßig.
* **Programme *Komfort* und *Eco*:** Diese Schalter (sofern vorhanden) überlagern
  das Heizkreisprogramm ebenfalls nur in der Betriebsart *Heizen und Warmwasser*.

#### Wichtige Hinweise
* **Verzögerung:** Änderungen gehen über die Viessmann-Cloud und das Gateway an
  den Regler. Bis die Pumpe schaltet, vergehen meist 1–2 Minuten. Der Status in
  Home Assistant aktualisiert sich mit dem nächsten Abruf (Abfrageintervall).
* **Änderungen in der ViCare-App** während eines aktiven Overrides werden beim
  Wiederherstellen **überschrieben**, weil das gespeicherte Original
  zurückgeschrieben wird. Programme deshalb nur ohne laufenden Boost oder
  Dauerbetrieb bearbeiten, oder per `vicare.set_schedule`. Dieser Service verwirft
  einen laufenden Override bewusst, damit das neue Programm bestehen bleibt.
* **API-Kontingent:** Jeder Boost kostet zwei Schreibzugriffe (Setzen und
  Wiederherstellen) und einen Lesezugriff. Für Automationen, etwa
  „Zirkulation bei Bewegung im Bad“, bitte eine Sperrzeit einbauen.
  Der Sensor *API-Aufrufe (24 h)* hilft dabei.
* **Zeitzone:** Die Uhrzeit der Anlage muss der Zeitzone von Home Assistant
  entsprechen, sonst sind Boost-Fenster verschoben.

### Abgeleitete Werte
* **Soll-Vorlauftemperatur laut Heizkurve** pro Heizkreis. Berechnet wird sie aus
  Außentemperatur, Raumsoll, Neigung und Niveau mit der Viessmann-Formel. Dazu
  kommt die **Abweichung** der gemessenen Vorlauftemperatur. Details stehen im
  Abschnitt [Heizkurve verstehen](#heizkurve-verstehen).
* **Brenner:** Starts in der letzten Stunde, Starts heute, Laufzeit heute,
  durchschnittliche Laufzeit pro Start, Dauer des letzten Laufs und der letzten Pause.
* **Takterkennung** (`binary_sensor` *Taktung*): Geht an, wenn der Brenner
  häufiger startet als eingestellt (Standard: 4 Starts pro Stunde).
* **Solar:** Temperaturdifferenz zwischen Kollektor und Speicher.
* **API-Aufrufe (24 h):** Zähler über ein rollierendes 24-h-Fenster. Viessmann
  erlaubt etwa 1450 Aufrufe pro Tag, der Sensor warnt also rechtzeitig.

### Heizkurve verstehen

#### Was der Sensor berechnet
Der Regler bestimmt die **Soll-Vorlauftemperatur** jedes Heizkreises aus der
Außentemperatur, also wie warm das Wasser in die Fußbodenheizung bzw. die
Heizkörper fließen soll. Die API liefert dafür nur die Parameter, nicht den
Sollwert selbst. ViCare Plus rechnet ihn mit der Viessmann-Heizkurvenformel nach:

```
ΔT   = Außentemperatur − Raumsoll
Soll = Raumsoll + Niveau − Neigung · ΔT · (1,4347 + 0,021 · ΔT + 247,9·10⁻⁶ · ΔT²)
```

Für Wärmepumpen gelten ein anderer Faktor (1,148987) und ein Zuschlag von +5 K.

Die Eingangsgrößen sind:

| Größe | Quelle | Wirkung |
|---|---|---|
| **Außentemperatur** | `heating.sensors.temperature.outside` | je kälter, desto höher der Vorlauf |
| **Raumsoll** | Temperatur des aktiven Heizprogramms (*Normal*, *Reduziert*, *Komfort* …) | verschiebt die Kurve; +1 K Raumsoll ergibt grob +2 … +3 K Vorlauf |
| **Neigung** (`slope`) | *Heizkurve Neigung* | Steilheit: wie stark der Vorlauf bei fallender Außentemperatur steigt |
| **Niveau** (`shift`) | *Heizkurve Niveau* | Parallelverschiebung: +1 K Niveau ergibt +1 K Vorlauf bei jeder Außentemperatur |

**Beispiel mit den Werten dieser Anlage:**
* HK1 Fußbodenheizung: Neigung 0,8, Niveau 1, Raumsoll 19 °C
* HK2 Heizkörper: Neigung 1,2, Niveau 1, Raumsoll 18 °C

| Außen | HK1 Fußboden | HK2 Heizkörper | HK2 mit Raumsoll 21 °C | HK2 mit Neigung 1,5 |
|---:|---:|---:|---:|---:|
| 15 °C | 24,3 °C | 23,9 °C | 31,5 °C | 25,2 °C |
| 10 °C | 29,1 °C | 31,3 °C | 38,3 °C | 34,4 °C |
| 5 °C | 33,3 °C | 37,8 °C | 44,3 °C | 42,5 °C |
| 0 °C | 37,1 °C | 43,6 °C | 49,8 °C | 49,7 °C |
| −5 °C | 40,6 °C | 48,9 °C | 55,0 °C | 56,4 °C |
| −10 °C | 44,0 °C | 54,0 °C | 60,0 °C | 62,7 °C |

Das zeigt zweierlei. Die **Neigung** wirkt vor allem bei Kälte. Das **Raumsoll**
bzw. das **Niveau** heben die Kurve dagegen über den ganzen Bereich an.

#### Welches Raumsoll verwendet wird
* Es zählt die Temperatur des **aktiven Programms**
  (`heating.circuits.N.operating.programs.active`).
* Hat dieses Programm keine Temperatur oder liegt sie unter 5 °C, wird das Programm
  **Normal** verwendet. Das betrifft etwa *standby*, *frostprotection* oder ein
  Reduziert-Soll von 3 °C, das praktisch „aus“ bedeutet.
* Welches Programm verwendet wurde, steht im Attribut `room_setpoint_program`.

#### Attribute
| Attribut | Bedeutung |
|---|---|
| `outside_temperature`, `room_setpoint`, `shift`, `slope` | die Eingangswerte der Rechnung |
| `room_setpoint_program` | Programm, dessen Raumsoll verwendet wurde |
| `operating_mode` | aktuelle Betriebsart des Heizkreises |
| `heating_enabled` | `false` bei *Nur Warmwasser* oder *Standby*: Der Wert ist dann rein theoretisch |
| `supply_temperature`, `target_supply_temperature` | nur beim Abweichungssensor: Ist- und berechneter Sollwert |

#### Interpretation: Soll-Vorlauf
* Der Wert zeigt, **was der Regler bei dieser Außentemperatur anstrebt**. Er
  eignet sich für Diagramme, um die Heizkurve über Tage zu beobachten, ohne in
  den Regler-Menüs nachzusehen.
* **Er ist ein Modellwert**, kein vom Gerät gemeldeter Sollwert. Der Regler kann
  abweichen, zum Beispiel durch:
  * eine gedämpfte Außentemperatur (Gebäudeträgheit),
  * die Raumtemperaturaufschaltung,
  * minimale und maximale Vorlaufbegrenzungen,
  * die Estrichtrocknung,
  * den Warmwasservorrang.
* **Heizgrenze:** Liegt die Außentemperatur nahe am oder über dem Raumsoll, ergibt
  die Formel Werte um oder unter dem Raumsoll. Der Regler heizt dann in der Regel
  gar nicht, wegen Sparschaltung bzw. Heizgrenze, und die Heizkreispumpe steht.

#### Interpretation: Abweichung zur Heizkurve
Die Abweichung ist **gemessener Vorlauf − berechneter Soll-Vorlauf** in Kelvin.

| Abweichung | typische Bedeutung |
|---|---|
| ca. −3 … +3 K | Regler arbeitet auf der Kurve, alles normal |
| deutlich **positiv** | Vorlauf heißer als die Kurve. Typisch während der Warmwasserbereitung, bei Aufheizen nach Absenkung, bei einem Mischerkreis hinter heißem Kessel oder kurz nach dem Brennerstart |
| deutlich **negativ** | Vorlauf kälter als die Kurve: Brenner aus (Taktpause, Heizgrenze), Pumpe aus, Betriebsart ohne Heizen, oder der Kessel schafft die Leistung nicht |
| dauerhaft negativ bei laufendem Brenner | Hinweis auf zu kleine Leistung, Luft im System oder Fühlerfehler |

Nur aussagekräftig, wenn `heating_enabled` `true` ist und die Heizkreispumpe
läuft (`binary_sensor` *Pumpe*). Für Auswertungen lohnt sich ein Mittelwert,
z. B. per Statistik-Helfer über 1 h; Einzelwerte schwanken durch das
Brennertakten stark.

#### Heizkurve einstellen
Neigung und Niveau lassen sich über die `number`-Entitäten *Heizkurve Neigung*
und *Heizkurve Niveau* ändern. Faustregeln:
* **Zu kalt nur bei Frost** → Neigung um 0,1 erhöhen.
* **Zu kalt in der Übergangszeit** (5 … 15 °C) → Niveau um 1–2 K erhöhen.
* **Überall zu warm** → Niveau senken.

Fußbodenheizungen brauchen typisch eine Neigung von 0,3 … 0,8, Heizkörper von
1,0 … 1,6. Nach jeder Änderung ein bis zwei Tage abwarten, denn Gebäude reagieren
träge. Der Sensor zeigt den neuen Sollwert sofort an.

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

Boost and permanent mode work by temporarily rewriting the device time program.
They only have an effect while the operating mode evaluates that program. For
example, a heating circuit boost does nothing in *DHW only* or *forced normal*,
and a DHW boost only charges the cylinder if it is below target minus
hysteresis. The derived heating curve value is a model of the controller's
target supply temperature. Its deviation sensor (measured − target) is only
meaningful while the circuit is heating. See the German sections
*Boost und Dauerbetrieb im Detail* and *Heizkurve verstehen* for tables and
examples.

Install via HACS as a custom repository or copy `custom_components/vicare` into
your config folder and restart. To go back to the core integration, delete the
folder and restart.

## Lizenz

Apache 2.0, wie Home Assistant. Der Code der Core-Integration ©
Home Assistant Contributors.

[hacs-badge]: https://img.shields.io/badge/HACS-Custom-orange.svg
[hacs-url]: https://hacs.xyz/docs/faq/custom_repositories
