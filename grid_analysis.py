"""
Analyse-Funktionen für Netzwerkzustand (Überlastungen, Spannungsverletzungen)
"""

import pandapower as pp
from pandapower.topology import unsupplied_buses
from config import Config


def berechne_lastfluesse(netzwerk):
    """
    Berechnet die Lastflüsse für das Netzwerk
    
    Args:
        netzwerk: pandapower Netzwerk
        
    Returns:
        pandapower Netzwerk mit Lastflussergebnissen oder None bei Fehler
    """
    try:
        pp.runpp(
            netzwerk,
            calculate_voltage_angles=Config.POWERFLOW_CALCULATE_VOLTAGE_ANGLES,
            init=Config.POWERFLOW_INIT,
            max_iteration=Config.POWERFLOW_MAX_ITERATION,
            numba=Config.POWERFLOW_NUMBA
        )
        
        # Prüfe Busversorgung
        pruefe_busversorgung(netzwerk)
        
        return netzwerk
    except Exception as e:
        print(f"  Fehler bei Lastflussberechnung: {e}")
        import traceback
        traceback.print_exc()
        return netzwerk


def pruefe_busversorgung(netzwerk):
    """
    Prüft, ob alle Busse mit Spannung versorgt sind.
    Gibt eine Warnung aus, wenn Busse ohne Spannung gefunden werden.
    
    Args:
        netzwerk: pandapower Netzwerk nach Lastflussberechnung
    """
    if 'res_bus' not in netzwerk or netzwerk.res_bus.empty:
        return
    
    if 'vm_pu' not in netzwerk.res_bus.columns:
        return
    
    # Finde Busse ohne Spannung (vm_pu == 0 oder sehr klein)
    unversorgte_busse = netzwerk.res_bus[
        (netzwerk.res_bus['vm_pu'] < 0.01) & 
        (netzwerk.bus['in_service'] == True)
    ]
    
    if len(unversorgte_busse) > 0:
        print(f"  ⚠️  WARNUNG: {len(unversorgte_busse)} Busse ohne Spannung gefunden:")
        for bus_idx in unversorgte_busse.index[:10]:  # Zeige max. 10
            bus_name = netzwerk.bus.at[bus_idx, 'name'] if 'name' in netzwerk.bus.columns else f"Bus {bus_idx}"
            vm_pu = netzwerk.res_bus.at[bus_idx, 'vm_pu']
            print(f"     Bus {bus_idx} ({bus_name}): vm_pu = {vm_pu:.6f}")
        if len(unversorgte_busse) > 10:
            print(f"     ... und {len(unversorgte_busse) - 10} weitere Busse")


def finde_ueberlastete_leitungen(netzwerk):
    """
    Findet überlastete Leitungen im Netzwerk
    
    Args:
        netzwerk: pandapower Netzwerk nach Lastflussberechnung
        
    Returns:
        list: Liste von Dictionaries mit Informationen zu überlasteten Leitungen
    """
    ueberlastete = []
    
    if 'res_line' not in netzwerk or 'loading_percent' not in netzwerk.res_line.columns:
        return ueberlastete
    
    # Nutze pandas Filterung direkt
    overloaded_lines = netzwerk.res_line[
        netzwerk.res_line['loading_percent'] > Config.LOADING_THRESHOLD_PERCENT
    ]
    
    for line_idx in overloaded_lines.index:
        ueberlastete.append({
            'idx': line_idx,
            'loading': netzwerk.res_line.at[line_idx, 'loading_percent'],
            'i_ka': netzwerk.res_line.at[line_idx, 'i_ka'] if 'i_ka' in netzwerk.res_line.columns else 0
        })
    
    return ueberlastete


def finde_spannungsverletzungen(netzwerk):
    """
    Findet Busse mit Spannungsverletzungen außerhalb des konfigurierten Spannungsbandes.
    
    Args:
        netzwerk: pandapower Netzwerk nach Lastflussberechnung
        
    Returns:
        list: Liste von Dictionaries mit Informationen zu Busse mit Spannungsverletzungen
    """
    verletzungen = []
    
    if 'res_bus' not in netzwerk or 'vm_pu' not in netzwerk.res_bus.columns:
        return verletzungen
    
    # Finde Busse außerhalb des Spannungsbandes
    verletzte_busse = netzwerk.res_bus[
        ((netzwerk.res_bus['vm_pu'] < Config.VOLTAGE_MIN_PU) | 
         (netzwerk.res_bus['vm_pu'] > Config.VOLTAGE_MAX_PU)) &
        (netzwerk.bus['in_service'] == True)
    ]
    
    for bus_idx in verletzte_busse.index:
        vm_pu = netzwerk.res_bus.at[bus_idx, 'vm_pu']
        bus_name = netzwerk.bus.at[bus_idx, 'name'] if 'name' in netzwerk.bus.columns else f"Bus {bus_idx}"
        
        # Bestimme Art der Verletzung
        if vm_pu < Config.VOLTAGE_MIN_PU:
            art = "Unterspannung"
            abweichung = (Config.VOLTAGE_MIN_PU - vm_pu) * 100
        else:
            art = "Überspannung"
            abweichung = (vm_pu - Config.VOLTAGE_MAX_PU) * 100
        
        verletzungen.append({
            'bus_idx': bus_idx,
            'bus_name': bus_name,
            'vm_pu': vm_pu,
            'art': art,
            'abweichung_prozent': abweichung
        })
    
    return verletzungen


def aktualisiere_statistik(statistik_ueberlastungen, ueberlastete_leitungen):
    """
    Aktualisiert die Statistik der Überlastungen
    
    Args:
        statistik_ueberlastungen: Dictionary mit Leitungs-Index als Key und Anzahl als Value
        ueberlastete_leitungen: Liste von Dictionaries mit überlasteten Leitungen
    """
    for leitung in ueberlastete_leitungen:
        leitung_idx = leitung['idx']
        if leitung_idx not in statistik_ueberlastungen:
            statistik_ueberlastungen[leitung_idx] = 0
        statistik_ueberlastungen[leitung_idx] += 1


def aktualisiere_spannungsstatistik(statistik_spannungsverletzungen, spannungsverletzungen):
    """
    Aktualisiert die Statistik der Spannungsverletzungen
    
    Args:
        statistik_spannungsverletzungen: Dictionary mit Bus-Index als Key und Anzahl als Value
        spannungsverletzungen: Liste von Dictionaries mit Spannungsverletzungen
    """
    for verletzung in spannungsverletzungen:
        bus_idx = verletzung['bus_idx']
        if bus_idx not in statistik_spannungsverletzungen:
            statistik_spannungsverletzungen[bus_idx] = 0
        statistik_spannungsverletzungen[bus_idx] += 1


def bestimme_kritischste_leitung(statistik_ueberlastungen):
    """
    Bestimmt die kritischste Leitung aus der Statistik
    
    Args:
        statistik_ueberlastungen: Dictionary mit Leitungs-Index als Key und Anzahl als Value
        
    Returns:
        int: Index der kritischsten Leitung oder None
    """
    if not statistik_ueberlastungen:
        return None
    
    # Finde Leitung mit höchster Anzahl von Überlastungen
    kritischste = max(statistik_ueberlastungen.items(), key=lambda x: x[1])
    return kritischste[0]

