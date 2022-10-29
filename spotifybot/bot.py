import datetime
import re
import sqlite3
from typing import Tuple, Type, Union
from uuid import uuid4

from aiohttp import ClientSession
from aiohttp.web import Request, Response
from aiohttp_session import (
    SimpleCookieStorage,  # TODO: replace by EncryptedCookieStorage
)
from aiohttp_session import get_session, session_middleware
from maubot import MessageEvent, Plugin
from maubot.handlers import command, event, web
from mautrix.types import EventType, Membership, StateEvent
from mautrix.util.async_db import Connection, UpgradeTable
from mautrix.util.config import BaseProxyConfig
from spotipy2.auth.token import Token
from spotipy2.exceptions import SpotifyException

from .config import Config
from .data import Data, TempData
from .spotify import OauthFlow, SpotifyClient

RE_SPOTIY_PLAYLIST = re.compile(
    "(.*)(https://open.spotify.com/playlist/([a-zA-Z0-9]*))( ?.*)"
)
CALLBACK_PATH = "/callback"

upgrade_table = UpgradeTable()


class AuthData:
    def __init__(self, mxid: str, oauth: OauthFlow):
        self.mxid = mxid
        self.oauth = oauth


@upgrade_table.register(description="Initial revision")
async def upgrade_v1(conn: Connection) -> None:
    await conn.execute(
        """CREATE TABLE users (
            mxid    TEXT PRIMARY KEY,
            token   TEXT NOT NULL
        )"""
    )


@upgrade_table.register(description="Add room playlist")
async def upgrade_v2(conn: Connection) -> None:
    await conn.execute(
        """CREATE TABLE room_playlists (
            room        TEXT PRIMARY KEY,
            playlist    TEXT NOT NULL
        )"""
    )


@upgrade_table.register(description="Add more parts of the user token")
async def upgrade_v3(conn: Connection) -> None:
    await conn.execute("ALTER TABLE users ADD token_type TEXT;")
    await conn.execute("ALTER TABLE users ADD expires_at INTEGER;")
    await conn.execute("ALTER TABLE users ADD refresh_token TEXT;")
    await conn.execute("ALTER TABLE users ADD scopes TEXT;")


@upgrade_table.register(description="Store active rooms")
async def upgrade_v4(conn: Connection) -> None:
    await conn.execute("CREATE TABLE active_rooms")


@upgrade_table.register(description="Fix active_rooms")
async def upgrade_v5(conn: Connection) -> None:
    pass


@upgrade_table.register(description="Fix active_rooms")
async def upgrade_v6(conn: Connection) -> None:
    await conn.execute("DROP TABLE active_rooms")
    await conn.execute(
        """CREATE TABLE active_rooms (
            room         TEXT PRIMARY KEY,
            joined_first INTEGER,
            joined_last  INTEGER
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
        self.client_session = ClientSession()
        self.log.debug(self.webapp_url.human_repr())
        self.webapp.add_middleware(session_middleware(SimpleCookieStorage()))
        # self.log.debug(len(self.webapp._middleware), self.webapp._middleware)

    @event.on(EventType.ROOM_MEMBER)
    async def handle_join(self, evt: StateEvent) -> None:
        if (
            evt.state_key == self.client.mxid
            and evt.content.membership == Membership.JOIN
        ):
            self.log.debug(
                f"Got join event for {evt.room_id} at {evt.timestamp}"
            )
            is_latest = await self._room_set_active(evt.room_id, evt.timestamp)
            if is_latest:
                self.log.info(f"Joined room {evt.room_id} at {evt.timestamp}")
                client_name = await self.client.get_displayname(
                    self.client.mxid
                )
                prefix = self.config["command_prefix"]
                await self.client.send_text(
                    room_id=evt.room_id,
                    text=f"Hi, I am {client_name}! \n"
                    "If you haven't done so already, connect your "
                    f"Spotify account with `!{prefix} login`.\n"
                    "Each room can be connected to a playlist. "
                    f"Use !`{prefix} set-playlist` to set a new "
                    "playlist for this room.\n"
                    f"Send `!{prefix} help`"
                    " to see what I can do.",
                )

    def get_command_name(self) -> str:
        return self.config["command_prefix"]

    @command.new(name=get_command_name, require_subcommand=True)
    async def spotify(self, evt: MessageEvent) -> None:
        pass

    @spotify.subcommand(help="Info about login and room state")
    async def info(self, evt: MessageEvent) -> None:
        user_logged_in = await self._is_logged_in(evt.sender)
        room_list = await self._get_room_playlist(evt.room_id)

        reply = f'You are {"" if user_logged_in else "not "}logged in.\n'
        pl_str = self._get_playlist_url(room_list) if room_list else "not set"
        reply += f"Room playlist is {pl_str}."
        await self.client.send_text(room_id=evt.room_id, text=reply)

    @spotify.subcommand(help="Login to your spotify account")
    async def login(self, evt: MessageEvent) -> None:
        await evt.reply(self._get_auth_url(evt.sender))

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
        await self._set_room_playlist(evt.room_id, pl_id)
        await self.client.send_text(
            room_id=evt.room_id, text=f"Room playlist was set to {pl_id}"
        )

    @command.passive(
        "(.*)(https://open.spotify.com/track/([a-zA-Z0-9]*))( ?.*)"
    )
    async def add_track(self, evt: MessageEvent, match: Tuple[str]) -> None:
        track_id = match[3]
        self.log.debug(
            f"{evt.sender} shared track in {evt.room_id}: {track_id}"
        )
        token = await self._get_user_token(evt.sender)
        if token is None:
            self.log.debug(f"User {evt.sender} not logged in")
            await evt.reply(
                "Click this link to login, "
                "so I can add the song to the playlist for you:\n"
                + self._get_auth_url(evt.sender)
            )
            return

        playlist = await self._get_room_playlist(evt.room_id)
        if playlist is None:
            self.log.debug(f"{evt.room_id} doesn't have a room playlist.")
            await evt.reply(
                "This room doesn't have a playlist yet. "
                "You can set it with `!spotify set-playlist`"
            )
            return

        oauth = self._new_oauth_flow(token)
        client = SpotifyClient(
            (await oauth.get_access_token(self.client_session)).access_token
        )
        try:
            client.add_song_to_playlist(playlist, track_id)
        except Exception as e:
            self.log.debug(
                f"ERROR: Failed to add song {track_id} to "
                f"playlist {playlist}: {e}"
            )
            await evt.react("❌")
            return
        await evt.react("✅")

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
        auth_data: AuthData = self.tempdata.get(userkey)
        if auth_data is None:
            self.log.debug("Invalid userkey")
            return Response(status=403, text="Unauthorized. Try again")

        user = auth_data.mxid
        self.log.debug(f"User is {user}")
        session["userkey"] = userkey
        self.log.debug(f"Session: {session}")
        link = await auth_data.oauth.get_redirect()
        return Response(
            text=f'<a href="{link}">Click here to login</a>',
            content_type="text/html",
        )

    @web.get(CALLBACK_PATH)
    async def callback(self, req: Request) -> Response:
        self.log.debug(f"Received callback: {req.rel_url.query}")
        session = await get_session(req)
        self.log.debug(f"Session: {session}")
        userkey = session.get("userkey")
        if userkey is None:
            self.log.debug("ERROR: Empty userkey")
            return Response(status=403, text="ERROR: Empty userkey")
        auth_data: AuthData = self.tempdata.get(userkey)
        if auth_data is None:
            self.log.debug("ERROR: Invalid userkey")
            return Response(status=403, text="ERROR: Invalid userkey")
        try:
            token = await OauthFlow._get_access_token(
                req.rel_url.query.get("code"),
                auth_data.oauth.client_id,
                auth_data.oauth.client_secret,
                self._callback_url(),
                self.client_session,
            )
        except SpotifyException as e:
            self.log.debug(f"ERROR: {e}")
            return Response(text=f"ERROR: {e}")
        self.log.debug(f"Token: {token}")

        await self._set_user_token(auth_data.mxid, token)
        return Response(text="Success")

    async def _set_user_token(self, mxid: str, token: Token):
        q = """
            INSERT INTO users (
                mxid, token, token_type, expires_at,
                    refresh_token, scopes
                ) VALUES ($1, $2, $3, $4, $5, $6)
            ON CONFLICT (mxid) DO
                UPDATE SET
                    token=excluded.token,
                    token_type=excluded.token_type,
                    expires_at=excluded.expires_at,
                    refresh_token=excluded.refresh_token,
                    scopes=excluded.scopes
        """

        await self.database.execute(
            q,
            mxid,
            token.access_token,
            token.token_type,
            token.expires_at.timestamp(),
            token.refresh_token,
            " ".join(token.scopes),
        )

    async def _get_user_token(self, mxid: str) -> Union[Token, None]:
        q = """
            SELECT mxid, token, token_type, expires_at,
                    refresh_token, scopes FROM users WHERE mxid=$1
        """
        row = await self.database.fetchrow(q, mxid)
        if row is None:
            return None
        return Token(
            access_token=row["token"],
            token_type=row["token_type"],
            scopes=row["scopes"].split(),
            expires_in=None,
            expires_at=datetime.datetime.fromtimestamp(
                row["expires_at"], tz=datetime.timezone.utc
            ),
            refresh_token=row["refresh_token"],
        )

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

    async def _room_set_active(self, room: str, joined_timestamp: int) -> bool:
        """
        Returns True if timestamp is new or later than the last recorded one
        """
        q = """
            INSERT INTO active_rooms (room, joined_first, joined_last)
                    VALUES ($1, $2, $2)
        """
        try:
            await self.database.execute(q, room, joined_timestamp)
        except sqlite3.IntegrityError:
            _, last = await self._room_active_since(room)
            if last is not None and last >= joined_timestamp:
                return False
            q = """
                UPDATE active_rooms SET joined_last=$2 WHERE room=$1
            """
            await self.database.execute(q, room, joined_timestamp)
        return True

    async def _room_active_since(self, room: str) -> (int, int):
        q = """
            SELECT joined_first, joined_last FROM active_rooms WHERE room=$1
        """
        row = await self.database.fetchrow(q, room)
        return (
            (
                row["joined_first"],
                row["joined_last"],
            )
            if row
            else None
        )

    def _get_playlist_id(self, playlist_url: str) -> Union[str, None]:
        m = RE_SPOTIY_PLAYLIST.match(playlist_url)
        return m.group(3) if m else None

    def _get_playlist_url(self, playlist_id: str) -> str:
        return f"https://open.spotify.com/playlist/{playlist_id}"

    async def _is_logged_in(self, mxid: str) -> bool:
        return (await self._get_user_token(mxid)) is not None

    def _get_auth_url(self, mxid: str) -> str:
        userkey = str(uuid4())
        self.tempdata.put(
            userkey,
            AuthData(
                mxid=mxid,
                oauth=self._new_oauth_flow(),
            ),
        )
        return self.webapp_url.human_repr() + "/auth?s=" + userkey

    def _callback_url(self) -> str:
        return self.webapp_url.human_repr() + CALLBACK_PATH

    def _new_oauth_flow(self, token: Union[Token, None] = None) -> OauthFlow:
        return OauthFlow(
            token=token,
            client_id=self.config["spotify_client_id"],
            client_secret=self.config["spotify_client_secret"],
            redirect_uri=self._callback_url(),
            scope=["playlist-modify-private"],
            disable_builtin_server=True,
        )
