import asyncio
import time
import discord
from discord.ext import commands

from config import config
from musicbot import utils
from musicbot.audiocontroller import AudioController


class General(commands.Cog):
    """ A collection of the commands for moving the bot around in you server.

            Attributes:
                bot: The instance of the bot that is executing the commands.
    """

    def __init__(self, bot):
        self.bot = bot
        self.kick_timer_tasks = {}
        self.voice_chat_activity = {}
        self.pomodoro_tasks = {}

    def get_current_guild(self, ctx):
        if ctx.guild is not None:
            return ctx.guild
        if ctx.message is not None:
            return utils.get_guild(self.bot, ctx.message)
        return None

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.guild is None or message.author.bot:
            return

        voice_state = getattr(message.author, 'voice', None)
        if voice_state is None or voice_state.channel is None:
            return
        if message.channel.id != voice_state.channel.id:
            return

        self.voice_chat_activity[(message.guild.id, message.author.id)] = time.monotonic()

    @commands.command(name='connect', description=config.HELP_CONNECT_SHORT, help=config.HELP_CONNECT_SHORT)
    async def _connect(self, ctx, *, dest_channel_name: str = None):
        current_guild = self.get_current_guild(ctx)

        if current_guild is None:
            await utils.send_message(ctx, config.NO_GUILD_MESSAGE)
            return

        if utils.guild_to_audiocontroller[current_guild] is None:
            utils.guild_to_audiocontroller[current_guild] = AudioController(self.bot, current_guild,
                                                                            config.DEFAULT_VOLUME)
        if current_guild.voice_client is not None:
            await ctx.send("Already connected.")
            return
        if dest_channel_name is None:
            voice_state = getattr(ctx.author, 'voice', None)
            if voice_state is None or voice_state.channel is None:
                await ctx.send("Join a voice channel first, or pass a channel name.")
                return
            await utils.guild_to_audiocontroller[current_guild].register_voice_channel(voice_state.channel)
            await ctx.send("Connected to " + voice_state.channel.name + ".")
            return
        await utils.connect_to_channel(current_guild, dest_channel_name, ctx, switch=False, default=True)
        utils.guild_to_audiocontroller[current_guild].voice_client = current_guild.voice_client
        utils.guild_to_audiocontroller[current_guild].schedule_idle_disconnect()
        await ctx.send("Connected.")

    @commands.command(name='disconnect', description=config.HELP_DISCONNECT_SHORT, help=config.HELP_DISCONNECT_SHORT)
    async def _disconnect(self, ctx):
        await self.leave_voice(ctx)

    @commands.command(name='leave', description=config.HELP_LEAVE_SHORT, help=config.HELP_LEAVE_SHORT)
    async def _leave(self, ctx):
        await self.leave_voice(ctx)

    async def leave_voice(self, ctx):
        current_guild = self.get_current_guild(ctx)

        if current_guild is None:
            await utils.send_message(ctx, config.NO_GUILD_MESSAGE)
            return
        if current_guild.voice_client is None:
            await ctx.send("Not connected.")
            return
        disconnected = await utils.guild_to_audiocontroller[current_guild].disconnect()
        if disconnected:
            await ctx.send("Disconnected.")
        else:
            await ctx.send("Not connected.")

    @commands.command(name='cc', aliases=["changechannel"], description=config.HELP_CC_SHORT, help=config.HELP_CC_SHORT)
    async def _changechannel(self, ctx, *, dest_channel_name: str):
        current_guild = self.get_current_guild(ctx)

        if current_guild is None:
            await utils.send_message(ctx, config.NO_GUILD_MESSAGE)
            return

        await utils.connect_to_channel(current_guild, dest_channel_name, ctx, switch=True, default=False)
        utils.guild_to_audiocontroller[current_guild].voice_client = current_guild.voice_client
        utils.guild_to_audiocontroller[current_guild].schedule_idle_disconnect()
        await ctx.send("Changed voice channel.")

    @commands.command(name='addbot', description=config.HELP_ADDBOT_SHORT, help=config.HELP_ADDBOT_SHORT)
    async def _addbot(self, ctx):
        await ctx.send(config.ADD_MESSAGE_1 + str(self.bot.user.id) + config.ADD_MESSAGE_2)

    @commands.command(name='pomodoro', aliases=["pomo"], description=config.HELP_POMODORO_SHORT, help=config.HELP_POMODORO_SHORT)
    async def _pomodoro(self, ctx):
        task_key = (ctx.guild.id if ctx.guild is not None else None, ctx.channel.id)
        existing_task = self.pomodoro_tasks.get(task_key)
        if existing_task is not None and not existing_task.done():
            existing_task.cancel()
            await ctx.send("Pomodoro stopped.")
            return

        self.pomodoro_tasks[task_key] = self.bot.loop.create_task(
            self.run_pomodoro(ctx.channel, ctx.guild, task_key)
        )
        await ctx.send("Pomodoro loop started: 25 minutes focus, 5 minutes break. Type !pomodoro again to stop.")

    async def run_pomodoro(self, channel, guild, task_key):
        timer_message = None
        try:
            while True:
                timer_message = await self.run_timer_phase(
                    channel,
                    timer_message,
                    "Focus",
                    config.POMODORO_FOCUS_SECONDS,
                )

                music_paused = self.pause_guild_music(guild)
                if music_paused:
                    await channel.send("Focus session done. Music paused. Break started: 5 minutes.")
                else:
                    await channel.send("Focus session done. Break started: 5 minutes.")

                timer_message = await self.run_timer_phase(
                    channel,
                    timer_message,
                    "Break",
                    config.POMODORO_BREAK_SECONDS,
                )
                if music_paused:
                    self.resume_guild_music(guild)
                    await channel.send("Break done. Music resumed. Starting next focus session.")
                else:
                    await channel.send("Break done. Starting next focus session.")
        except asyncio.CancelledError:
            return
        finally:
            self.pomodoro_tasks.pop(task_key, None)

    async def run_timer_phase(self, channel, timer_message, label, total_seconds):
        start_time = time.monotonic()
        while True:
            elapsed_seconds = min(int(time.monotonic() - start_time), total_seconds)
            content = self.format_timer_message(label, elapsed_seconds, total_seconds)
            if timer_message is None:
                timer_message = await channel.send(content)
            else:
                await timer_message.edit(content=content)

            if elapsed_seconds >= total_seconds:
                return timer_message

            remaining_seconds = total_seconds - elapsed_seconds
            await asyncio.sleep(min(60, remaining_seconds))

    def format_timer_message(self, label, elapsed_seconds, total_seconds):
        progress_width = 20
        filled = int(progress_width * elapsed_seconds / total_seconds)
        progress_bar = "[" + ("#" * filled) + ("-" * (progress_width - filled)) + "]"
        remaining_seconds = max(total_seconds - elapsed_seconds, 0)
        return (
            label + " timer\n"
            + progress_bar + " "
            + self.format_seconds(remaining_seconds) + " remaining"
        )

    def format_seconds(self, seconds):
        minutes = seconds // 60
        seconds = seconds % 60
        return str(minutes).zfill(2) + ":" + str(seconds).zfill(2)

    def pause_guild_music(self, guild):
        if guild is None or guild.voice_client is None:
            return False
        if not guild.voice_client.is_playing():
            return False
        guild.voice_client.pause()
        return True

    def resume_guild_music(self, guild):
        if guild is None or guild.voice_client is None:
            return False
        if not guild.voice_client.is_paused():
            return False
        guild.voice_client.resume()
        return True

    @commands.command(name='set', description=config.HELP_SET_SHORT, help=config.HELP_SET_SHORT)
    async def _set_timer(self, ctx, seconds: int, *, username: str = None):
        current_guild = self.get_current_guild(ctx)
        if current_guild is None:
            await utils.send_message(ctx, config.NO_GUILD_MESSAGE)
            return
        if not ctx.author.guild_permissions.move_members:
            await ctx.send("You need Move Members permission to use this command.")
            return
        if seconds <= 0:
            await ctx.send("Timer must be greater than 0 seconds.")
            return

        if ctx.message.mentions:
            member = ctx.message.mentions[0]
        else:
            await ctx.send("Mention a user to monitor. Example: !set 60 @username")
            return
        if member is None:
            await ctx.send("Could not find user: " + username)
            return
        if member.voice is None or member.voice.channel is None:
            await ctx.send(member.display_name + " is not in a voice channel.")
            return

        task_key = (current_guild.id, member.id)
        existing_task = self.kick_timer_tasks.get(task_key)
        if existing_task is not None and not existing_task.done():
            existing_task.cancel()

        self.kick_timer_tasks[task_key] = self.bot.loop.create_task(
            self.kick_after_inactivity(ctx.channel, member, seconds)
        )
        await ctx.send("Monitoring " + member.display_name + ". They will be disconnected after " + str(seconds) + " seconds of inactivity.")

    def find_member(self, guild, username):
        username = username.strip()
        if username.startswith("<@") and username.endswith(">"):
            user_id = username.strip("<@!>")
            if user_id.isdigit():
                return guild.get_member(int(user_id))
        if username.isdigit():
            member = guild.get_member(int(username))
            if member is not None:
                return member

        username_lower = username.lower()
        for member in guild.members:
            if member.name.lower() == username_lower:
                return member
            if member.display_name.lower() == username_lower:
                return member
            if str(member).lower() == username_lower:
                return member
        return None

    def get_inactive_reason(self, guild, member):
        voice = member.voice
        if voice is None or voice.channel is None:
            return None
        if guild.afk_channel is not None and voice.channel == guild.afk_channel:
            return "in AFK channel"
        if getattr(voice, 'afk', False):
            return "marked AFK"
        if getattr(voice, 'self_deaf', False) or getattr(voice, 'deaf', False):
            return "deafened"
        if getattr(voice, 'self_mute', False) or getattr(voice, 'mute', False):
            return "muted"
        if getattr(voice, 'suppress', False):
            return "suppressed"
        if member.status == discord.Status.idle:
            return "idle status"
        return None

    async def kick_after_inactivity(self, channel, member, seconds):
        inactive_seconds = 0
        last_reason = None
        task_key = (member.guild.id, member.id)
        last_seen_voice_chat = self.voice_chat_activity.get(task_key, 0)
        try:
            while True:
                await asyncio.sleep(1)
                if member.voice is None or member.voice.channel is None:
                    await channel.send(member.display_name + " is no longer in a voice channel.")
                    return

                latest_voice_chat = self.voice_chat_activity.get(task_key, 0)
                if latest_voice_chat > last_seen_voice_chat:
                    inactive_seconds = 0
                    last_reason = None
                    last_seen_voice_chat = latest_voice_chat
                    continue

                inactive_reason = self.get_inactive_reason(member.guild, member)
                if inactive_reason is None:
                    inactive_seconds = 0
                    last_reason = None
                    continue

                inactive_seconds += 1
                last_reason = inactive_reason
                if inactive_seconds >= seconds:
                    await member.move_to(None)
                    await channel.send("Disconnected " + member.display_name + " after " + str(seconds) + " seconds of inactivity (" + last_reason + ").")
                    return
        except asyncio.CancelledError:
            return
        except discord.Forbidden:
            await channel.send("I do not have permission to disconnect " + member.display_name + ".")
        except discord.HTTPException as error:
            await channel.send("Could not disconnect " + member.display_name + ": " + str(error))
        finally:
            self.kick_timer_tasks.pop((member.guild.id, member.id), None)


async def setup(bot):
    await bot.add_cog(General(bot))
