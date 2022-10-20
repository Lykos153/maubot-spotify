import spotipy
from spotipy.oauth2 import SpotifyOAuth


class SpotifyClient:
    def __init__(self):
        self.scope = "playlist-modify-private"
        self.sp = spotipy.Spotify(
            auth_manager=SpotifyOAuth(scope=self.scope, open_browser=True)
        )

    def add_song_to_playlist(self, playlist: str, song: str):
        pl_id = playlist
        song_url = [song]

        result = self.sp.playlist_add_items(pl_id, song_url)
        print(result)


s = SpotifyClient()
s.add_song_to_playlist("0E77gEsMy0AuWi5Oi3RHLX", "6zmEDMJ9MA4C4ZoPngpz0a")

# spotipy.SpotifyClientCredentials()
