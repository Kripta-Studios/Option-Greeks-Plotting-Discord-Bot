from threading import Thread
from bot import *
from discord_send_plots import start_scheduler
import asyncio
from data_plotting import get_options_data
import re

# Crear un event loop global para manejar las tareas asíncronas
loop = asyncio.get_event_loop()


async def run_bot_async():
    try:
        await bot.start(DISCORD_TOKEN)
    except Exception as e:
        print(f"Error running Discord bot: {e}")
    finally:
        await bot.close()

async def run_scheduler_async():
    try:
        # Asumiendo que start_scheduler es async; si no, ajustar en consecuencia
        await start_scheduler()
    except Exception as e:
        print(f"Error running scheduler: {e}")

async def keep_alive():
    
    # Ejecutar el bot y el scheduler como tareas asíncronas
    tasks = [
        run_bot_async(),
        run_scheduler_async()
    ]
    await asyncio.gather(*tasks)

if __name__ == "__main__":
    # Crear y configurar el event loop en el hilo principal
    loop = asyncio.get_event_loop()
    try:
        loop.run_until_complete(keep_alive())
    except Exception as e:
        print("Shutting down...", e)