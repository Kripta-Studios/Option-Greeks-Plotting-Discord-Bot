import pandas as pd
from pandas.tseries.offsets import BDay
import numpy as np
import matplotlib
matplotlib.use('Agg')  # Non-interactive backend
import matplotlib.pyplot as plt
import matplotlib.colors as mcolors
import math
import orjson
import modules.stats as stats
from modules.tasty_handler import tasty_data, tasty_expirations_strikes
from modules.ticker_dwn import dwn_data
from modules.utils import *
from tastytrade import Session
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from pathlib import Path
from os import getcwd, makedirs, path, getenv
import datetime
from dotenv import load_dotenv

async def plot_greeks_table(
        df,
        today_ddt,
        today_ddt_string,
        monthly_options_dates,
        spot_price,
        from_strike,
        to_strike,
        levels,
        totaldelta,
        totalgamma,
        totalvanna,
        totalcharm,
        zerodelta,
        zerogamma,
        call_ivs,
        put_ivs,
        exp, 
        ticker,
        lower_bound,
        upper_bound,
        greek_filter=None
):
    if not isinstance(df, pd.DataFrame) or df.empty:
        return False
    
    filenames = []
    GREEKS = [greek_filter] if greek_filter else ["delta", "gamma", "vanna", "charm"]

    VISUALIZATIONS = {
        "delta": ["Absolute Delta Exposure", "Delta Exposure By Calls/Puts", "Delta Exposure Profile"],
        "gamma": ["Absolute Gamma Exposure", "Gamma Exposure By Calls/Puts", "Gamma Exposure Profile"],
        "vanna": ["Absolute Vanna Exposure", "Implied Volatility Average", "Vanna Exposure Profile"],
        "charm": ["Absolute Charm Exposure", "Charm Exposure Profile"],
    }
    PLOT_DIR = "plots"
    timestamp = datetime.datetime.now(ZoneInfo("America/New_York")).strftime("%Y%m%d_%H%M%S")
    
    plt.rcParams.update(plt.rcParamsDefault)
    plt.style.use("dark_background")  # Modo oscuro
    
    
    # Definir colormap personalizado sin blanco
    colors = [
        (0.0, (0.0, 0.0, 1)),    # Azul oscuro para valores negativos extremos
        (0.2, (0.1, 0.5, 1.0)),    # Azul más claro
        (0.4, (0.3, 0.3, 1)),    # Azul-violeta
        (0.5, (0.5, 0.0, 0.5)),    # Violeta puro en el centro (cero)
        (0.6, (1, 0.3, 0.3)),    # Rojo-violeta
        (0.8, (1.0, 0.5, 0.1)),    # Rojo más claro
        (1.0, (1, 0.0, 0.0)),    # Rojo oscuro para valores positivos extremos
    ]
    custom_cmap = mcolors.LinearSegmentedColormap.from_list("custom_cmap", colors)

    for greek in GREEKS:
        for value in VISUALIZATIONS[greek]:
            if "Absolute" not in value:
                continue  # Solo generar heatmaps para "Absolute Exposure"
            
            try:
                name = greek.capitalize()
                metric = f'total_{greek.lower()}'
                
                # Calcular límites de strikes
                available_strikes = sorted(df['strike_price'].unique())
                if len(available_strikes) > 50:
                    # Encontrar el índice del strike más cercano al spot_price
                    spot_idx = np.searchsorted(available_strikes, spot_price, side='left')
                    # Seleccionar hasta 50 strikes por encima y por debajo
                    lower_idx = max(0, spot_idx - 50)
                    upper_idx = min(len(available_strikes), spot_idx + 51)  # +51 para incluir el strike en spot_idx
                    # Aplicar límites de 0.95 y 1.05
                    lower_limit = spot_price * 0.75
                    upper_limit = spot_price * 1.25
                    lower_strike = max(available_strikes[lower_idx], lower_limit)
                    upper_strike = min(available_strikes[upper_idx - 1], upper_limit)
                else:
                    # Usar el strike más bajo y más alto, respetando los límites de 0.95 y 1.05
                    lower_limit = spot_price * 0.75
                    upper_limit = spot_price * 1.25
                    lower_strike = max(min(available_strikes), lower_limit)
                    upper_strike = min(max(available_strikes), upper_limit)

                # Filtrar datos por strikes y expiraciones relevantes
                df_filtered = df[(df['strike_price'] >= lower_strike) & (df['strike_price'] <= upper_strike)]
                #df_filtered = df_filtered[df_filtered['expiration_date'] <= today_ddt + timedelta(days=31)]
                
                if df_filtered.empty:
                    continue
                
                # Crear tabla pivote para el heatmap
                pivot_table = df_filtered.pivot_table(
                    index='strike_price', 
                    columns='expiration_date', 
                    values=metric, 
                    aggfunc='sum'
                )

                pivot_table = pivot_table.fillna(0)
                
                if pivot_table.empty:
                    continue
                
                # Ordenar strikes y expiraciones
                strikes = sorted(pivot_table.index, reverse=True)
                expirations = sorted(pivot_table.columns)
                pivot_table = pivot_table.reindex(index=strikes, columns=expirations, fill_value=0)
                
                # Calcular el rango máximo para una escala de colores simétrica
                max_abs = max(abs(math.floor(pivot_table.min().min())), abs(math.ceil(pivot_table.max().max())))
                if max_abs == 0:
                    max_abs = 1e-6
                
                # Formatear etiquetas de expiración
                expiration_labels = [d.strftime('%b %d') for d in expirations]
                
                # Crear figura y ejes
                fig, ax = plt.subplots(figsize=(12, 19))
                
                # Crear el heatmap con colores degradados
                im = ax.imshow(
                    pivot_table.values, 
                    cmap=custom_cmap, 
                    aspect="auto", 
                    norm=mcolors.TwoSlopeNorm(vmin=-max_abs, vcenter=0, vmax=max_abs)
                )
                # Añadir valores en cada celda del heatmap
                for i in range(len(strikes)):
                    for j in range(len(expirations)):
                        value2text = pivot_table.values[i, j]
                        if not np.isnan(value2text):  # Solo añadir texto si el valor no es NaN
                            text_color = 'white' if value2text <= 0 else 'black'
                            ax.text(j, i, f"$ {value2text*100000:,.2f}k" if value2text % 1 != 0 else f"$ {int(value2text)*100000:,d}k",
                                    ha='center', va='center', color=text_color, fontsize=8)
                
                # Configurar ejes
                ax.set_xticks(np.arange(len(expirations)))
                ax.set_xticklabels(expiration_labels, rotation=0, ha='center')
                ax.set_yticks(np.arange(len(strikes)))
                ax.set_yticklabels([f"{s:.2f}" if s % 1 != 0 else f"{int(s)}" for s in strikes])
                ax.set_xlabel("Expiration Date")
                ax.set_ylabel("Strike Price")
                spot_idx = len(strikes) - np.searchsorted(strikes[::-1], spot_price, side='left') - 1
                ax.axhline(y=spot_idx, color='white', linestyle='--', linewidth=1, label=f'Spot Price: {spot_price:.2f}')


                # Calcular valores agregados por strike para encontrar máximo, mínimo y transición
                agg_by_strike = df_filtered.groupby('strike_price')[metric].sum()
                max_positive_strike = agg_by_strike.idxmax()
                max_negative_strike = agg_by_strike.idxmin()

                # Encontrar el índice en strikes para el máximo y mínimo
                if not pd.isna(max_positive_strike):
                    max_positive_idx = len(strikes) - np.searchsorted(strikes[::-1], max_positive_strike, side='left') - 1
                    ax.axhline(
                        y=max_positive_idx,
                        color="yellow",
                        linestyle="--",
                        linewidth=1.2,
                        label=f"Max Positive {name}: {max_positive_strike:.2f}",
                        xmin=0.5,  # Desde el centro hacia la derecha
                        xmax=1.0
                    )
                if not pd.isna(max_negative_strike):
                    max_negative_idx = len(strikes) - np.searchsorted(strikes[::-1], max_negative_strike, side='left') - 1
                    ax.axhline(
                        y=max_negative_idx,
                        color="purple",
                        linestyle="--",
                        linewidth=1.2,
                        label=f"Max Negative {name}: {max_negative_strike:.2f}",
                        xmin=0.0,  # Desde el centro hacia la izquierda
                        xmax=0.5
                    )

                # Encontrar el punto de transición de positivo a negativo más cercano al spot_price, ignorando outliers
                signs = np.sign(agg_by_strike.values)
                runs = []
                if len(signs) > 0:
                    current_sign = signs[0]
                    start = 0
                    for j in range(1, len(signs)):
                        if signs[j] != current_sign:
                            runs.append((current_sign, start, j-1))
                            current_sign = signs[j]
                            start = j
                    runs.append((current_sign, start, len(signs)-1))

                # Encontrar transiciones válidas donde ambas runs tengan longitud >=2
                zero_strikes = []
                for r in range(1, len(runs)):
                    prev_run = runs[r-1]
                    curr_run = runs[r]
                    prev_len = prev_run[2] - prev_run[1] + 1
                    curr_len = curr_run[2] - curr_run[1] + 1
                    if prev_len >= 2 and curr_len >= 2 and prev_run[0] != curr_run[0] and prev_run[0] != 0 and curr_run[0] != 0:
                        idx1 = prev_run[2]
                        idx2 = curr_run[1]
                        strike1 = agg_by_strike.index[idx1]
                        value1 = agg_by_strike.iloc[idx1]
                        strike2 = agg_by_strike.index[idx2]
                        value2 = agg_by_strike.iloc[idx2]
                        # Interpolar el zero strike
                        zero_strike = strike2 - ((strike2 - strike1) * value2 / (value2 - value1))
                        zero_strikes.append(zero_strike)

                # Encontrar el cambio de signo más cercano al spot_price
                if zero_strikes:
                    zero_strikes = np.array(zero_strikes)
                    closest_idx = np.argmin(np.abs(zero_strikes - spot_price))
                    zero_strike = zero_strikes[closest_idx]
                    zero_idx = len(strikes) - np.searchsorted(strikes[::-1], zero_strike, side='left') - 1
                    ax.axhline(
                        y=zero_idx,
                        color="cyan",
                        linestyle="--",
                        linewidth=1.2,
                        label=f"{name} Flip: {zero_strike:.2f}"
                    )




                ax.legend(loc='upper right')

                # Añadir barra de color
                cbar = fig.colorbar(im, ax=ax)
                cbar.set_label(f"{name} Exposure")
                
                # Configurar título
                title = f"{ticker} {value} Heatmap, {today_ddt_string}"
                ax.set_title(title)
                
                # Guardar el gráfico
                filename = f"{PLOT_DIR}/{ticker}/{exp}/{greek}/{value.replace(' ', '_')}_Heatmap/{timestamp}.png"
                makedirs(path.dirname(filename), exist_ok=True)
                plt.savefig(filename, bbox_inches="tight", facecolor='black')
                plt.close()
                if not path.exists(filename):
                    print(f"No se guardó correctamente el gráfico: {filename}")
                    return None
                filenames.append(filename)
                
                
            except Exception as e:
                print(f"Error processing {ticker}/{exp}/{greek}/{value}: {e}")
    
    return filenames

async def plot_greeks_histogram(
        df,
        today_ddt,
        today_ddt_string,
        monthly_options_dates,
        spot_price,
        from_strike,
        to_strike,
        levels,
        totaldelta,
        totalgamma,
        totalvanna,
        totalcharm,
        zerodelta,
        zerogamma,
        call_ivs,
        put_ivs,
        exp, 
        ticker,
        lower_bound,
        upper_bound,
        greek_filter = None

):

    if not isinstance(df, pd.DataFrame) or df.empty:
        return None

    filenames = []    
    GREEKS = [greek_filter] if greek_filter else ["delta", "gamma", "vanna", "charm"]
    VISUALIZATIONS = {
    "delta": ["Absolute Delta Exposure", "Delta Exposure By Calls/Puts", "Delta Exposure Profile"],
    "gamma": ["Absolute Gamma Exposure", "Gamma Exposure By Calls/Puts", "Gamma Exposure Profile"],
    "vanna": ["Absolute Vanna Exposure", "Implied Volatility Average", "Vanna Exposure Profile"],
    "charm": ["Absolute Charm Exposure", "Charm Exposure Profile"],
    }
    PLOT_DIR = "plots"
    timestamp = datetime.datetime.now(ZoneInfo("America/New_York")).strftime("%Y%m%d_%H%M%S")
    plt.style.use("dark_background")  # dark mode
    colors = {
        "total": "#89CFF0",  # azul claro
        "call": "#90EE90",   # verde claro
        "put": "#FF7F7F",    # rojo claro
        "spot_line": "#C0C0C0",  # gris claro
        "flip_line": "lightgray"
    }
    
    for greek in GREEKS:
        for value in VISUALIZATIONS[greek]:
            try:
                
                date_condition = not "Profile" in value
                if date_condition:
                    if not isinstance(from_strike, (int, float)) or not isinstance(to_strike, (int, float)):
                        print("Invalid: ", greek, value)
                        #print(f"Invalid from_strike/to_strike for {ticker}/{exp}, skipping")
                        continue
                    df_agg = df.groupby(["strike_price"]).sum(numeric_only=True)
                    strikes_sorted = np.sort(df_agg.index.values)
                    strike_steps = np.diff(strikes_sorted)
                    if len(strike_steps) == 0:
                        step = 1  # fallback en caso de un solo strike
                    else:
                        step = np.min(strike_steps[strike_steps > 0])
                    #print(f"df_agg index type: {type(df_agg.index)}, index values: {df_agg.index[:5]}")
                    
                    lower_strike = max(np.floor(lower_bound / step) * step, df_agg.index.min())
                    upper_strike = min(np.ceil(upper_bound / step) * step, df_agg.index.max())
                    strikes = np.arange(lower_strike, upper_strike + step, step)
                    df_agg = df_agg.reindex(strikes, method='ffill').fillna(0)
                    if df_agg.empty:
                        #print(f"Empty df_agg after slicing for {ticker}/{exp}, skipping")
                        continue
                else:
                    df_agg = df.groupby(["expiration_date"]).sum(numeric_only=True)
                    #print(f"df_agg index type: {type(df_agg.index)}, index values: {df_agg.index[:5]}")
                    if df_agg.empty:
                        #print(f"Empty df_agg for {ticker}/{exp}, skipping")
                        continue

                if "Calls/Puts" in value or value == "Implied Volatility Average":
                    key = "strike" if date_condition else "exp"
                    if not (isinstance(call_ivs, dict) and isinstance(put_ivs, dict) and
                            key in call_ivs and key in put_ivs):
                        #print(f"Invalid call_ivs/put_ivs for {ticker}/{exp}/{value}, skipping")
                        continue
                    call_ivs_data, put_ivs_data = call_ivs[key], put_ivs[key]
                else:
                    call_ivs_data, put_ivs_data = None, None


                name = value.split()[1] if "Absolute" in value else value.split()[0]
                name_to_vals = {
                    "Delta": (f"per 1% {ticker} Move", f"{name} Exposure (price / 1% move)", zerodelta),
                    "Gamma": (f"per 1% {ticker} Move", f"{name} Exposure (delta / 1% move)", zerogamma),
                    "Vanna": (f"per 1% {ticker} IV Move", f"{name} Exposure (delta / 1% IV move)", 0),
                    "Charm": (f"a day til {ticker} Expiry", f"{name} Exposure (delta / day til expiry)", 0),
                    "Implied": ("", "Implied Volatility (IV) Average", 0),
                }
                description, y_title, zeroflip = name_to_vals[name]
                scale = 10**9
                plt.rcParams.update({
                "figure.figsize": (19.2, 10.8), #(12, 16), # Use (12.8, 7.2) for 720p, (38.4, 21.6) for 4K,  (19.2, 10.8) for 1080p
                "axes.titlesize": 16 * 1.5,     # Multiply everything by 1.0 for 720p, by 3.0 for 4K
                "axes.labelsize": 14 * 1.5,
                "xtick.labelsize": 12 * 1.5,
                "ytick.labelsize": 12 * 1.5,
                "legend.fontsize": 12 * 1.5,
                "figure.titlesize": 18 * 1.5,
                "lines.linewidth": 1.2 * 1.5,
                })
                plt.rcParams.update({
                "axes.edgecolor": "lightgray",
                "axes.labelcolor": "lightgray",
                "xtick.color": "lightgray",
                "ytick.color": "lightgray",
                "grid.color": "#444444",
                "text.color": "lightgray",
                })
                title = f"{ticker} {value}, {today_ddt_string} for {exp}"
                plt.title(title.replace("<br>", " "))
                plt.grid(True, color="lightgray", linewidth=0.4, alpha=0.5)

                if "Absolute" in value:
                    metric_data = df_agg[f"total_{name.lower()}"]
                    max_positive_strike = metric_data.idxmax()
                    max_negative_strike = metric_data.idxmin()
                    plt.bar(
                        df_agg.index, # para que la barra esté centrada, siendo el width=4, la mitad de 4 es 2
                        df_agg[f"total_{name.lower()}"],
                        align='edge',
                        width=step*0.9,
                        label=f"{name} Exposure",
                        alpha=0.9,
                        color=colors["total"],
                    )
                    if not pd.isna(max_positive_strike):
                        plt.axvline(
                            x=max_positive_strike,
                            color="lime",
                            linestyle="--",
                            linewidth=1.2,
                            label=f"Max Positive {name}: {max_positive_strike:.2f}",
                            ymin=0.0,  # Desde el eje x hacia arriba
                            ymax=1.0
                        )
                    if not pd.isna(max_negative_strike):
                        plt.axvline(
                            x=max_negative_strike,
                            color="red",
                            linestyle="--",
                            linewidth=1.2,
                            label=f"Max Negative {name}: {max_negative_strike:.2f}",
                            ymin=0.0,  # Desde el eje x hacia abajo
                            ymax=1.0
                        )
                    
                    # Encontrar el punto de transición de positivo a negativo más cercano al spot_price, ignorando outliers
                    metric_data = df_agg[f"total_{name.lower()}"]
                    signs = np.sign(metric_data.values)

                    # Encontrar runs de signos iguales
                    runs = []
                    if len(signs) > 0:
                        current_sign = signs[0]
                        start = 0
                        for j in range(1, len(signs)):
                            if signs[j] != current_sign:
                                runs.append((current_sign, start, j-1))
                                current_sign = signs[j]
                                start = j
                        runs.append((current_sign, start, len(signs)-1))

                    # Encontrar transiciones válidas donde ambas runs tengan longitud >=2
                    zero_strikes = []
                    for r in range(1, len(runs)):
                        prev_run = runs[r-1]
                        curr_run = runs[r]
                        prev_len = prev_run[2] - prev_run[1] + 1
                        curr_len = curr_run[2] - curr_run[1] + 1
                        if prev_len >= 2 and curr_len >= 2 and prev_run[0] != curr_run[0] and prev_run[0] != 0 and curr_run[0] != 0:
                            idx1 = prev_run[2]
                            idx2 = curr_run[1]
                            strike1 = metric_data.index[idx1]
                            value1 = metric_data.iloc[idx1]
                            strike2 = metric_data.index[idx2]
                            value2 = metric_data.iloc[idx2]
                            # Interpolar el zero strike
                            zero_strike = strike2 - ((strike2 - strike1) * value2 / (value2 - value1))
                            zero_strikes.append(zero_strike)

                    # Encontrar el cambio de signo más cercano al spot_price
                    if zero_strikes:
                        zero_strikes = np.array(zero_strikes)
                        closest_idx = np.argmin(np.abs(zero_strikes - spot_price))
                        zero_strike = zero_strikes[closest_idx]
                        
                        plt.axvline(
                            x=zero_strike,
                            color="yellow",
                            linestyle="--",
                            linewidth=1.2,
                            label=f"{name} Flip: {zero_strike:.2f}"
                        )
                    
                elif "Calls/Puts" in value:
                    metric_data = df_agg[f"total_{name.lower()}"]
                    max_positive_strike = metric_data.idxmax()
                    max_negative_strike = metric_data.idxmin()
                    plt.bar(
                        df_agg.index,
                        df_agg[f"call_{name[:1].lower()}ex"] / scale,
                        align='edge',
                        width=step*0.9,
                        label=f"Call {name}",
                        alpha=0.9,
                        color=colors["call"],
                    )
                    plt.bar(
                        df_agg.index,
                        df_agg[f"put_{name[:1].lower()}ex"] / scale,
                        align='edge',
                        width=step*0.9,
                        label=f"Put {name}",
                        alpha=0.9,
                        color=colors["put"],
                    )
                    if not pd.isna(max_positive_strike):
                        plt.axvline(
                            x=max_positive_strike,
                            color="lime",
                            linestyle="--",
                            linewidth=1.2,
                            label=f"Max Positive {name}: {max_positive_strike:.2f}",
                            ymin=0.0,  # Desde el eje x hacia arriba
                            ymax=1.0
                        )
                    if not pd.isna(max_negative_strike):
                        plt.axvline(
                            x=max_negative_strike,
                            color="red",
                            linestyle="--",
                            linewidth=1.2,
                            label=f"Max Negative {name}: {max_negative_strike:.2f}",
                            ymin=0.0,  # Desde el eje x hacia abajo
                            ymax=1.0
                        )
                    
                    # Encontrar el punto de transición de positivo a negativo más cercano al spot_price, ignorando outliers
                    metric_data = df_agg[f"total_{name.lower()}"]
                    signs = np.sign(metric_data.values)

                    # Encontrar runs de signos iguales
                    runs = []
                    if len(signs) > 0:
                        current_sign = signs[0]
                        start = 0
                        for j in range(1, len(signs)):
                            if signs[j] != current_sign:
                                runs.append((current_sign, start, j-1))
                                current_sign = signs[j]
                                start = j
                        runs.append((current_sign, start, len(signs)-1))

                    # Encontrar transiciones válidas donde ambas runs tengan longitud >=2
                    zero_strikes = []
                    for r in range(1, len(runs)):
                        prev_run = runs[r-1]
                        curr_run = runs[r]
                        prev_len = prev_run[2] - prev_run[1] + 1
                        curr_len = curr_run[2] - curr_run[1] + 1
                        if prev_len >= 2 and curr_len >= 2 and prev_run[0] != curr_run[0] and prev_run[0] != 0 and curr_run[0] != 0:
                            idx1 = prev_run[2]
                            idx2 = curr_run[1]
                            strike1 = metric_data.index[idx1]
                            value1 = metric_data.iloc[idx1]
                            strike2 = metric_data.index[idx2]
                            value2 = metric_data.iloc[idx2]
                            # Interpolar el zero strike
                            zero_strike = strike2 - ((strike2 - strike1) * value2 / (value2 - value1))
                            zero_strikes.append(zero_strike)

                    # Encontrar el cambio de signo más cercano al spot_price
                    if zero_strikes:
                        zero_strikes = np.array(zero_strikes)
                        closest_idx = np.argmin(np.abs(zero_strikes - spot_price))
                        zero_strike = zero_strikes[closest_idx]
                        
                        plt.axvline(
                            x=zero_strike,
                            color="yellow",
                            linestyle="--",
                            linewidth=1.2,
                            label=f"{name} Flip: {zero_strike:.2f}"
                        )
                elif value == "Implied Volatility Average":
                    plt.plot(
                        df_agg.index,
                        put_ivs_data * 100,
                        label="Put IV",
                        color=colors["put"],
                    )
                    plt.fill_between(df_agg.index, put_ivs_data * 100, alpha=0.3, color=colors["put"])
                    plt.plot(
                        df_agg.index,
                        call_ivs_data * 100,
                        label="Call IV",
                        color=colors["call"],
                    )
                    plt.fill_between(df_agg.index, call_ivs_data * 100, alpha=0.3, color=colors["call"])
                else:
                    name_to_vals = {
                        "Delta": (totaldelta["all"], totaldelta["ex_next"], totaldelta["ex_fri"]),
                        "Gamma": (totalgamma["all"], totalgamma["ex_next"], totalgamma["ex_fri"]),
                        "Vanna": (totalvanna["all"], totalvanna["ex_next"], totalvanna["ex_fri"]),
                        "Charm": (totalcharm["all"], totalcharm["ex_next"], totalcharm["ex_fri"]),
                    }
                    all_ex, ex_next, ex_fri = name_to_vals[name]
                    if not (all_ex.size > 0 and ex_next.size > 0 and ex_fri.size > 0):
                        #print(f"Invalid profile data for {ticker}/{exp}/{value}: empty arrays")
                        continue
                    plt.plot(levels, all_ex, label="All Expiries")
                    plt.plot(levels, ex_fri, label="Next Monthly Expiry")
                    plt.plot(levels, ex_next, label="Next Expiry")
                    if name in ["Charm", "Vanna"]:
                        all_ex_min, all_ex_max = all_ex.min(), all_ex.max()
                        min_n = [all_ex_min, ex_fri.min() if ex_fri.size != 0 else all_ex_min, ex_next.min() if ex_next.size != 0 else all_ex_min]
                        max_n = [all_ex_max, ex_fri.max() if ex_fri.size != 0 else all_ex_max, ex_next.max() if ex_next.size != 0 else all_ex_max]
                        min_n.sort()
                        max_n.sort()
                        if min_n[0] < 0:
                            plt.axhspan(0, min_n[0] * 1.5, facecolor="red", alpha=0.1)
                        if max_n[2] > 0:
                            plt.axhspan(0, max_n[2] * 1.5, facecolor="green", alpha=0.1)
                        plt.axhline(y=0, color="lightgray", linestyle="--", label=f"{name} Flip")
                    elif zeroflip > 0:
                        plt.axvline(x=zeroflip, color="lightgray", linestyle="--", label=f"{name} Flip: {zeroflip:,.0f}")
                        plt.axvspan(from_strike, zeroflip, facecolor="red", alpha=0.1)
                        plt.axvspan(zeroflip, to_strike, facecolor="green", alpha=0.1)

                if date_condition:
                    step = math.log10(spot_price)
                    
                    if step < 1:
                        step = 0.5

                    elif 1 <= step < 2:
                        step = 2
                    
                    elif 2 <= step < 2.5:
                        step = 5

                    elif 2.5 <= step < 3:
                        step = 10
                    
                    else:
                        step = (math.floor(step))
                        step = (10 ** (step-1))*0.4
                    
                    # Ajustar límites para que sean múltiplos de step:
                    lower_bound = step * np.floor(float(lower_bound) / step)
                    upper_bound = step * np.ceil(float(upper_bound) / step)

                    plt.axvline(x=spot_price, color=colors["spot_line"], linestyle="--", linewidth=0.9, label=f"{ticker} Spot: {spot_price:,.2f}")
                    plt.xlim(lower_bound, upper_bound)
                    x_ticks = np.arange(lower_bound, upper_bound + step, step)
                   
                    plt.xticks(x_ticks, [f"{x:.2f}" if step < 1 else f"{int(x)}" for x in x_ticks])

                else:
                    plt.xlim(today_ddt, today_ddt + timedelta(days=31))

                plt.xlabel("Strike" if date_condition else "Date")
                plt.ylabel(y_title)
                plt.legend()
                today = datetime.datetime.now(ZoneInfo("America/New_York")).date()
                tomorrow = next_open_day(today)
                date_formats = {
                    "monthly": monthly_options_dates[0].strftime("%Y %b") if monthly_options_dates else "N/A",
                    "opex": monthly_options_dates[1].strftime("%Y %b %d") if len(monthly_options_dates) > 1 else "N/A",
                    "0dte": monthly_options_dates[0].strftime("%Y %b %d") if monthly_options_dates else "N/A",
                    "1dte": tomorrow.strftime("%Y %b %d"),
                    "all": "All Expirations",
                }
                if exp not in date_formats.keys():
                    legend_title = expir_to_datetime(exp)
                    plt.legend(title=legend_title)
                else:
                    plt.legend(title=date_formats.get(exp, "All Expirations"))

                value = value.replace('Calls/Puts', 'Calls Puts')
                filename = f"{PLOT_DIR}/{ticker}/{exp}/{greek}/{value.replace(' ', '_')}/{timestamp}.png"
                dir_path = path.dirname(filename)
                if not path.exists(dir_path):
                    makedirs(dir_path, exist_ok=True)
                makedirs(path.dirname(filename), exist_ok=True)
                plt.savefig(filename, bbox_inches="tight", facecolor='black')
                plt.close()
                if not path.exists(filename):
                    print(f"No se guardó correctamente el gráfico: {filename}")
                    return None
                #await send_plot_to_discord(filename, ticker, exp, greek)
                #shutil.rmtree(PLOT_DIR)
                filenames.append(filename)


            except Exception as e:
                print(f"Error processing {ticker}/{exp}/{greek}/{value}: {e}")
    return filenames
                             
async def calc_exposures(
    option_data,
    ticker,
    expir,
    first_expiry,
    this_monthly_opex,
    spot_price,
    today_ddt,
    today_ddt_string,
    SOFR_yield
):
    dividend_yield = 0.0  # assume 0
    risk_free_yield = SOFR_yield

    monthly_options_dates = [first_expiry, this_monthly_opex]

    strike_prices = option_data["strike_price"].to_numpy()
    expirations = option_data["expiration_date"].to_numpy()
    time_till_exp = option_data["time_till_exp"].to_numpy()
    opt_call_ivs = option_data["call_iv"].to_numpy()
    opt_put_ivs = option_data["put_iv"].to_numpy()
    call_open_interest = option_data["call_open_int"].to_numpy()
    put_open_interest = option_data["put_open_int"].to_numpy()

    nonzero_call_cond = (time_till_exp > 0) & (opt_call_ivs > 0)
    nonzero_put_cond = (time_till_exp > 0) & (opt_put_ivs > 0)
    np_spot_price = np.array([[spot_price]])

    call_dp, call_cdf_dp, call_pdf_dp = stats.calc_dp_cdf_pdf(
        np_spot_price,
        strike_prices,
        opt_call_ivs,
        time_till_exp,
        risk_free_yield,
        dividend_yield,
    )
    put_dp, put_cdf_dp, put_pdf_dp = stats.calc_dp_cdf_pdf(
        np_spot_price,
        strike_prices,
        opt_put_ivs,
        time_till_exp,
        risk_free_yield,
        dividend_yield,
    )

    from_strike = 0.5 * spot_price
    to_strike = 1.5 * spot_price

    # ---=== CALCULATE EXPOSURES ===---
    option_data["call_dex"] = (
        option_data["call_delta"].to_numpy() * call_open_interest * spot_price
    )
    option_data["put_dex"] = (
        option_data["put_delta"].to_numpy() * put_open_interest * spot_price
    )
    option_data["call_gex"] = (
        option_data["call_gamma"].to_numpy()
        * call_open_interest
        * spot_price
        * spot_price
    )
    option_data["put_gex"] = (
        option_data["put_gamma"].to_numpy()
        * put_open_interest
        * spot_price
        * spot_price
        * -1
    )
    option_data["call_vex"] = np.where(
        nonzero_call_cond,
        stats.calc_vanna_ex(
            np_spot_price,
            opt_call_ivs,
            time_till_exp,
            dividend_yield,
            call_open_interest,
            call_dp,
            call_pdf_dp,
        )[0],
        0,
    )
    option_data["put_vex"] = np.where(
        nonzero_put_cond,
        stats.calc_vanna_ex(
            np_spot_price,
            opt_put_ivs,
            time_till_exp,
            dividend_yield,
            put_open_interest,
            put_dp,
            put_pdf_dp,
        )[0],
        0,
    )
    option_data["call_cex"] = np.where(
        nonzero_call_cond,
        stats.calc_charm_ex(
            np_spot_price,
            opt_call_ivs,
            time_till_exp,
            risk_free_yield,
            dividend_yield,
            "call",
            call_open_interest,
            call_dp,
            call_cdf_dp,
            call_pdf_dp,
        )[0],
        0,
    )
    option_data["put_cex"] = np.where(
        nonzero_put_cond,
        stats.calc_charm_ex(
            np_spot_price,
            opt_put_ivs,
            time_till_exp,
            risk_free_yield,
            dividend_yield,
            "put",
            put_open_interest,
            put_dp,
            put_cdf_dp,
            put_pdf_dp,
        )[0],
        0,
    )
    # Calculate total and scale down
    option_data["total_delta"] = (
        option_data["call_dex"].to_numpy() + option_data["put_dex"].to_numpy()
    ) / 10**9
    option_data["total_gamma"] = (
        option_data["call_gex"].to_numpy() + option_data["put_gex"].to_numpy()
    ) / 10**9
    option_data["total_vanna"] = (
        option_data["call_vex"].to_numpy() - option_data["put_vex"].to_numpy()
    ) / 10**9
    option_data["total_charm"] = (
        option_data["call_cex"].to_numpy() - option_data["put_cex"].to_numpy()
    ) / 10**9

    # group all options by strike / expiration then average their IVs
    df_agg_strike_mean = (
        option_data[["strike_price", "call_iv", "put_iv"]]
        .groupby(["strike_price"])
        .mean(numeric_only=True)
    )
    df_agg_exp_mean = (
        option_data[["expiration_date", "call_iv", "put_iv"]]
        .groupby(["expiration_date"])
        .mean(numeric_only=True)
    )
    # filter strikes / expirations for relevance
    df_agg_strike_mean = df_agg_strike_mean[from_strike:to_strike]
    # df_agg_exp_mean = df_agg_exp_mean[: today_ddt + timedelta(weeks=52)]

    call_ivs = {
        "strike": df_agg_strike_mean["call_iv"].to_numpy(),
        "exp": df_agg_exp_mean["call_iv"].to_numpy(),
    }
    put_ivs = {
        "strike": df_agg_strike_mean["put_iv"].to_numpy(),
        "exp": df_agg_exp_mean["put_iv"].to_numpy(),
    }

    # ---=== CALCULATE EXPOSURE PROFILES ===---
    levels = np.linspace(from_strike, to_strike, 300).reshape(-1, 1)

    totaldelta = {
        "all": np.array([]),
        "ex_next": np.array([]),
        "ex_fri": np.array([]),
    }
    totalgamma = {
        "all": np.array([]),
        "ex_next": np.array([]),
        "ex_fri": np.array([]),
    }
    totalvanna = {
        "all": np.array([]),
        "ex_next": np.array([]),
        "ex_fri": np.array([]),
    }
    totalcharm = {
        "all": np.array([]),
        "ex_next": np.array([]),
        "ex_fri": np.array([]),
    }

    # For each spot level, calculate greek exposure at that point
    call_dp, call_cdf_dp, call_pdf_dp = stats.calc_dp_cdf_pdf(
        levels,
        strike_prices,
        opt_call_ivs,
        time_till_exp,
        risk_free_yield,
        dividend_yield,
    )
    put_dp, put_cdf_dp, put_pdf_dp = stats.calc_dp_cdf_pdf(
        levels,
        strike_prices,
        opt_put_ivs,
        time_till_exp,
        risk_free_yield,
        dividend_yield,
    )
    call_delta_ex = np.where(
        nonzero_call_cond,
        stats.calc_delta_ex(
            levels,
            time_till_exp,
            dividend_yield,
            "call",
            call_open_interest,
            call_cdf_dp,
        ),
        0,
    )
    put_delta_ex = np.where(
        nonzero_put_cond,
        stats.calc_delta_ex(
            levels,
            time_till_exp,
            dividend_yield,
            "put",
            put_open_interest,
            put_cdf_dp,
        ),
        0,
    )
    call_gamma_ex = np.where(
        nonzero_call_cond,
        stats.calc_gamma_ex(
            levels,
            opt_call_ivs,
            time_till_exp,
            dividend_yield,
            call_open_interest,
            call_pdf_dp,
        ),
        0,
    )
    put_gamma_ex = np.where(
        nonzero_put_cond,
        stats.calc_gamma_ex(
            levels,
            opt_put_ivs,
            time_till_exp,
            dividend_yield,
            put_open_interest,
            put_pdf_dp,
        ),
        0,
    )
    call_vanna_ex = np.where(
        nonzero_call_cond,
        stats.calc_vanna_ex(
            levels,
            opt_call_ivs,
            time_till_exp,
            dividend_yield,
            call_open_interest,
            call_dp,
            call_pdf_dp,
        ),
        0,
    )
    put_vanna_ex = np.where(
        nonzero_put_cond,
        stats.calc_vanna_ex(
            levels,
            opt_put_ivs,
            time_till_exp,
            dividend_yield,
            put_open_interest,
            put_dp,
            put_pdf_dp,
        ),
        0,
    )
    call_charm_ex = np.where(
        nonzero_call_cond,
        stats.calc_charm_ex(
            levels,
            opt_call_ivs,
            time_till_exp,
            risk_free_yield,
            dividend_yield,
            "call",
            call_open_interest,
            call_dp,
            call_cdf_dp,
            call_pdf_dp,
        ),
        0,
    )
    put_charm_ex = np.where(
        nonzero_put_cond,
        stats.calc_charm_ex(
            levels,
            opt_put_ivs,
            time_till_exp,
            risk_free_yield,
            dividend_yield,
            "put",
            put_open_interest,
            put_dp,
            put_cdf_dp,
            put_pdf_dp,
        ),
        0,
    )

    # delta exposure
    totaldelta["all"] = (call_delta_ex.sum(axis=1) + put_delta_ex.sum(axis=1)) / 10**9
    # gamma exposure
    totalgamma["all"] = (call_gamma_ex.sum(axis=1) - put_gamma_ex.sum(axis=1)) / 10**9
    # vanna exposure
    totalvanna["all"] = (call_vanna_ex.sum(axis=1) - put_vanna_ex.sum(axis=1)) / 10**9
    # charm exposure
    totalcharm["all"] = (call_charm_ex.sum(axis=1) - put_charm_ex.sum(axis=1)) / 10**9

    expirs_next_expiry = expirations == first_expiry
    expirs_up_to_monthly_opex = expirations <= this_monthly_opex
    if expir != "0dte":
        # exposure for next expiry
        totaldelta["ex_next"] = (
            np.where(expirs_next_expiry, call_delta_ex, 0).sum(axis=1)
            + np.where(expirs_next_expiry, put_delta_ex, 0).sum(axis=1)
        ) / 10**9
        totalgamma["ex_next"] = (
            np.where(expirs_next_expiry, call_gamma_ex, 0).sum(axis=1)
            - np.where(expirs_next_expiry, put_gamma_ex, 0).sum(axis=1)
        ) / 10**9
        totalvanna["ex_next"] = (
            np.where(expirs_next_expiry, call_vanna_ex, 0).sum(axis=1)
            - np.where(expirs_next_expiry, put_vanna_ex, 0).sum(axis=1)
        ) / 10**9
        totalcharm["ex_next"] = (
            np.where(expirs_next_expiry, call_charm_ex, 0).sum(axis=1)
            - np.where(expirs_next_expiry, put_charm_ex, 0).sum(axis=1)
        ) / 10**9
        if expir == "all":
            # exposure for next monthly opex
            totaldelta["ex_fri"] = (
                np.where(expirs_up_to_monthly_opex, call_delta_ex, 0).sum(axis=1)
                + np.where(expirs_up_to_monthly_opex, put_delta_ex, 0).sum(axis=1)
            ) / 10**9
            totalgamma["ex_fri"] = (
                np.where(expirs_up_to_monthly_opex, call_gamma_ex, 0).sum(axis=1)
                - np.where(expirs_up_to_monthly_opex, put_gamma_ex, 0).sum(axis=1)
            ) / 10**9
            totalvanna["ex_fri"] = (
                np.where(expirs_up_to_monthly_opex, call_vanna_ex, 0).sum(axis=1)
                - np.where(expirs_up_to_monthly_opex, put_vanna_ex, 0).sum(axis=1)
            ) / 10**9
            totalcharm["ex_fri"] = (
                np.where(expirs_up_to_monthly_opex, call_charm_ex, 0).sum(axis=1)
                - np.where(expirs_up_to_monthly_opex, put_charm_ex, 0).sum(axis=1)
            ) / 10**9

    # Find Delta Flip Point
    zero_cross_idx = np.where(np.diff(np.sign(totaldelta["all"])))[0]
    neg_delta = totaldelta["all"][zero_cross_idx]
    pos_delta = totaldelta["all"][zero_cross_idx + 1]
    neg_strike = levels[zero_cross_idx]
    pos_strike = levels[zero_cross_idx + 1]
    zerodelta = pos_strike - (
        (pos_strike - neg_strike) * pos_delta / (pos_delta - neg_delta)
    )
    # Find Gamma Flip Point
    zero_cross_idx = np.where(np.diff(np.sign(totalgamma["all"])))[0]
    negGamma = totalgamma["all"][zero_cross_idx]
    posGamma = totalgamma["all"][zero_cross_idx + 1]
    neg_strike = levels[zero_cross_idx]
    pos_strike = levels[zero_cross_idx + 1]
    zerogamma = pos_strike - (
        (pos_strike - neg_strike) * posGamma / (posGamma - negGamma)
    )

    if zerodelta.size > 0:
        zerodelta = zerodelta[0][0]
    else:
        zerodelta = 0
        print("delta flip not found for", ticker, expir, "probably error downloading data")
    if zerogamma.size > 0:
        zerogamma = zerogamma[0][0]
    else:
        zerogamma = 0
        print("gamma flip not found for", ticker, expir, "probably error downloading data")

    return (
        option_data,
        today_ddt,
        today_ddt_string,
        monthly_options_dates,
        spot_price,
        from_strike,
        to_strike,
        levels.ravel(),
        totaldelta,
        totalgamma,
        totalvanna,
        totalcharm,
        zerodelta,
        zerogamma,
        call_ivs,
        put_ivs,
    )

async def get_options_data(ticker, expir, greek_filter):

    #inicio = time.perf_counter()
    load_dotenv()
    username = getenv("TASTYTRADE_USERNAME")
    password = getenv("TASTYTRADE_PASSWORD")

    session = Session(username, password)
    #fin = time.perf_counter()
    #print(f"El inicio de sesión tardó {fin - inicio:.4f} segundos.")

    tz = "America/New_York"

    ticker = ticker.replace("^", "").replace(" ", '').upper()
    # Get Spot and Options Data
    if '/' in ticker:
        tickerList = [get_future_ticker(ticker)]
    else:
        tickerList = [ticker]
    useCBOEdelayedData = False

    if ticker == "SPX":
        tickerList.append("SPXW")
    if ticker == "SPXW":
        tickerList.append("SPX")
    
    tickerList.append(get_SOFR_ticker())

    #inicio = time.perf_counter()
    
    _, tickers_quotes = await tasty_data(session, equities_ticker=tickerList)

    if '/' in ticker:
        tickerList = [ticker]
    else:
        tickerList = tickerList[:-1]

    for quote in tickers_quotes:
        if quote.get("symbol") == get_SOFR_ticker():
            SOFRrate = float(quote.get("last"))
        elif ticker in quote.get("symbol"):
            spot_price = float(quote.get("last"))
   
    SOFR_yield = float((100 - SOFRrate)/100)

    #fin = time.perf_counter()
    #print(f"La descarga del spot price y SOFR tardó {fin - inicio:.4f} segundos. SOFR: ")


    expir = expir.replace(" ", '').lower()            
    selected_date = 0
    boundary = 0
    if expir == "all":
        pass  # Keep all data
    else:
        selected_date = pd.Timestamp(expir_to_datetime(expir)).tz_localize('America/New_York') + timedelta(hours=16)
        boundary = pd.Timestamp(expir_to_datetime("0dte")).tz_localize('America/New_York') + BDay(10) + timedelta(hours=16)
    
    pandas_today = pd.Timestamp(expir_to_datetime("0dte")).tz_localize('America/New_York') + timedelta(hours=0)

    

    if ticker == "NDX":
        useCBOEdelayedData = True

    if ((selected_date > boundary) or (selected_date == 0)) and ticker == "SPX":
        useCBOEdelayedData = True
    
    #inicio = time.perf_counter()
    options_expirations, options_strikes = await tasty_expirations_strikes(session, tickerList)
    #fin = time.perf_counter()
    #print(f"La descarga de las expiraciones y strikes de opciones tardó {fin - inicio:.4f} segundos.")

    if useCBOEdelayedData:
        dwn_data([ticker])
        try:
            # CBOE file format, json
            ticker = ticker.upper()
            with open(
                Path(f"{getcwd()}/data/json/{ticker}_quotedata.json"), encoding="utf-8"
            ) as json_file:
                json_data = json_file.read()
            data = pd.json_normalize(orjson.loads(json_data))
        except orjson.JSONDecodeError as e:
            print(f"{e}, {ticker} {expir} data is unavailable")
            return

    # Get Today's Date
    today_ddt = pd.Timestamp.now(tz=tz)
    today_ddt_string = today_ddt.strftime("%Y %b %d, %I:%M %p %Z")

    # Get all unique expiration dates, sorted
    all_dates = get_all_unique_expirations_timestamps(options_expirations)
    first_expiry = all_dates[0]
    
    if today_ddt > first_expiry:
        first_expiry = all_dates[1]    

    this_monthly_opex, _ = is_third_friday(first_expiry, tz)
    # Filter options based on expir parameter

    if useCBOEdelayedData:
        # Converts CBOE JSON pd df into another pd df with only interest columns renamed
        option_data = format_CBOE_data(
            data["data.options"][0],
            today_ddt
            )

        lower_strike, upper_strike = get_strike_bounds(options_strikes, spot_price)
        if selected_date != 0:
            option_data = option_data[  (option_data["expiration_date"] >= pandas_today) &
                                        (option_data["expiration_date"] <= selected_date)]
            #option_data = option_data[option_data["expiration_date"] <= selected_date]
    
            
    else:

        if selected_date == 0:
            selected_date = all_dates[-1]

        lower_strike, upper_strike = get_strike_bounds(options_strikes, spot_price)

        start_date = first_expiry.date()
        end_date = selected_date.date()

        if start_date > end_date:
            tmp = start_date
            start_date = end_date
            end_date = tmp

        options_requested = {
            "tickers" : tickerList,
            "start_date" : start_date,
            "end_date" : end_date,
            "lower_strike" : lower_strike,
            "upper_strike" : upper_strike

        }
        
        #inicio = time.perf_counter()
        gr_list, _ = await tasty_data(session, options_requested = options_requested)
        #fin = time.perf_counter()
        #print(f"La función descarga de datos de opciones tardó {fin - inicio:.4f} segundos.")
        #inicio = time.perf_counter()   
        option_data = format_data(gr_list, today_ddt)
        #fin = time.perf_counter()
        #print(f"El formateo de datos tardó {fin - inicio:.4f} segundos.")
  
    #inicio = time.perf_counter()
    exposure_data = (await calc_exposures(
        option_data,
        ticker,
        expir,
        first_expiry,
        this_monthly_opex,
        spot_price,
        today_ddt,
        today_ddt_string,
        SOFR_yield
    ))
    #fin = time.perf_counter()
    #print(f"La función cálculo de exposiciones tardó {fin - inicio:.4f} segundos.")
    exposure_data = exposure_data + (expir,ticker,lower_strike, upper_strike, greek_filter)
    #inicio = time.perf_counter()
    histogram_filename = await plot_greeks_histogram(*exposure_data)
    table_filename = await plot_greeks_table(*exposure_data)
    #fin = time.perf_counter()
    #print(f"La función de visualización y plotting tardó {fin - inicio:.4f} segundos.")
    
    return [histogram_filename, table_filename]
