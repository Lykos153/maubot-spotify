

== Datenstruktur

Global (aus Config):
* Client ID & Secret
* Public URL
---
Raum => Playlist
---
mxid => Spotify User
mxid => control room
---
Spotify User => Auth Token etc.

== Config functions
* get client id & secret
* get public url

== Model (db) functions
* get user by mxid
* get pl by room
* get control room by mxid

== Spotify functions:
* Add song to pl
  * Check for duplicates
  => return success/failure/already added when
* Add (best/first) song of album to pl
  * Get (best/first) song from album
  => return which song was added

== Bot funktions:
* Listen for track links
  => give some kind of feedback. reactions? what to return
* Listen for album links
  => give some kind of feedback. reactions?
* Authenticate user
  * invite to control room for
* Set room playlist


== Fragen:
* Bot: Wie aktuellen Raum herausfinden?
* Bot: Wie reguläre Nachricht senden?
* Spotify: Wie Auth token übergeben
* Spotify: Wie Auth Flow für Bot implementieren?
* How to store everything in a database?
* How to act on all past history?
* Wie von der Konfig lesen?
