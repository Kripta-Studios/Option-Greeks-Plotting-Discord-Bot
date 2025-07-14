import asyncio
import re
from collections import defaultdict
from decimal import Decimal
# Documentation: https://tastyworks-api.readthedocs.io/en/latest/market-data.html
# Documentation: https://pypi.org/project/tastytrade/ 
from tastytrade import Session, DXLinkStreamer
from tastytrade.instruments import NestedOptionChain,NestedFutureOptionChain, get_option_chain
from tastytrade.market_data import get_market_data_by_type
from tastytrade.utils import get_tasty_monthly
from tastytrade.dxfeed import Greeks, Summary
from zoneinfo import ZoneInfo
import time, os, orjson
from typing import TypedDict, List, Tuple
import datetime


def get_future_ticker(symbol: str, current_date: datetime.datetime = None, monthly: bool = None) -> str:
    """
    Devuelve el ticker de futuros siguiente a la fecha actual para el símbolo dado.
    - Detecta automáticamente si el contrato es mensual o trimestral según el símbolo.
    - Acepta símbolos con o sin prefijo "/".
    - Si `monthly` se especifica, sobrescribe la detección automática.
    """
    if current_date is None:
        current_date = datetime.datetime.utcnow()

    symbol = symbol.upper().lstrip("/")  # elimina prefijo "/" si existe

    # Contratos con vencimientos mensuales
    monthly_contracts = {
        'CL', 'QM', 'BZ',      # Petróleo
        'NG', 'QG',            # Gas natural
        'GC', 'HG', 'PL',# Metales
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
        next_month = current_date.month + 1
        year = current_date.year
        if next_month > 12:
            next_month = 1
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



def chunks(lst, n):
    """Divide una lista en bloques de tamaño n."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

class OptionsRequest(TypedDict):
    tickers: List[str]
    start_date: datetime.date
    end_date: datetime.date
    lower_strike: str
    upper_strike: str

async def get_chain_async(session, ticker):
    if '/' in ticker:
        return await asyncio.to_thread(NestedFutureOptionChain.get, session, ticker)

    return await asyncio.to_thread(NestedOptionChain.get, session, ticker)

async def get_market_data_async(session, equities=None, options=None):
    return await asyncio.to_thread(get_market_data_by_type, session, equities=equities, options=options)


async def tasty_expirations_strikes(session, options_ticker : list[str]):
    expiries_chain = defaultdict(set)
    expiries_list = []
    strikes_chain = defaultdict(set)
    strikes_list = []
    chains_list = await asyncio.gather(*[get_chain_async(session, t) for t in options_ticker])
    # Flatten lista de listas
    for i in options_ticker:
        if '/' in i:
            for chain in chains_list:
                for subchain in chain.option_chains:
                    for expiration in subchain.expirations:  # <- NestedFutureOptionChainExpiration
                        for strike in expiration.strikes:
                            ticker = str(strike.call).split()[0]
                            if get_future_ticker(i) in ticker:
                                expiries_chain[i].add(expiration.expiration_date)
                                strikes_chain[ticker].add(float(strike.strike_price))

        else:                            
            chains = [item for sublist in chains_list for item in sublist]

            
            for chain in chains:
                for expiration in chain.expirations:
                    for strike in expiration.strikes:
                        ticker = str(strike.call).split()[0]
                        expiries_chain[ticker].add(expiration.expiration_date)
                        strikes_chain[ticker].add(float(strike.strike_price))
                        

    for ticker, dates in expiries_chain.items():
        dates_list = sorted(dates)
        expiries_list.append({
            ticker: {
                "expirations": dates_list,
                "min_date": min(dates_list),
                "max_date": max(dates_list)
            }
        })
    
    for ticker, strikes in strikes_chain.items():
        strikes_order = sorted(strikes)
        strikes_list.append({
            ticker: {
                "strikes": strikes_order,
                "min_strike": min(strikes_order),
                "max_strike": max(strikes_order)
            }
        })
    
    return expiries_list, strikes_list


async def collect_events(streamer, event_type, symbols, greeks_list, symbol_pairs, timeout=2):
    await streamer.subscribe(event_type, symbols)
    received = set()
    end_time = asyncio.get_event_loop().time() + timeout

    while True:
        remaining = end_time - asyncio.get_event_loop().time()
        if remaining <= 0:
            break
        try:
            event = await asyncio.wait_for(streamer.get_event(event_type), timeout=2)
            received.add(event.event_symbol)

            # Procesar evento: actualizar greeks_list según event_type
            for _, tasty_symbol in symbol_pairs:
                if event.event_symbol == tasty_symbol:
                    for idx, d in enumerate(greeks_list):
                        if d.get("symbol") == tasty_symbol:
                            if event_type == Greeks:
                                d.update({
                                    "delta": str(event.delta),
                                    "gamma": str(event.gamma),
                                    "theta": str(event.theta),
                                    "vega": str(event.vega),
                                    "rho": str(event.rho),
                                    "vol": str(event.volatility),
                                    "price": str(event.price)
                                })
                            elif event_type == Summary:
                                d.update({
                                    "open_interest": str(event.open_interest),
                                })
            
                            break
                    break

        except asyncio.TimeoutError:
            # Timeout para un solo get_event: solo continuar para terminar si timeout global excedido
            continue

    missing = [s for s in symbols if s not in received]
    if missing:
        print(f"Timeout loading {event_type.__name__} events for symbols (not received)")

    return received



async def main_downloader(session, options_requested : OptionsRequest = None, equities_ticker : List[str] = []) -> Tuple[List, List]:

    if (not isinstance(options_requested, dict)) and options_requested != None:
        raise TypeError("""Parameter 'options_requested' must be a dict (TypedDict) with the following string keys : value 
                        tickers: List[str],
                        start_date: datetime.date,
                        end_date: datetime.date,
                        lower_strike: str,
                        upper_strike: str
                        """)

    data = await get_market_data_async(
        session,
        equities=equities_ticker)
    equities_spot = []


    for i in data:
        equities_spot.append({
            "symbol": str(i.symbol),
            "ask" : str(i.ask),
            "ask_size" : str(i.ask_size),
            "bid": str(i.bid),
            "bid_size" : str(i.bid_size),
            "mid": str(i.mid),
            "mark": str(i.mark),
            "last": str(i.last),
            'last_mkt': str(i.last_mkt),
            'open': str(i.open), 
            'prev_close': str(i.prev_close),
            'day_high_price': str(i.day_high_price),
            "day_low_price": str(i.day_low_price),
            "prev_close_date": str(i.prev_close_date),
            "time": i.updated_at.astimezone(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M:%S")
        })

    
    greeks_list = []

    if options_requested is None:
        return greeks_list[::-1], equities_spot[::-1]

    options_ticker = options_requested.get("tickers", [])
    
    start_date = options_requested.get("start_date", datetime.datetime.now())
  

    end_date = options_requested.get("end_date", datetime.datetime.now())


    lower_strike = options_requested.get("lower_strike", "0")
    upper_strike = options_requested.get("upper_strike", "0")

    for i in options_ticker:
        if "/" in i:
            options_ticker = [extract_base_symbol(i)]
    
    # Obtener todas las cadenas de opciones
    chains_list = await asyncio.gather(*[get_chain_async(session, t) for t in options_ticker])

    # Flatten lista de listas
    symbol_pairs = []
    for i in options_ticker:
        if '/' in i:
            for chain in chains_list:
                for subchain in chain.option_chains:
                    for expiration in subchain.expirations:  # <- NestedFutureOptionChainExpiration
                        exp_date = expiration.expiration_date
                        if not (start_date <= exp_date <= end_date):
                            continue
                        
                        for strike in expiration.strikes:
                            strike_price = float(str(strike.strike_price))

                            if float(lower_strike) <= strike_price <= float(upper_strike):
                                if strike.call:
                                    call_entry = {
                                    "expiration": exp_date,
                                    "strike": str(strike.strike_price),
                                    "option": str(strike.call),
                                    "symbol": str(strike.call_streamer_symbol)
                                    }

                                    if call_entry not in greeks_list:
                                        symbol_pairs.append((strike.call, strike.call_streamer_symbol))
                                        greeks_list.append(call_entry)

                                if strike.put:
                                    put_entry = {
                                        "expiration": exp_date,
                                        "strike": str(strike.strike_price),
                                        "option": str(strike.put),
                                        "symbol": str(strike.put_streamer_symbol)
                                    }

                                    if put_entry not in greeks_list:
                                        symbol_pairs.append((strike.put, strike.put_streamer_symbol))
                                        greeks_list.append(put_entry)
            

        else:                            
            chains = [item for sublist in chains_list for item in sublist]
            
            for chain in chains:
                for expiration in chain.expirations:
                    exp_date = expiration.expiration_date
                    if not (start_date <= exp_date <= end_date):
                        continue

                    for strike in expiration.strikes:
                        strike_price = float(str(strike.strike_price))
                        if float(lower_strike) <= strike_price <= float(upper_strike):
                            if strike.call:
                                call_entry = {
                                "expiration": exp_date,
                                "strike": str(strike.strike_price),
                                "option": str(strike.call),
                                "symbol": str(strike.call_streamer_symbol)
                                }

                                if call_entry not in greeks_list:
                                    symbol_pairs.append((strike.call, strike.call_streamer_symbol))
                                    greeks_list.append(call_entry)

                            if strike.put:
                                put_entry = {
                                    "expiration": exp_date,
                                    "strike": str(strike.strike_price),
                                    "option": str(strike.put),
                                    "symbol": str(strike.put_streamer_symbol)
                                }

                                if put_entry not in greeks_list:
                                    symbol_pairs.append((strike.put, strike.put_streamer_symbol))
                                    greeks_list.append(put_entry)
                      
    # Hacer requests en batches de 100
    async def get_data_batch(batch):
        symbols = [s[0] for s in batch]
        return await get_market_data_async(session, options=symbols), batch

    batch_tasks = [get_data_batch(batch) for batch in chunks(symbol_pairs, 100)]
    batch_results = await asyncio.gather(*batch_tasks)

    # Procesar resultados batch
    processed = set()
    for data, batch in batch_results:
        for i in data:
            for symbol, tasty_symbol in batch:
                #print("Symbol:",symbol, "Tasty symbol", tasty_symbol, "i symbol", i.symbol)
                if i.symbol == symbol:
                    if tasty_symbol in processed:
                        break
                    for idx, d in enumerate(greeks_list):
                        if d.get("symbol") == str(tasty_symbol):
                            #print("d.get:", d.get("symbol"), " tasy symbol: ", str(tasty_symbol))

                            ticker = str(symbol).split()[0]
                            greeks_list[idx].update({
                                "ticker": ticker,
                                "ask": str(i.ask),
                                "ask_size": str(i.ask_size),
                                "bid": str(i.bid),
                                "bid_size": str(i.bid_size),
                                "mid": str(i.mid),
                                "last": str(i.last),
                                "time": i.updated_at.astimezone(ZoneInfo("America/New_York")).strftime("%Y-%m-%d %H:%M:%S")
                            })
                            #print(greeks_list[idx])

                            processed.add(tasty_symbol)
                            break
        

        # Podrías guardar la info de market data aquí si la necesitas

    # Obtener griegas con DXLink
    async with DXLinkStreamer(session) as streamer:
        tasty_symbols = [t for (_, t) in symbol_pairs]
        
        await asyncio.gather(
        collect_events(streamer, Greeks, tasty_symbols, greeks_list, symbol_pairs, timeout=2),
        collect_events(streamer, Summary, tasty_symbols, greeks_list, symbol_pairs, timeout=2)
        )

    return greeks_list[::-1], equities_spot[::-1]

async def run_batched_main(
    session,
    options_requested,
    date_chunk_size=100,  # días
    strike_step=100       # puntos
):
    end_date = options_requested["end_date"]
    start_date = options_requested["start_date"]
    delta_days = (end_date - start_date).days
    date_ranges = [
        (
            start_date + datetime.timedelta(days=i),
            min(start_date + datetime.timedelta(days=i + date_chunk_size), end_date)
        )
        for i in range(0, delta_days + 1, date_chunk_size)
    ]

    # Generar todos los pares de strikes
    strike_ranges = []
    lower_strike = float(options_requested["lower_strike"])
    upper_strike = float(options_requested["upper_strike"])
    strike = lower_strike
    while strike < upper_strike:
        next_strike = min(strike + strike_step, upper_strike)
        strike_ranges.append((strike, next_strike))
        strike = next_strike

    greeks_list_total = []

    # Para cada combinación fecha/strike, ejecutar llamadas a main
    for d_start, d_end in date_ranges:
        tasks = []
        for s_low, s_high in strike_ranges:
            for ticker_ in options_requested["tickers"]:
                if '/' in ticker_:
                    options_requested["tickers"] = [get_future_ticker(ticker_)]
            options_requested = {
                "tickers": options_requested["tickers"],
                "start_date": d_start,
                "end_date": d_end,
                "lower_strike": str(s_low),
                "upper_strike": str(s_high),
            }
            tasks.append(main_downloader(session, options_requested=options_requested))

        # Ejecutar en paralelo
        try:

            results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for result in results:
                if isinstance(result, Exception):
                    print(f"[!] Error en una tarea: {result}")
                else:
                    greeks_chunk, _ = result
                    greeks_list_total.extend(greeks_chunk)
        except:
            continue

    return greeks_list_total


async def tasty_data(session, options_requested : OptionsRequest = None, equities_ticker : List[str] = []) -> Tuple[List, List]:
    
    greeks_list, equities_spot = await main_downloader(session, equities_ticker = equities_ticker)

    if options_requested == None:
        return greeks_list, equities_spot        

    
    exp, _ = await tasty_expirations_strikes(session, options_requested["tickers"])

    size = sum(len(e[list(e.keys())[0]]["expirations"]) for e in exp)
    size = round(size * (float(options_requested["upper_strike"]) - float(options_requested["lower_strike"])))
    
    try:
        greeks_list = await (
        run_batched_main(
            session,
            options_requested,
            date_chunk_size=size,
            strike_step=size
        )
    )
    except:
        greeks_list = await (
        run_batched_main(
            session,
            options_requested,
            date_chunk_size=size,
            strike_step=size
        )
    )
        
    return greeks_list, equities_spot



