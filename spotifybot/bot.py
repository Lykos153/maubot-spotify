from typing import Tuple

from maubot import MessageEvent, Plugin
from maubot.handlers import command


class SpotifyBot(Plugin):
    @command.new(require_subcommand=True)
    async def spotify(self, evt: MessageEvent) -> None:
        await evt.reply("Hello, World!")

    @spotify.subcommand(help="Login to your spotify account")
    async def login(self, evt: MessageEvent) -> None:
        await evt.react("subcommand!")

    @command.passive("(.*)(https://open.spotify.com/track/[a-zA-Z0-9]*)( ?.*)")
    async def add_track(self, evt: MessageEvent, match: Tuple[str]) -> None:
        await evt.reply(str(match))
