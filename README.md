# maubot-spotify
Listens for spotify track links and adds them to a room specific playlist.

## Installation
### Prerequisites
* Sign up on https://developer.spotify.com
* Create a new app. Add yourself to the user allowlist.
* You'll need `client_id` and `client_secret`.

### Installation as a plugin
* Download mbp file from current [release](https://github.com/Lykos153/maubot-spotify/releases)
* Upload it to the maubot and create an instance, see https://docs.mau.fi/maubot/usage/basic.html
* Once the instance has started, add `client_id` and `client_secret` in the config field that shows up on the instance page (maybe you need to refresh)
* Restart the instance

## Usage
* Invite the bot to a room
* Login with your Spotify account using `!spotify login`
* Set a room playlist with `!spotify set playlist <playlist>`
* All future song links you send to the room will be added to the playlist by your Spotify user.
