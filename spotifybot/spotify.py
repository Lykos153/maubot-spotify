import spotipy
from spotipy.oauth2 import SpotifyOAuth


class Spotify:
    def __init__(self):
        scope = "playlist-modify-private"
        sp = spotipy.Spotify(auth_manager=SpotifyOAuth(scope=scope))

        pl_id = "0E77gEsMy0AuWi5Oi3RHLX"
        song_url = ["6zmEDMJ9MA4C4ZoPngpz0a"]

        result = sp.playlist_add_items(pl_id, song_url)
        print(result)


s = Spotify()
