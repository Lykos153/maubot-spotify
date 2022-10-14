from typing import Tuple

from maubot import MessageEvent, Plugin
from maubot.handlers import command


class SpotifyBot(Plugin):
    @command.new(require_subcommand=True)
    async def spotify(self, evt: MessageEvent) -> None:
        await evt.reply("Hello, World!")

    @spotify.subcommand(help="Do subcommand things")
    async def help(self, evt: MessageEvent) -> None:
        await evt.react("subcommand!")

    @command.passive("https://open.spotify.com")
    async def command(self, evt: MessageEvent, match: Tuple[str]) -> None:
        await evt.react("🐈️")
