"""
Validierungs-Funktionen für Netzausbau-Maßnahmen
"""

import multiprocessing as mp
import pandapower as pp
from copy import deepcopy
from grid_parallel import berechne_ausfall_szenario
from grid_analysis import aktualisiere_statistik


def pruefe_massnahme_wirksamkeit(netzwerk, leitung_idx, massnahme_funktion, lastfaelle, ausfallkandidaten, all_cases):
    """
    Prüft, ob eine Maßnahme wirksam ist, d.h. ob die getauschte Leitung danach
    in keinem Fall mehr überlastet ist.
    
    Args:
        netzwerk: pandapower Netzwerk (wird nicht verändert)
        leitung_idx: Index der zu tauschenden Leitung
        massnahme_funktion: Die Maßnahme-Funktion
        lastfaelle: Liste aller Lastfälle
        ausfallkandidaten: Liste aller Ausfallkandidaten
        all_cases: Dictionary mit allen Lastfall-Daten
        
    Returns:
        dict mit:
            'wirksam': bool - True wenn getauschte Leitung in keinem Fall überlastet
            'getauschte_leitung_ueberlastet': bool
            'anzahl_ueberlastungen_getauschte_leitung': int
            'neue_statistik': dict
            'fehler': str | None
    """
    # Erstelle tiefe Kopie des Netzwerks für Test
    netzwerk_test = deepcopy(netzwerk)
    
    # Unterdrücke Ausgaben während der Prüfung
    import sys
    from io import StringIO
    old_stdout = sys.stdout
    sys.stdout = StringIO()
    
    # Führe Maßnahme auf Test-Netzwerk durch
    try:
        massnahme_funktion(netzwerk_test, leitung_idx)
        output = sys.stdout.getvalue()
    except Exception as e:
        sys.stdout = old_stdout
        error_msg = f"Fehler bei Maßnahme-Durchführung: {e}"
        print(f"  ⚠️  [PRÜFUNG] {error_msg}")
        import traceback
        traceback.print_exc()
        return {
            'wirksam': False,
            'getauschte_leitung_ueberlastet': True,
            'anzahl_ueberlastungen_getauschte_leitung': 999,
            'neue_statistik': {},
            'fehler': error_msg
        }
    finally:
        sys.stdout = old_stdout
    
    # Führe vollständige N-1-Analyse durch - PARALLELISIERT
    statistik_ueberlastungen = {}
    
    # Serialisiere Netzwerk und all_cases für Parallelisierung
    netz_json_string = pp.to_json(netzwerk_test, filename=None)
    
    # Serialisiere all_cases DataFrames zu dicts
    all_cases_dict = {}
    for key, loadcase_df in all_cases.items():
        all_cases_dict[key] = loadcase_df.to_dict('index')
    
    # Bestimme Anzahl CPU-Kerne
    num_cores = mp.cpu_count()
    
    # Erstelle Argumente für parallele Berechnung
    args_list = []
    for lastfall in lastfaelle:
        for leitung_ausfall in ausfallkandidaten:
            args_list.append((netz_json_string, leitung_ausfall, all_cases_dict, lastfall))
    
    # Führe Berechnungen parallel durch
    with mp.Pool(processes=num_cores) as pool:
        ergebnisse = pool.map(berechne_ausfall_szenario, args_list)
    
    # Sammle Ergebnisse und aktualisiere Statistiken
    for ergebnis in ergebnisse:
        if ergebnis is not None:
            aktualisiere_statistik(statistik_ueberlastungen, ergebnis['ueberlastete_leitungen'])
        else:
            # Fehler bei Lastflussberechnung - zähle kritischste Leitung als überlastet
            if leitung_idx not in statistik_ueberlastungen:
                statistik_ueberlastungen[leitung_idx] = 0
            statistik_ueberlastungen[leitung_idx] += 1
    
    # Prüfe ob getauschte Leitung in der Statistik ist
    anzahl_ueberlastungen = statistik_ueberlastungen.get(leitung_idx, 0)
    getauschte_leitung_ueberlastet = anzahl_ueberlastungen > 0
    wirksam = not getauschte_leitung_ueberlastet
    
    return {
        'wirksam': wirksam,
        'getauschte_leitung_ueberlastet': getauschte_leitung_ueberlastet,
        'anzahl_ueberlastungen_getauschte_leitung': anzahl_ueberlastungen,
        'neue_statistik': statistik_ueberlastungen,
        'fehler': None
    }

