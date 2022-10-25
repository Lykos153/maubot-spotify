from typing import Tuple, Type
from uuid import uuid4

from aiohttp.web import Request, Response
from aiohttp_session import (
    SimpleCookieStorage,  # TODO: replace by EncryptedCookieStorage
)
from aiohttp_session import get_session, session_middleware
from maubot import MessageEvent, Plugin
from maubot.handlers import command, web
from mautrix.util.config import BaseProxyConfig
from spotipy.oauth2 import SpotifyOAuth, SpotifyOauthError

from .config import Config
from .data import Data, TempData
from .spotify import SpotifyClient


class SpotifyBot(Plugin):
    @classmethod
    def get_config_class(cls) -> Type[BaseProxyConfig]:
        return Config

    async def start(self) -> None:
        self.config.load_and_update()
        self.data = Data()
        self.tempdata = TempData()
        self.log.debug(self.webapp_url.human_repr())
        self.spotify_oauth = SpotifyOAuth(
            client_id=self.config["spotify_client_id"],
            client_secret=self.config["spotify_client_secret"],
            redirect_uri=self.webapp_url.human_repr() + "/callback",
        )
        self.webapp.add_middleware(session_middleware(SimpleCookieStorage()))
        # self.log.debug(len(self.webapp._middleware), self.webapp._middleware)

    def get_command_name(self) -> str:
        return self.config["command_prefix"]

    @command.new(name=get_command_name, require_subcommand=True)
    async def spotify(self, evt: MessageEvent) -> None:
        pass

    @spotify.subcommand(help="Login to your spotify account")
    async def login(self, evt: MessageEvent) -> None:
        userkey = str(uuid4())
        self.tempdata.put(userkey, evt.sender)
        await evt.reply(self.webapp_url.human_repr() + "/auth?s=" + userkey)

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

    @command.passive("(.*)(https://open.spotify.com/album/[a-zA-Z0-9]*)( ?.*)")
    async def add_album(self, evt: MessageEvent, match: Tuple[str]) -> None:
        self.log.debug(
            f"{evt.sender} shared album in {evt.room_id}: {match[2]}"
        )
        await self.client.send_text(room_id=evt.room_id, text=str(match))

    @web.get("/auth")
    async def auth(self, req: Request) -> Response:
        session = await get_session(req)
        userkey = req.rel_url.query.get("s")
        self.log.debug(f"Auth request with s={userkey}")
        user = self.tempdata.get(userkey)
        if user is None:
            self.log.debug("Invalid userkey")
            return Response(status=403, text="Unauthorized. Try again")
        self.log.debug(f"User is {user}")
        session["userkey"] = userkey
        self.log.debug(f"Session: {session}")
        link = self.spotify_oauth.get_authorize_url()
        return Response(
            text=f'<a href="{link}">{link}</a>', content_type="text/html"
        )

    @web.get("/callback")
    async def callback(self, req: Request) -> Response:
        self.log.debug(f"Received callback: {req.rel_url.query}")
        session = await get_session(req)
        self.log.debug(f"Session: {session}")
        userkey = session.get("userkey")
        if userkey is None:
            self.log.debug("ERROR: Empty userkey")
            return Response(status=403, text="ERROR: Empty userkey")
        user = self.tempdata.get(userkey)
        if user is None:
            self.log.debug("ERROR: Invalid userkey")
            return Response(status=403, text="ERROR: Invalid userkey")
        try:
            token = self.spotify_oauth.get_access_token(
                req.rel_url.query["code"], as_dict=False
            )
        except SpotifyOauthError as e:
            self.log.debug(f"ERROR: {e}")
            return Response(text=f"ERROR: {e}")
        self.log.debug(f"Token: {token}")

        client = SpotifyClient(token)
        self.data.set_spotify_user(user, client)
        return Response(text="Success")
