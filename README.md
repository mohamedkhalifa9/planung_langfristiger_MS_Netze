# Grid Expansion Algorithmus

## Projektkontext

Dieser Code entstand im Rahmen einer **Gruppenarbeit** an der Universität im Projekt bzw. der Lehrveranstaltung **„Planung langfristig optimaler Mittelspannungsnetze“**. Ausgangspunkt war die **Implementierungsphase** aus dem Kursmaterial (vgl. `grid_expansion.ipynb` im Projekt „Project Netz“): dort wird die Aufgabenstellung für den Netzausbau des fiktiven MS-Netzes „Bielefeld“ beschrieben.

## Aufgabenstellung 

Im Szenario sind Sie **Verteilnetzbetreiber** eines fiktiven Mittelspannungsnetzes („Bielefeld“). Mit der **Energiewende** steigen u. a. der Anteil von **Elektromobilität**, **Wärmepumpen** und **Photovoltaik** – das Netz repräsentiert bereits ein **Zukunftsszenario** (Datei `mv_grid_bielefeld.json`). Ihre Aufgabe ist, ein **Werkzeug** zu entwickeln, mit dem der **Netzausbau** so geplant werden kann, dass das System **künftig unter N-1-Bedingungen** weiter betrieben werden kann und die **Investitionskosten** der Maßnahmen **möglichst günstig** ausfallen.

Dazu liegen das Netzmodell sowie **Kosten für Leitungen und Transformatoren** (z. B. `Equipment_Cost.xlsx`) vor. Die Lösung darf – wie im Notebook angedeutet – sowohl in Notebooks als auch in **eigenständigen Python-Dateien** umgesetzt werden; **dieses Projekt** folgt der modularen `.py`-Variante.

**Ergänzende Aufgabe im Kursnotebook (optional / Folgeaufgabe):** Anbindung eines **Rechenzentrums mit 5 MW** im Norden (Bus 44) – Prüfung, ob zusätzliche Ausbaumaßnahmen nötig sind, welche infrage kommen und mit welchen Kosten.

## Was dieser Code konkret macht

Das Programm (`main.py` und die zugehörigen Module) ist ein **iterativer Netzausbau-Algorithmus** auf Basis von **pandapower** und **simbench**:

- **Lastfluss** und **Auswertung** über die vorgegebenen **Lastfälle** (und Ausfallkandidaten für die N-1-bezogene Absicherung).
- Erkennung von **Leitungsüberlastungen** und **Spannungsbandverletzungen** (konfigurierbares pu-Band).
- **Maßnahmen** mit Kostenverfolgung: u. a. **Leitungsupgrades** (Erdkabel/Freileitung gemäß Kostentabelle), **Parallelleitungen**, sowie **Blindleistungssteuerung** an statischen Erzeugern nach **VDE-AR-N 4105**, um Spannungsprobleme kostenfrei mit abzufangen wo möglich.
- **Validierung** von Upgrades und **parallelisierte** Szenario-Berechnung (siehe `grid_parallel.py`).
- Ausgabe des **optimierten Netzmodells** (JSON) und optional einer **Folium-/HTML-Kartenvisualisierung**.

Dieser Ordner enthält die **refaktorisierte**, modular aufgeteilte Version des Grid-Expansion-Algorithmus (siehe auch `STRUCTURE.md`).

## Struktur

```
newAlgorithm/
├── config.py                  # Konfigurationsparameter
├── utils.py                   # Hilfsfunktionen
├── grid_analysis.py           # Netzwerk-Analyse
├── grid_switches.py           # Schalter-Logik
├── grid_types.py              # Leitungstyp-Erkennung
├── grid_upgrades.py           # Upgrade-Funktionen
├── grid_parallel.py           # Parallelisierung
├── grid_validation.py         # Validierung
├── grid_reactive_power.py     # Blindleistungssteuerung (VDE-AR-N 4105)
├── main.py                    # Hauptalgorithmus
├── STRUCTURE.md               # Detaillierte Dokumentation
└── README.md                  # Diese Datei
```

## Verwendung

### Ausführung

```bash
cd Bielefeld/newAlgorithm
python main.py
```

### Voraussetzungen

Die folgenden Dateien müssen im übergeordneten Verzeichnis (`Bielefeld/`) vorhanden sein:
- `mv_grid_bielefeld.json` - Netzwerk-Datei
- `Equipment_Cost.xlsx` - Equipment-Kosten

### Ausgabe

Die Ergebnisse werden im übergeordneten Verzeichnis gespeichert:
- `mv_grid_bielefeld_optimized.json` - Optimiertes Netzwerk
- `mv_grid_bielefeld_optimized_visualization.html` - Visualisierung

## Unterschiede zur Original-Version

- ✅ Modularer Aufbau (10 Module statt 1 große Datei)
- ✅ Eliminierte Code-Duplikation
- ✅ Bessere Nutzung von pandapower-Funktionen
- ✅ Zentrale Konfiguration
- ✅ Verbesserte Wartbarkeit
- ✅ Blindleistungssteuerung nach VDE-AR-N 4105

## Blindleistungssteuerung (VDE-AR-N 4105)

Das Modul `grid_reactive_power.py` implementiert die Blindleistungssteuerung für Erzeugungsanlagen (`sgen`-Elemente) gemäß VDE-AR-N 4105 zur Behandlung von Spannungsverletzungen.

### Funktionen

#### `berechne_q_limits_aus_cos_phi(p_mw, cos_phi=0.95)`
Berechnet die Blindleistungsgrenzen basierend auf cos φ = 0.95:
- **Input**: Wirkleistung P in MW
- **Output**: `(min_q_mvar, max_q_mvar)` - Blindleistungsgrenzen in MVar
- **Berechnung**: 
  - Scheinleistung: `S = P / cos_φ`
  - Blindleistung: `Q = √(S² - P²)`
  - Grenzen: `min_q = -Q` (untererregt, kapazitiv), `max_q = +Q` (übererregt, induktiv)

#### `wende_reactive_power_control_an(netzwerk, cos_phi=0.95, fuer_spannungsverletzungen=False)`
Wendet Blindleistungssteuerung auf alle `sgen`-Elemente an:
- **Input**: 
  - `netzwerk`: pandapower Netzwerk
  - `cos_phi`: Verschiebungsfaktor (Standard: 0.95)
  - `fuer_spannungsverletzungen`: Wenn `True`, wird Blindleistung zur Behandlung von Spannungsverletzungen angepasst
- **Output**: Dictionary mit Informationen zu geänderten `sgen`-Elementen
- **Funktionsweise**:
  - Setzt `q_mvar` direkt in den `sgen`-Elementen
  - Bei `fuer_spannungsverletzungen=True`:
    - **Unterspannung** (< 0.95 pu): Induktive Blindleistung (positiv) zur Spannungserhöhung
    - **Überspannung** (> 1.05 pu): Kapazitive Blindleistung (negativ) zur Spannungssenkung
    - **Normalbereich** (0.95 - 1.05 pu): Q = 0.0

### Anwendungszeitpunkte

#### 1. Initial (vor Iterationen)
- **Zeitpunkt**: Nach dem Laden des Netzwerks, vor der Hauptschleife
- **Ablauf**:
  1. Erster Lastfall wird angewendet
  2. Initialer Lastfluss wird berechnet
  3. Blindleistungssteuerung wird mit `fuer_spannungsverletzungen=True` angewendet
  4. Ergebnis wird geprüft und ausgegeben
- **Zweck**: Optimiert das Netzwerk bereits vor den Iterationen

#### 2. Während Iterationen (parallel zu Überlastungsmaßnahmen)
- **Zeitpunkt**: In jeder Iteration, wenn Spannungsverletzungen vorhanden sind
- **Ablauf**:
  1. Netzwerk wird analysiert (N-1-Analyse)
  2. Wenn Spannungsverletzungen vorhanden:
     - Lastfluss wird berechnet
     - Blindleistungssteuerung wird angewendet
     - Erfolg wird geprüft
     - Als kostenlose Maßnahme dokumentiert
  3. Parallel dazu: Überlastungsmaßnahmen (Leitung-Upgrades)
- **Zweck**: Behebt Spannungsverletzungen parallel zu anderen Maßnahmen

### Konfiguration

In `config.py`:
```python
# Blindleistungssteuerung (VDE-AR-N 4105)
REACTIVE_POWER_COS_PHI = 0.95  # Standard cos φ = 0.95

# Spannungsband (pu)
VOLTAGE_MIN_PU = 0.95  # Untere Grenze
VOLTAGE_MAX_PU = 1.05  # Obere Grenze
```

### Vorteile

- ✅ **Kostenlos**: Keine Investitionskosten
- ✅ **Schnell**: Sofortige Anpassung möglich
- ✅ **Effektiv**: Kann viele Spannungsverletzungen beheben
- ✅ **Normkonform**: Entspricht VDE-AR-N 4105
- ✅ **Parallel**: Läuft parallel zu anderen Maßnahmen

### Beispiel-Ausgabe

```
================================================================================
BLINDLEISTUNGSSTEUERUNG (VOR ITERATIONEN)
================================================================================
→ Wende Blindleistungssteuerung an (vor allen Iterationen)...

✓ Blindleistung für 15 sgen-Elemente gesetzt:
  sgen 0 (Bus 5, V=0.942 pu, P=2.50 MW): Q = 0.00 → 0.82 MVar [-0.82, 0.82]
  sgen 1 (Bus 12, V=1.062 pu, P=1.80 MW): Q = 0.00 → -0.59 MVar [-0.59, 0.59]
  ...

✓ INITIALE BLINDLEISTUNGSSTEUERUNG AUSGEFÜHRT:
  - 15 sgen-Elemente angepasst
  ✓ Keine Spannungsverletzungen mehr vorhanden
```

Siehe `STRUCTURE.md` für detaillierte Informationen zur Code-Struktur.
