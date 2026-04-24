"""
Upgrade-Funktionen für Leitungen und Netzausbau
"""

import re
import numpy as np
from copy import deepcopy
from config import Config
from utils import format_deutsch


# Globale Variablen für Kosten (werden von main.py gesetzt)
line_costs_df = None
trafo_costs_df = None


def set_costs(line_costs, trafo_costs):
    """Setzt die globalen Kosten-DataFrames"""
    global line_costs_df, trafo_costs_df
    line_costs_df = line_costs
    trafo_costs_df = trafo_costs


def finde_naechstes_upgrade(netzwerk, leitung_idx, ist_erdkabel=True):
    """
    Findet das nächste Upgrade für eine Leitung basierend auf Equipment_Cost.xlsx.
    Berücksichtigt auch die Spannungsebene, um kompatible Upgrades zu finden.
    
    Args:
        netzwerk: pandapower Netzwerk
        leitung_idx: Index der Leitung
        ist_erdkabel: True für Erdkabel, False für Freileitung
        
    Returns:
        dict mit 'std_type', 'max_i_ka', 'params' oder None wenn kein Upgrade gefunden
    """
    if line_costs_df is None:
        return None
    
    current_std_type = netzwerk.line.at[leitung_idx, 'std_type']
    current_max_i = netzwerk.line.at[leitung_idx, 'max_i_ka']
    
    # Extrahiere Spannungsebene aus aktuellem Typ
    voltage_match = re.search(r'(\d+/\d+)\s*kV', current_std_type)
    current_voltage = voltage_match.group(1) if voltage_match else None
    
    # Filtere nach Erdkabel oder Freileitung
    if ist_erdkabel:
        available_lines = line_costs_df[line_costs_df['Underground_work_eur_p_m'] > 0].copy()
    else:
        available_lines = line_costs_df[line_costs_df['Underground_work_eur_p_m'] == 0].copy()
    
    if len(available_lines) == 0:
        return None
    
    # Finde alle Typen mit höherer Kapazität
    candidates = []
    
    for idx, row in available_lines.iterrows():
        candidate_std_type = row['std_type']
        
        # Prüfe, ob dieser Typ in pandapower std_types existiert
        if candidate_std_type in netzwerk.std_types['line']:
            candidate_params = netzwerk.std_types['line'][candidate_std_type]
            candidate_max_i = candidate_params.get('max_i_ka', 0)
            
            # Nur wenn Kapazität größer ist
            if candidate_max_i > current_max_i + Config.FLOAT_TOLERANCE:
                # Prüfe Spannungskompatibilität
                candidate_voltage_match = re.search(r'(\d+/\d+)\s*kV', candidate_std_type)
                candidate_voltage = candidate_voltage_match.group(1) if candidate_voltage_match else None
                
                # Bevorzuge Typen mit gleicher Spannungsebene
                voltage_match_score = 1 if (current_voltage and candidate_voltage and current_voltage == candidate_voltage) else 0
                
                candidates.append({
                    'std_type': candidate_std_type,
                    'max_i_ka': candidate_max_i,
                    'params': candidate_params,
                    'voltage_match': voltage_match_score,
                    'voltage': candidate_voltage
                })
    
    if len(candidates) == 0:
        return None
    
    # Sortiere: Zuerst nach Spannungskompatibilität, dann nach Kapazität
    candidates.sort(key=lambda x: (-x['voltage_match'], x['max_i_ka']))
    
    # Wähle den kleinsten größeren Typ (mit bevorzugter Spannungsebene)
    return candidates[0]


def upgrade_leitung(netzwerk, leitung_idx, ist_erdkabel=None):
    """
    Generische Upgrade-Funktion für alle Leitungstypen.
    Findet automatisch das nächste größere Kabel/Freileitung aus Equipment_Cost.xlsx.
    
    Args:
        netzwerk: pandapower Netzwerk
        leitung_idx: Index der Leitung
        ist_erdkabel: True für Erdkabel, False für Freileitung, None für automatische Erkennung
        
    Returns:
        dict mit Informationen zum Upgrade und Kosten
    """
    alte_std_type = netzwerk.line.at[leitung_idx, 'std_type']
    current_max_i = netzwerk.line.at[leitung_idx, 'max_i_ka']
    
    # Bestimme ob Erdkabel oder Freileitung (falls nicht angegeben)
    if ist_erdkabel is None:
        ist_erdkabel = bestimme_ist_erdkabel(alte_std_type)
    
    # Versuche Upgrade aus Equipment_Cost.xlsx zu finden
    upgrade = finde_naechstes_upgrade(netzwerk, leitung_idx, ist_erdkabel=ist_erdkabel)
    
    if upgrade is None:
        # Fallback: Versuche in pandapower std_types
        upgrade = finde_upgrade_in_std_types(netzwerk, leitung_idx, alte_std_type, current_max_i, ist_erdkabel)
    
    if upgrade is None:
        print(f"  Warnung: Kein Upgrade für Leitung {leitung_idx} gefunden")
        return {
            'typ': 'upgrade',
            'leitung_idx': leitung_idx,
            'alte_std_type': alte_std_type,
            'neue_std_type': alte_std_type,
            'kosten': 0
        }
    
    # Setze neue Parameter
    neue_std_type = upgrade['std_type']
    neue_max_i = upgrade['max_i_ka']
    
    # Validierung: Prüfe ob wirklich ein Upgrade stattfindet
    if neue_std_type == alte_std_type or neue_max_i <= current_max_i:
        print(f"  ⚠️  Warnung: Kein echtes Upgrade möglich für Leitung {leitung_idx}")
        return {
            'typ': 'upgrade',
            'leitung_idx': leitung_idx,
            'alte_std_type': alte_std_type,
            'neue_std_type': alte_std_type,
            'kosten': 0
        }
    
    # Setze neue Parameter
    netzwerk.line.at[leitung_idx, 'std_type'] = neue_std_type
    netzwerk.line.at[leitung_idx, 'max_i_ka'] = neue_max_i
    netzwerk.line.at[leitung_idx, 'r_ohm_per_km'] = upgrade['params']['r_ohm_per_km']
    netzwerk.line.at[leitung_idx, 'x_ohm_per_km'] = upgrade['params']['x_ohm_per_km']
    netzwerk.line.at[leitung_idx, 'c_nf_per_km'] = upgrade['params']['c_nf_per_km']
    
    # Berechne Kosten
    kosten = berechne_upgrade_kosten(netzwerk, leitung_idx, neue_std_type, ist_erdkabel)
    
    typ_name = "Erdkabel" if ist_erdkabel else "Freileitung"
    if kosten > 0:
        print(f"  ✓ {typ_name} {leitung_idx} aufgerüstet ({alte_std_type} -> {neue_std_type}) - Kosten: €{format_deutsch(kosten, 0)}")
    else:
        print(f"  ✓ {typ_name} {leitung_idx} aufgerüstet ({alte_std_type} -> {neue_std_type})")
    
    return {
        'typ': 'upgrade',
        'leitung_idx': leitung_idx,
        'alte_std_type': alte_std_type,
        'neue_std_type': neue_std_type,
        'kosten': kosten
    }


def bestimme_ist_erdkabel(std_type):
    """Bestimmt ob Leitung ein Erdkabel ist basierend auf std_type"""
    if line_costs_df is not None:
        line_cost_row = line_costs_df[line_costs_df['std_type'] == std_type]
        if len(line_cost_row) > 0:
            return line_cost_row['Underground_work_eur_p_m'].iloc[0] > 0
    
    # Fallback: String-basierte Erkennung
    erdkabel_patterns = ['NA2XS2Y', 'NAYY', 'NA2XY']
    return any(pattern in std_type for pattern in erdkabel_patterns)


def finde_upgrade_in_std_types(netzwerk, leitung_idx, alte_std_type, current_max_i, ist_erdkabel):
    """
    Fallback-Funktion: Sucht Upgrade in pandapower std_types
    
    Returns:
        dict mit upgrade info oder None
    """
    line_std_types = netzwerk.std_types['line']
    candidates = []
    
    # Extrahiere Spannungsebene
    voltage_match = re.search(r'(\d+/\d+)\s*kV', alte_std_type)
    current_voltage = voltage_match.group(1) if voltage_match else None
    
    for type_name, params in line_std_types.items():
        # Filter nach Erdkabel oder Freileitung
        is_candidate_underground = any(pattern in type_name for pattern in ['NA2XS2Y', 'NAYY', 'NA2XY'])
        
        if is_candidate_underground != ist_erdkabel:
            continue
        
        candidate_max_i = params.get('max_i_ka', 0)
        
        # Nur wenn Kapazität größer ist
        if candidate_max_i > current_max_i + Config.FLOAT_TOLERANCE:
            # Prüfe Spannungskompatibilität
            candidate_voltage_match = re.search(r'(\d+/\d+)\s*kV', type_name)
            candidate_voltage = candidate_voltage_match.group(1) if candidate_voltage_match else None
            voltage_match_score = 1 if (current_voltage and candidate_voltage and current_voltage == candidate_voltage) else 0
            
            candidates.append({
                'std_type': type_name,
                'max_i_ka': candidate_max_i,
                'params': params,
                'voltage_match': voltage_match_score
            })
    
    if not candidates:
        return None
    
    # Sortiere und wähle kleinsten größeren Typ
    candidates.sort(key=lambda x: (-x['voltage_match'], x['max_i_ka']))
    return candidates[0]


def berechne_upgrade_kosten(netzwerk, leitung_idx, neue_std_type, ist_erdkabel):
    """
    Berechnet die Kosten für ein Leitungs-Upgrade
    
    Returns:
        float: Kosten in Euro
    """
    if line_costs_df is None:
        return 0
    
    line_length = netzwerk.line.at[leitung_idx, 'length_km']
    line_cost_row = line_costs_df[line_costs_df['std_type'] == neue_std_type]
    
    if len(line_cost_row) == 0:
        return 0
    
    cost_per_m = (
        line_cost_row['Material_eur_p_m'].iloc[0] +
        line_cost_row['Planning_eur_p_m'].iloc[0]
    )
    
    if ist_erdkabel:
        cost_per_m += line_cost_row['Underground_work_eur_p_m'].iloc[0]
    
    total_cost = cost_per_m * line_length * 1000  # Konvertiere km zu m
    return total_cost


def fuege_parallelleitungen_hinzu(netzwerk, leitung_idx):
    """
    Fügt zwei Parallelleitungen hinzu und teilt den Ring.
    Vom nächstgelegenen Trafo zu beiden Enden der Leitung.
    
    Args:
        netzwerk: pandapower Netzwerk
        leitung_idx: Index der kritischen Leitung
        
    Returns:
        dict mit Informationen zu den neuen Leitungen und Kosten
    """
    # Hole Informationen zur bestehenden Leitung
    from_bus = netzwerk.line.at[leitung_idx, 'from_bus']
    to_bus = netzwerk.line.at[leitung_idx, 'to_bus']
    length_km = netzwerk.line.at[leitung_idx, 'length_km']
    std_type = netzwerk.line.at[leitung_idx, 'std_type']
    
    # Finde nächstgelegenen Trafo
    trafo_bus = finde_naechsten_trafo(netzwerk, from_bus)
    
    if trafo_bus is None:
        print(f"  Warnung: Kein Trafo für Leitung {leitung_idx} gefunden")
        return {
            'typ': 'parallel',
            'leitung_idx': leitung_idx,
            'neue_leitungen': [],
            'deaktivierte_leitung': leitung_idx,
            'kosten': 0
        }
    
    # Hole Parameter der ursprünglichen Leitung
    max_i_ka = netzwerk.line.at[leitung_idx, 'max_i_ka']
    r_ohm_per_km = netzwerk.line.at[leitung_idx, 'r_ohm_per_km']
    x_ohm_per_km = netzwerk.line.at[leitung_idx, 'x_ohm_per_km']
    c_nf_per_km = netzwerk.line.at[leitung_idx, 'c_nf_per_km']
    
    # Berechne Länge (vereinfacht: halbe Länge)
    length_km_half = length_km / 2
    
    # Erstelle erste Parallelleitung (Trafo -> from_bus)
    new_line1_idx = len(netzwerk.line)
    netzwerk.line.loc[new_line1_idx] = {
        'name': f'parallel_line_1_{leitung_idx}',
        'from_bus': trafo_bus,
        'to_bus': from_bus,
        'length_km': length_km_half,
        'std_type': std_type,
        'max_i_ka': max_i_ka,
        'r_ohm_per_km': r_ohm_per_km,
        'x_ohm_per_km': x_ohm_per_km,
        'c_nf_per_km': c_nf_per_km,
        'in_service': True
    }
    
    # Erstelle zweite Parallelleitung (Trafo -> to_bus)
    new_line2_idx = len(netzwerk.line)
    netzwerk.line.loc[new_line2_idx] = {
        'name': f'parallel_line_2_{leitung_idx}',
        'from_bus': trafo_bus,
        'to_bus': to_bus,
        'length_km': length_km_half,
        'std_type': std_type,
        'max_i_ka': max_i_ka,
        'r_ohm_per_km': r_ohm_per_km,
        'x_ohm_per_km': x_ohm_per_km,
        'c_nf_per_km': c_nf_per_km,
        'in_service': True
    }
    
    # Deaktiviere ursprüngliche Leitung
    netzwerk.line.at[leitung_idx, 'in_service'] = False
    
    # Berechne Kosten
    kosten = berechne_parallelleitungen_kosten(netzwerk, std_type, length_km)
    
    if kosten > 0:
        print(f"  Zwei Parallelleitungen zu Leitung {leitung_idx} hinzugefügt - Kosten: €{format_deutsch(kosten, 0)}")
    else:
        print(f"  Zwei Parallelleitungen zu Leitung {leitung_idx} hinzugefügt")
    
    return {
        'typ': 'parallel',
        'leitung_idx': leitung_idx,
        'neue_leitungen': [new_line1_idx, new_line2_idx],
        'deaktivierte_leitung': leitung_idx,
        'kosten': kosten
    }


def finde_naechsten_trafo(netzwerk, bus_idx):
    """
    Findet den nächstgelegenen Trafo zu einem Bus.
    
    Args:
        netzwerk: pandapower Netzwerk
        bus_idx: Index des Busses
        
    Returns:
        int: Index des nächsten Trafo-Busses oder None
    """
    bus_has_geodata = 'bus_geodata' in netzwerk and len(netzwerk.bus_geodata) > 0
    
    if bus_has_geodata and bus_idx in netzwerk.bus_geodata.index:
        bus_x = netzwerk.bus_geodata.at[bus_idx, 'x']
        bus_y = netzwerk.bus_geodata.at[bus_idx, 'y']
    else:
        bus_x = 0
        bus_y = 0
    
    min_distance = float('inf')
    naechster_trafo_bus = None
    
    for trafo_idx in netzwerk.trafo.index:
        hv_bus = netzwerk.trafo.at[trafo_idx, 'hv_bus']
        
        if bus_has_geodata and hv_bus in netzwerk.bus_geodata.index:
            trafo_x = netzwerk.bus_geodata.at[hv_bus, 'x']
            trafo_y = netzwerk.bus_geodata.at[hv_bus, 'y']
            distance = np.sqrt((bus_x - trafo_x)**2 + (bus_y - trafo_y)**2)
        else:
            distance = 1  # Fallback
        
        if distance < min_distance:
            min_distance = distance
            naechster_trafo_bus = hv_bus
    
    return naechster_trafo_bus


def berechne_parallelleitungen_kosten(netzwerk, std_type, total_length_km):
    """Berechnet Kosten für zwei Parallelleitungen"""
    if line_costs_df is None:
        return 0
    
    line_cost_row = line_costs_df[line_costs_df['std_type'] == std_type]
    
    if len(line_cost_row) == 0:
        return 0
    
    cost_per_m = (
        line_cost_row['Material_eur_p_m'].iloc[0] +
        line_cost_row['Planning_eur_p_m'].iloc[0] +
        line_cost_row['Underground_work_eur_p_m'].iloc[0]
    )
    
    # Kosten für beide Leitungen
    total_cost = cost_per_m * total_length_km * 1000
    return total_cost

