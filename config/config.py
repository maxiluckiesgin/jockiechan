import os


token: str = os.environ.get("DISCORD_TOKEN", "")
DEFAULT_NICKNAME = "🎵JockieChan🎵"

STARTUP_MESSAGE = "Starting Bot..."
STARTUP_COMPLETE_MESSAGE = "Startup Complete"

NO_GUILD_MESSAGE = 'Error: Please join a voice channel or enter the command in guild chat'
NOT_CONNECTED_MESSAGE = "Error: Bot not connected to any voice channel"
CHANNEL_NOT_FOUND_MESSAGE = "Error: Could not find channel "
DEFAULT_CHANNEL_JOIN_FAILED = "Error: Could not join the default voice channel"
INVALID_INVITE_MESSAGE = "Error: Invalid invitation link"

ADD_MESSAGE_1 = """```To add this bot to your own Server, click the following link:
                ```\n<https://discordapp.com/oauth2/authorize?client_id="""
ADD_MESSAGE_2 = "&scope=bot>"

DEFAULT_VOLUME = 7
IDLE_DISCONNECT_SECONDS = 180

INFO_HISTORY_TITLE = "Songs Played:"
MAX_HISTORY_LENGTH = 10
MAX_TRACKNAME_HISTORY_LENGTH = 15

SONGINFO_UPLOADER = "Uploader: "
SONGINFO_DURATION = "Duration: "
SONGINFO_SECONDS = "s"
SONGINFO_LIKES = "Likes: "
SONGINFO_DISLIKES = "Dislikes: "

HELP_ADDBOT_SHORT = "Add Bot to another server"
HELP_ADDBOT_LONG = "Gives you the link for adding this bot to another server of yours."
HELP_CC_SHORT = "Change voicechannel"
HELP_CC_LONG = "Switches the bot to another voicechannel."
HELP_CONNECT_SHORT = "Connect bot to voicechannel"
HELP_CONNECT_LONG = ""
HELP_DISCONNECT_SHORT = "Connect bot from voicechannel"
HELP_DISCONNECT_LONG = ""
HELP_LEAVE_SHORT = "Leave voicechannel"
HELP_LEAVE_LONG = "Disconnects the bot from its current voicechannel."
HELP_SET_SHORT = "Set voice disconnect timer"
HELP_SET_LONG = "Disconnects a mentioned user after they have been inactive for the timer duration."

HELP_HISTORY_SHORT = "Show history of songs"
HELP_HISTORY_LONG = "Shows the " + str(MAX_TRACKNAME_HISTORY_LENGTH) + " last played songs."
HELP_AUTOPLAY_SHORT = "Toggle autoplay"
HELP_AUTOPLAY_LONG = "Keeps playing related songs when the queue ends."
HELP_LOOP_SHORT = "Toggle loop"
HELP_LOOP_LONG = "Repeats the current song until loop is disabled."
HELP_LYRICS_SHORT = "Search lyrics"
HELP_LYRICS_LONG = "Shows a lyrics search link for the current song or a provided query."
HELP_PAUSE_SHORT = "Pause Music"
HELP_PAUSE_LONG = "Pauses the AudioPlayer. Playback can be continued with the resume command."
HELP_PREV_SHORT = "Go back one Song"
HELP_PREV_LONG = "Plays the previous song again."
HELP_REMOVE_SHORT = "Remove song from queue"
HELP_REMOVE_LONG = "Removes a song by queue number. Number 1 is the current song."
HELP_RESUME_SHORT = "Resume Music"
HELP_RESUME_LONG = "Resumes the AudioPlayer."
HELP_SEARCH_SHORT = "Search and play YouTube"
HELP_SEARCH_LONG = "Plays the first YouTube result for the search term."
HELP_SKIP_SHORT = "Skip a song"
HELP_SKIP_LONG = "Skips the currently playing song and goes to the next item in the queue."
HELP_SONGINFO_SHORT = "Info about current Song"
HELP_SONGINFO_LONG = "Shows details about the song currently being played and posts a link to the song."
HELP_STOP_SHORT = "Stop Music"
HELP_STOP_LONG = "Stops the AudioPlayer and clears the songqueue"
HELP_VOL_SHORT = "Change volume %"
HELP_VOL_LONG = "Changes the volume of the AudioPlayer. Argument specifies the % to which the volume should be set."
HELP_YT_SHORT = "Play song from Youtube"
HELP_YT_LONG = ("Plays the audio of a Youtube video. Argument can either be:\n"
                "  - A link to the video (https://ww...)\n"
                "  - The title of a video (Rick Astley - Never Gonna Give You Up)\n" 
                "  - Keywords for a search(lofi hip-hop) -> the bot plays the first result)\n"
                "  - A link to a playlist -> the bot will play the songs one after another\n"
                "If the player is already playing, the command adds the song to the playingqueue")
