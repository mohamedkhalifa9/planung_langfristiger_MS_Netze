"""
Grid Expansion Algorithmus - Hauptskript (Refactored Version)

Vereinfachte und modularisierte Version des Grid Expansion Algorithmus
"""

import pandapower as pp
import simbench as sb
import pandas as pd
from copy import deepcopy
import webbrowser
import os
from pathlib import Path

# Importiere alle Module
from config import Config
from utils import format_deutsch
from grid_analysis import (
    bestimme_kritischste_leitung,
    berechne_lastfluesse
)
from grid_parallel import analysiere_netzwerk_parallel
from grid_types import leitungs_typ, set_line_costs
from grid_upgrades import (
    upgrade_leitung,
    fuege_parallelleitungen_hinzu,
    finde_naechstes_upgrade,
    set_costs
)
from grid_validation import pruefe_massnahme_wirksamkeit
from grid_reactive_power import wende_reactive_power_control_an
from grid_analysis import finde_spannungsverletzungen

def lade_netzwerk_und_kosten():
    """
    Lädt Netzwerk, Lastfälle und Equipment-Kosten
    
    Returns:
        tuple: (netzwerk, all_cases, lastfaelle, line_costs_df, trafo_costs_df)
    """
    print("="*80)
    print("GRID EXPANSION ALGORITHMUS (Refactored)")
    print("="*80)
    
    # Bestimme Basis-Verzeichnis (übergeordnetes Verzeichnis)
    script_dir = Path(__file__).parent
    base_dir = script_dir.parent
    
    # Lade Netzwerk
    grid_file = base_dir / Config.GRID_FILE.replace("../", "")
    print(f"\nLade Netzwerk aus {grid_file}...")
    
    # Prüfe ob Datei existiert
    if not grid_file.exists():
        raise FileNotFoundError(f"Netzwerk-Datei nicht gefunden: {grid_file}")
    
    # Prüfe ob Datei nicht leer ist
    if grid_file.stat().st_size == 0:
        raise ValueError(f"Netzwerk-Datei ist leer: {grid_file}")
    
    netzwerk = pp.from_json(str(grid_file))
    print(f"✓ Netzwerk geladen: {len(netzwerk.bus)} Busse, {len(netzwerk.line)} Leitungen")
    
    # Lade Lastfälle
    print("Lade Lastfälle...")
    all_cases = sb.get_absolute_values(netzwerk, False)
    lastfaelle = list(all_cases[('load', 'p_mw')].index)
    
    # Entferne n1 aus Lastfällen falls vorhanden
    if 'n1' in lastfaelle:
        lastfaelle.remove('n1')
        print("N1 aus Lastfällen entfernt (wird anders behandelt)")
    
    print(f"✓ Verfügbare Lastfälle: {lastfaelle}")
    
    # Wende Blindleistungssteuerung an (VDE-AR-N 4105) für sgen-Elemente
    # Berechne initialen Lastfluss mit erstem Lastfall für Spannungsverletzungen
    if 'sgen' in netzwerk and len(netzwerk.sgen) > 0:
        print("\n→ Berechne initialen Lastfluss für Blindleistungssteuerung...")
        if lastfaelle:
            # Wende ersten Lastfall an für initiale Analyse
            import pandas as pd
            from grid_parallel import wende_lastfall_an
            
            # Konvertiere all_cases zu dict-Format für wende_lastfall_an
            all_cases_dict = {}
            for key, loadcase_df in all_cases.items():
                all_cases_dict[key] = loadcase_df.to_dict('index')
            
            wende_lastfall_an(netzwerk, all_cases_dict, lastfaelle[0])
            berechne_lastfluesse(netzwerk)
            print(f"✓ Initialer Lastfluss berechnet (Lastfall: {lastfaelle[0]})")
        
        # Wende Blindleistungssteuerung mit aktiver Spannungsverletzungsbehandlung an
        print(f"\n{'='*80}")
        print("BLINDLEISTUNGSSTEUERUNG (VOR ITERATIONEN)")
        print(f"{'='*80}")
        print("→ Wende Blindleistungssteuerung an (vor allen Iterationen)...")
        aenderungen_initial = wende_reactive_power_control_an(
            netzwerk,
            cos_phi=Config.REACTIVE_POWER_COS_PHI,
            fuer_spannungsverletzungen=True  # Aktive Anpassung für Spannungsverletzungen
        )
        
        # Prüfe ob Spannungsverletzungen behoben wurden
        
        verletzungen_nach = finde_spannungsverletzungen(netzwerk)
        if aenderungen_initial:
            print(f"\n✓ INITIALE BLINDLEISTUNGSSTEUERUNG AUSGEFÜHRT:")
            print(f"  - {len(aenderungen_initial)} sgen-Elemente angepasst")
            if verletzungen_nach:
                print(f"  ⚠️  {len(verletzungen_nach)} Spannungsverletzungen verbleiben")
            else:
                print(f"  ✓ Keine Spannungsverletzungen mehr vorhanden")
        else:
            print(f"  ⚠️  Keine sgen-Elemente gefunden oder keine Änderungen vorgenommen")
    
    # Lade Kosten
    costs_file = base_dir / Config.EQUIPMENT_COSTS_FILE.replace("../", "")
    print(f"Lade Equipment-Kosten aus {costs_file}...")
    
    # Prüfe ob Datei existiert
    if not costs_file.exists():
        print(f"⚠️  Warnung: Equipment-Kosten-Datei nicht gefunden: {costs_file}")
        print("  Fortfahren ohne Kosten-Informationen...")
        return netzwerk, all_cases, lastfaelle, None, None
    
    try:
        line_costs_df = pd.read_excel(str(costs_file), sheet_name='Lines')
        trafo_costs_df = pd.read_excel(str(costs_file), sheet_name='Transformers')
        print(f"✓ Kosten geladen: {len(line_costs_df)} Leitungstypen, {len(trafo_costs_df)} Transformator-Typen")
        
        # Setze globale Kosten-Variablen in den Modulen
        set_line_costs(line_costs_df)
        set_costs(line_costs_df, trafo_costs_df)
    except Exception as e:
        print(f"⚠️  Fehler beim Laden der Kosten: {e}")
        line_costs_df = None
        trafo_costs_df = None
    
    return netzwerk, all_cases, lastfaelle, line_costs_df, trafo_costs_df


def bestimme_massnahme_mit_validierung(netzwerk, leitung_idx, lastfaelle, ausfallkandidaten, all_cases):
    """
    Bestimmt die optimale Maßnahme mit Validierung
    
    Args:
        netzwerk: pandapower Netzwerk
        leitung_idx: Index der kritischen Leitung
        lastfaelle: Liste der Lastfälle
        ausfallkandidaten: Liste der Ausfallkandidaten
        all_cases: Dictionary mit Lastfall-Daten
        
    Returns:
        dict: Informationen zur durchgeführten Maßnahme
    """
    typ = leitungs_typ(netzwerk, leitung_idx)
    print(f"Leitungstyp: {typ}")
    
    # Teste verschiedene Upgrade-Stufen
    max_stufen = Config.MAX_UPGRADE_STUFEN
    netzwerk_basis = netzwerk
    
    for stufe in range(1, max_stufen + 1):
        print(f"\n  [PRÜFUNG] Maßnahme Stufe {stufe} für Leitung {leitung_idx}...")
        
        # Bestimme Maßnahme basierend auf Typ
        massnahme_funktion, ist_letztes_upgrade = bestimme_massnahme_funktion(
            netzwerk_basis, leitung_idx, typ
        )
        
        if massnahme_funktion is None:
            print(f"  ⚠️  Keine Maßnahme verfügbar")
            break
        
        # Bei Parallelleitungen: Direkt durchführen ohne Validierung (TODO)
        if massnahme_funktion == fuege_parallelleitungen_hinzu:
            print(f"  → [UMSETZUNG] Führe Parallelleitungen durch (nicht validiert)")
            return massnahme_funktion(netzwerk, leitung_idx)
        
        # Prüfe Wirksamkeit der Maßnahme
        print(f"  → [PRÜFUNG] Prüfe Wirksamkeit der Maßnahme...")
        validierung = pruefe_massnahme_wirksamkeit(
            netzwerk_basis, leitung_idx, massnahme_funktion,
            lastfaelle, ausfallkandidaten, all_cases
        )
        
        if validierung['fehler']:
            print(f"  ⚠️  [PRÜFUNG] Fehler bei Validierung: {validierung['fehler']}")
            if ist_letztes_upgrade:
                print(f"  → [UMSETZUNG] Keine höhere Stufe verfügbar, führe Maßnahme durch")
                return massnahme_funktion(netzwerk, leitung_idx)
            else:
                # Versuche nächste Stufe
                netzwerk_basis = fuehre_massnahme_temporaer_durch(netzwerk_basis, leitung_idx, massnahme_funktion)
                typ = leitungs_typ(netzwerk_basis, leitung_idx)
                continue
        
        if validierung['wirksam']:
            print(f"  ✓ [PRÜFUNG] Maßnahme ist wirksam - getauschte Leitung in keinem Fall überlastet")
            print(f"  → [UMSETZUNG] Führe alle Schritte bis Stufe {stufe} durch")
            return fuehre_alle_stufen_durch(netzwerk, leitung_idx, stufe)
        else:
            print(f"  ✗ [PRÜFUNG] Maßnahme nicht wirksam - noch {validierung['anzahl_ueberlastungen_getauschte_leitung']} mal überlastet")
            
            if ist_letztes_upgrade:
                print(f"  → [UMSETZUNG] Keine höhere Stufe verfügbar, versuche Parallelleitungen")
                return fuege_parallelleitungen_hinzu(netzwerk, leitung_idx)
            
            # Versuche nächste Stufe
            netzwerk_basis = fuehre_massnahme_temporaer_durch(netzwerk_basis, leitung_idx, massnahme_funktion)
            typ = leitungs_typ(netzwerk_basis, leitung_idx)
            continue
    
    # Fallback
    print(f"  → [UMSETZUNG] Keine wirksame Maßnahme gefunden, führe letzte Maßnahme durch")
    return upgrade_leitung(netzwerk, leitung_idx)


def bestimme_massnahme_funktion(netzwerk, leitung_idx, typ):
    """
    Bestimmt die Maßnahmen-Funktion basierend auf Leitungstyp
    
    Returns:
        tuple: (massnahme_funktion, ist_letztes_upgrade)
    """
    erdkabel_typen = ["70er_erdkabel", "95er_erdkabel", "120er_erdkabel",
                      "150er_erdkabel", "185er_erdkabel", "240er_erdkabel"]
    
    if typ in erdkabel_typen:
        upgrade = finde_naechstes_upgrade(netzwerk, leitung_idx, ist_erdkabel=True)
        if upgrade is not None:
            current_max_i = netzwerk.line.at[leitung_idx, 'max_i_ka']
            print(f"  → Upgrade auf größeres Erdkabel (max_i_ka: {current_max_i:.3f} → {upgrade['max_i_ka']:.3f})")
            return upgrade_leitung, False
        else:
            print(f"  → Kein größeres Erdkabel verfügbar, Parallelleitungen")
            return fuege_parallelleitungen_hinzu, True
    
    elif typ == "freileitung":
        upgrade = finde_naechstes_upgrade(netzwerk, leitung_idx, ist_erdkabel=False)
        if upgrade is not None:
            current_max_i = netzwerk.line.at[leitung_idx, 'max_i_ka']
            print(f"  → Upgrade auf größere Freileitung (max_i_ka: {current_max_i:.3f} → {upgrade['max_i_ka']:.3f})")
            return upgrade_leitung, False
        else:
            return upgrade_leitung, True
    
    else:
        return upgrade_leitung, True


def fuehre_massnahme_temporaer_durch(netzwerk_basis, leitung_idx, massnahme_funktion):
    """Führt Maßnahme temporär durch für nächste Prüfung"""
    import sys
    from io import StringIO
    
    netzwerk_temp = deepcopy(netzwerk_basis)
    old_stdout = sys.stdout
    sys.stdout = StringIO()
    
    try:
        massnahme_funktion(netzwerk_temp, leitung_idx)
    except:
        pass
    finally:
        sys.stdout = old_stdout
    
    return netzwerk_temp


def fuehre_alle_stufen_durch(netzwerk, leitung_idx, anzahl_stufen):
    """
    Führt alle Upgrade-Stufen durch (nur letzte Stufe mit Kosten)
    
    Returns:
        dict: Informationen zur finalen Maßnahme
    """
    alte_std_type_initial = netzwerk.line.at[leitung_idx, 'std_type']
    aenderung = None
    
    for schritt in range(1, anzahl_stufen + 1):
        ist_letzter_schritt = (schritt == anzahl_stufen)
        
        if ist_letzter_schritt:
            print(f"  → [UMSETZUNG] Schritt {schritt}/{anzahl_stufen}: Finale Maßnahme (mit Kosten)")
            aenderung = upgrade_leitung(netzwerk, leitung_idx)
        else:
            print(f"  → [UMSETZUNG] Schritt {schritt}/{anzahl_stufen}: Zwischenschritt (kostenlos)")
            aenderung_temp = upgrade_leitung(netzwerk, leitung_idx)
            if aenderung_temp:
                aenderung_temp['kosten'] = 0
    
    # Aktualisiere mit initialem Typ
    if aenderung:
        aenderung['alte_std_type'] = alte_std_type_initial
        print(f"  → [UMSETZUNG] Finale Kosten: €{format_deutsch(aenderung.get('kosten', 0), 2)}")
    
    return aenderung if aenderung else upgrade_leitung(netzwerk, leitung_idx)


def zeige_statistik(statistik_ueberlastungen, statistik_spannungsverletzungen, netzwerk):
    """Zeigt Überlastungs- und Spannungsstatistik"""
    print(f"\nÜberlastungs-Statistik:")
    if statistik_ueberlastungen:
        sorted_stats = sorted(statistik_ueberlastungen.items(), key=lambda x: x[1], reverse=True)
        for leitung_idx, anzahl in sorted_stats[:10]:
            print(f"  Leitung {leitung_idx}: {anzahl} mal überlastet")
    else:
        print(f"  Keine Überlastungen gefunden")
    
    print(f"\nSpannungsverletzungs-Statistik ({Config.VOLTAGE_MIN_PU} - {Config.VOLTAGE_MAX_PU} pu):")
    if statistik_spannungsverletzungen:
        sorted_spannung = sorted(statistik_spannungsverletzungen.items(), key=lambda x: x[1], reverse=True)
        for bus_idx, anzahl in sorted_spannung[:10]:
            bus_name = netzwerk.bus.at[bus_idx, 'name'] if 'name' in netzwerk.bus.columns else f"Bus {bus_idx}"
            print(f"  Bus {bus_idx} ({bus_name}): {anzahl} mal außerhalb des Spannungsbandes")
    else:
        print(f"  Keine Spannungsverletzungen gefunden")


def erstelle_visualisierung(netzwerk, aenderungen, gesamtkosten):
    """Erstellt HTML-Visualisierung des optimierten Netzwerks"""
    print(f"\n{'='*80}")
    print("ERSTELLE VISUALISIERUNG")
    print(f"{'='*80}")
    
    try:
        from visualizer import (
            determine_colors, determine_voltages, determine_tooltips,
            determine_plot_style, plot_grid, add_colormap
        )
        from folium import Map
        from branca.element import Element
        
        # Erstelle Kopie für Visualisierung
        netzwerk_viz = deepcopy(netzwerk)
        
        # Sammle geänderte Leitungen
        geaenderte_leitungen = set()
        neue_leitungen = set()
        
        for aend in aenderungen:
            if aend['typ'] == 'upgrade':
                geaenderte_leitungen.add(aend['leitung_idx'])
            elif aend['typ'] == 'parallel':
                geaenderte_leitungen.add(aend['leitung_idx'])
                neue_leitungen.update(aend['neue_leitungen'])
        
        # Erstelle Karte
        center = [netzwerk_viz.bus_geodata['y'].median(), netzwerk_viz.bus_geodata['x'].median()]
        m = Map(location=center, zoom_start=14, max_zoom=19, tiles='OpenStreetMap')
        
        # Visualisierung vorbereiten
        determine_voltages(netzwerk_viz)
        determine_colors(netzwerk_viz, None, 'lv_mv_grids', True)
        
        # Überschreibe Farben für geänderte Leitungen
        for line_idx in geaenderte_leitungen.union(neue_leitungen):
            if line_idx in netzwerk_viz.line.index:
                netzwerk_viz.line.at[line_idx, 'color'] = Config.COLOR_GEAENDERTE_LEITUNG
        
        determine_tooltips(netzwerk_viz, True, True, True, False, False, None)
        determine_plot_style(netzwerk_viz, True, False, True)
        plot_grid(m, netzwerk_viz, True, True, False, False, None)
        add_colormap(m, 'lv_mv_grids')
        
        # Füge Info-Box hinzu
        info_html = f'''
        <div style="position: fixed; top: 10px; right: 10px; width: 300px; height: auto; 
                    background-color: white; border:2px solid grey; z-index:9999; 
                    font-size:14px; padding: 10px">
        <h4>Netzwerk-Info</h4>
        <b>Busse:</b> {len(netzwerk.bus)}<br>
        <b>Leitungen:</b> {len(netzwerk.line)}<br>
        <b>Geänderte Leitungen:</b> {len(geaenderte_leitungen)}<br>
        <b>Neue Leitungen:</b> {len(neue_leitungen)}<br>
        <b>Gesamtkosten:</b> €{format_deutsch(gesamtkosten, 2)}<br><br>
        <b>Legende:</b><br>
        <span style="color:{Config.COLOR_STANDARD_LEITUNG}">●</span> Unveränderte Leitungen<br>
        <span style="color:{Config.COLOR_GEAENDERTE_LEITUNG}">●</span> Geänderte/Neue Leitungen
        </div>
        '''
        m.get_root().html.add_child(Element(info_html))
        
        # Speichere und öffne Karte
        script_dir = Path(__file__).parent
        base_dir = script_dir.parent
        vis_file = base_dir / Config.VISUALIZATION_FILE.replace("../", "")
        m.save(str(vis_file))
        webbrowser.open('file://' + str(vis_file.absolute()))
        print(f"✓ Visualisierung gespeichert: {vis_file}")
        
    except Exception as e:
        print(f"⚠️  Fehler bei Visualisierung: {e}")
        import traceback
        traceback.print_exc()


def main():
    """Hauptfunktion des Grid Expansion Algorithmus"""
    
    # Initialisierung
    netzwerk, all_cases, lastfaelle, line_costs_df, trafo_costs_df = lade_netzwerk_und_kosten()
    
    # Ausfallkandidaten: Alle Leitungen
    ausfallkandidaten = list(netzwerk.line.index)
    print(f"Ausfallkandidaten: {len(ausfallkandidaten)} Leitungen")
    
    # Hauptschleife
    aenderungen = []
    gesamtkosten = 0
    iteration = 0
    ueberlastung_vorhanden = True
    
    while ueberlastung_vorhanden and iteration < Config.MAX_ITERATIONS:
        iteration += 1
        print(f"\n{'='*80}")
        print(f"ITERATION {iteration}")
        print(f"{'='*80}")
        
        # Analysiere Netzwerk (parallelisiert)
        statistik_ueberlastungen, statistik_spannungsverletzungen = analysiere_netzwerk_parallel(
            netzwerk, lastfaelle, ausfallkandidaten, all_cases
        )
        
        # Zeige Statistik
        zeige_statistik(statistik_ueberlastungen, statistik_spannungsverletzungen, netzwerk)
        
        # Blindleistungssteuerung parallel zu Überlastungsmaßnahmen (wenn Spannungsverletzungen vorhanden)
        if statistik_spannungsverletzungen and 'sgen' in netzwerk and len(netzwerk.sgen) > 0:
            print(f"\n→ [MASSNAHME] Blindleistungssteuerung für {len(statistik_spannungsverletzungen)} Spannungsverletzungen...")
            berechne_lastfluesse(netzwerk)  # Berechne Lastfluss für aktuelle Spannungen
            aenderungen_sgen = wende_reactive_power_control_an(
                netzwerk,
                cos_phi=Config.REACTIVE_POWER_COS_PHI,
                fuer_spannungsverletzungen=True
            )
            
            if aenderungen_sgen:
                # Prüfe erneut nach Anpassung der Blindleistung
                berechne_lastfluesse(netzwerk)
                from grid_analysis import finde_spannungsverletzungen
                neue_verletzungen = finde_spannungsverletzungen(netzwerk)
                if len(neue_verletzungen) < len(statistik_spannungsverletzungen):
                    print(f"✓ Spannungsverletzungen reduziert: {len(statistik_spannungsverletzungen)} → {len(neue_verletzungen)}")
                    # Blindleistungssteuerung als Maßnahme dokumentieren
                    aenderung = {
                        'typ': 'reactive_power',
                        'iteration': iteration,
                        'kosten': 0,  # Blindleistungssteuerung ist kostenlos
                        'anzahl_sgen_geaendert': len(aenderungen_sgen),
                        'spannungsverletzungen_vorher': len(statistik_spannungsverletzungen),
                        'spannungsverletzungen_nachher': len(neue_verletzungen)
                    }
                    aenderungen.append(aenderung)
                else:
                    print(f"⚠️  Spannungsverletzungen nicht reduziert: {len(neue_verletzungen)} verbleiben")
        
        # Bestimme kritischste Leitung
        kritischste_leitung = bestimme_kritischste_leitung(statistik_ueberlastungen)
        
        if kritischste_leitung is None:
            if statistik_spannungsverletzungen:
                print("\n✓ Keine Überlastungen mehr vorhanden!")
                print(f"⚠️  Aber {len(statistik_spannungsverletzungen)} Busse mit Spannungsverletzungen")
                print("  (Blindleistungssteuerung wurde bereits in dieser Iteration angewendet)")
            else:
                print("\n✓ Keine Überlastungen mehr vorhanden!")
                print("✓ Keine Spannungsverletzungen mehr vorhanden!")
            ueberlastung_vorhanden = False
            break
        
        print(f"\nKritischste Leitung: {kritischste_leitung} ({statistik_ueberlastungen[kritischste_leitung]} mal überlastet)")
        
        # Bestimme und führe Maßnahme durch
        aenderung = bestimme_massnahme_mit_validierung(
            netzwerk, kritischste_leitung, lastfaelle, ausfallkandidaten, all_cases
        )
        
        if aenderung:
            aenderung['iteration'] = iteration
            aenderung['typ_leitung'] = leitungs_typ(netzwerk, kritischste_leitung)
            aenderungen.append(aenderung)
            gesamtkosten += aenderung.get('kosten', 0)
    
    # Abschluss
    print(f"\n{'='*80}")
    print("ALGORITHMUS ABGESCHLOSSEN")
    print(f"{'='*80}")
    
    if iteration >= Config.MAX_ITERATIONS:
        print(f"⚠️  Maximale Iterationen ({Config.MAX_ITERATIONS}) erreicht")
    
    # Speichere optimiertes Netzwerk
    script_dir = Path(__file__).parent
    base_dir = script_dir.parent
    output_file = base_dir / Config.OUTPUT_FILE.replace("../", "")
    pp.to_json(netzwerk, str(output_file))
    print(f"\n✓ Optimiertes Netzwerk gespeichert: {output_file}")
    
    # Zusammenfassung
    print(f"\n{'='*80}")
    print("ZUSAMMENFASSUNG DER ÄNDERUNGEN")
    print(f"{'='*80}")
    print(f"\nAnzahl Änderungen: {len(aenderungen)}")
    print(f"Gesamtkosten: €{format_deutsch(gesamtkosten, 2)}\n")
    
    if aenderungen:
        print("Detaillierte Änderungen:")
        print("-" * 80)
        for i, aend in enumerate(aenderungen, 1):
            print(f"\n{i}. Iteration {aend['iteration']} - {aend.get('typ_leitung', 'unbekannt')}")
            if aend['typ'] == 'upgrade':
                print(f"   Leitung {aend['leitung_idx']}: Upgrade")
                print(f"   Alt: {aend['alte_std_type']}")
                print(f"   Neu: {aend['neue_std_type']}")
                print(f"   Kosten: €{format_deutsch(aend['kosten'], 2)}")
            elif aend['typ'] == 'parallel':
                print(f"   Leitung {aend['leitung_idx']}: Parallelleitungen hinzugefügt")
                print(f"   Neue Leitungen: {aend['neue_leitungen']}")
                print(f"   Kosten: €{format_deutsch(aend['kosten'], 2)}")
            elif aend['typ'] == 'reactive_power':
                print(f"   Blindleistungssteuerung (VDE-AR-N 4105)")
                print(f"   {aend.get('anzahl_sgen_geaendert', 0)} sgen-Elemente angepasst")
                print(f"   Spannungsverletzungen: {aend.get('spannungsverletzungen_vorher', 0)} → {aend.get('spannungsverletzungen_nachher', 0)}")
                print(f"   Kosten: €{format_deutsch(aend.get('kosten', 0), 2)} (kostenlos)")
    
    # Visualisierung
    erstelle_visualisierung(netzwerk, aenderungen, gesamtkosten)


if __name__ == "__main__":
    main()

