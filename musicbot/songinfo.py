from config import config


class Songinfo:
    """A wrapper for information about the song currently being played."""

    def __init__(self, uploader, creator, title, duration, like_count, dislike_count, webpage_url):
        self.uploader = uploader
        self.creator = creator
        self.title = title
        self.duration = duration
        self.like_count = like_count
        self.dislike_count = dislike_count
        self.webpage_url = webpage_url

        self._output = ""
        self.format_output()

    @property
    def output(self):
        return self._output

    def format_duration(self):
        if self.duration is None:
            return "Unknown"
        try:
            duration = int(self.duration)
        except (TypeError, ValueError):
            return str(self.duration)

        hours = duration // 3600
        minutes = (duration % 3600) // 60
        seconds = duration % 60
        if hours > 0:
            return str(hours) + ":" + str(minutes).zfill(2) + ":" + str(seconds).zfill(2)
        return str(minutes) + ":" + str(seconds).zfill(2)

    def format_output(self):
        self._output = "```[" + self.title + "]\n"
        self._output += config.SONGINFO_UPLOADER + str(self.uploader) + "\n"
        self._output += config.SONGINFO_DURATION + self.format_duration() + "\n"
        self._output += config.SONGINFO_LIKES + str(self.like_count) + "\n"
        self._output += config.SONGINFO_DISLIKES + str(self.dislike_count)
        self._output += "```\n" + str(self.webpage_url)
