# Intro
A utility program written in python using the libtcod library.  Warning: Contains spaghetti code.

The main program main.py requires
libtcod-1.5.1. which can be freely downloaded at:
http://doryen.eptalys.net/libtcod/download/

# Features
* Displays information about a SS13 server without needing to log into it.
 * Shows the number of players and admins on.
 * Shows the public gamemode (IE if it's secret, it displays secret, not the 'real' gamemode).
 * Shows the server's "version" (IE if it's using baycode or not)
 * (Bay/Goon only) Can list all ckeys online on that server.
* Friends list.
 * If the server supports it, highlights ckeys inside the player list green if they are on your friends list in the program.
* Auto-syncs to the current server every ten minutes.
* Guesses what time it is on the server in almost-real time.
* One button launch Dreemseeker and connect to the server.
 
# Roadmap
* Friend notification when a friend logs in.
* Ability to config auto-sync frequency.
* Ability to save a default server.
* Ability to hold a list of servers.

# Using
The utility is able to support servers using all major codebases (Baycode, /tg/ code, even gooncode surprisingly).
Features may be missing if using the program that isn't using baycode.

To connect to a server, type '1', type in the IP, then type '2' and type in the port, and press enter.
The program will query the server every ten minutes.  If you are lost, press '?' for a list of buttons to press.

#License

This program is free software; you can redistribute it and/or
modify it under the terms of the GNU General Public License
as published by the Free Software Foundation; either version 2
of the License, or (at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.
