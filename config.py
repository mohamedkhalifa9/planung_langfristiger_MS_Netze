"""
Konfigurationsparameter für Grid Expansion Algorithmus
"""

class Config:
    """Zentrale Konfigurationsklasse"""
    
    # Algorithmus-Parameter
    MAX_ITERATIONS = 50
    MAX_UPGRADE_STUFEN = 10
    
    # Spannungsband (pu)
    VOLTAGE_MIN_PU = 0.95
    VOLTAGE_MAX_PU = 1.05
    
    # Überlastungsschwelle
    LOADING_THRESHOLD_PERCENT = 100
    
    # Lastfluss-Parameter
    POWERFLOW_CALCULATE_VOLTAGE_ANGLES = False
    POWERFLOW_INIT = "auto"
    POWERFLOW_MAX_ITERATION = 50
    POWERFLOW_NUMBA = False
    
    # Parallelisierung
    USE_MULTIPROCESSING = True
    
    # Dateinamen (relativ zum übergeordneten Verzeichnis)
    GRID_FILE = "../mv_grid_bielefeld.json"
    EQUIPMENT_COSTS_FILE = "../Equipment_Cost.xlsx"
    OUTPUT_FILE = "../mv_grid_bielefeld_optimized.json"
    VISUALIZATION_FILE = "../mv_grid_bielefeld_optimized_visualization.html"
    
    # Erdkabel-Typen (Querschnitte in mm²)
    ERDKABEL_QUERSCHNITTE = [70, 95, 120, 150, 185, 240]
    
    # Leitungstyp-Erkennungsmuster
    ERDKABEL_PATTERN = ['NA2XS2Y', 'NAYY', 'NA2XY']
    FREILEITUNG_PATTERN = ['AL1', 'AL']
    
    # Toleranz für Vergleiche
    FLOAT_TOLERANCE = 0.001
    
    # Farben für Visualisierung
    COLOR_GEAENDERTE_LEITUNG = '#f94144'  # Rot
    COLOR_STANDARD_LEITUNG = '#023E8A'    # Blau
    
    # Blindleistungssteuerung (VDE-AR-N 4105)
    # Standard cos φ = 0.95 (untererregt bis übererregt)
    # Die Blindleistung wird basierend auf Spannungsverletzungen angepasst:
    # - Unterspannung (< VOLTAGE_MIN_PU): Induktive Blindleistung (positiv)
    # - Überspannung (> VOLTAGE_MAX_PU): Kapazitive Blindleistung (negativ)
    REACTIVE_POWER_COS_PHI = 0.95  # Verschiebungsfaktor nach VDE-AR-N 4105

