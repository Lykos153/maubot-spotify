import spotipy
from spotipy2.auth.oauth_flow import ClientSession
from spotipy2.auth.oauth_flow import OauthFlow as OAF
from spotipy2.auth.oauth_flow import Token


# TODO: Remove once upstream fix has been released
class OauthFlow(OAF):
    async def refresh_token(self, http: ClientSession) -> Token:
        """
        ### Args
        - http: `ClientSession`, Aiohttp ClientSession to use

        ### Returns
        - `Token`, The access token

        ### Errors raised
        - None

        ### Function / Notes
        - None
        """
        API_URL = "https://accounts.spotify.com/api/token"
        data = {
            "refresh_token": self.token.refresh_token,
            "grant_type": "refresh_token",
        }

        HEADER = self.header

        async with http.post(API_URL, data=data, headers=HEADER) as r:
            response = await r.json()
            # Refresh token is not received on token refresh
            response["refresh_token"] = self.token.refresh_token
            self.token = await Token.from_dict(response)
            return self.token


class SpotifyElement:
    def __init__(self, id: str):
        self.id = id


class Playlist(SpotifyElement):
    def __init__(self, id):
        super().__init__(id)

    def name(self) -> str:
        pass


class Album(SpotifyElement):
    def __init__(self, id):
        super().__init__(id)


class Song(SpotifyElement):
    def __init__(self, id):
        super().__init__(id)


class SpotifyClient:
    def __init__(self, token):
        self.scope = "playlist-modify-private"
        self.sp = spotipy.Spotify(auth=token)

    def add_song_to_playlist(self, playlist: Playlist, song: Song):
        result = self.sp.playlist_add_items(playlist, [song])
        print(result)


# s = SpotifyClient()
# s.add_song_to_playlist(
#     Playlist("0E77gEsMy0AuWi5Oi3RHLX"), Song("6zmEDMJ9MA4C4ZoPngpz0a")
# )

# spotipy.SpotifyClientCredentials()
