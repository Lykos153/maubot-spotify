from .spotify import Playlist, SpotifyClient


class Data:
    def __init__(self):
        self._rooms: dict[str, Playlist] = {}
        self._users: dict[str, SpotifyClient] = {}

    def spotify_client_by_mxid(self, mxid: str) -> SpotifyClient:
        return self._users[mxid]

    def playlist_by_room(self, room: str) -> Playlist:
        return self._rooms[room]

    def set_room_playlist(self, room: str, playlist: Playlist):
        self._rooms[room] = playlist

    def set_spotify_user(self, mxid: str, spotify_user: SpotifyClient):
        self._users[mxid] = spotify_user


class TempData:
    def __init__(self):
        self._data: dict[str, str] = {}
        # TODO: expire or use expiringdict oder so

    def put(self, key: str, value: str) -> None:
        if key not in self._data:
            self._data[key] = value

    def get(self, key: str) -> str:
        return self._data.get(key)
