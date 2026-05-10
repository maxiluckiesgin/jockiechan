import json
import urllib.parse
import urllib.error
import urllib.request

from discord.ext import commands

from musicbot import utils
from config import config


class Music(commands.Cog):
    """ A collection of the commands related to music playback.

        Attributes:
            bot: The instance of the bot that is executing the commands.
    """
    def __init__(self, bot):
        self.bot = bot

    def format_duration(self, duration):
        if duration is None:
            return "Unknown"
        try:
            duration = int(duration)
        except (TypeError, ValueError):
            return str(duration)

        hours = duration // 3600
        minutes = (duration % 3600) // 60
        seconds = duration % 60
        if hours > 0:
            return str(hours) + ":" + str(minutes).zfill(2) + ":" + str(seconds).zfill(2)
        return str(minutes) + ":" + str(seconds).zfill(2)

    def parse_lyrics_query(self, query, songinfo=None):
        if query is not None and not query.isspace():
            query = query.strip()
            if " - " in query:
                artist, title = query.split(" - ", 1)
                return artist.strip(), title.strip(), query
            return None, query, query

        if songinfo is None:
            return None, None, None

        title = songinfo.title
        artist = None
        if title is not None and " - " in title:
            parsed_artist, parsed_title = title.split(" - ", 1)
            artist = parsed_artist.strip()
            title = parsed_title.strip()
        display_query = title
        if artist is not None:
            display_query = str(artist) + " - " + str(title)
        return artist, title, display_query

    def fetch_lyrics(self, artist, title):
        query_params = {"track_name": title}
        if artist is not None:
            query_params["artist_name"] = artist
        url = "https://lrclib.net/api/search?" + urllib.parse.urlencode(query_params)
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "DiscordJockey/1.0",
            },
        )

        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                results = json.loads(response.read().decode("utf-8"))
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
            return None

        for result in results:
            lyrics = result.get("plainLyrics")
            if lyrics:
                return {
                    "artist": result.get("artistName"),
                    "title": result.get("trackName"),
                    "lyrics": lyrics,
                }
        return None

    def split_discord_message(self, text, max_length=1800):
        chunks = []
        current_chunk = ""
        for line in text.splitlines():
            if len(current_chunk) + len(line) + 1 > max_length:
                if current_chunk:
                    chunks.append(current_chunk)
                current_chunk = line
            else:
                if current_chunk:
                    current_chunk += "\n"
                current_chunk += line
        if current_chunk:
            chunks.append(current_chunk)
        return chunks

    def get_current_guild(self, ctx):
        if ctx.guild is not None:
            return ctx.guild
        if ctx.message is not None:
            return utils.get_guild(self.bot, ctx.message)
        return None

    async def ensure_voice_connection(self, ctx, current_guild):
        if current_guild.voice_client is not None:
            utils.guild_to_audiocontroller[current_guild].voice_client = current_guild.voice_client
            return True
        voice_state = getattr(ctx.author, 'voice', None)
        if voice_state is None or voice_state.channel is None:
            await ctx.send("Join a voice channel first.")
            return False
        await utils.guild_to_audiocontroller[current_guild].register_voice_channel(voice_state.channel)
        return True

    @commands.command(name='yt', description=config.HELP_YT_SHORT, help=config.HELP_YT_SHORT)
    async def _play_youtube(self, ctx, *, track: str):
        current_guild = self.get_current_guild(ctx)

        if current_guild is None:
            await utils.send_message(ctx, config.NO_GUILD_MESSAGE)
            return
        if not await self.ensure_voice_connection(ctx, current_guild):
            return
        audiocontroller = utils.guild_to_audiocontroller[current_guild]
        audiocontroller.announce_channel = ctx.channel

        if track.isspace() or not track:
            return
        added = await audiocontroller.add_youtube(track)
        if added:
            await ctx.send("Queued or playing: " + track)
        else:
            await ctx.send("Could not find or play: " + track)

    @commands.command(name='s', aliases=["search"], description=config.HELP_SEARCH_SHORT, help=config.HELP_SEARCH_SHORT)
    async def _search_youtube(self, ctx, *, query: str):
        current_guild = self.get_current_guild(ctx)

        if current_guild is None:
            await utils.send_message(ctx, config.NO_GUILD_MESSAGE)
            return
        if not await self.ensure_voice_connection(ctx, current_guild):
            return

        if query.isspace() or not query:
            await ctx.send("Search query is empty.")
            return

        status_message = await ctx.send("Processing search...")
        audiocontroller = utils.guild_to_audiocontroller[current_guild]
        audiocontroller.announce_channel = ctx.channel
        results = audiocontroller.search_youtube(query, limit=1)
        if not results:
            await status_message.edit(content="No results found for: " + query)
            return

        result = results[0]
        added = await audiocontroller.add_youtube(result['url'])
        if added:
            await status_message.edit(content="Queued or playing: " + result['title'] + " (" + self.format_duration(result.get('duration')) + ")")
        else:
            await status_message.edit(content="Could not play first result for: " + query)

    @commands.command(name='pause', description=config.HELP_PAUSE_SHORT, help=config.HELP_PAUSE_SHORT)
    async def _pause(self, ctx):
        current_guild = self.get_current_guild(ctx)
        if current_guild is None:
            await utils.send_message(ctx, config.NO_GUILD_MESSAGE)
            return
        if current_guild.voice_client is None or not current_guild.voice_client.is_playing():
            await ctx.send("Nothing is playing.")
            return
        current_guild.voice_client.pause()
        await ctx.send("Paused.")

    @commands.command(name='stop', description=config.HELP_STOP_SHORT, help=config.HELP_STOP_SHORT)
    async def _stop(self, ctx):
        current_guild = self.get_current_guild(ctx)
        if current_guild is None:
            await utils.send_message(ctx, config.NO_GUILD_MESSAGE)
            return
        await utils.guild_to_audiocontroller[current_guild].stop_player()
        await ctx.send("Stopped.")

    @commands.command(name='skip', description=config.HELP_SKIP_SHORT, help=config.HELP_SKIP_SHORT)
    async def _skip(self, ctx):
        current_guild = self.get_current_guild(ctx)
        if current_guild is None:
            await utils.send_message(ctx, config.NO_GUILD_MESSAGE)
            return
        if current_guild.voice_client is None or (
                not current_guild.voice_client.is_paused() and not current_guild.voice_client.is_playing()):
            await ctx.send("Nothing is playing.")
            return
        status_message = await ctx.send("Processing skip...")
        utils.guild_to_audiocontroller[current_guild].skip()
        await status_message.edit(content="Skipped.")

    @commands.command(name='loop', description=config.HELP_LOOP_SHORT, help=config.HELP_LOOP_SHORT)
    async def _loop(self, ctx, enabled: bool = None):
        current_guild = self.get_current_guild(ctx)
        if current_guild is None:
            await utils.send_message(ctx, config.NO_GUILD_MESSAGE)
            return

        audiocontroller = utils.guild_to_audiocontroller[current_guild]
        if enabled is None:
            audiocontroller.loop_enabled = not audiocontroller.loop_enabled
        else:
            audiocontroller.loop_enabled = enabled

        if audiocontroller.loop_enabled:
            await ctx.send("Loop enabled.")
        else:
            await ctx.send("Loop disabled.")

    @commands.command(name='autoplay', description=config.HELP_AUTOPLAY_SHORT, help=config.HELP_AUTOPLAY_SHORT)
    async def _autoplay(self, ctx, enabled: bool = None):
        current_guild = self.get_current_guild(ctx)
        if current_guild is None:
            await utils.send_message(ctx, config.NO_GUILD_MESSAGE)
            return

        audiocontroller = utils.guild_to_audiocontroller[current_guild]
        if enabled is None:
            audiocontroller.autoplay_enabled = not audiocontroller.autoplay_enabled
        else:
            audiocontroller.autoplay_enabled = enabled

        if audiocontroller.autoplay_enabled:
            if (audiocontroller.current_autoplay_url is None
                    and audiocontroller.current_extracted_info is not None):
                audiocontroller.current_autoplay_url = audiocontroller.get_autoplay_url(
                    audiocontroller.current_extracted_info
                )
            if audiocontroller.current_autoplay_url is None:
                await ctx.send("Autoplay enabled. Play a song with !search or !yt to start it.")
            else:
                await ctx.send("Autoplay enabled. The next song will start when the current one ends.")
        else:
            await ctx.send("Autoplay disabled.")

    @commands.command(name='remove', description=config.HELP_REMOVE_SHORT, help=config.HELP_REMOVE_SHORT)
    async def _remove(self, ctx, queue_number: int):
        current_guild = self.get_current_guild(ctx)
        if current_guild is None:
            await utils.send_message(ctx, config.NO_GUILD_MESSAGE)
            return

        audiocontroller = utils.guild_to_audiocontroller[current_guild]
        if queue_number < 1 or queue_number > len(audiocontroller.playlist.playque):
            await ctx.send("Queue number not found.")
            return

        if queue_number == 1:
            if current_guild.voice_client is None or (
                    not current_guild.voice_client.is_paused() and not current_guild.voice_client.is_playing()):
                audiocontroller.playlist.remove(0)
                await ctx.send("Removed queue item 1.")
                return
            audiocontroller.skip()
            await ctx.send("Removed and skipped current song.")
            return

        audiocontroller.playlist.remove(queue_number - 1)
        await ctx.send("Removed queue item " + str(queue_number) + ".")

    @commands.command(name='prev', description=config.HELP_PREV_SHORT, help=config.HELP_PREV_SHORT)
    async def _prev(self, ctx):
        current_guild = self.get_current_guild(ctx)
        if current_guild is None:
            await utils.send_message(ctx, config.NO_GUILD_MESSAGE)
            return
        await utils.guild_to_audiocontroller[current_guild].prev_song()
        await ctx.send("Playing previous song.")

    @commands.command(name='resume', description=config.HELP_RESUME_SHORT, help=config.HELP_RESUME_SHORT)
    async def _resume(self, ctx):
        current_guild = self.get_current_guild(ctx)
        if current_guild is None:
            await utils.send_message(ctx, config.NO_GUILD_MESSAGE)
            return
        if current_guild.voice_client is None or not current_guild.voice_client.is_paused():
            await ctx.send("Nothing is paused.")
            return
        current_guild.voice_client.resume()
        await ctx.send("Resumed.")

    @commands.command(name='vol', aliases=["volume"], description=config.HELP_VOL_SHORT, help=config.HELP_VOL_SHORT)
    async def _volume(self, ctx, volume: int):
        current_guild = self.get_current_guild(ctx)
        if current_guild is None:
            await utils.send_message(ctx, config.NO_GUILD_MESSAGE)
            return

        utils.guild_to_audiocontroller[current_guild].volume = volume
        await ctx.send("Volume set to " + str(volume) + "%.")

    @commands.command(name='songinfo', description=config.HELP_SONGINFO_SHORT, help=config.HELP_SONGINFO_SHORT)
    async def _songinfo(self, ctx):
        current_guild = self.get_current_guild(ctx)
        if current_guild is None:
            await utils.send_message(ctx, config.NO_GUILD_MESSAGE)
            return
        songinfo = utils.guild_to_audiocontroller[current_guild].current_songinfo
        if songinfo is None:
            await ctx.send("No song is currently playing.")
            return
        await ctx.author.send(songinfo.output)
        await ctx.send("Sent song info to your DMs.")

    @commands.command(name='lyrics', description=config.HELP_LYRICS_SHORT, help=config.HELP_LYRICS_SHORT)
    async def _lyrics(self, ctx, *, query: str = None):
        current_guild = self.get_current_guild(ctx)
        if current_guild is None:
            await utils.send_message(ctx, config.NO_GUILD_MESSAGE)
            return

        songinfo = None
        if query is None or query.isspace():
            songinfo = utils.guild_to_audiocontroller[current_guild].current_songinfo
            if songinfo is None:
                await ctx.send("No song is currently playing. Try !lyrics artist - title")
                return

        artist, title, display_query = self.parse_lyrics_query(query, songinfo)
        if title is None:
            await ctx.send("No lyrics query found. Try !lyrics artist - title")
            return

        await ctx.send("Searching lyrics for " + display_query + "...")
        result = await asyncio.to_thread(self.fetch_lyrics, artist, title)
        if result is None:
            lyrics_url = "https://www.google.com/search?q=" + urllib.parse.quote(display_query + " lyrics")
            await ctx.send("Could not find lyrics. Search link:\n" + lyrics_url)
            return

        header = "Lyrics for " + result["artist"] + " - " + result["title"]
        await ctx.send(header)
        for chunk in self.split_discord_message(result["lyrics"]):
            await ctx.send("```" + chunk.replace("```", "'''") + "```")

    @commands.command(name='history', description=config.HELP_HISTORY_SHORT, help=config.HELP_HISTORY_SHORT)
    async def _history(self, ctx):
        current_guild = self.get_current_guild(ctx)
        if current_guild is None:
            await utils.send_message(ctx, config.NO_GUILD_MESSAGE)
            return
        await utils.send_message(ctx,utils.guild_to_audiocontroller[current_guild].track_history())

async def setup(bot):
    await bot.add_cog(Music(bot))
