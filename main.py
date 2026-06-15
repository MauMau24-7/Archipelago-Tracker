import discord
from discord.ext import commands
import logging
from dotenv import load_dotenv
import os
import websockets
import asyncio
import json


load_dotenv()
token = os.getenv('DISCORD_TOKEN')

handler = logging.FileHandler(filename='discord.log', encoding='utf-8', mode='w')
intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix='!', intents=intents)
tasks = {}


async def ap_listener(port, channel):
    uri = f"wss://archipelago.gg:{port}"
    while True:
        try:
            async with websockets.connect(uri) as ws:

                room_info = json.loads(await ws.recv())[0]
                games = [g for g in room_info["games"] if g != "Archipelago"]

                connect_packet = json.dumps([{
                    "cmd": "Connect",
                    "game": "",
                    "name": "TheSillyBlaze",
                    "password": "",
                    "version": {"major": 0, "minor": 6, "build": 7, "class": "Version"},
                    "items_handling": 0,
                    "tags": ["TextOnly", "Tracker"],
                    "uuid": "discord-bot-001"
                }])
                await ws.send(connect_packet)

                players = {}
                slot_games = {}
                item_names = {}
                location_names = {}

                packets = json.loads(await ws.recv())
                for packet in packets:
                    if packet["cmd"] == "Connected":
                        for player in packet["players"]:
                            players[player["slot"]] = player["name"]
                        for slot, info in packet["slot_info"].items():
                            slot_games[int(slot)] = info["game"]

                await ws.send(json.dumps([{"cmd": "GetDataPackage", "games": games}]))
                while True:
                    raw = json.loads(await ws.recv())
                    for packet in raw:
                        if packet["cmd"] == "DataPackage":
                            for game, gdata in packet["data"]["games"].items():
                                for name, id in gdata["item_name_to_id"].items():
                                    item_names[(game, id)] = name
                                for name, id in gdata["location_name_to_id"].items():
                                    location_names[(game, id)] = name
                            break
                    else:
                        continue
                    break

                async for message in ws:
                    packets = json.loads(message)
                    for packet in packets:
                        if packet["cmd"] == "PrintJSON" and packet.get("type") == "ItemSend":
                            text = ""
                            for segment in packet["data"]:
                                t = segment.get("type")
                                if t == "player_id":
                                    text += players.get(int(segment["text"]), segment["text"])
                                elif t == "item_id":
                                    game = slot_games.get(packet["receiving"])
                                    text += item_names.get((game, int(segment["text"])), segment["text"])
                                elif t == "location_id":
                                    game = slot_games.get(segment["player"])
                                    text += location_names.get((game, int(segment["text"])), segment["text"])
                                else:
                                    text += segment["text"]
                            await channel.send(text)
        except asyncio.CancelledError:
            break
        except websockets.ConnectionClosed:
            await channel.send("Connection lost, reconnecting in 5 seconds...")
            await asyncio.sleep(5)
        except Exception as e:
            await channel.send(f"Error: {e}, reconnecting in 5 seconds...")
            await asyncio.sleep(5)


@bot.event
async def on_ready():
    print(f"{bot.user.name} started successfully")


@bot.command()
async def start(ctx, *, port):
    print(tasks)
    if ctx.channel.name != "archipelago-tracking":
        await ctx.send("This Command ist only allowed in <#1515806957615714457>!")
        return
    if ctx.channel.id in tasks and not tasks[ctx.channel.id].done():
        await ctx.send("A Tracker is already active in this Channel!")
        return
    await ctx.send(f"Connecting to Archipelago server at `wss://archipelago.gg:{port}`")
    task = asyncio.create_task(ap_listener(port, ctx.channel))
    tasks[ctx.channel.id] = task


@bot.command()
async def stop(ctx):
    if ctx.channel.name != "archipelago-tracking":
        await ctx.send("This Command ist only allowed in <#1515806957615714457>!")
        return
    task = tasks.pop(ctx.channel.id, None)
    if task:
        task.cancel()
        await ctx.send("Disconnected.")
    else:
        await ctx.send("No active Tracker in this Channel.")


@bot.command()
async def commands(ctx):
    await ctx.send("Here's a list of commands: <#1516068302776959149>")

bot.run(token, log_handler=handler, log_level=logging.DEBUG)
