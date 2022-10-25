import spotipy


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
        pl_id = playlist.id
        song_url = [song.id]

        result = self.sp.playlist_add_items(pl_id, song_url)
        print(result)


# s = SpotifyClient()
# s.add_song_to_playlist(
#     Playlist("0E77gEsMy0AuWi5Oi3RHLX"), Song("6zmEDMJ9MA4C4ZoPngpz0a")
# )

# spotipy.SpotifyClientCredentials()
