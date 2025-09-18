import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from calendar import monthrange
from cachetools import TTLCache
import cachetools
from pathlib import Path
from os import getcwd, makedirs, path
from re import compile
import exchange_calendars as xcals
import datetime


def get_friday_of_this_week():
    today = datetime.datetime.today()
    weekday = today.weekday()  # lunes = 0, domingo = 6

    # Si ya es viernes (4), devolver hoy
    if weekday == 4:
        friday = today
    elif weekday < 4:
        # Aún no es viernes: sumar los días necesarios
        friday = today + timedelta(days=(4 - weekday))
    else:
        # Sábado (5) o domingo (6): restar días hasta el viernes anterior
        friday = today - timedelta(days=(weekday - 4))

    return friday.strftime("%Y %b %d")


@cachetools.cached(cache=TTLCache(maxsize=16, ttl=60 * 60 * 4))  # in-memory cache for 4 hrs
def is_third_friday(date, tz):
    def get_third_friday_or_thursday(year, month, tz):
        _, last = monthrange(year, month)
        first = datetime.datetime(year, month, 1)
        last = datetime.datetime(year, month, last)
        result = xcals.get_calendar("XNYS", start=first, end=last)
        result = result.sessions.to_pydatetime()

        found = [None, None]
        for i in result:
            if i.weekday() == 4 and 15 <= i.day <= 21 and i.month == month:
                # Third Friday
                found[0] = i.replace(tzinfo=ZoneInfo(tz)) + timedelta(hours=16)
            elif i.weekday() == 3 and 15 <= i.day <= 21 and i.month == month:
                # Thursday alternative
                found[1] = i.replace(tzinfo=ZoneInfo(tz)) + timedelta(hours=16)
        return found[0] or found[1], result

    # Intentamos con el mes actual
    candidate, result = get_third_friday_or_thursday(date.year, date.month, tz)
    if candidate and pd.Timestamp(date).date() > candidate.date():
        # Si la fecha actual ya pasó, buscar en el siguiente mes
        next_month = date.month + 1
        next_year = date.year
        if next_month > 12:
            next_month = 1
            next_year += 1
        candidate, result = get_third_friday_or_thursday(next_year, next_month, tz)
    
    return candidate, result

def expir_to_datetime(expir: str):
    tz = "America/New_York"
    today = datetime.datetime.now(ZoneInfo(tz))
    today_date = today.date()

    expir = expir.lower().strip()

    _, last = monthrange(today.year, today.month)
    first = datetime.datetime(today.year, today.month, 1)
    last = datetime.datetime(today.year, today.month, last)
    calendar = xcals.get_calendar("XNYS", start=first, end=last)
    trading_days = calendar.sessions.to_pydatetime()
    trading_dates = [d.date() for d in trading_days]

    if expir == "0dte":
        # Si el mercado está abierto hoy, devolvemos hoy
        

        if today_date in trading_dates:
            return today_date
        else:
            return next_open_day(today_date)

    elif expir.endswith("dte"):
        try:
            dte = int(expir.replace("dte", ""))
            future_date = today_date
            for _ in range(dte):
                future_date = next_open_day(future_date)
            return future_date
        except ValueError:
            raise ValueError(f"Formato de expiración no reconocido: {expir}")

    elif expir == "weekly":
        # Buscar viernes de esta semana
        this_friday = today_date + datetime.timedelta((4 - today_date.weekday()) % 7)

        _, last = monthrange(this_friday.year, this_friday.month)
        first = datetime.datetime(this_friday.year, this_friday.month, 1)
        last = datetime.datetime(this_friday.year, this_friday.month, last)
        calendar = xcals.get_calendar("XNYS", start=first, end=last)
        trading_days = calendar.sessions.to_pydatetime()
        trading_dates = [d.date() for d in trading_days]

        if this_friday in trading_dates:
            return this_friday
        elif (this_friday - datetime.timedelta(days=1)) in trading_dates:
            return this_friday - datetime.timedelta(days=1)
        else:
            raise ValueError("Ni viernes ni jueves son días hábiles esta semana.")


    elif expir == "opex":
        date_, result = is_third_friday(today_date, tz)
        return date_.date()

    elif expir == "monthly":
        return trading_dates[-1]

    else:
        raise ValueError(f"Tipo de expiración desconocido: {expir}")

        
def next_open_day(date):
    tz_europe = ZoneInfo("Europe/Madrid")
    now_europe = datetime.datetime.now(tz_europe)
    hour = now_europe.hour
    days_to_add = 2 if 22 <= hour <= 23 else 1
    next_day = date + datetime.timedelta(days=days_to_add)

    _, last = monthrange(next_day.year, next_day.month)
    first = datetime.datetime(next_day.year, next_day.month, 1)
    last = datetime.datetime(next_day.year, next_day.month, last)
    calendar = xcals.get_calendar("XNYS", start=first, end=last)
    trading_days = calendar.sessions.to_pydatetime()
    trading_dates = [d.date() for d in trading_days]

    while next_day not in trading_dates:
        next_day += datetime.timedelta(days=1)
    return next_day

def is_parsable(date):
    try:
        datetime.datetime.strptime(date.split()[-2], "%H:%M")
        return True
    except ValueError:
        return False

def format_data(gr_list, today_ddt):
    import pandas as pd
    import numpy as np
    import datetime

    columns = [
        "calls", "call_iv", "call_open_int", "call_delta", "call_gamma",
        "puts", "put_iv", "put_open_int", "put_delta", "put_gamma",
        "strike_price", "expiration_date", "time_till_exp"
    ]

    grouped = {}

    for option in gr_list:
        strike = float(option["strike"])
        raw_expiration = pd.to_datetime(option["expiration"])
        expiration = pd.Timestamp(
            datetime.datetime.combine(raw_expiration, datetime.time(16, 0))
        ).tz_localize("America/New_York")

        # Usamos una base común eliminando solo la letra final C/P
        option_code = str(option["option"]).replace(' ', '')
        option_base = option_code[:-9] + option_code[-8:]  # elimina la C/P (ej: SPXW25071806250000)

        if "/" in option_base:
            option_base = option_base.replace("C", '')
            option_base = option_base.replace("P", '')

        key = (option_base, strike, expiration)

        if key not in grouped:
            grouped[key] = {
                "strike_price": strike,
                "expiration_date": expiration,
                "time_till_exp": None,  # se completará luego
                "calls": None,
                "call_iv": None,
                "call_open_int": None,
                "call_delta": None,
                "call_gamma": None,
                "puts": None,
                "put_iv": None,
                "put_open_int": None,
                "put_delta": None,
                "put_gamma": None,
            }

        is_call = "C" in option["option"][6:]

        if is_call:
            grouped[key]["calls"] = option_code
            grouped[key]["call_iv"] = float(option.get("vol", 0))
            grouped[key]["call_open_int"] = float(option.get("open_interest", 0))
            grouped[key]["call_delta"] = float(option.get("delta", 0))
            grouped[key]["call_gamma"] = float(option.get("gamma", 0))
        else:
            grouped[key]["puts"] = option_code
            grouped[key]["put_iv"] = float(option.get("vol", 0))
            grouped[key]["put_open_int"] = float(option.get("open_interest", 0))
            grouped[key]["put_delta"] = float(option.get("delta", 0))
            grouped[key]["put_gamma"] = float(option.get("gamma", 0))

    # Crear DataFrame
    option_data = pd.DataFrame(grouped.values(), columns=columns)
    # Calcular DTE (sin zona horaria)
    expiration_dates = pd.to_datetime(option_data["expiration_date"].dt.tz_localize(None)).values.astype("datetime64[D]")
    busday_counts = np.busday_count(today_ddt.date(), expiration_dates)
    option_data["time_till_exp"] = np.where(busday_counts == 0, 1 / 252, busday_counts / 252)

    # Ordenar
    option_data = option_data.sort_values(by=["expiration_date", "strike_price"]).reset_index(drop=True)

    return option_data


def format_CBOE_data(data, today_ddt):
    # Precompile regex patterns for performance
    _strike_regex = compile(r"\d[A-Z](\d+)\d\d\d")
    _exp_date_regex = compile(r"(\d{6})[CP]")

    keys_to_keep = ["option", "iv", "open_interest", "delta", "gamma"]
    data = pd.DataFrame([{k: d[k] for k in keys_to_keep if k in d} for d in data])
    data = pd.concat(
        [
            data.rename(
                columns={
                    "option": "calls",
                    "iv": "call_iv",
                    "open_interest": "call_open_int",
                    "delta": "call_delta",
                    "gamma": "call_gamma",
                }
            )
            .iloc[0::2]
            .reset_index(drop=True),
            data.rename(
                columns={
                    "option": "puts",
                    "iv": "put_iv",
                    "open_interest": "put_open_int",
                    "delta": "put_delta",
                    "gamma": "put_gamma",
                }
            )
            .iloc[1::2]
            .reset_index(drop=True),
        ],
        axis=1,
    )
    data["strike_price"] = data["calls"].str.extract(_strike_regex).astype(float)
    data["expiration_date"] = data["calls"].str.extract(_exp_date_regex)
    data["expiration_date"] = pd.to_datetime(
        data["expiration_date"], format="%y%m%d"
    ).dt.tz_localize('America/New_York') + timedelta(hours=16)

    busday_counts = np.busday_count(
        today_ddt.date(),
        data["expiration_date"].values.astype("datetime64[D]"),
    )
    # set DTE. 0DTE options are included in 1 day expirations
    # time to expiration in years (252 trading days)
    data["time_till_exp"] = np.where(busday_counts == 0, 1 / 252, busday_counts / 252)

    data = data.sort_values(by=["expiration_date", "strike_price"]).reset_index(
        drop=True
    )

    return data

def get_strike_bounds(options_strikes: list, spot_price: float):
    all_strikes = []

    for ticker_dict in options_strikes:
        for data in ticker_dict.values():
            all_strikes.extend(data["strikes"])

    if not all_strikes:
        raise ValueError("No hay strikes disponibles en options_strikes")

    # Elimina duplicados y ordena
    all_strikes = sorted(set(all_strikes))

    # Limites absoluto del rango permitido
    if spot_price < 10:
        min_allowed = 0.5 * spot_price
        max_allowed = 1.5 * spot_price
    elif spot_price < 50:
        min_allowed = 0.7 * spot_price
        max_allowed = 1.3 * spot_price

    else:
        min_allowed = 0.80 * spot_price
        max_allowed = 1.20 * spot_price

    # Filtra strikes dentro del rango permitido
    filtered_strikes = [s for s in all_strikes if min_allowed <= s <= max_allowed]

    if not filtered_strikes:
        raise ValueError("No hay strikes dentro del rango permitido [0.5x, 1.5x] del spot.")

    # Encuentra índice más cercano al spot
    closest_idx = min(range(len(filtered_strikes)), key=lambda i: abs(filtered_strikes[i] - spot_price))

    # Índices con ±50 strikes, dentro de límites del array
    lower_idx = max(0, closest_idx - 50)
    upper_idx = min(len(filtered_strikes) - 1, closest_idx + 50)
    
    lower_strike = filtered_strikes[lower_idx]
    upper_strike = filtered_strikes[upper_idx]

    return lower_strike, upper_strike


def get_all_unique_expirations_timestamps(options_expirations):
    ny_tz = ZoneInfo("America/New_York")
    unique_dates = set()

    for entry in options_expirations:
        for ticker, data in entry.items():
            expirations = data.get("expirations", [])
            for date in expirations:
                # date es datetime.date, convertir a Timestamp con hora y zona horaria
                ts = pd.Timestamp(year=date.year, month=date.month, day=date.day,
                                  hour=16, minute=0, second=0, tz=ny_tz)
                unique_dates.add(ts)

    # Devolver la lista ordenada
    return sorted(unique_dates)

def get_SOFR_ticker():
    month_codes = {
        3: "H", 6: "M", 9: "U", 12: "Z"
    }

    def third_wednesday(year, month):
        count = 0
        for day in range(1, 32):
            try:
                date = datetime.date(year, month, day)
            except ValueError:
                break
            if date.weekday() == 2:
                count += 1
                if count == 3:
                    return date
        return None

    def sofr_expiration_date(year, month):
        wednesday = third_wednesday(year, month)
        return wednesday - datetime.timedelta(days=5)

    def next_sofr_contract(today=None):
        if today is None:
            today = datetime.date.today()
        year = today.year
        quarterly_months = [3, 6, 9, 12]

        for i, m in enumerate(quarterly_months):
            expiration = sofr_expiration_date(year, m)
            if today < expiration:
                contract_month = m
                break
            elif today == expiration:
                if i + 1 < len(quarterly_months):
                    contract_month = quarterly_months[i + 1]
                    break
                else:
                    contract_month = 3
                    year += 1
                    break
        else:
            contract_month = 3
            year += 1

        month_code = month_codes[contract_month]
        year_code = str(year)[-1]
        ticker = f"/SR3{month_code}{year_code}"
        expiration_date = sofr_expiration_date(year, contract_month)

        return ticker, expiration_date

    ticker, expiration = next_sofr_contract()
    return ticker


def get_future_ticker(symbol: str, current_date: datetime.datetime = None, monthly: bool = None, tz: str = "America/New_York") -> str:
    """
    Devuelve el ticker de futuros siguiente a la fecha actual para el símbolo dado.
    - Detecta automáticamente si el contrato es mensual o trimestral según el símbolo.
    - Acepta símbolos con o sin prefijo "/".
    - Si `monthly` se especifica, sobrescribe la detección automática.
    """
    if current_date is None:
        current_date = datetime.datetime.now(ZoneInfo(tz))

    symbol = symbol.upper().lstrip("/")  # elimina prefijo "/" si existe

    # Contratos con vencimientos mensuales
    monthly_contracts = {
        'CL', 'QM', 'BZ',      # Petróleo
        'NG', 'QG',            # Gas natural
        'GC', 'HG', 'PL',      # Metales
        'VX',                  # Volatilidad
        'ZT', 'ZF', 'ZN', 'ZB',# Bonos
        'SR3',                 # RBA
        'BTC', 'ETH'           # Criptos
    }

    # Si monthly no está especificado, se detecta automáticamente
    if monthly is None:
        monthly = symbol in monthly_contracts

    month_codes = {
        1: 'F', 2: 'G', 3: 'H', 4: 'J', 5: 'K', 6: 'M',
        7: 'N', 8: 'Q', 9: 'U', 10: 'V', 11: 'X', 12: 'Z'
    }

    if monthly:
        # usar is_third_friday para decidir +1 o +2 meses
        this_third_friday, _ = is_third_friday(current_date, tz)
        if current_date > this_third_friday:
            next_month = current_date.month + 2
        else:
            next_month = this_third_friday.month

        year = current_date.year
        if next_month > 12:
            next_month -= 12
            year += 1

        code = month_codes[next_month]

    else:
        quarterly_months = [3, 6, 9, 12]
        year = current_date.year
        for m in quarterly_months:
            # tercer viernes del mes
            first_day = datetime.datetime(year, m, 1)
            weekday = first_day.weekday()
            delta = (4 - weekday + 7) % 7
            third_friday = 1 + delta + 14
            opex = datetime.datetime(year, m, third_friday)
            opex = opex.replace(tzinfo=ZoneInfo(tz))
            if current_date < opex:
                code = month_codes[m]
                break
        else:
            year += 1
            code = month_codes[3]  # marzo siguiente año

    year_code = str(year)[-1]
    symbol = '/' + symbol
    return f"{symbol}{code}{year_code}"



def extract_base_symbol(future_ticker: str) -> str:
    """
    Extrae el símbolo base desde un ticker de futuros (e.g., '/ESU5' → '/ES').

    Detecta automáticamente el símbolo base eliminando el código de mes y año.
    """
    # Tabla de códigos de mes de futuros
    month_codes = {'F', 'G', 'H', 'J', 'K', 'M', 'N', 'Q', 'U', 'V', 'X', 'Z'}

    ticker = future_ticker.strip().upper()

    # Buscar código de mes y año en las últimas posiciones
    if len(ticker) < 3:
        raise ValueError(f"Ticker demasiado corto: {ticker}")

    # Recorrer desde el final hacia atrás para detectar patrón válido
    for i in range(len(ticker) - 2, 0, -1):
        if ticker[i] in month_codes and ticker[i+1].isdigit():
            return ticker[:i]  # Devuelve todo lo anterior al mes

    raise ValueError(f"No se pudo extraer símbolo base de: {ticker}")



