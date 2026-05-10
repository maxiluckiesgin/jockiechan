import discord
import traceback
from discord.ext import commands

from config.config import *
from musicbot.audiocontroller import AudioController
from musicbot.utils import guild_to_audiocontroller


initial_extensions = ['musicbot.commands.music', 'musicbot.commands.general']
intents = discord.Intents.default()
intents.message_content = True


class JockeyBot(commands.Bot):
    async def setup_hook(self):
        for extension in initial_extensions:
            try:
                await self.load_extension(extension)
            except Exception as e:
                print(e)


bot = JockeyBot(command_prefix="!", pm_help=True, intents=intents)


@bot.event
async def on_ready():
    print(STARTUP_MESSAGE)
    print("Message Content Intent enabled: ! commands should work.")
    await bot.change_presence(status=discord.Status.online, activity=discord.Game(name=" Music, type !help "))

    for guild in bot.guilds:
        print(guild.name)
        await guild.me.edit(nick=DEFAULT_NICKNAME)
        guild_to_audiocontroller[guild] = AudioController(bot, guild, DEFAULT_VOLUME)

    for guild in bot.guilds:
        try:
            bot.tree.clear_commands(guild=guild)
            synced_commands = await bot.tree.sync(guild=guild)
            print("Cleared", len(synced_commands), "slash commands for", guild.name)
        except Exception as e:
            print("Could not clear slash commands for", guild.name, e)
        
    print(STARTUP_COMPLETE_MESSAGE)


@bot.event
async def on_guild_join(guild):
    print(guild.name)
    guild_to_audiocontroller[guild] = AudioController(bot, guild, DEFAULT_VOLUME)


@bot.event
async def on_command_error(ctx, error):
    traceback.print_exception(type(error), error, error.__traceback__)
    await ctx.send("Command failed. Check the bot console for the error.")


if not token:
    raise RuntimeError("Set DISCORD_TOKEN before starting the bot.")


bot.run(token, reconnect=True)
