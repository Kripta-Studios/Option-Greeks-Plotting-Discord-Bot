import discord
from discord.ext import commands
from dotenv import load_dotenv
import os
from discord_send_plots import request_plots, set_discord_client

load_dotenv()
DISCORD_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="#", intents=intents)

@bot.event
async def on_ready():
    #print(f"Bot logged in as {bot.user}")
    set_discord_client(bot)

@bot.command()
async def load(ctx, ticker: str, expiration: str, greek: str):
    channel_id = ctx.channel.id  # Aquí obtienes el ID del canal
    channel = bot.get_channel(channel_id)
    ticker = ticker.upper()
    
    #print("Command invoked")
    if expiration.lower() not in ["0dte", "1dte", "weekly", "opex", "monthly", "all"]:
        await ctx.send(f"Invalid expiration: {expiration}. Must be 0dte, 1dte, weekly, opex, monthly, or all.")
        return
    if greek.lower() not in ["delta", "gamma", "vanna", "charm"]:
        await ctx.send(f"Invalid Greek: {greek}. Must be delta, gamma, vanna, or charm.")
        return
    await ctx.send(f"Generating plots for {ticker}/{expiration}/{greek.lower()}...")
    send = await request_plots(specific_ticker=ticker, specific_exp=expiration, specific_greek=greek.lower(), channel_id=channel_id)
    if not send:
        #print(send)
        await ctx.send(f"Failed to send plots for {ticker}/{expiration}/{greek.lower()} sent to {channel}. Retry in a minute.")
    else:
        await ctx.send(f"Plots for {ticker}/{expiration}/{greek.lower()} sent to {channel}")

def run_bot():
    bot.run(DISCORD_TOKEN)
