import re
from typing import Tuple, Type, Union
from uuid import uuid4

from aiohttp.web import Request, Response
from aiohttp_session import (
    SimpleCookieStorage,  # TODO: replace by EncryptedCookieStorage
)
from aiohttp_session import get_session, session_middleware
from maubot import MessageEvent, Plugin
from maubot.handlers import command, web
from mautrix.util.async_db import Connection, UpgradeTable
from mautrix.util.config import BaseProxyConfig
from spotipy.oauth2 import SpotifyOAuth, SpotifyOauthError

from .config import Config
from .data import Data, TempData

RE_SPOTIY_PLAYLIST = re.compile(
    "(.*)(https://open.spotify.com/playlist/([a-zA-Z0-9]*))( ?.*)"
)

upgrade_table = UpgradeTable()


@upgrade_table.register(description="Initial revision")
async def upgrade_v1(conn: Connection) -> None:
    await conn.execute(
        """CREATE TABLE users (
            mxid   TEXT PRIMARY KEY,
            token TEXT NOT NULL
        )"""
    )


@upgrade_table.register(description="Add room playlist")
async def upgrade_v2(conn: Connection) -> None:
    await conn.execute(
        """CREATE TABLE room_playlists (
            room   TEXT PRIMARY KEY,
            playlist TEXT NOT NULL
        )"""
    )


class SpotifyBot(Plugin):
    @classmethod
    def get_config_class(cls) -> Type[BaseProxyConfig]:
        return Config

    @classmethod
    def get_db_upgrade_table(cls) -> Union[UpgradeTable, None]:
        return upgrade_table

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

    @spotify.subcommand(help="Info about login and room state")
    async def info(self, evt: MessageEvent) -> None:
        user_logged_in = (await self._get_user_token(evt.sender)) is not None
        room_list = await self._get_room_playlist(evt.room_id)

        reply = f'You are {"" if user_logged_in else "not "}logged in.\n'
        pl_str = self._get_playlist_url(room_list) if room_list else "not set"
        reply += f"Room playlist is {pl_str}."
        await self.client.send_text(room_id=evt.room_id, text=reply)

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

        # TODO: Use matrix room events for storing the playlist
        self.log.debug(
            f"{evt.sender} set the playlist of {evt.room_id} to {playlist}"
        )
        pl_id = self._get_playlist_id(playlist)
        if pl_id is None:
            self.log.debug("No playlist ID found")
            await evt.reply("Invalid playlist link")
            return
        self._set_room_playlist(evt.room_id, pl_id)
        await self.client.send_text(
            room_id=evt.room_id, text=f"Room playlist was set to {pl_id}"
        )

    @command.passive(
        "(.*)(https://open.spotify.com/track/([a-zA-Z0-9]*))( ?.*)"
    )
    async def add_track(self, evt: MessageEvent, match: Tuple[str]) -> None:
        self.log.debug(
            f"{evt.sender} shared track in {evt.room_id}: {match[3]}"
        )

        await self.client.send_text(
            room_id=evt.room_id,
            text=str(self._get_user_token(evt.sender) is not None),
        )

    @command.passive(
        "(.*)(https://open.spotify.com/album/([a-zA-Z0-9]*))( ?.*)"
    )
    async def add_album(self, evt: MessageEvent, match: Tuple[str]) -> None:
        self.log.debug(
            f"{evt.sender} shared album in {evt.room_id}: {match[3]}"
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

        await self._set_user_token(user, token)
        return Response(text="Success")

    async def _set_user_token(self, mxid: str, token: str):
        q = """
            INSERT INTO users (mxid, token) VALUES ($1, $2)
            ON CONFLICT (mxid) DO UPDATE SET token=excluded.token
        """
        await self.database.execute(q, mxid, token)

    async def _get_user_token(self, mxid: str) -> Union[str, None]:
        q = """
            SELECT token FROM users WHERE mxid=$1
        """
        row = await self.database.fetchrow(q, mxid)
        return row["token"] if row else None

    async def _set_room_playlist(self, room: str, playlist: str):
        q = """
            INSERT INTO room_playlists (room, playlist) VALUES ($1, $2)
            ON CONFLICT (room) DO UPDATE SET playlist=excluded.playlist
        """
        await self.database.execute(q, room, playlist)

    async def _get_room_playlist(self, room: str) -> Union[str, None]:
        q = """
            SELECT playlist FROM room_playlists WHERE room=$1
        """
        row = await self.database.fetchrow(q, room)
        return row["playlist"] if row else None

    def _get_playlist_id(self, playlist_url: str) -> Union[str, None]:
        m = RE_SPOTIY_PLAYLIST.match(playlist_url)
        return m.group(3) if m else None

    def _get_playlist_url(self, playlist_id: str) -> str:
        return f"https://open.spotify.com/playlist/{playlist_id}"
