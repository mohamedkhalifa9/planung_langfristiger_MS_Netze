"""
Hilfsfunktionen für Grid Expansion Algorithmus
"""


def format_deutsch(zahl, dezimalstellen=2):
    """
    Formatiert eine Zahl im deutschen Format:
    - Punkt als Tausendertrennzeichen
    - Komma als Dezimaltrennzeichen
    
    Args:
        zahl: Die zu formatierende Zahl
        dezimalstellen: Anzahl der Dezimalstellen (default: 2)
        
    Returns:
        str: Formatierte Zahl im deutschen Format
    """
    return f"{zahl:,.{dezimalstellen}f}".replace(",", "X").replace(".", ",").replace("X", ".")

