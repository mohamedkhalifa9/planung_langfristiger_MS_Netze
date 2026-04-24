"""
Reactive Power Control für Erzeugungsanlagen nach VDE-AR-N 4105

Implementiert Blindleistungssteuerung für sgen-Elemente zur Behandlung von Spannungsverletzungen.
- cos φ = 0.95 untererregt bis 0.95 übererregt
"""

import pandapower as pp
import numpy as np
from config import Config


# Standard cos φ nach VDE-AR-N 4105
COS_PHI_STANDARD = 0.95


def berechne_q_limits_aus_cos_phi(p_mw, cos_phi=COS_PHI_STANDARD):
    """
    Berechnet die Blindleistungsgrenzen basierend auf cos φ.
    
    Bei Wirkleistungsabgabe muss die Erzeugungsanlage mit einer Blindleistung
    betrieben werden können, die einem Verschiebungsfaktor von cos φ = 0.95
    untererregt bis 0.95 übererregt entspricht.
    
    Args:
        p_mw: Wirkleistung in MW (positiv für Erzeugung)
        cos_phi: Verschiebungsfaktor (Standard: 0.95)
        
    Returns:
        tuple: (min_q_mvar, max_q_mvar) - Blindleistungsgrenzen in MVar
    """
    if p_mw <= 0:
        # Keine Wirkleistung -> keine Blindleistungsanforderung
        return 0.0, 0.0
    
    # Berechne Scheinleistung S aus P und cos φ
    # S = P / cos φ
    s_mva = p_mw / cos_phi
    
    # Berechne Blindleistung Q aus S und P
    # Q = sqrt(S² - P²)
    q_mvar = np.sqrt(s_mva**2 - p_mw**2)
    
    # Untererregt (Quadrant II): Q negativ (kapazitiv)
    # Übererregt (Quadrant III): Q positiv (induktiv)
    min_q_mvar = -q_mvar  # Untererregt
    max_q_mvar = q_mvar   # Übererregt
    
    return min_q_mvar, max_q_mvar


def wende_reactive_power_control_an(netzwerk, cos_phi=COS_PHI_STANDARD, 
                                    fuer_spannungsverletzungen=False):
    """
    Wendet Blindleistungssteuerung auf alle sgen-Elemente im Netzwerk an.
    
    Setzt die Blindleistung q_mvar direkt in den sgen-Elementen basierend auf
    cos φ = 0.95. Kann auch zur Behandlung von Spannungsverletzungen verwendet werden.
    
    Args:
        netzwerk: pandapower Netzwerk
        cos_phi: Verschiebungsfaktor (Standard: 0.95)
        fuer_spannungsverletzungen: Wenn True, wird Blindleistung zur Behandlung
                                   von Spannungsverletzungen angepasst
        
    Returns:
        dict: Informationen zu geänderten sgen-Elementen
    """
    if 'sgen' not in netzwerk or len(netzwerk.sgen) == 0:
        print("  ⚠️  Keine sgen-Elemente im Netzwerk gefunden")
        return {}
    
    # Finde aktive sgen-Elemente
    sgen_indices = netzwerk.sgen.index[netzwerk.sgen['in_service'] == True].tolist()
    
    if not sgen_indices:
        print("  ⚠️  Keine aktiven sgen-Elemente gefunden")
        return {}
    
    aenderungen = {}
    
    # Wenn für Spannungsverletzungen, benötigen wir Lastfluss-Ergebnisse
    if fuer_spannungsverletzungen:
        if 'res_bus' not in netzwerk or netzwerk.res_bus.empty:
            print("  ⚠️  Keine Lastfluss-Ergebnisse vorhanden für Spannungsverletzungen")
            print("  → Verwende Standard cos φ = 0.95")
            fuer_spannungsverletzungen = False
    
    for idx in sgen_indices:
        p_mw = netzwerk.sgen.at[idx, 'p_mw']
        bus_idx = netzwerk.sgen.at[idx, 'bus']
        alte_q = netzwerk.sgen.at[idx, 'q_mvar'] if 'q_mvar' in netzwerk.sgen.columns else 0.0
        
        # Berechne Blindleistungsgrenzen
        min_q, max_q = berechne_q_limits_aus_cos_phi(p_mw, cos_phi)
        
        # Bestimme neue Blindleistung
        if fuer_spannungsverletzungen:
            # Für Spannungsverletzungen: Wähle Blindleistung basierend auf Spannung
            vm_pu = netzwerk.res_bus.at[bus_idx, 'vm_pu']
            
            if vm_pu < Config.VOLTAGE_MIN_PU:
                # Unterspannung: Induktive Blindleistung (positiv) zur Spannungserhöhung
                neue_q = max_q  # Maximale induktive Blindleistung
            elif vm_pu > Config.VOLTAGE_MAX_PU:
                # Überspannung: Kapazitive Blindleistung (negativ) zur Spannungssenkung
                neue_q = min_q  # Maximale kapazitive Blindleistung
            else:
                # Spannung im Normalbereich: Verwende Standard (0 oder aktueller Wert)
                neue_q = 0.0
        else:
            # Standard: Setze Blindleistung auf 0 (kann später angepasst werden)
            neue_q = 0.0
        
        # Stelle sicher, dass neue_q innerhalb der Grenzen liegt
        neue_q = max(min_q, min(max_q, neue_q))
        
        # Setze Blindleistung im Netzwerk
        if 'q_mvar' not in netzwerk.sgen.columns:
            netzwerk.sgen['q_mvar'] = 0.0
        netzwerk.sgen.at[idx, 'q_mvar'] = neue_q
        
        aenderungen[idx] = {
            'bus': bus_idx,
            'p_mw': p_mw,
            'alte_q_mvar': alte_q,
            'neue_q_mvar': neue_q,
            'min_q_mvar': min_q,
            'max_q_mvar': max_q
        }
    
    if aenderungen:
        print(f"\n✓ Blindleistung für {len(aenderungen)} sgen-Elemente gesetzt:")
        for sgen_idx, info in list(aenderungen.items())[:5]:  # Zeige max. 5
            vm_info = ""
            if fuer_spannungsverletzungen and 'res_bus' in netzwerk:
                vm_pu = netzwerk.res_bus.at[info['bus'], 'vm_pu']
                vm_info = f", V={vm_pu:.3f} pu"
            print(f"  sgen {sgen_idx} (Bus {info['bus']}{vm_info}, P={info['p_mw']:.2f} MW): "
                  f"Q = {info['alte_q_mvar']:.2f} → {info['neue_q_mvar']:.2f} MVar "
                  f"[{info['min_q_mvar']:.2f}, {info['max_q_mvar']:.2f}]")
        if len(aenderungen) > 5:
            print(f"  ... und {len(aenderungen) - 5} weitere sgen-Elemente")
    else:
        print("  ⚠️  Keine sgen-Elemente gefunden oder konfiguriert")
    
    return aenderungen
