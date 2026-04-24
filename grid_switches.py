"""
Schalter-Logik für N-1-Sicherheit
"""

import pandapower as pp
from pandapower.topology import unsupplied_buses
from copy import deepcopy


def finde_schalter_zur_wiederherstellung(netzwerk, leitung_ausfall):
    """
    Findet einen einzelnen Schalter, der nach Leitungsausfall
    die Versorgung wiederherstellt.
    
    Args:
        netzwerk: pandapower Netzwerk (Original mit allen Leitungen in Betrieb)
        leitung_ausfall: Index der ausgefallenen Leitung
        
    Returns:
        int: Index des Schalters, "none" wenn kein Schalter nötig, oder None wenn kein Schalter gefunden
    """
    # N-1 Basisszenario
    net_n1 = deepcopy(netzwerk)
    net_n1.line.at[leitung_ausfall, "in_service"] = False
    
    try:
        pp.runpp(net_n1)
    except:
        return None
    
    # Keine unversorgten Busse → kein Schalter nötig
    if len(unsupplied_buses(net_n1)) == 0:
        return "none"
    
    # Schalter einzeln testen
    for sidx in netzwerk.switch.index:
        net_test = deepcopy(netzwerk)
        net_test.line.at[leitung_ausfall, "in_service"] = False
        net_test.switch.at[sidx, "closed"] = True
        
        try:
            pp.runpp(net_test)
        except:
            continue
        
        if len(unsupplied_buses(net_test)) == 0:
            return int(sidx)
    
    return None


def schalter_optimal_stellen(szenario, leitung_ausfall):
    """
    Stellt den richtigen Schalter ein, um nach Leitungsausfall
    die Versorgung wiederherzustellen.
    
    Args:
        szenario: Das pandapower Netzwerk (ist eine Kopie)
        leitung_ausfall: Index der ausgefallenen Leitung
    """
    # Erstelle temporäre Kopie mit Original-Zustand für Schalter-Suche
    netz_fuer_suche = deepcopy(szenario)
    netz_fuer_suche.line.at[leitung_ausfall, 'in_service'] = True
    
    schalter = finde_schalter_zur_wiederherstellung(netz_fuer_suche, leitung_ausfall)
    
    # Schalter schalten (falls nötig)
    if isinstance(schalter, int):
        szenario.switch.at[schalter, 'closed'] = True
        print(f"  [schalterOptimalStellen] Schalter {schalter} geschlossen für Leitung {leitung_ausfall}")


def simuliere_ausfall(szenario, leitung_ausfall):
    """
    Simuliert einen Leitungsausfall und stellt gezielt einen
    Wiederherstellungsschalter ein.
    
    Args:
        szenario: pandapower Netzwerk
        leitung_ausfall: Index der ausgefallenen Leitung
    """
    # Leitung außer Betrieb
    szenario.line.at[leitung_ausfall, 'in_service'] = False
    
    # Geeigneten Schalter finden und schalten
    schalter_optimal_stellen(szenario, leitung_ausfall)

