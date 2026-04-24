"""
Leitungstyp-Erkennung und -Kategorisierung
"""

import re
from config import Config


# Globale Variable für Kosten (wird von main.py gesetzt)
line_costs_df = None


def set_line_costs(costs_df):
    """Setzt die globale line_costs_df Variable"""
    global line_costs_df
    line_costs_df = costs_df


def leitungs_typ(netzwerk, leitung_idx):
    """
    Bestimmt den Typ einer Leitung mit klarer Priorität:
    1. Equipment_Cost.xlsx
    2. String-basierte Erkennung
    3. max_i_ka Fallback
    
    Args:
        netzwerk: pandapower Netzwerk
        leitung_idx: Index der Leitung
        
    Returns:
        str: Leitungstyp (z.B. "70er_erdkabel", "freileitung")
    """
    std_type = netzwerk.line.at[leitung_idx, 'std_type']
    current_max_i = netzwerk.line.at[leitung_idx, 'max_i_ka']
    
    # 1. Prüfe Equipment_Cost.xlsx
    if line_costs_df is not None:
        line_cost_row = line_costs_df[line_costs_df['std_type'] == std_type]
        if len(line_cost_row) > 0:
            is_underground = line_cost_row['Underground_work_eur_p_m'].iloc[0] > 0
            if is_underground:
                return kategorisiere_erdkabel(std_type, current_max_i)
            else:
                return "freileitung"
    
    # 2. String-basierte Erkennung
    if ist_erdkabel_string(std_type):
        return kategorisiere_erdkabel(std_type, current_max_i)
    elif ist_freileitung_string(std_type):
        return "freileitung"
    
    # 3. Fallback: Kategorisiere nach max_i_ka
    return kategorisiere_nach_max_i(current_max_i)


def ist_erdkabel_string(std_type):
    """Prüft ob String-Name auf Erdkabel hindeutet"""
    return any(pattern in std_type for pattern in Config.ERDKABEL_PATTERN)


def ist_freileitung_string(std_type):
    """Prüft ob String-Name auf Freileitung hindeutet"""
    return any(pattern in std_type for pattern in Config.FREILEITUNG_PATTERN)


def kategorisiere_erdkabel(std_type, max_i_ka):
    """
    Kategorisiert Erdkabel nach Querschnitt oder max_i_ka
    
    Args:
        std_type: Standard-Typ String
        max_i_ka: Maximaler Strom in kA
        
    Returns:
        str: Erdkabel-Kategorie (z.B. "120er_erdkabel")
    """
    # Versuche Querschnitt zu extrahieren
    querschnitt = extrahiere_querschnitt(std_type)
    
    if querschnitt:
        return querschnitt_zu_typ(querschnitt)
    
    # Fallback: Kategorisiere nach max_i_ka
    return max_i_zu_erdkabel_typ(max_i_ka)


def extrahiere_querschnitt(std_type):
    """
    Extrahiert Querschnitt aus std_type String
    
    Args:
        std_type: Standard-Typ String (z.B. "NA2XS2Y 1x120 RM/25 12/20 kV")
        
    Returns:
        int: Querschnitt in mm² oder None
    """
    # Suche nach Mustern wie "1x120", "4x120", etc.
    querschnitt_match = re.search(r'(\d+)x(\d+)', std_type)
    if querschnitt_match:
        return int(querschnitt_match.group(2))
    
    # Fallback: Suche nach einzelnen Zahlen (z.B. "120" in "NA2XS2Y 1x120")
    querschnitt_match = re.search(r'(\d+)\s*(?:RM|SE|kV|$)', std_type)
    if querschnitt_match:
        querschnitt = int(querschnitt_match.group(1))
        # Prüfe ob es eine sinnvolle Querschnitts-Zahl ist
        if querschnitt in Config.ERDKABEL_QUERSCHNITTE or (50 <= querschnitt <= 300):
            return querschnitt
    
    return None


def querschnitt_zu_typ(querschnitt):
    """
    Konvertiert Querschnitt zu Erdkabel-Typ
    
    Args:
        querschnitt: Querschnitt in mm²
        
    Returns:
        str: Erdkabel-Typ (z.B. "120er_erdkabel")
    """
    if querschnitt <= 70:
        return "70er_erdkabel"
    elif querschnitt <= 95:
        return "95er_erdkabel"
    elif querschnitt <= 120:
        return "120er_erdkabel"
    elif querschnitt <= 150:
        return "150er_erdkabel"
    elif querschnitt <= 185:
        return "185er_erdkabel"
    else:
        return "240er_erdkabel"


def max_i_zu_erdkabel_typ(max_i_ka):
    """
    Kategorisiert Erdkabel nach max_i_ka
    
    Args:
        max_i_ka: Maximaler Strom in kA
        
    Returns:
        str: Erdkabel-Typ
    """
    if max_i_ka < 0.25:
        return "70er_erdkabel"
    elif max_i_ka < 0.3:
        return "95er_erdkabel"
    elif max_i_ka < 0.4:
        return "120er_erdkabel"
    elif max_i_ka < 0.5:
        return "150er_erdkabel"
    elif max_i_ka < 0.6:
        return "185er_erdkabel"
    else:
        return "240er_erdkabel"


def kategorisiere_nach_max_i(max_i_ka):
    """
    Fallback-Kategorisierung nach max_i_ka (wenn Typ unbekannt)
    
    Args:
        max_i_ka: Maximaler Strom in kA
        
    Returns:
        str: Leitungstyp
    """
    return max_i_zu_erdkabel_typ(max_i_ka)

