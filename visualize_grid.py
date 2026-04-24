"""
Netz-Visualisierung mit Farbcodierung nach Auslastung (Folium-basiert)
"""

import os
import webbrowser
import pandas as pd
import pandapower as pp
import simbench as sb
import branca
import numpy as np
from folium import Map, PolyLine, Circle, Polygon
from branca.element import Element

# Farb-Schema wie im visualizer.py
COLOR_SETUP = {
    'grey': '#8D99AE',
    'mv_line_color': '#023E8A',
    'bus_color': '#8D99AE',
    'trafo_color': '#03045E',
    'load_color': '#5390D9',
    'gen_color': '#F4A261',
    'nan_color': '#000000'
}


def apply_colormap(x, colormap):
    """Wendet Colormap auf einen Wert an"""
    if np.isnan(x):
        return COLOR_SETUP['nan_color']
    else:
        return colormap(x)


def ensure_line_geodata(net):
    """Erstellt line_geodata aus bus_geodata falls nicht vorhanden"""
    if 'line_geodata' not in net or net.line_geodata.empty:
        print("  Generiere line_geodata aus bus_geodata...")
        # Erstelle leeres line_geodata DataFrame
        net.line_geodata = pd.DataFrame(columns=['coords'], index=net.line.index)
        
    # Fülle fehlende coords aus bus_geodata
    for line_idx in net.line.index:
        if line_idx not in net.line_geodata.index or net.line_geodata.at[line_idx, 'coords'] is None or (isinstance(net.line_geodata.at[line_idx, 'coords'], float) and np.isnan(net.line_geodata.at[line_idx, 'coords'])):
            from_bus = net.line.at[line_idx, 'from_bus']
            to_bus = net.line.at[line_idx, 'to_bus']
            
            x_from = net.bus_geodata.at[from_bus, 'x']
            y_from = net.bus_geodata.at[from_bus, 'y']
            x_to = net.bus_geodata.at[to_bus, 'x']
            y_to = net.bus_geodata.at[to_bus, 'y']
            
            # Erstelle gerade Linie zwischen den Bussen
            net.line_geodata.at[line_idx, 'coords'] = [(x_from, y_from), (x_to, y_to)]
    
    return net


def visualize_with_loading(net, loadcase, all_cases, filename, show_map=True):
    """
    Visualisiert das Netz mit Farbcodierung nach Auslastung (Folium-basiert)
    """
    print(f"\nErstelle Visualisierung für Lastfall '{loadcase}'...")
    
    # Wende Lastfall an
    for key, loadcase_df in all_cases.items():
        net[key[0]][key[1]] = loadcase_df.loc[loadcase]
    
    # Berechne Lastfluss
    pp.runpp(net, calculate_voltage_angles=False, init="auto", max_iteration=50)
    
    # Stelle sicher, dass line_geodata existiert
    ensure_line_geodata(net)
    
    # Erstelle Folium-Karte mit OpenStreetMap
    center = [net.bus_geodata['y'].median(), net.bus_geodata['x'].median()]
    m = Map(location=center, zoom_start=13, max_zoom=19, tiles='OpenStreetMap')
    
    # Colormap für Leitungsauslastung (wie im visualizer)
    colormap = branca.colormap.linear.Spectral_10.scale(0, 120)
    colormap.colors.reverse()
    
    # Zeichne Leitungen mit Farbcodierung nach Auslastung
    for line_idx in net.line.index:
        if not net.line.at[line_idx, 'in_service']:
            continue
            
        loading = net.res_line.at[line_idx, 'loading_percent']
        line_color = apply_colormap(loading, colormap)
        
        # Line coordinates (coords from line_geodata or from/to bus)
        if line_idx in net.line_geodata.index and net.line_geodata.at[line_idx, 'coords'] is not None:
            line_coords = [(coord[1], coord[0]) for coord in net.line_geodata.at[line_idx, 'coords']]
        else:
            # Fallback: Direkte Linie zwischen Bussen
            from_bus = net.line.at[line_idx, 'from_bus']
            to_bus = net.line.at[line_idx, 'to_bus']
            line_coords = [
                (net.bus_geodata.at[from_bus, 'y'], net.bus_geodata.at[from_bus, 'x']),
                (net.bus_geodata.at[to_bus, 'y'], net.bus_geodata.at[to_bus, 'x'])
            ]
        
        # Tooltip mit Informationen
        from_bus = net.line.at[line_idx, 'from_bus']
        to_bus = net.line.at[line_idx, 'to_bus']
        v_from_pu = net.res_bus.at[from_bus, 'vm_pu']
        v_to_pu = net.res_bus.at[to_bus, 'vm_pu']
        
        tooltip = f'<b>Line Index:</b> {line_idx}<br>' \
                  f'<b>Voltage p.u.:</b> {v_from_pu:.3f} / {v_to_pu:.3f}<br>' \
                  f'<b>Active Power:</b> {net.res_line.at[line_idx, "p_from_mw"]*1000:.1f} kW<br>' \
                  f'<b>Reactive Power:</b> {net.res_line.at[line_idx, "q_from_mvar"]*1000:.1f} kVAr<br>' \
                  f'<b>Utilization:</b> {loading:.0f} %%'
        
        PolyLine(line_coords, color=line_color, tooltip=tooltip, weight=5.5, opacity=0.8).add_to(m)
    
    # Zeichne Busse (mit Farbcodierung nach Spannung)
    for bus_idx in net.bus.index:
        if not net.bus.at[bus_idx, 'in_service']:
            continue
            
        y = net.bus_geodata.at[bus_idx, 'y']
        x = net.bus_geodata.at[bus_idx, 'x']
        vm_pu = net.res_bus.at[bus_idx, 'vm_pu']
        
        # Bus-Farbe basierend auf Spannung (±4% = 0.96-1.04 p.u.)
        if vm_pu < 0.96 or vm_pu > 1.04:
            bus_color = '#DC143C'  # Rot (Crimson) - Verletzung
            bus_radius = 4.0  # Größer für bessere Sichtbarkeit
        elif vm_pu < 0.98 or vm_pu > 1.02:
            bus_color = '#FFA500'  # Orange - Warnung
            bus_radius = 3.0
        else:
            bus_color = '#90EE90'  # Hellgrün - OK
            bus_radius = 2.25
        
        tooltip = f'<b>Bus Index:</b> {bus_idx}<br>' \
                  f'<b>Voltage p.u.:</b> {vm_pu:.3f} ({vm_pu*100:.1f}%)<br>' \
                  f'<b>Active Power:</b> {net.res_bus.at[bus_idx, "p_mw"]*1000:.1f} kW<br>' \
                  f'<b>Reactive Power:</b> {net.res_bus.at[bus_idx, "q_mvar"]*1000:.1f} kVAr'
        
        Circle([y, x], color=bus_color, tooltip=tooltip, radius=bus_radius, fill=True, 
               fill_opacity=0.9).add_to(m)
    
    # Zeichne Transformatoren
    for trafo_idx in net.trafo.index:
        if not net.trafo.at[trafo_idx, 'in_service']:
            continue
            
        hv_bus = net.trafo.at[trafo_idx, 'hv_bus']
        lv_bus = net.trafo.at[trafo_idx, 'lv_bus']
        
        hv_coords = [net.bus_geodata.at[hv_bus, 'y'], net.bus_geodata.at[hv_bus, 'x']]
        lv_coords = [net.bus_geodata.at[lv_bus, 'y'], net.bus_geodata.at[lv_bus, 'x']]
        center_coords = [(hv_coords[i] + lv_coords[i]) * 0.5 for i in [0, 1]]
        
        v_hv_pu = net.res_bus.at[hv_bus, 'vm_pu']
        v_lv_pu = net.res_bus.at[lv_bus, 'vm_pu']
        loading = net.res_trafo.at[trafo_idx, 'loading_percent']
        
        tooltip = f'<b>Trafo Index:</b> {trafo_idx}<br>' \
                  f'<b>Type:</b> {net.trafo.at[trafo_idx, "std_type"]}<br>' \
                  f'<b>Voltage p.u.:</b> {v_hv_pu:.3f} / {v_lv_pu:.3f}<br>' \
                  f'<b>Active Power:</b> {abs(net.res_trafo.at[trafo_idx, "p_hv_mw"])*1000:.1f} kW<br>' \
                  f'<b>Reactive Power:</b> {abs(net.res_trafo.at[trafo_idx, "q_hv_mvar"])*1000:.1f} kVAr<br>' \
                  f'<b>Utilization:</b> {loading:.0f} %%'
        
        Circle(location=center_coords, radius=5, fill=True, tooltip=tooltip,
               color=COLOR_SETUP['trafo_color']).add_to(m)
    
    # Füge Colormap-Legende hinzu
    colormap.caption = 'Line Utilization in %'
    colormap.add_to(m)
    
    # Füge Titel hinzu
    title_html = f'<h3 align="center" style="font-size:20px"><b>Bielefeld MV Grid - {loadcase}</b></h3>'
    m.get_root().html.add_child(Element(title_html))
    
    # Statistiken als Overlay
    max_line_load = net.res_line['loading_percent'].max()
    avg_line_load = net.res_line['loading_percent'].mean()
    overloaded = (net.res_line['loading_percent'] > 100).sum()
    max_trafo_load = net.res_trafo['loading_percent'].max()
    min_voltage = net.res_bus['vm_pu'].min()
    max_voltage = net.res_bus['vm_pu'].max()
    
    # Spannungsverletzungen zählen
    voltage_critical = ((net.res_bus['vm_pu'] < 0.96) | (net.res_bus['vm_pu'] > 1.04)).sum()
    voltage_warning = ((net.res_bus['vm_pu'] < 0.98) | (net.res_bus['vm_pu'] > 1.02)).sum() - voltage_critical
    voltage_ok = len(net.res_bus) - voltage_critical - voltage_warning
    
    stats_html = f'''
    <div style="position: fixed; 
                top: 10px; right: 10px; width: 320px; height: auto; 
                background-color: white; border:2px solid grey; z-index:9999; 
                font-size:14px; padding: 10px">
    <h4>Statistiken: {loadcase}</h4>
    <b>Leitungen:</b><br>
    • Max: {max_line_load:.1f}% | Ø: {avg_line_load:.1f}%<br>
    • Überlastet (>100%): {overloaded}<br>
    • Kritisch (>80%): {(net.res_line['loading_percent'] > 80).sum()}<br>
    <b>Transformatoren:</b><br>
    • Max: {max_trafo_load:.1f}%<br>
    <b>Spannungen:</b><br>
    • Min: {min_voltage:.3f} p.u. ({min_voltage*100:.1f}%)<br>
    • Max: {max_voltage:.3f} p.u. ({max_voltage*100:.1f}%)<br>
    • <span style="color: #DC143C">●</span> Verletzung (±4%): {voltage_critical}<br>
    • <span style="color: #FFA500">●</span> Warnung (±2%): {voltage_warning}<br>
    • <span style="color: #90EE90">●</span> OK: {voltage_ok}<br>
    <b>Leistung:</b><br>
    • Last: {net.load['p_mw'].sum():.2f} MW<br>
    • Erzeugung: {net.sgen['p_mw'].sum():.2f} MW
    </div>
    '''
    m.get_root().html.add_child(Element(stats_html))
    
    # Legende für Bus-Spannungen hinzufügen
    legend_html = f'''
    <div style="position: fixed; 
                bottom: 50px; left: 10px; width: 280px; height: auto; 
                background-color: white; border:2px solid grey; z-index:9999; 
                font-size:13px; padding: 10px">
    <h4 style="margin-top: 0">Bus-Spannungen</h4>
    <span style="color: #90EE90; font-size: 20px">●</span> 0.98-1.02 p.u. (±2% - OK)<br>
    <span style="color: #FFA500; font-size: 20px">●</span> 0.96-0.98 / 1.02-1.04 p.u. (Warnung)<br>
    <span style="color: #DC143C; font-size: 20px">●</span> <0.96 / >1.04 p.u. (±4% - Verletzung)
    </div>
    '''
    m.get_root().html.add_child(Element(legend_html))
    
    # Speichere und öffne Karte
    m.save(os.path.abspath(filename))
    print(f"✓ Visualisierung gespeichert: {filename}")
    
    if show_map:
        webbrowser.open('file://' + os.path.abspath(filename))
    
    return m


def visualize_topology_simple(net, filename, show_map=True):
    """Einfache Topologie ohne Auslastung (Folium-basiert)"""
    print(f"\nErstelle Topologie-Visualisierung...")
    
    # Stelle sicher, dass line_geodata existiert
    ensure_line_geodata(net)
    
    # Erstelle Folium-Karte mit OpenStreetMap
    center = [net.bus_geodata['y'].median(), net.bus_geodata['x'].median()]
    m = Map(location=center, zoom_start=13, max_zoom=19, tiles='OpenStreetMap')
    
    # Zeichne alle Leitungen in MV-Farbe
    for line_idx in net.line.index:
        if not net.line.at[line_idx, 'in_service']:
            continue
            
        # Line coordinates
        if line_idx in net.line_geodata.index and net.line_geodata.at[line_idx, 'coords'] is not None:
            line_coords = [(coord[1], coord[0]) for coord in net.line_geodata.at[line_idx, 'coords']]
        else:
            from_bus = net.line.at[line_idx, 'from_bus']
            to_bus = net.line.at[line_idx, 'to_bus']
            line_coords = [
                (net.bus_geodata.at[from_bus, 'y'], net.bus_geodata.at[from_bus, 'x']),
                (net.bus_geodata.at[to_bus, 'y'], net.bus_geodata.at[to_bus, 'x'])
            ]
        
        tooltip = f'<b>Line Index:</b> {line_idx}<br>' \
                  f'<b>From Bus:</b> {net.line.at[line_idx, "from_bus"]}<br>' \
                  f'<b>To Bus:</b> {net.line.at[line_idx, "to_bus"]}<br>' \
                  f'<b>Type:</b> {net.line.at[line_idx, "std_type"]}'
        
        PolyLine(line_coords, color=COLOR_SETUP['mv_line_color'], tooltip=tooltip, 
                 weight=5.5, opacity=0.7).add_to(m)
    
    # Zeichne Busse
    for bus_idx in net.bus.index:
        if not net.bus.at[bus_idx, 'in_service']:
            continue
            
        y = net.bus_geodata.at[bus_idx, 'y']
        x = net.bus_geodata.at[bus_idx, 'x']
        
        tooltip = f'<b>Bus Index:</b> {bus_idx}<br>' \
                  f'<b>Name:</b> {net.bus.at[bus_idx, "name"]}<br>' \
                  f'<b>Voltage:</b> {net.bus.at[bus_idx, "vn_kv"]} kV'
        
        Circle([y, x], color=COLOR_SETUP['grey'], tooltip=tooltip, radius=2.25, 
               fill=True, fill_opacity=1).add_to(m)
    
    # Zeichne Transformatoren
    for trafo_idx in net.trafo.index:
        if not net.trafo.at[trafo_idx, 'in_service']:
            continue
            
        hv_bus = net.trafo.at[trafo_idx, 'hv_bus']
        lv_bus = net.trafo.at[trafo_idx, 'lv_bus']
        
        hv_coords = [net.bus_geodata.at[hv_bus, 'y'], net.bus_geodata.at[hv_bus, 'x']]
        lv_coords = [net.bus_geodata.at[lv_bus, 'y'], net.bus_geodata.at[lv_bus, 'x']]
        center_coords = [(hv_coords[i] + lv_coords[i]) * 0.5 for i in [0, 1]]
        
        tooltip = f'<b>Trafo Index:</b> {trafo_idx}<br>' \
                  f'<b>Type:</b> {net.trafo.at[trafo_idx, "std_type"]}<br>' \
                  f'<b>HV Bus:</b> {hv_bus}<br>' \
                  f'<b>LV Bus:</b> {lv_bus}'
        
        Circle(location=center_coords, radius=5, fill=True, tooltip=tooltip,
               color=COLOR_SETUP['trafo_color']).add_to(m)
    
    # Füge Titel hinzu
    title_html = '<h3 align="center" style="font-size:20px"><b>Bielefeld MV Grid - Topology</b></h3>'
    m.get_root().html.add_child(Element(title_html))
    
    # Netz-Info als Overlay
    info_html = f'''
    <div style="position: fixed; 
                top: 10px; right: 10px; width: 250px; height: auto; 
                background-color: white; border:2px solid grey; z-index:9999; 
                font-size:14px; padding: 10px">
    <h4>Netzwerk-Info</h4>
    <b>Busse:</b> {len(net.bus)}<br>
    <b>Leitungen:</b> {len(net.line)}<br>
    <b>Transformatoren:</b> {len(net.trafo)}<br>
    <b>Lasten:</b> {len(net.load)}<br>
    <b>Erzeuger:</b> {len(net.sgen)}
    </div>
    '''
    m.get_root().html.add_child(Element(info_html))
    
    # Speichere und öffne Karte
    m.save(os.path.abspath(filename))
    print(f"✓ Visualisierung gespeichert: {filename}")
    
    if show_map:
        webbrowser.open('file://' + os.path.abspath(filename))
    
    return m


def main():
    """Hauptfunktion"""
    
    print("="*80)
    print("BIELEFELD NETZ-VISUALISIERUNG MIT OPENSTREETMAP (FOLIUM)")
    print("="*80)
    
    # Lade Netz
    print("\nLade Netz...")
    net = pp.from_json("mv_grid_bielefeld.json")
    all_cases = sb.get_absolute_values(net, False)
    
    print(f"Netz geladen: {len(net.bus)} Busse, {len(net.line)} Leitungen, {len(net.trafo)} Transformatoren")
    
    # 1. Topologie
    print("\n" + "="*80)
    print("1. TOPOLOGIE (ohne Auslastung)")
    print("="*80)
    visualize_topology_simple(net, filename="bielefeld_grid_topology.html", show_map=False)
    
    # 2. Auslastungs-Visualisierungen
    print("\n" + "="*80)
    print("2. AUSLASTUNGS-VISUALISIERUNGEN (Farbcodiert mit Spectral Colormap)")
    print("="*80)
    
    loadcases = ['bc', 'hL', 'n1', 'lW', 'hPV']
    
    for idx, loadcase in enumerate(loadcases):
        net_copy = pp.from_json("mv_grid_bielefeld.json")
        # Nur die letzte Karte im Browser öffnen
        show_map = (idx == len(loadcases) - 1)
        visualize_with_loading(
            net_copy,
            loadcase=loadcase,
            all_cases=all_cases,
            filename=f"bielefeld_grid_{loadcase}.html",
            show_map=show_map
        )
    
    print(f"\n{'='*80}")
    print("✓ ALLE VISUALISIERUNGEN ERSTELLT")
    print(f"{'='*80}")
    print("\nErstellte Dateien (HTML mit OpenStreetMap):")
    print("  • bielefeld_grid_topology.html - Topologie")
    print("  • bielefeld_grid_bc.html - Base Case")
    print("  • bielefeld_grid_hL.html - High Load")
    print("  • bielefeld_grid_n1.html - n-1 Case")
    print("  • bielefeld_grid_lW.html - Low Wind")
    print("  • bielefeld_grid_hPV.html - High PV")
    print(f"\n{'='*80}")
    print("Features:")
    print("  🗺️  Interaktive OpenStreetMap-Karte")
    print("  🎨  Spectral Colormap für Leitungsauslastung (0-120%)")
    print("  💡  Tooltips mit detaillierten Informationen")
    print("  📊  Statistik-Overlay (oben rechts)")
    print("  🔍  Zoom und Pan möglich")
    print(f"{'='*80}\n")


if __name__ == "__main__":
    main()
