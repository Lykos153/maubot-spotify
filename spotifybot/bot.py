from typing import Tuple

from maubot import MessageEvent, Plugin
from maubot.handlers import command

from .data import Data


class SpotifyBot(Plugin):
    async def start(self) -> None:
        self.data = Data()

    @command.new(require_subcommand=True)
    async def spotify(self, evt: MessageEvent) -> None:
        await evt.reply("Hello, World!")

    @spotify.subcommand(help="Login to your spotify account")
    async def login(self, evt: MessageEvent) -> None:
        await evt.react("subcommand!")

    @spotify.subcommand(help="Set the room playlist")
    @command.argument("playlist", pass_raw=False, required=True)
    async def set_playlist(self, evt: MessageEvent, playlist: str) -> None:
        if not playlist:
            # TODO: How to get original event to reply to if message was edited
            await evt.reply("Missing playlist link")
            return

        self.log.debug(
            f"{evt.sender} set the playlist of {evt.room_id} to {playlist}"
        )
        self.data.set_room_playlist(evt.room_id, playlist)
        await self.client.send_text(
            room_id=evt.room_id, text=f"Room playlist was set to {playlist}"
        )

    @command.passive("(.*)(https://open.spotify.com/track/[a-zA-Z0-9]*)( ?.*)")
    async def add_track(self, evt: MessageEvent, match: Tuple[str]) -> None:
        self.log.debug(
            f"{evt.sender} shared track in {evt.room_id}: {match[2]}"
        )
        await self.client.send_text(room_id=evt.room_id, text=str(match))
        # await evt.reply(str(match))

    @command.passive("(.*)(https://open.spotify.com/album/[a-zA-Z0-9]*)( ?.*)")
    async def add_album(self, evt: MessageEvent, match: Tuple[str]) -> None:
        self.log.debug(
            f"{evt.sender} shared album in {evt.room_id}: {match[2]}"
        )
        await self.client.send_text(room_id=evt.room_id, text=str(match))
        # await evt.reply(str(match))
