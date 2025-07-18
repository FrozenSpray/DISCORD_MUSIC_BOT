# Importing libraries and modules
import os
import discord
from discord.ext import commands
from discord import app_commands
import yt_dlp # NEW
from collections import deque # NEW
import asyncio # NEW
import urllib.parse as urlparse
import re
from discord.ui import View, Button

cookies_file = "youtube_cookies.txt"

TOKEN = os.environ["TOKEN"]
COOKIES_CONTENT = os.environ["YOUTUBE_COOKIES"]

if COOKIES_CONTENT:
    with open(cookies_file, "w", encoding="utf-8") as f:
        f.write(COOKIES_CONTENT)

GUILD_ID = discord.Object(id=int(os.environ["GUILD_ID"]))

# Create the structure for queueing songs - Dictionary of queues
SONG_QUEUES = {}

async def search_ytdlp_async(query, ydl_opts):
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(None, lambda: _extract(query, ydl_opts))

def _extract(query, ydl_opts):
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        return ydl.extract_info(query, download=False)
    
def extract_youtube_video_id(url: str) -> str | None:
    """
    Extracts the video ID from a YouTube URL (youtube.com or youtu.be).
    Returns None if no ID is found.
    """
    if "youtube.com" in url:
        parsed = urlparse.urlparse(url)
        query = urlparse.parse_qs(parsed.query)
        video_id = query.get("v")
        if video_id:
            return video_id[0]
    elif "youtu.be" in url:
        parsed = urlparse.urlparse(url)
        video_id = parsed.path.lstrip("/")
        if re.match(r"^[\w-]{11}$", video_id):
            return video_id
    return None

def normalize_youtube_url(input_string: str) -> str:
    """
    If the input is a YouTube link, returns a cleaned version.
    Otherwise, returns the input unchanged (assumes it's a search query).
    """
    video_id = extract_youtube_video_id(input_string)
    if video_id:
        return f"https://www.youtube.com/watch?v={video_id}"
    return input_string


# Setup of intents. Intents are permissions the bot has on the server
intents = discord.Intents.default()
intents.message_content = True

# Bot setup
bot = commands.Bot(command_prefix="!", intents=intents)

# Bot ready-up code
@bot.event
async def on_ready():
    try:
        synced = await bot.tree.sync(guild=GUILD_ID)
        print(f"Synced {len(synced)} command(s) for {GUILD_ID.id}")
    except Exception as e:
        print(f"Sync failed: {e}")
    print(f"{bot.user} is online!")


@bot.tree.command(name="skip", description="Skips the current playing song")
async def skip(interaction: discord.Interaction):
    if interaction.guild.voice_client and (interaction.guild.voice_client.is_playing() or interaction.guild.voice_client.is_paused()):
        interaction.guild.voice_client.stop()
        await interaction.response.send_message("Skipped the current song.")
    else:
        await interaction.response.send_message("Not playing anything to skip.")


@bot.tree.command(name="pause", description="Pause the currently playing song.")
async def pause(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client

    # Check if the bot is in a voice channel
    if voice_client is None:
        return await interaction.response.send_message("I'm not in a voice channel.")

    # Check if something is actually playing
    if not voice_client.is_playing():
        return await interaction.response.send_message("Nothing is currently playing.")
    
    # Pause the track
    voice_client.pause()
    await interaction.response.send_message("Playback paused!")


@bot.tree.command(name="resume", description="Resume the currently paused song.")
async def resume(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client

    # Check if the bot is in a voice channel
    if voice_client is None:
        return await interaction.response.send_message("I'm not in a voice channel.")

    # Check if it's actually paused
    if not voice_client.is_paused():
        return await interaction.response.send_message("I’m not paused right now.")
    
    # Resume playback
    voice_client.resume()
    await interaction.response.send_message("Playback resumed!")


@bot.tree.command(name="stop", description="Stop playback and clear the queue.")
async def stop(interaction: discord.Interaction):
    voice_client = interaction.guild.voice_client

    # Check if the bot is in a voice channel
    if not voice_client or not voice_client.is_connected():
        return await interaction.response.send_message("I'm not connected to any voice channel.")

    # Clear the guild's queue
    guild_id_str = str(interaction.guild_id)
    if guild_id_str in SONG_QUEUES:
        SONG_QUEUES[guild_id_str].clear()

    # If something is playing or paused, stop it
    if voice_client.is_playing() or voice_client.is_paused():
        voice_client.stop()

    # (Optional) Disconnect from the channel
    await voice_client.disconnect()

    await interaction.response.send_message("Stopped playback and disconnected!")


@bot.tree.command(name="play", description="Play a song or add it to the queue.", guild=GUILD_ID)
@app_commands.describe(song_query="Search query")
async def play(interaction: discord.Interaction, song_query: str):
    
    if not interaction.user.voice or not interaction.user.voice.channel:
        await interaction.response.send_message("❌ You must be connected to a voice channel to use this command.", ephemeral=True)
        return
    
    await interaction.response.defer()

    voice_channel = interaction.user.voice.channel

    if voice_channel is None:
        await interaction.followup.send("You must be in a voice channel.")
        return

    voice_client = interaction.guild.voice_client

    if voice_client is None:
        voice_client = await voice_channel.connect()
    elif voice_channel != voice_client.channel:
        await voice_client.move_to(voice_channel)

    ydl_options = {
        "format": "bestaudio/best",
        "noplaylist": False,
        "youtube_include_dash_manifest": False,
        "youtube_include_hls_manifest": False,
        "cookiefile": cookies_file
    }

    sanitized_input = normalize_youtube_url(song_query)

    if "youtube.com" in sanitized_input or "youtu.be" in sanitized_input:
        query = sanitized_input  # Clean direct link
    else:
        query = "ytsearch1: " + sanitized_input  # Search query

    results = await search_ytdlp_async(query, ydl_options)

    if 'entries' in results:
        tracks = results['entries']
        if not tracks:
            await interaction.followup.send("No results found.")
            return
        first_track = tracks[0]
    else:
        first_track = results

    audio_url = first_track["url"]
    title = first_track.get("title", "Untitled")

    guild_id = str(interaction.guild_id)
    if SONG_QUEUES.get(guild_id) is None:
        SONG_QUEUES[guild_id] = deque()

    SONG_QUEUES[guild_id].append((audio_url, title))

    if voice_client.is_playing() or voice_client.is_paused():
        await interaction.followup.send(f"Added to queue: **{title}**")
        await show_queue(interaction, SONG_QUEUES[guild_id])
    else:
        await interaction.followup.send(f"Now playing: **{title}**")
        await play_next_song(voice_client, guild_id, interaction.channel)

@bot.tree.command(name="queue", description="Show the current music queue.", guild=GUILD_ID)
async def queue_command(interaction: discord.Interaction):
    guild_id = str(interaction.guild_id)
    queue = SONG_QUEUES.get(guild_id, deque())
    await interaction.response.defer()
    await show_queue(interaction, queue)


async def play_next_song(voice_client, guild_id, channel):
    if SONG_QUEUES[guild_id]:
        audio_url, title = SONG_QUEUES[guild_id].popleft()

        ffmpeg_options = {
            "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
            "options": "-vn -c:a libopus -b:a 96k",
            # Remove executable if FFmpeg is in PATH
        }

        source = discord.FFmpegOpusAudio(audio_url, **ffmpeg_options)

        def after_play(error):
            if error:
                print(f"Error playing {title}: {error}")
            asyncio.run_coroutine_threadsafe(play_next_song(voice_client, guild_id, channel), bot.loop)

        voice_client.play(source, after=after_play)
        asyncio.create_task(channel.send(f"Now playing: **{title}**"))
    else:
        await voice_client.disconnect()
        SONG_QUEUES[guild_id] = deque()


def get_queue_pages(queue: deque, page_size: int = 5):
    pages = []
    queue_list = list(queue)
    for i in range(0, len(queue_list), page_size):
        chunk = queue_list[i:i + page_size]
        formatted = "\n".join(
            f"**{idx + 1}**. {title}" for idx, (_, title) in enumerate(chunk, start=i)
        )
        pages.append(formatted or "*No songs in queue*")
    return pages

def estimate_total_time(queue: deque, avg_song_secs: int = 180):
    total_secs = len(queue) * avg_song_secs
    minutes, seconds = divmod(total_secs, 60)
    return f"{minutes}m {seconds}s"

async def show_queue(interaction, queue: deque):
    if not queue:
        await interaction.followup.send("Queue is empty.")
        return

    pages = get_queue_pages(queue)
    total_songs = len(queue)
    estimated_time = estimate_total_time(queue)

    view = QueuePaginator(pages, total_songs, estimated_time)

    await interaction.followup.send(
        content=view.get_content(),
        view=view
    )

class QueuePaginator(View):
    def __init__(self, pages, total_songs, estimated_time, *, timeout=60):
        super().__init__(timeout=timeout)
        self.pages = pages
        self.total_songs = total_songs
        self.estimated_time = estimated_time
        self.current_page = 0

    def get_content(self):
        queue_info = f"**Queue:** {self.total_songs} songs | ⏳ {self.estimated_time}\n"
        page_content = self.pages[self.current_page]
        return f"{queue_info}\n**Page {self.current_page + 1}/{len(self.pages)}**\n\n{page_content}"

    async def update_message(self, interaction):
        await interaction.response.edit_message(content=self.get_content(), view=self)

    @discord.ui.button(label="◀️ Prev", style=discord.ButtonStyle.secondary)
    async def previous_page(self, interaction, button):
        if self.current_page > 0:
            self.current_page -= 1
            await self.update_message(interaction)

    @discord.ui.button(label="▶️ Next", style=discord.ButtonStyle.secondary)
    async def next_page(self, interaction, button):
        if self.current_page < len(self.pages) - 1:
            self.current_page += 1
            await self.update_message(interaction)

    @discord.ui.button(label="🛑 Stop", style=discord.ButtonStyle.danger)
    async def stop_view(self, interaction, button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(view=self)


# Run the bot
bot.run(TOKEN)