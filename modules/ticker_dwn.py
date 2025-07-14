import requests
import base64
import orjson
from multiprocessing.dummy import Pool as ThreadPool
from datetime import datetime
from os import environ, getcwd
from pathlib import Path
from functools import partial


def fulfill_req(ticker, session):
    #print(ticker)
    api_url = (
        environ.get("API_URL")
        or f"https://cdn.cboe.com/api/global/delayed_quotes/options/{ticker.upper()}.json"
    ).strip()
    ticker = ticker.upper() if ticker[0] != "_" else ticker[1:].upper()
    d_format = "json"
    filename = (
        Path(f"{getcwd()}/data/json/{ticker}_quotedata.json")
    )
    Path(filename).parent.mkdir(parents=True, exist_ok=True)
    with open(filename, "wb") as f, session.get(api_url) as r:
        for _ in range(3):  # in case of unavailable data, retry twice
            try:  # check if data is available
                r.raise_for_status()
            except requests.exceptions.HTTPError as e:
                print(e)
                f.write("Unavailable".encode("utf-8"))
                if r.status_code == 504:  # check if timeout occurred
                    print("gateway timeout, retrying search for", ticker, d_format)
                    continue
                elif r.status_code == 500:  # internal server error
                    print(
                        "internal server error, retrying search for", ticker, d_format
                    )
                    continue
            else:
                # incoming json data
                f.write(orjson.dumps(r.json()))
                #print("\nrequest done for", ticker, d_format)
                break


def dwn_data(select):
    pool = ThreadPool()
    tickers_pool = (environ.get("TICKERS") or "^SPX,^NDX,^RUT").strip().split(",")
    #print(select)
    if select:  # select tickers to download
        tickers_pool = [f"^{t}" if f"^{t}" in tickers_pool else t for t in select]
    tickers_format = [
        f"_{ticker[1:]}" if ticker[0] == "^" else ticker for ticker in tickers_pool
    ]
    #print(tickers_format)
    session = requests.Session()
    session.headers.update({"Accept": "application/json"})
    fulfill_req_with_args = partial(fulfill_req, session=session)
    pool.map(fulfill_req_with_args, tickers_format)
    pool.close()
    pool.join()


if __name__ == "__main__":
    dwn_data(select=None)
