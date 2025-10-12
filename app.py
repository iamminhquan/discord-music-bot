"""
Discord Music Bot (Python)

Commands:
!join, !leave, !play <url>, !skip, !stop, !pause, !resume, !queue, !volume <0-100>, !volup, !voldown
"""

import asyncio
import os
from dataclasses import dataclass
from typing import Optional, Dict

import discord
from discord.ext import commands
from dotenv import load_dotenv
import yt_dlp

load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
PREFIX = os.getenv("PREFIX", "!")

intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix=PREFIX, intents=intents, help_command=None)


BLOCKED_USERS = [1189920410792382524]


@dataclass
class GuildMusic:
    voice_client: Optional[discord.VoiceClient]
    queue: asyncio.Queue
    player_task: Optional[asyncio.Task]
    volume: float = 0.6


music_map: Dict[int, GuildMusic] = {}

ytdl = yt_dlp.YoutubeDL({"format": "bestaudio/best", "noplaylist": True, "quiet": True})


async def ensure_guild(ctx: commands.Context) -> GuildMusic:
    g = music_map.get(ctx.guild.id)
    if g is None:
        g = GuildMusic(voice_client=None, queue=asyncio.Queue(), player_task=None)
        music_map[ctx.guild.id] = g
    return g


async def audio_player_task(guild_id: int):
    g = music_map.get(guild_id)
    if not g or not g.voice_client:
        return

    while True:
        try:
            item = await g.queue.get()
        except asyncio.CancelledError:
            break

        if item is None:
            break

        url, title = item
        info = ytdl.extract_info(url, download=False)
        if "entries" in info:
            info = info["entries"][0]

        audio_url = info.get("url") or info.get("webpage_url")
        source = discord.FFmpegPCMAudio(audio_url, options="-vn")
        player = discord.PCMVolumeTransformer(source, volume=g.volume)

        finished = asyncio.Event()

        def after_play(err):
            if err:
                print("Player error:", err)
            bot.loop.call_soon_threadsafe(finished.set)

        g.voice_client.play(player, after=after_play)
        await finished.wait()

    if g.voice_client and g.voice_client.is_connected():
        await g.voice_client.disconnect()


@bot.event
async def on_ready():
    print(f"Logged in as {bot.user}")


@bot.command()
async def join(ctx):
    if not ctx.author.voice:
        return await ctx.send("Vào voice channel trước đã bro 😎")
    channel = ctx.author.voice.channel
    g = await ensure_guild(ctx)
    if not g.voice_client or not g.voice_client.is_connected():
        g.voice_client = await channel.connect()
        await ctx.send(f"Đã vô kênh **{channel.name}** 🎧")


@bot.command()
async def play(ctx, *, url: str):
    g = await ensure_guild(ctx)
    if not g.voice_client or not g.voice_client.is_connected():
        await join(ctx)
    info = ytdl.extract_info(url, download=False)
    if "entries" in info:
        info = info["entries"][0]
    title = info.get("title", "Không rõ tên bài")
    await g.queue.put((url, title))
    await ctx.send(f"Đã thêm **{title}** vào hàng chờ 🎵")
    if not g.player_task or g.player_task.done():
        g.player_task = bot.loop.create_task(audio_player_task(ctx.guild.id))


@bot.command()
async def skip(ctx):
    g = music_map.get(ctx.guild.id)
    if not g or not g.voice_client or not g.voice_client.is_playing():
        return await ctx.send("Không có bài nào để skip 😅")
    g.voice_client.stop()
    await ctx.send("⏭️ Qua bài mới rồi nè!")


@bot.command()
async def stop(ctx):
    g = music_map.get(ctx.guild.id)
    if not g:
        return await ctx.send("Chưa có gì để dừng hết 😅")
    while not g.queue.empty():
        g.queue.get_nowait()
    if g.voice_client and g.voice_client.is_playing():
        g.voice_client.stop()
    await ctx.send("🛑 Dừng phát và xoá hàng chờ!")


@bot.command()
async def pause(ctx):
    g = music_map.get(ctx.guild.id)
    if g and g.voice_client and g.voice_client.is_playing():
        g.voice_client.pause()
        await ctx.send("⏸️ Dừng tạm thời bài hát.")


@bot.command()
async def resume(ctx):
    g = music_map.get(ctx.guild.id)
    if g and g.voice_client and g.voice_client.is_paused():
        g.voice_client.resume()
        await ctx.send("▶️ Tiếp tục phát nhạc.")


@bot.command()
async def volume(ctx, vol: int):
    g = music_map.get(ctx.guild.id)
    if not g or not g.voice_client:
        return await ctx.send("Chưa phát gì đâu 😅")
    vol = max(0, min(100, vol))
    g.volume = vol / 100
    if g.voice_client.source and isinstance(
        g.voice_client.source, discord.PCMVolumeTransformer
    ):
        g.voice_client.source.volume = g.volume
    await ctx.send(f"🔊 Đặt âm lượng: **{vol}%**")


@bot.command()
async def volup(ctx):
    g = music_map.get(ctx.guild.id)
    if not g:
        return await ctx.send("Chưa có nhạc phát mà 😅")
    g.volume = min(1.0, g.volume + 0.1)
    if g.voice_client.source and isinstance(
        g.voice_client.source, discord.PCMVolumeTransformer
    ):
        g.voice_client.source.volume = g.volume
    await ctx.send(f"🔼 Âm lượng: **{int(g.volume * 100)}%**")


@bot.command()
async def voldown(ctx):
    g = music_map.get(ctx.guild.id)
    if not g:
        return await ctx.send("There is no song")
    g.volume = max(0.0, g.volume - 0.1)
    if g.voice_client.source and isinstance(
        g.voice_client.source, discord.PCMVolumeTransformer
    ):
        g.voice_client.source.volume = g.volume
    await ctx.send(f"🔽 Âm lượng: **{int(g.volume * 100)}%**")


@bot.check
async def block_specific_users(ctx):
    if ctx.author.id in BLOCKED_USERS:
        await ctx.send(f"Nè {ctx.author.mention}, anh Ngôn Tình không được xài nhạc :D")
        return False
    return True


bot.run(TOKEN)
