import os
import webbrowser

import branca
import numpy as np
import pandas as pd
from branca.element import Element
from folium import Map, PolyLine, Circle, Polygon

COLOR_SETUP = {'grey': '#8D99AE',
               'lv_line_color': ['#f94144', '#f3722c', '#f8961e', '#f9844a', '#f9c74f', '#90be6d', '#43aa8b', '#4d908e',
                                 '#577590', '#277da1'],
               'mv_line_color': '#023E8A',
               'bus_color': '',
               'trafo_color': '#03045E',
               'load_color': '#5390D9',
               'gen_color': '#F4A261',
               'building_color': '#A5A58D',
               'nan_color': '#00000'}


def visualize_grid(grid, buildings=None, color_according_to='lv_mv_grids', tooltips=True, show_map=True, plot_mv=True,
                   plot_lv=True, plot_buses=True, plot_trafos=True, plot_loads=False, plot_gens=False,
                   consider_out_of_service=True, path_output='map.html', tiles='OpenStreetMap',
                   map_title='IAEW Grid Visualization Toolbox', line_utilization=None, bus_voltage=None, load=None,
                   generation=None, s_generation=None):
    if color_according_to == 'bus_voltage':
        plot_buses = True
    # Create a copy of the grid and buildings
    grid = grid.deepcopy()
    if buildings is not None:
        buildings = buildings.copy()
    # Add custom values to the grid
    add_values_to_grid(grid, line_utilization, bus_voltage, load, s_generation, generation)
    # Create a map object
    center = [grid['bus_geodata']['y'].median(), grid['bus_geodata']['x'].median()]
    m = Map(location=center, zoom_start=14, max_zoom=19, tiles=tiles)
    # Determine voltages at lines and trafos
    determine_voltages(grid)
    # Determine colors
    determine_colors(grid, buildings, color_according_to, consider_out_of_service)
    # Determine tooltips
    determine_tooltips(grid, tooltips, plot_buses, plot_trafos, plot_loads, plot_gens, buildings)
    # Determine status
    determine_plot_style(grid, plot_mv, plot_lv, consider_out_of_service)
    # Plot the grid and it's elements
    plot_grid(m, grid, plot_buses, plot_trafos, plot_loads, plot_gens, buildings)
    # Add colormap
    add_colormap(m, color_according_to)
    # Add legend
    # add_legend(m, grid)
    # Add map title
    m.get_root().header.add_child(Element(f'<title>{map_title}</title>'))
    # Save and show the map
    if show_map:
        m.save(os.path.abspath(path_output))
        webbrowser.open('file://' + os.path.abspath(path_output))
    # Return
    return m


def add_values_to_grid(grid, line_utilization, bus_voltage, load, s_generation, generation):
    if line_utilization is not None:
        grid['res_line']['loading_percent'] = line_utilization
    if bus_voltage is not None:
        grid['res_bus']['vm_pu'] = bus_voltage
    if load is not None:
        grid['load'][['p_mw', 'q_mva']] = load
    if s_generation is not None:
        grid['sgen'][['p_mw', 'q_mva']] = s_generation
    if generation is not None:
        grid['res_gen'][['p_mw', 'q_mva']] = generation


def determine_colors(grid, buildings, color_according_to, consider_out_of_service):
    # Determine the colors of the buses and/or lines according to the chosen method
    grid['bus']['color'] = ''
    grid['line']['color'] = ''
    grid['trafo']['color'] = ''
    grid['load']['color'] = ''
    grid['gen']['color'] = ''
    grid['sgen']['color'] = ''
    if color_according_to == 'lv_mv_grids':
        lv_grids = identify_lv_grids(grid, consider_out_of_service)
        n_colors = len(COLOR_SETUP['lv_line_color'])
        idx_c = 0
        for idx, lvg in enumerate(lv_grids):
            grid['bus'].loc[lvg['buses'], 'color'] = COLOR_SETUP['lv_line_color'][idx_c]
            grid['line'].loc[lvg['lines'], 'color'] = COLOR_SETUP['lv_line_color'][idx_c]
            idx_c = (idx_c + 1) % n_colors
        # Fill color values for all other elements
        grid['bus']['color'] = grid['bus']['color'].replace('', COLOR_SETUP['mv_line_color'])
        grid['line']['color'] = grid['line']['color'].replace('', COLOR_SETUP['mv_line_color'])
        grid['trafo']['color'] = grid['trafo']['color'].replace('', COLOR_SETUP['trafo_color'])
        grid['load']['color'] = grid['load']['color'].replace('', COLOR_SETUP['load_color'])
        grid['gen']['color'] = grid['gen']['color'].replace('', COLOR_SETUP['gen_color'])
        grid['sgen']['color'] = grid['sgen']['color'].replace('', COLOR_SETUP['gen_color'])

    elif color_according_to == 'line_utilization':
        # Other nice colormaps: RdYlGn_10, Spectral_06, YlOrRd_08
        colormap = branca.colormap.linear.Spectral_10.scale(0, 120)
        colormap.colors.reverse()
        grid['bus']['color'] = COLOR_SETUP['grey'] # Show buses in grey
        grid['line']['color'] = grid['res_line']['loading_percent'].apply(lambda x: apply_colormap(x, colormap))
        grid['trafo']['color'] = grid['res_trafo']['loading_percent'].apply(lambda x: apply_colormap(x, colormap))
        grid['load']['color'] = grid['load']['color'].replace('', COLOR_SETUP['load_color']) # Hide loads, gen, sgen
        grid['gen']['color'] = grid['gen']['color'].replace('', COLOR_SETUP['gen_color'])
        grid['sgen']['color'] = grid['sgen']['color'].replace('', COLOR_SETUP['gen_color'])
        
    ###################ToDo########################
    #Expand the plotting function in 'visualizer.py' with an option to show the voltage at each bus similar to the line utilizatio
    
    
    #################################################
    if buildings is not None:
        buildings['color'] = COLOR_SETUP['building_color']


def apply_colormap(x, colormap):
    if pd.isna(x):
        return COLOR_SETUP['nan_color']
    else:
        return colormap(x)


def determine_tooltips(grid, tooltips, plot_buses, plot_trafos, plot_loads, plot_gens, buildings):
    if tooltips:
        grid['bus']['tooltip'] = ''
        grid['line']['tooltip'] = ''
        grid['trafo']['tooltip'] = ''
        grid['load']['tooltip'] = ''
        grid['gen']['tooltip'] = ''
        grid['sgen']['tooltip'] = ''
        # Lines
        for idx, row in grid['line'].iterrows():
            grid['line'].loc[idx, 'tooltip'] = '<b>Line Index:</b> %d<br>' \
                                               '<b>Voltage p.u.:</b> %.3f / %.3f<br>' \
                                               '<b>Active Power:</b> %.1f kW<br>' \
                                               '<b>Reactive Power:</b> %.1f kVAr<br>' \
                                               '<b>Utilization:</b> %.0f %%' % (
                                                   idx, row['v_from_pu'], row['v_to_pu'],
                                                   grid['res_line'].loc[idx, ['p_from_mw',
                                                                              'p_to_mw']].abs().max() * 1000,
                                                   grid['res_line'].loc[idx, ['q_from_mvar',
                                                                              'q_to_mvar']].abs().max() * 1000,
                                                   grid['res_line'].loc[idx, 'loading_percent'])
        # Buses
        if plot_buses:
            for idx, row in grid['bus'].iterrows():
                grid['bus'].loc[idx, 'tooltip'] = '<b>Bus Index:</b> %d<br>' \
                                                  '<b>Voltage p.u.:</b> %.3f<br>' \
                                                  '<b>Active Power:</b> %.1f kW<br>' \
                                                  '<b>Reactive Power:</b> %.1f kVAr<br>' % (
                                                      idx, grid['res_bus'].loc[idx, 'vm_pu'],
                                                      grid['res_bus'].loc[idx, 'p_mw'] * 1000,
                                                      grid['res_bus'].loc[idx, 'q_mvar'] * 1000)
        else:
            grid['bus']['tooltip'] = None
        # Transformers
        if plot_trafos:
            for idx, row in grid['trafo'].iterrows():
                grid['trafo'].loc[idx, 'tooltip'] = '<b>Trafo Index:</b> %d<br>' \
                                                    '<b>Type:</b> %s<br>' \
                                                    '<b>Voltage p.u.:</b> %.3f / %.3f<br>' \
                                                    '<b>Active Power:</b> %.1f kW<br>' \
                                                    '<b>Reactive Power:</b> %.1f kVAr<br>' \
                                                    '<b>Utilization:</b> %.0f %%' % (
                                                        idx, row['std_type'], row['v_hv_pu'], row['v_lv_pu'],
                                                        grid['res_trafo'].loc[idx, ['p_hv_mw',
                                                                                    'p_lv_mw']].abs().max() * 1000,
                                                        grid['res_trafo'].loc[idx, ['q_hv_mvar',
                                                                                    'q_lv_mvar']].abs().max() * 1000,
                                                        grid['res_trafo'].loc[idx, 'loading_percent'])
        else:
            grid['trafo']['tooltip'] = None
        # Loads
        if plot_loads:
            for idx, row in grid['load'].iterrows():
                grid['load'].loc[idx, 'tooltip'] = '<b>Load Index:</b> %d<br>' \
                                                   '<b>Active Power:</b> %.1f kW<br>' \
                                                   '<b>Reactive Power:</b> %.1f kVAr<br>' % (
                                                       idx, grid['load'].loc[idx, 'p_mw'] * 1000,
                                                       grid['load'].loc[idx, 'q_mvar'] * 1000)
        else:
            grid['load']['tooltip'] = None
        # Generators
        if plot_gens:
            for idx, row in grid['gen'].iterrows():
                grid['gen'].loc[idx, 'tooltip'] = '<b>Generator Index:</b> %d<br>' \
                                                  '<b>Active Power:</b> %.1f kW<br>' \
                                                  '<b>Reactive Power:</b> %.1f kVAr<br>' % (
                                                      idx, grid['res_gen'].loc[idx, 'p_mw'] * 1000,
                                                      grid['res_gen'].loc[idx, 'q_mvar'] * 1000)
            for idx, row in grid['sgen'].iterrows():
                grid['sgen'].loc[idx, 'tooltip'] = '<b>Static Generator Index:</b> %d<br>' \
                                                   '<b>Active Power:</b> %.1f kW<br>' \
                                                   '<b>Reactive Power:</b> %.1f kVAr<br>' % (
                                                       idx, grid['res_sgen'].loc[idx, 'p_mw'] * 1000,
                                                       grid['res_sgen'].loc[idx, 'q_mvar'] * 1000)
        else:
            grid['gen']['tooltip'] = None
            grid['sgen']['tooltip'] = None
        # Buildings:
        if buildings is not None:
            buildings['tooltip'] = ''
            buildings['YEC'] = buildings['HH_YEC'] + buildings['CTS_IND_YEC'].fillna(0)
            buildings['NUM_EMPL'] = buildings['NUM_EMPL'].fillna('0')
            buildings['NUM_HH'] = buildings['NUM_HH'].fillna(0)
            for idx, building in buildings.iterrows():
                num_employees = ','.join([str(int(float(bd))) for bd in building['NUM_EMPL'].split(',')])
                buildings.loc[idx, 'tooltip'] = '<b>OSM ID:</b> %d<br>' \
                                                '<b>Households:</b> %d<br>' \
                                                '<b>CTS Employees:</b> %s<br>' \
                                                '<b>Installed power:</b> %.1f kW<br>' \
                                                '<b>Yearly energy consumption:</b> %d kWh' % (
                                                    building['osmid'], building['NUM_HH'],
                                                    num_employees, building['P_KW'], building['YEC'])
    else:
        grid['bus']['tooltip'] = None
        grid['line']['tooltip'] = None
        grid['trafo']['tooltip'] = None
        grid['load']['tooltip'] = None
        grid['gen']['tooltip'] = None
        grid['sgen']['tooltip'] = None
        if buildings is not None:
            buildings['tooltip'] = None


def determine_voltages(grid):
    """Determine the voltage (from/to) of all lines and trafos"""
    grid['line'][['v_from_pu', 'v_to_pu', 'vn_kv']] = np.nan
    grid['trafo'][['v_hv_pu', 'v_lv_pu']] = np.nan
    grid['load']['vn_kv'] = np.nan
    grid['gen']['vn_kv'] = np.nan
    grid['sgen']['vn_kv'] = np.nan
    for idx, row in grid['line'].iterrows():
        grid['line'].loc[idx, ['v_from_pu', 'v_to_pu', 'vn_kv']] = \
            grid['res_bus'].loc[row[['from_bus', 'to_bus']], 'vm_pu'].to_list() + \
            [grid['bus'].loc[row['from_bus'], 'vn_kv']]
    for idx, row in grid['trafo'].iterrows():
        grid['trafo'].loc[idx, ['v_hv_pu', 'v_lv_pu']] = grid['res_bus'].loc[
            row[['hv_bus', 'lv_bus']], 'vm_pu'].to_list()
    for idx, row in grid['load'].iterrows():
        grid['load'].loc[idx, 'vn_kv'] = grid['bus'].loc[row['bus'], 'vn_kv']
    for idx, row in grid['gen'].iterrows():
        grid['gen'].loc[idx, 'vn_kv'] = grid['bus'].loc[row['bus'], 'vn_kv']
    for idx, row in grid['sgen'].iterrows():
        grid['sgen'].loc[idx, 'vn_kv'] = grid['bus'].loc[row['bus'], 'vn_kv']


def determine_plot_style(grid, plot_mv, plot_lv, consider_out_of_service):
    """If elements are out of service and should be considered, lines will be dashed and buses will not be filled.
    Else, out of service elements will not be shown"""
    # Add new columns to describe how to plot lines and buses
    grid['line'][['dash', 'plot']] = [None, True]
    grid['bus'][['fill', 'plot']] = [True, True]
    grid['trafo']['fill'] = True
    grid['load'][['fill', 'plot']] = [True, True]
    grid['sgen'][['fill', 'plot']] = [True, True]
    grid['gen'][['fill', 'plot']] = [True, True]
    # Convert data type
    for field in ['line', 'bus', 'trafo', 'load', 'sgen', 'gen']:
        grid[field]['in_service'] = grid[field]['in_service'].astype(bool)
    # Determine if elements are plotted, depending on if they are in service
    if consider_out_of_service:
        grid['line'].loc[~grid['line']['in_service'], 'dash'] = 10
        grid['bus'].loc[~grid['bus']['in_service'], 'fill'] = False
        grid['trafo'].loc[~grid['trafo']['in_service'], 'fill'] = False
        grid['load'].loc[~grid['load']['in_service'], 'fill'] = False
        grid['sgen'].loc[~grid['sgen']['in_service'], 'fill'] = False
        grid['gen'].loc[~grid['gen']['in_service'], 'fill'] = False
    else:
        grid['line'].loc[~grid['line']['in_service'], 'plot'] = False
        grid['bus'].loc[~grid['bus']['in_service'], 'plot'] = False
        grid['load'].loc[~grid['load']['in_service'], 'plot'] = False
        grid['sgen'].loc[~grid['sgen']['in_service'], 'plot'] = False
        grid['gen'].loc[~grid['gen']['in_service'], 'plot'] = False
    # Do not plot lines and buses of mv and lv grids, if they are not considered
    if not plot_mv:
        grid['line'].loc[~grid['line']['vn_kv'] > 1, 'plot'] = False
        grid['bus'].loc[~grid['bus']['vn_kv'] > 1, 'plot'] = False
        grid['load'].loc[~grid['load']['vn_kv'] > 1, 'plot'] = False
        grid['sgen'].loc[~grid['sgen']['vn_kv'] > 1, 'plot'] = False
        grid['gen'].loc[~grid['gen']['vn_kv'] > 1, 'plot'] = False
    if not plot_lv:
        grid['line'].loc[~grid['line']['vn_kv'] < 1, 'plot'] = False
        grid['bus'].loc[~grid['bus']['vn_kv'] < 1, 'plot'] = False
        grid['load'].loc[~grid['load']['vn_kv'] < 1, 'plot'] = False
        grid['sgen'].loc[~grid['sgen']['vn_kv'] < 1, 'plot'] = False
        grid['gen'].loc[~grid['gen']['vn_kv'] < 1, 'plot'] = False


def identify_lv_grids(grid, consider_out_of_service):
    """Identify all lv grids in the grid"""
    # Determine all mv/lv trafos
    mv_lv_trafos = grid['trafo'].index[grid['trafo']['vn_lv_kv'].eq(0.4)]
    lv_grids = []
    # Only bus switches should be considered
    switch = grid['switch'].copy()
    switch = switch.drop(index=switch.index[switch['type'].eq('b')])
    line = grid['line'].copy()
    if not consider_out_of_service:
        line = line.drop(index=line.index[~line['in_service'].astype(bool)])
        switch = switch.drop(index=switch.index[~switch['in_service'].astype(bool)])
    # Every trafo represents an lv grid
    for idx_trafo in mv_lv_trafos:
        buses = {grid['trafo'].loc[idx_trafo, 'lv_bus']}  # Set of all buses in this grid
        lines = set()  # Set of all lines in this grid
        n_lines = -1  # Set to -1 to enable the first iteration
        n_buses = -1  # Set to -1 to enable the first iteration
        # Add new lines and buses until no new elements can be found
        while n_lines != len(lines) and n_buses != len(buses):
            n_lines = len(lines)
            n_buses = len(buses)
            lines.update(line.index[line['to_bus'].isin(buses)].to_list())
            lines.update(line.index[line['from_bus'].isin(buses)].to_list())
            buses.update(line.loc[lines, 'to_bus'].to_list())
            buses.update(line.loc[lines, 'from_bus'].to_list())
            buses.update(switch.loc[switch['bus'].isin(buses), 'element'].to_list())
            buses.update(switch.loc[switch['element'].isin(buses), 'bus'].to_list())
        lv_grids.append({'buses': buses, 'lines': lines})
    return lv_grids


def plot_grid(m, grid, plot_buses, plot_trafos, plot_loads, plot_gens, buildings):
    # Plot buildings
    if buildings is not None:
        for idx, building, in buildings.iterrows():
            for poly in building['geometry']:
                coords = [[coord[1], coord[0]] for coord in list(poly.exterior.coords)]
                Polygon(locations=coords, weight=2, fill=True, fill_opacity=0.3, color=building['color'],
                        tooltip=building['tooltip']).add_to(m)
    # Plot lines
    # Plot mv lines first, so they are below the lv lines
    for idx, line in grid['line'].iterrows():
        if line['plot'] and line['vn_kv'] > 1:
            # Get line coordinates
            line_coords = [(coord[1], coord[0]) for coord in grid['line_geodata'].loc[idx, 'coords']]
            PolyLine(line_coords, color=line['color'], tooltip=line['tooltip'], weight=5.5,
                     dash_array=line['dash']).add_to(m)
    # Plot lv lines
    for idx, line in grid['line'].iterrows():
        if line['plot'] and line['vn_kv'] < 1:
            # Get line coordinates
            line_coords = [(coord[1], coord[0]) for coord in grid['line_geodata'].loc[idx, 'coords']]
            PolyLine(line_coords, color=line['color'], tooltip=line['tooltip'], weight=2.5).add_to(m)
    # Plot buses
    if plot_buses:
        # Plot mv buses first, so they are below the lv buses
        for idx, bus in grid['bus'].iterrows():
            if bus['plot'] and bus['vn_kv'] > 1:
                Circle(grid['bus_geodata'].loc[idx, ['y', 'x']].to_list(), color=bus['color'], tooltip=bus['tooltip'],
                       radius=2.25, fill=bus['fill'], fill_opacity=1).add_to(m)
        # Plot lv buses
        for idx, bus in grid['bus'].iterrows():
            if bus['plot'] and bus['vn_kv'] < 1:
                Circle(grid['bus_geodata'].loc[idx, ['y', 'x']].to_list(), color=bus['color'], tooltip=bus['tooltip'],
                       radius=1, fill=bus['fill'], fill_opacity=1).add_to(m)

    # Plot transformers
    if plot_trafos:
        for idx, trafo in grid['trafo'].iterrows():
            hv_coords = grid['bus_geodata'].loc[trafo['hv_bus'], ['y', 'x']].to_list()
            lv_coords = grid['bus_geodata'].loc[trafo['lv_bus'], ['y', 'x']].to_list()
            cc = [(hv_coords[c] + lv_coords[c]) * 0.5 for c in [0, 1]]
            Circle(location=cc, radius=5, fill=trafo['fill'], tooltip=trafo['tooltip'],
                   color=trafo['color']).add_to(m)
    # Setup for triangles
    dist = 0.00002
    offset = 0.00005
    # Plot loads
    if plot_loads:
        for idx, load in grid['load'].iterrows():
            if load['plot']:
                coord = grid['bus_geodata'].loc[load['bus'], ['y', 'x']].to_list()
                c1 = [coord[0] - dist * 0.7, coord[1] - offset]
                c2 = [coord[0] + dist * 0.7, coord[1] + dist - offset]
                c3 = [coord[0] + dist * 0.7, coord[1] - dist - offset]
                Polygon(locations=[c1, c2, c3], tooltip=load['tooltip'], fill=load['fill'], fill_opacity=1,
                        color=load['color']).add_to(m)
    # Plot generators
    if plot_gens:
        for idx, gen in grid['gen'].iterrows():
            if gen['plot']:
                coord = grid['bus_geodata'].loc[gen['bus'], ['y', 'x']].to_list()
                c1 = [coord[0] + dist * 0.7, coord[1] + offset]
                c2 = [coord[0] - dist * 0.7, coord[1] + dist + offset]
                c3 = [coord[0] - dist * 0.7, coord[1] - dist + offset]
                Polygon(locations=[c1, c2, c3], tooltip=gen['tooltip'], fill=gen['fill'], fill_opacity=1,
                        color=gen['color']).add_to(m)
    if plot_gens:
        for idx, sgen in grid['sgen'].iterrows():
            if sgen['plot']:
                coord = grid['bus_geodata'].loc[sgen['bus'], ['y', 'x']].to_list()
                c1 = [coord[0] + dist * 0.7, coord[1] + offset]
                c2 = [coord[0] - dist * 0.7, coord[1] + dist + offset]
                c3 = [coord[0] - dist * 0.7, coord[1] - dist + offset]
                Polygon(locations=[c1, c2, c3], tooltip=sgen['tooltip'], fill=sgen['fill'], fill_opacity=1,
                        color=sgen['color']).add_to(m)


def add_colormap(m, color_according_to):
    if color_according_to == 'bus_voltage':
        colormap = branca.colormap.linear.Spectral_10.scale(0.9, 1.1)
        colormap.caption = 'Bus Voltage in %'
        colormap.add_to(m)
    elif color_according_to == 'line_utilization':
        colormap = branca.colormap.linear.Spectral_10.scale(0, 120)
        colormap.colors.reverse()
        colormap.caption = 'Line Utilization in %'
        colormap.add_to(m)
