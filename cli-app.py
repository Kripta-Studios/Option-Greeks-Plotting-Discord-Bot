from modules.utils import *
from data_plotting import *
import time
import asyncio

pd.options.display.float_format = "{:,.4f}".format

async def main(ticker, expiration, greek_filter):
    inicio = time.perf_counter()
    if greek_filter != None:
        a = await get_options_data(ticker.upper().replace(" ", ""), expiration.lower().replace(" ", ""), greek_filter.lower().replace(" ", ""))
    else:
        a = await get_options_data(ticker.upper().replace(" ", ""), expiration.lower().replace(" ", ""), greek_filter)
    fin = time.perf_counter()
    print(f"The script lasted {fin - inicio:.4f} seconds.")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Run the script with parameters")
    parser.add_argument("ticker", type=str, help="Ticker symbol (example: SPX, QQQ)")
    parser.add_argument("expiration", type=str, help="Expiration in dte, or weekly, opex, monthly, all")
    parser.add_argument("greek", type=str, nargs='?', default=None, help="Greek to plot: vanna, charm, gamma o delta")

    args = parser.parse_args()
    asyncio.run(main(args.ticker, args.expiration, args.greek))

