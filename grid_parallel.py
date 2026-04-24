"""
Parallelisierungs-Logik für N-1-Analysen
"""

import pandapower as pp
import multiprocessing as mp
import io
from copy import deepcopy
from grid_analysis import finde_ueberlastete_leitungen, finde_spannungsverletzungen, berechne_lastfluesse
from grid_switches import simuliere_ausfall


def berechne_ausfall_szenario(args):
    """
    Berechnet ein einzelnes Ausfallszenario (für Parallelisierung).
    
    Args:
        args: Tuple mit (netz_json_string, leitung_ausfall, all_cases_dict, lastfall)
    
    Returns:
        dict mit 'leitung_ausfall', 'ueberlastete_leitungen', 'spannungsverletzungen' oder None bei Fehler
    """
    netz_json_string, leitung_ausfall, all_cases_dict, lastfall = args
    
    # Unterdrücke Ausgaben in Worker-Prozessen
    import sys
    from io import StringIO
    old_stdout = sys.stdout
    sys.stdout = StringIO()
    
    try:
        # Lade Netzwerk aus JSON-String
        netzwerk_temp = pp.from_json(io.StringIO(netz_json_string))
        
        # Wende Lastfall an
        wende_lastfall_an(netzwerk_temp, all_cases_dict, lastfall)
        
        # Simuliere Ausfall
        szenario = deepcopy(netzwerk_temp)
        simuliere_ausfall(szenario, leitung_ausfall)
        lastfluss_ergebnis = berechne_lastfluesse(szenario)
        
        # Stelle stdout wieder her
        sys.stdout = old_stdout
        
        if lastfluss_ergebnis is not None:
            ueberlastete_leitungen = finde_ueberlastete_leitungen(lastfluss_ergebnis)
            spannungsverletzungen = finde_spannungsverletzungen(lastfluss_ergebnis)
            
            return {
                'leitung_ausfall': leitung_ausfall,
                'ueberlastete_leitungen': ueberlastete_leitungen,
                'spannungsverletzungen': spannungsverletzungen
            }
        else:
            return None
    except Exception as e:
        # Stelle stdout wieder her
        sys.stdout = old_stdout
        return None


def wende_lastfall_an(netzwerk, all_cases_dict, lastfall):
    """
    Wendet einen Lastfall auf das Netzwerk an
    
    Args:
        netzwerk: pandapower Netzwerk
        all_cases_dict: Dictionary mit Lastfall-Daten
        lastfall: Name des Lastfalls
    """
    import pandas as pd
    
    for key, loadcase_dict in all_cases_dict.items():
        if lastfall in loadcase_dict:
            element_type, attribute = key if isinstance(key, tuple) else (key, None)
            if attribute:
                # Konvertiere zurück zu Series
                loadcase_data = loadcase_dict[lastfall]
                loadcase_series = pd.Series(loadcase_data)
                netzwerk[element_type][attribute] = loadcase_series


def analysiere_netzwerk_parallel(netzwerk, lastfaelle, ausfallkandidaten, all_cases):
    """
    Führt vollständige N-1-Analyse parallel durch
    
    Args:
        netzwerk: pandapower Netzwerk
        lastfaelle: Liste der Lastfälle
        ausfallkandidaten: Liste der Leitungs-Indizes für N-1-Analyse
        all_cases: Dictionary mit Lastfall-Daten
        
    Returns:
        tuple: (statistik_ueberlastungen, statistik_spannungsverletzungen)
    """
    from grid_analysis import aktualisiere_statistik, aktualisiere_spannungsstatistik
    
    statistik_ueberlastungen = {}
    statistik_spannungsverletzungen = {}
    
    # Serialisiere Netzwerk und all_cases für Parallelisierung
    netz_json_string = pp.to_json(netzwerk, filename=None)
    
    # Serialisiere all_cases DataFrames zu dicts
    all_cases_dict = {}
    for key, loadcase_df in all_cases.items():
        all_cases_dict[key] = loadcase_df.to_dict('index')
    
    # Bestimme Anzahl CPU-Kerne
    num_cores = mp.cpu_count()
    print(f"\nVerwende {num_cores} CPU-Kerne für Parallelisierung")
    
    # Erstelle Argumente für parallele Berechnung
    args_list = []
    for lastfall in lastfaelle:
        for leitung_ausfall in ausfallkandidaten:
            args_list.append((netz_json_string, leitung_ausfall, all_cases_dict, lastfall))
    
    # Führe Berechnungen parallel durch
    print(f"Berechne {len(args_list)} Ausfallszenarien parallel...")
    
    import time
    start_time = time.time()
    
    with mp.Pool(processes=num_cores) as pool:
        ergebnisse = pool.map(berechne_ausfall_szenario, args_list)
    
    elapsed_time = time.time() - start_time
    
    # Sammle Ergebnisse und aktualisiere Statistiken
    erfolgreiche_berechnungen = 0
    for ergebnis in ergebnisse:
        if ergebnis is not None:
            erfolgreiche_berechnungen += 1
            aktualisiere_statistik(statistik_ueberlastungen, ergebnis['ueberlastete_leitungen'])
            aktualisiere_spannungsstatistik(statistik_spannungsverletzungen, ergebnis['spannungsverletzungen'])
    
    print(f"✓ {erfolgreiche_berechnungen}/{len(args_list)} Berechnungen erfolgreich in {elapsed_time:.2f}s")
    
    return statistik_ueberlastungen, statistik_spannungsverletzungen

