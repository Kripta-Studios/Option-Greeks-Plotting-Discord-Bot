from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from os import environ, makedirs
import os
import shutil
from dotenv import load_dotenv
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from data_plotting import get_options_data
from cachetools import TTLCache
import discord
import asyncio

# Load environment variables
load_dotenv()

# Configuration
TICKERS = ["SPX", "Ticker"]  # Yahoo Finance format
#EXPIRATIONS = ["0dte", "1dte", "weekly", "opex", "monthly", "all"]
EXPIRATIONS = ["0dte", "1dte", "weekly"]
GREEKS = ["delta", "gamma", "vanna", "charm"]
VISUALIZATIONS = {
    "delta": ["Absolute Delta Exposure", "Delta Exposure By Calls/Puts", "Delta Exposure Profile"],
    "gamma": ["Absolute Gamma Exposure", "Gamma Exposure By Calls/Puts", "Gamma Exposure Profile"],
    "vanna": ["Absolute Vanna Exposure", "Implied Volatility Average", "Vanna Exposure Profile"],
    "charm": ["Absolute Charm Exposure", "Charm Exposure Profile"],
}
PLOT_DIR = "plots"
TZ = "America/New_York"  # EST timezone
DISCORD_CHANNEL_IDS = {
    "SPX/0dte/delta": 1387377585427841094,  # Replace with actual channel IDs
    "SPX/0dte/gamma": 1387376148950028288,
    "SPX/0dte/vanna": 1387376757413515344,
    "SPX/0dte/charm": 1387377438589194270,
    "SPX/1dte/delta": 1387377603031207976,
    "SPX/1dte/gamma": 1387376325399941231,
    "SPX/1dte/vanna": 1387376810559275158,
    "SPX/1dte/charm": 1387377460810744019,
    "SPX/opex/delta": 1387377627505102909,
    "SPX/opex/gamma": 1387376441389486131,
    "SPX/opex/vanna": 1387376838757711913,
    "SPX/opex/charm": 1387377489562828952,
    "SPX/monthly/delta": 1387377650565382234,
    "SPX/monthly/gamma": 1387376549967167569,
    "SPX/monthly/vanna": 1387376930101395528,
    "SPX/monthly/charm": 1387377520105619627,
    "SPX/all/delta": 1387377665589116938,
    "SPX/all/gamma": 1387376590912229396,
    "SPX/all/vanna": 1387376953237180537,
    "SPX/all/charm": 1387377535570018404,
    "SPX/weekly/delta": 1393732731413987434,
    "SPX/weekly/gamma": 1393732774296420352,
    "SPX/weekly/vanna": 1393732835923198033,
    "SPX/weekly/charm": 1393732884933906512,
    "Ticker/0dte/delta": 1387378772805947492,
    "Ticker/0dte/gamma": 1387377700465016862,
    "Ticker/0dte/vanna": 1387378541284425828,
    "Ticker/0dte/charm": 1387378654039904417,
    "Ticker/1dte/delta": 1387378789184442378,
    "Ticker/1dte/gamma": 1387378422325448795,
    "Ticker/1dte/vanna": 1387378559214948393,
    "Ticker/1dte/charm": 1387378677075021856,
    "Ticker/opex/delta": 1387378811393282208,
    "Ticker/opex/gamma": 1387378439182352476,
    "Ticker/opex/vanna": 1387378578173198366,
    "Ticker/opex/charm": 1387378698826682409,
    "Ticker/monthly/delta": 1387378837318275132,
    "Ticker/monthly/gamma": 1387378471835144292,
    "Ticker/monthly/vanna": 1387378607344848977,
    "Ticker/monthly/charm": 1387378733371097128,
    "Ticker/all/delta": 1387378868247203901,
    "Ticker/all/gamma": 1387378499417014392,
    "Ticker/all/vanna": 1387378622293344356,
    "Ticker/all/charm": 1387378750827794644,
}

# Initialize cache
cache = TTLCache(maxsize=150, ttl=60 * 15)  # 15-minute cache

# Check and clean plot directory on first run
try:
    shutil.rmtree(PLOT_DIR)
except:
    pass

makedirs(PLOT_DIR, exist_ok=True)

# Discord client (passed from bot.py)
discord_client = None

def set_discord_client(client):
    global discord_client
    discord_client = client
    print(f"Discord client set: {client}")

async def send_plot_to_discord(filenames, ticker, exp, greek, channel_id):
    if discord_client is None:
        print("Discord client not initialized")
        return
    if channel_id == None:
        if (ticker == "SPX") and (exp in EXPIRATIONS):
            channel_key = f"{ticker}/{exp}/{greek}"
            channel_id = DISCORD_CHANNEL_IDS.get(channel_key)
        elif ticker == "SPX":
            channel_key = f"SPX/0dte/{greek}"
            channel_id = DISCORD_CHANNEL_IDS.get(channel_key)
        elif (ticker != "SPX") and (exp in EXPIRATIONS):
            channel_key = f"Ticker/{exp}/{greek}"
            channel_id = DISCORD_CHANNEL_IDS.get(channel_key)
        else:
            channel_key = f"Ticker/0dte/{greek}"
            channel_id = DISCORD_CHANNEL_IDS.get(channel_key)

    channel = discord_client.get_channel(channel_id)
    channel_key = channel
    #print("Channel:", channel)
    if not channel:
        print(f"Channel ID {channel_id} on {channel_key} not found")
        return
    # Check if the file exists before attempting to send
    for i in filenames:
        for j in i:
            if not os.path.exists(j):
                print(f"File not found: {j}")
                message = f"{ticker}/{exp}/{greek} failed to download. Retry in a minute"
                await channel.send(message)
                return
    
    try:

        message = f"{ticker}/{exp}/{greek} at {datetime.now(ZoneInfo("America/New_York")).ctime()} EST"
        await channel.send(message)
        message = "Render Webservice"
        await channel.send(message)
        #print(f"Sent message: {message} to Discord channel {channel_key}")
        # Let discord.File handle the file opening
        files = []
        for i in filenames:
            tmp = []
            for j in i:
                if greek in j:
                    tmp.append(discord.File(j))
            files.append(tmp)
        for i in files:
            await channel.send(files=i)
            print(f"Sent {i} to Discord channel {channel_key}")
    except Exception as e:
        print(f"Failed to send {filenames} to {channel_key}: {type(e).__name__} - {e}")

def cleanup_directory():
    shutil.rmtree(PLOT_DIR)


async def request_plots(specific_ticker=None, specific_exp=None, specific_greek=None, channel_id = None):
    #print("###################3 Comienza la ejecución E#######################")
    try:
        if not specific_ticker:
            specific_ticker = "SPX"

        expirations = [specific_exp] if specific_exp else EXPIRATIONS

        if specific_greek == None:
            specific_greek = [None]

        if not isinstance(specific_greek, list):
            specific_greek = [specific_greek]

        #print("Requested:", specific_ticker, specific_exp, specific_greek, channel_id)
        for exp in expirations:
            for greek in specific_greek:
                #print("Requesting the filenames")
                filenames = await get_options_data(specific_ticker, exp, greek)
                #print("Filename got in discord_send_plots.py")
                files_per_greek = []
                if greek == None:
                    for loop_greek in GREEKS:
                        for i in filenames:
                            tmp = []
                            for j in i:
                                if loop_greek in j:
                                    tmp.append(j)
                            files_per_greek.append(tmp)
                        #print("Send send_plot_to_discord")
                        await send_plot_to_discord(filenames, specific_ticker, exp, loop_greek, channel_id)
                else:
                    await send_plot_to_discord(filenames, specific_ticker, exp, greek, channel_id)

        return True
    
    except Exception as e:
        print("ERROR loading request_plots", "specific_ticker", specific_ticker, "specific_exp", specific_exp, "specific_greek", specific_greek)
        print("Error: ", e)
        return False

        

async def start_scheduler():
    #print("Cleanup dir")
    cleanup_directory()
    sched = BackgroundScheduler(daemon=True)
    sched.add_job(
        lambda: asyncio.run_coroutine_threadsafe(request_plots(), discord_client.loop).result(),
        CronTrigger.from_crontab(
            "0,1,2,3,4,5,6,7,8,9,10,11,12,13,14,15,16,17,18,19,20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,35,36,37,38,39,40,41,42,43,44,45,46,47,48,49,50,51,52,53,54,55,56,57,58,59 7-18 * * 0-4",
            timezone=ZoneInfo("America/New_York")
        ),max_instances=3
    )
    sched.start()
    
