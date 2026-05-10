import traceback
import asyncio
import os
import urllib.parse
import re
from collections import deque
from string import printable

import discord
import yt_dlp

from config import config
from musicbot.playlist import Playlist
from musicbot.songinfo import Songinfo


YTDLP_COOKIES_FILE = os.environ.get("YTDLP_COOKIES_FILE")


def build_ytdlp_options(options):
    options = dict(options)
    if YTDLP_COOKIES_FILE:
        options['cookiefile'] = YTDLP_COOKIES_FILE
    return options


YTDLP_OPTIONS = {
    'format': 'bestaudio/best',
    'noplaylist': True,
    'quiet': True,
    'no_warnings': True,
    'extractor_args': {
        'youtube': {
            'player_client': ['default', 'ios'],
        },
    },
}

YTDLP_PLAYLIST_OPTIONS = {
    'extract_flat': True,
    'ignoreerrors': True,
    'quiet': True,
    'no_warnings': True,
}

YTDLP_SEARCH_OPTIONS = {
    'extract_flat': True,
    'ignoreerrors': True,
    'quiet': True,
    'no_warnings': True,
}

FFMPEG_BEFORE_OPTIONS = (
    '-reconnect 1 '
    '-reconnect_streamed 1 '
    '-reconnect_delay_max 5 '
    '-reconnect_on_network_error 1 '
    '-reconnect_on_http_error 4xx,5xx'
)


def playing_string(title):
    """Formats the name of the current song to better fit the nickname format."""
    if title is None:
        return config.DEFAULT_NICKNAME
    short_title = "".join(character for character in title if character in printable).strip()
    short_title = short_title.replace("(", "").replace(")", "")
    return short_title[:32] or config.DEFAULT_NICKNAME


class AudioController(object):
    """ Controls the playback of audio and the sequential playing of the songs.

            Attributes:
                bot: The instance of the bot that will be playing the music.
                _volume: the volume of the music being played.
                playlist: A Playlist object that stores the history and queue of songs.
                current_songinfo: A Songinfo object that stores details of the current song.
                guild: The guild in which the Audiocontroller operates.
        """

    def __init__(self, bot, guild, volume):
        self.bot = bot
        self._volume = volume
        self.playlist = Playlist()
        self.current_songinfo = None
        self.guild = guild
        self.voice_client = None
        self.idle_disconnect_task = None
        self.loop_enabled = False
        self.autoplay_enabled = False
        self.skip_requested = False
        self.current_track_url = None
        self.current_autoplay_url = None
        self.current_extracted_info = None
        self.announce_channel = None
        self.recent_video_ids = deque(maxlen=25)
        self.recent_titles = deque(maxlen=25)

    @property
    def volume(self):
        return self._volume

    @volume.setter
    def volume(self, value):
        self._volume = value
        try:
            self.voice_client.source.volume = float(value) / 100.0
        except Exception as e:
            print(e)
        
    async def register_voice_channel(self, channel):
        self.cancel_idle_disconnect()
        self.voice_client = await channel.connect()
        self.schedule_idle_disconnect()

    def cancel_idle_disconnect(self):
        current_task = asyncio.current_task()
        if (self.idle_disconnect_task is not None
                and not self.idle_disconnect_task.done()
                and self.idle_disconnect_task is not current_task):
            self.idle_disconnect_task.cancel()
        self.idle_disconnect_task = None

    def schedule_idle_disconnect(self):
        self.cancel_idle_disconnect()
        if self.guild.voice_client is not None:
            self.idle_disconnect_task = self.bot.loop.create_task(self.disconnect_after_idle())

    async def disconnect_after_idle(self):
        try:
            await asyncio.sleep(config.IDLE_DISCONNECT_SECONDS)
            voice_client = self.guild.voice_client
            if voice_client is None or voice_client.is_playing() or voice_client.is_paused():
                return
            await self.disconnect()
            print("Disconnected from", self.guild.name, "after idle timeout.")
        except asyncio.CancelledError:
            return

    async def disconnect(self):
        self.cancel_idle_disconnect()
        voice_client = self.guild.voice_client
        self.voice_client = voice_client
        if voice_client is None:
            return False
        if voice_client.is_playing() or voice_client.is_paused():
            self.skip_requested = True
            voice_client.stop()
        self.playlist.playque.clear()
        self.current_songinfo = None
        self.current_track_url = None
        self.current_autoplay_url = None
        self.current_extracted_info = None
        await voice_client.disconnect()
        self.voice_client = None
        await self.guild.me.edit(nick=config.DEFAULT_NICKNAME)
        return True
            
        

    def track_history(self):
        history_string = config.INFO_HISTORY_TITLE
        for trackname in self.playlist.trackname_history:
            history_string += "\n" + trackname
        return history_string

    def next_song(self, error):
        """Invoked after a song is finished. Plays the next song if there is one, resets the nickname otherwise"""

        self.current_songinfo = None
        if self.loop_enabled and not self.skip_requested and self.current_track_url is not None:
            self.bot.loop.create_task(self.play_youtube(self.current_track_url))
            return

        self.skip_requested = False
        if len(self.playlist.playque) == 0:
            async def finish_empty_queue():
                await self.guild.me.edit(nick=config.DEFAULT_NICKNAME)
                self.schedule_idle_disconnect()
            self.bot.loop.create_task(finish_empty_queue())
            return

        next_song = self.playlist.next()

        if next_song is None:
            if self.autoplay_enabled and self.current_autoplay_url is not None:
                autoplay_url = self.current_autoplay_url
                self.current_autoplay_url = None
                coro = self.add_song(autoplay_url)
            else:
                async def finish_playback():
                    await self.guild.me.edit(nick=config.DEFAULT_NICKNAME)
                    self.schedule_idle_disconnect()
                coro = finish_playback()

            self.bot.loop.create_task(coro)
            return

        self.bot.loop.create_task(self.play_youtube(next_song))

    def skip(self):
        self.skip_requested = True
        if self.guild.voice_client is not None:
            self.guild.voice_client.stop()

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

    async def announce_current_song(self, extracted_info):
        if self.announce_channel is None:
            return
        await self.announce_channel.send(
            "```Now playing:\n"
            "Uploader: " + str(extracted_info.get('uploader')) + "\n"
            "Creator: " + str(extracted_info.get('creator')) + "\n"
            "Title: " + str(extracted_info.get('title')) + "\n"
            "Duration: " + self.format_duration(extracted_info.get('duration')) + "\n```"
        )

    async def add_youtube(self, link):
        """Processes a youtube link and passes elements of a playlist to the add_song function one by one"""

        # Pass it on if it is not a playlist
        if "list=" not in link:
            return await self.add_song(link)

        try:
            with yt_dlp.YoutubeDL(build_ytdlp_options(YTDLP_PLAYLIST_OPTIONS)) as downloader:
                playlist_info = downloader.extract_info(link, download=False)
        except Exception as error:
            print("Could not extract playlist from:", link)
            traceback.print_exception(type(error), error, error.__traceback__)
            return False

        entries = (playlist_info or {}).get('entries') or []
        if not entries:
            return await self.add_song(link)

        added = False
        for entry in entries:
            if entry is None:
                continue
            video_url = self.get_entry_url(entry)
            if video_url is None:
                continue
            added = await self.add_song(video_url) or added
        return added

    async def add_song(self, track):
        """Adds the track to the playlist instance and plays it, if it is the first song"""

        # If the track is a video title, get the corresponding video link first
        if track.startswith(("http://", "https://")):
            link = track
        else:
            link = self.convert_to_youtube_link(track)
            if link is None:
                return False
        self.playlist.add(link)
        if len(self.playlist.playque) == 1:
            return await self.play_youtube(link)
        return True

    def convert_to_youtube_link(self, title):
        """Searches youtube for the video title and returns the first results video link"""

        results = self.search_youtube(title, limit=1)
        if results:
            return results[0]['url']
        return None

    def search_youtube(self, query, limit=5, autoplay=False, preferred_artist=None):
        """Searches YouTube and returns a list of result dictionaries."""

        search_limit = max(limit, 15)
        try:
            with yt_dlp.YoutubeDL(build_ytdlp_options(YTDLP_SEARCH_OPTIONS)) as downloader:
                search_info = downloader.extract_info("ytsearch" + str(search_limit) + ":" + query, download=False)
        except Exception as error:
            print("Could not search youtube for:", query)
            traceback.print_exception(type(error), error, error.__traceback__)
            return []

        results = []
        entries = (search_info or {}).get('entries') or []
        for entry in entries:
            if entry is None:
                continue
            url = self.get_entry_url(entry)
            if url is None:
                continue

            duration = entry.get('duration')
            if self.is_too_long(duration):
                continue
            if not self.is_music_category(entry):
                continue

            result = {
                'id': entry.get('id'),
                'title': entry.get('title') or 'Untitled',
                'url': url,
                'duration': duration,
                'uploader': entry.get('uploader') or entry.get('channel'),
                'categories': entry.get('categories'),
            }
            result['score'] = self.get_search_result_score(
                query,
                result,
                autoplay=autoplay,
                preferred_artist=preferred_artist,
            )
            results.append(result)
        results.sort(key=lambda result: result['score'], reverse=True)
        return results[:limit]

    def is_too_long(self, duration):
        if duration is None:
            return False
        try:
            return int(duration) > 10 * 60
        except (TypeError, ValueError):
            return False

    def is_music_category(self, entry):
        categories = entry.get('categories')
        if not categories:
            return True
        normalized_categories = [str(category).lower() for category in categories]
        return any(category == 'music' for category in normalized_categories)

    def get_query_artist(self, query):
        if " - " in query:
            return query.split(" - ", 1)[0].strip()
        return query.strip()

    def get_search_result_score(self, query, result, autoplay=False, preferred_artist=None):
        score = 0
        query_text = self.normalize_title(query)
        artist = preferred_artist if autoplay and preferred_artist else self.get_query_artist(query)
        artist_text = self.normalize_title(artist)
        title_text = self.normalize_title(result.get('title'))
        uploader_text = self.normalize_title(result.get('uploader'))

        if result.get('categories'):
            score += 20 if autoplay else 10
        if "official" in title_text:
            score += 40 if autoplay else 50
        if "music video" in title_text or "official video" in title_text:
            score += 25 if autoplay else 30
        if artist_text and (artist_text == uploader_text or artist_text in uploader_text or uploader_text in artist_text):
            score += 60 if autoplay else 45
        if not autoplay and query_text and query_text in title_text:
            score += 20
        if "lyrics" in title_text:
            score -= 20 if autoplay else 25
        if "cover" in title_text or "reaction" in title_text or "karaoke" in title_text:
            score -= 35 if autoplay else 25
        if autoplay and ("live" in title_text or "concert" in title_text):
            score -= 10
        return score

    def get_entry_url(self, entry):
        if entry.get('webpage_url'):
            return entry['webpage_url']
        if entry.get('original_url'):
            return entry['original_url']
        if entry.get('url'):
            if entry['url'].startswith(("http://", "https://")):
                return entry['url']
            return "https://www.youtube.com/watch?v=" + entry['url']
        if entry.get('id'):
            return "https://www.youtube.com/watch?v=" + entry['id']
        return None

    def get_youtube_id_from_url(self, url):
        parsed_url = urllib.parse.urlparse(url)
        hostname = parsed_url.hostname or ""
        if hostname.endswith("youtu.be"):
            return parsed_url.path.lstrip("/") or None
        if "youtube.com" in hostname:
            query = urllib.parse.parse_qs(parsed_url.query)
            video_ids = query.get("v")
            if video_ids:
                return video_ids[0]
            if parsed_url.path.startswith("/shorts/"):
                return parsed_url.path.split("/")[2]
            if parsed_url.path.startswith("/embed/"):
                return parsed_url.path.split("/")[2]
        return None

    def normalize_title(self, title):
        if title is None:
            return ""
        title = title.lower()
        title = re.sub(r'\([^)]*\)|\[[^]]*\]', ' ', title)
        title = re.sub(r'\b(official|music|video|audio|lyrics?|lyric|hd|hq|mv|remastered|visualizer)\b', ' ', title)
        title = re.sub(r'[^a-z0-9]+', ' ', title)
        return " ".join(title.split())

    def clean_artist_name(self, artist):
        if artist is None:
            return None
        artist = str(artist).strip()
        artist = re.sub(r'\s*-\s*topic$', '', artist, flags=re.IGNORECASE)
        artist = re.sub(r'\s*official\s*$', '', artist, flags=re.IGNORECASE)
        artist = re.sub(r'\s*(vevo|records|recordings|music)\s*$', '', artist, flags=re.IGNORECASE)
        artist = artist.strip(" -|")
        return artist or None

    def extract_artist_name(self, extracted_info):
        artist = self.clean_artist_name(extracted_info.get('artist'))
        if artist:
            return artist

        title = extracted_info.get('title')
        if not title:
            return None

        title = re.sub(r'\([^)]*\)|\[[^]]*\]', ' ', title).strip()
        for separator in (' - ', ' – ', ' — ', ' | '):
            if separator in title:
                artist = self.clean_artist_name(title.split(separator, 1)[0])
                if artist:
                    return artist
        return None

    def remember_played_track(self, extracted_info):
        video_id = extracted_info.get('id') or self.get_youtube_id_from_url(extracted_info.get('webpage_url') or "")
        if video_id:
            self.recent_video_ids.append(video_id)
        normalized_title = self.normalize_title(extracted_info.get('title'))
        if normalized_title:
            self.recent_titles.append(normalized_title)

    def is_recent_or_current_result(self, result, current_id, current_url, current_title):
        url = result.get('url')
        result_id = result.get('id') or self.get_youtube_id_from_url(url or "")
        if result_id is not None and (result_id == current_id or result_id in self.recent_video_ids):
            return True
        if current_url is not None and url == current_url:
            return True

        result_title = self.normalize_title(result.get('title'))
        if not result_title:
            return False
        if result_title == current_title or result_title in self.recent_titles:
            return True
        if current_title and (result_title in current_title or current_title in result_title):
            return True
        return False

    def get_autoplay_url(self, extracted_info):
        search_url = self.search_autoplay_url(extracted_info)
        if search_url is not None:
            return search_url

        current_id = extracted_info.get('id')
        current_url = extracted_info.get('webpage_url')
        related_videos = extracted_info.get('related_videos') or []
        for related_video in related_videos:
            if related_video is None:
                continue
            related_url = self.get_entry_url(related_video)
            if related_url is None:
                continue
            if related_video.get('id') == current_id or related_url == current_url:
                continue
            return related_url
        return None

    def search_autoplay_url(self, extracted_info):
        title = extracted_info.get('title')
        if not title:
            return None

        preferred_artist = self.extract_artist_name(extracted_info) or title
        query = preferred_artist + " official music"

        current_id = extracted_info.get('id')
        current_url = extracted_info.get('webpage_url')
        current_title = self.normalize_title(title)
        results = self.search_youtube(query, limit=10, autoplay=True, preferred_artist=preferred_artist)
        for result in results:
            url = result.get('url')
            if url is None:
                continue
            if self.is_recent_or_current_result(result, current_id, current_url, current_title):
                continue
            return url
        return None

    async def play_youtube(self, youtube_link):
        """Downloads and plays the audio of the youtube link passed"""

        youtube_link = youtube_link.split("&list=")[0]

        try:
            with yt_dlp.YoutubeDL(build_ytdlp_options(YTDLP_OPTIONS)) as downloader:
                extracted_info = downloader.extract_info(youtube_link, download=False)
        # "format" is not available for livestreams - redownload the page with no options
        except Exception as first_error:
            try:
                fallback_options = build_ytdlp_options(YTDLP_OPTIONS)
                fallback_options.pop('format', None)
                with yt_dlp.YoutubeDL(fallback_options) as downloader:
                    extracted_info = downloader.extract_info(youtube_link, download=False)
            except Exception as second_error:
                print("Could not extract youtube audio from:", youtube_link)
                traceback.print_exception(type(first_error), first_error, first_error.__traceback__)
                print("Could not extract youtube audio with fallback from:", youtube_link)
                traceback.print_exception(type(second_error), second_error, second_error.__traceback__)
                self.next_song(None)
                return False

        if extracted_info is None or extracted_info.get('url') is None:
            print("Could not extract a playable audio URL from:", youtube_link)
            self.next_song(None)
            return False

        if self.voice_client is None or self.guild.voice_client is None:
            return False

        
        # Update the songinfo to reflect the current song
        self.current_extracted_info = extracted_info
        self.remember_played_track(extracted_info)
        self.current_track_url = extracted_info.get('webpage_url') or youtube_link
        self.current_autoplay_url = self.get_autoplay_url(extracted_info)
        self.current_songinfo = Songinfo(extracted_info.get('uploader'), extracted_info.get('creator'),
                                         extracted_info.get('title'), extracted_info.get('duration'),
                                         extracted_info.get('like_count'), extracted_info.get('dislike_count'),
                                         extracted_info.get('webpage_url'))

        # Change the nickname to indicate, what song is currently playing
        self.cancel_idle_disconnect()
        await self.guild.me.edit(nick=playing_string(extracted_info.get('title')))
        self.playlist.add_name(extracted_info.get('title'))
        await self.announce_current_song(extracted_info)
        
        self.voice_client.play(
            discord.FFmpegPCMAudio(
                extracted_info['url'],
                before_options=FFMPEG_BEFORE_OPTIONS,
            ),
            after=lambda e: self.next_song(e),
        )
        self.voice_client.source = discord.PCMVolumeTransformer(self.guild.voice_client.source)
        self.voice_client.source.volume = float(self.volume) / 100.0
        return True

    async def stop_player(self):
        """Stops the player and removes all songs from the queue"""
        if self.guild.voice_client is None or (
                not self.guild.voice_client.is_paused() and not self.guild.voice_client.is_playing()):
            return
        self.playlist.next()
        self.playlist.playque.clear()
        self.skip_requested = True
        self.guild.voice_client.stop()
        await self.guild.me.edit(nick=config.DEFAULT_NICKNAME)
        self.schedule_idle_disconnect()

    async def prev_song(self):
        """Loads the last ong from the history into the queue and starts it"""
        if len(self.playlist.playhistory) == 0:
            return None
        if self.guild.voice_client is None or (
                not self.guild.voice_client.is_paused() and not self.guild.voice_client.is_playing()):
            prev_song = self.playlist.prev()
            # The Dummy is used if there is no song in the history
            if prev_song == "Dummy":
                self.playlist.next()
                return None
            await self.play_youtube(prev_song)
        else:
            self.playlist.prev()
            self.playlist.prev()
            self.guild.voice_client.stop()
