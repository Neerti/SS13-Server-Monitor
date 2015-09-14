
#
#

import libtcodpy as libtcod
import time
import textwrap
import socket
import struct
import urlparse
import shelve
import webbrowser
import platform
import sound
import threading

try: #This won't work on linux/osx/anything else
	import balloontip
except:
	print 'Failed to import'

#actual size of the window
SCREEN_WIDTH = 80
SCREEN_HEIGHT = 30

CON_HEIGHT = SCREEN_HEIGHT
CON_WIDTH = SCREEN_WIDTH

LOG_HEIGHT = 20
LOG_WIDTH = SCREEN_WIDTH
LOG_Y = SCREEN_HEIGHT - LOG_HEIGHT
MSG_X = 1
MSG_WIDTH = LOG_WIDTH - 2
MSG_HEIGHT = LOG_Y - 2

STATUS_HEIGHT = 5
STATUS_WIDTH = SCREEN_WIDTH

PLAYER_WIDTH = 16

LIMIT_FPS = 20  #20 frames-per-second maximum

AUTOSYNC_OPTIONS = [5, 10, 20, 30, 60, 120] #minutes

player_pos = 6

class Server_Data():
	#Used to hold the data we fetch from the server.
	name = "The Server"
	address = "baystation12.net"
	port = 8000
	server = address,port
	status = None
	players = []
	admins = []
	players_num = 0
	admins_num = 0
	gamemode = "Extended"
	time = "12:00:00 PM"
	hour = 12
	minute = 0
	second = 0
	failed_sync = True
	reconnect = True
	reconnect_attempts = 3
	last_queried = 0
	alerted_end_of_round = False

	#Mloc's server method/function/whatever python calls it
	def Export(self, msg, get_reply = True):
		self.reconnect = True
		try:
			sock = socket.create_connection(self.server)
			#message('Server replied to query.',libtcod.green)
		except socket.error,e:
			print str(e)
			message('Failed to connect.',libtcod.red)
			message(e, libtcod.red)
			self.failed_sync = True
			return None

		sock.sendall(struct.pack('!xcH5x{}sx'.format(len(msg) + 1), b'\x83', len(msg) + 7, ('?' + msg)))

		if True:
			resp = sock.recv(5)

			length, typeid = struct.unpack('!xxHc', resp)
			length -= 1

			resp = ""
			while len(resp) != length:
				resp += sock.recv(length - len(resp)).decode('ascii')

			print resp
			resp = str(resp)
			if msg == 'status' or msg == 'status=2':
				self.status = urlparse.parse_qs(resp, keep_blank_values=False, strict_parsing=False)
				print self.status
				self.update_vars()
			self.failed_sync = False



			sock.close()

			ret = None

			if typeid == ('\x2a'): #float
				ret = struct.unpack('<f', (resp))[0] #most numbers in this format are big-endian, but floats are small-endian
			elif typeid == ('\x06'): #string
				ret = struct.unpack('!{}s'.format(length), (resp))[0][:-1].decode('ascii') #cut off trailing nullchar

			self.last_queried = Time.tick_total #Remember how recently we sent a query out to the server.
			return ret

		return "hi"

	def ping(self):
		return bool(self.Export_threaded('ping'))

	def update_vars(self):
		status = self.status
		#Different codebases are willing to give us certain information.  A lot of try/except statements should allow maximum server compatibility.
		try:
			self.name = str(status['version'][0])
		except:
			message('Server failed to supply the game version.',libtcod.orange)

		try:
			self.players_num = int(status['players'][0])
		except:
			message('Server failed to supply the number of players.',libtcod.orange)

		try:
			unfixed_admins_num = str(status['admins'][0])
			self.admins_num = int(unfixed_admins_num[:1]) #for some reason we get something like 4/x00 for four admins, so this works around this.
		except:
			message('Server failed to supply amount of admins.',libtcod.orange)

		try:
			self.gamemode = str(status['mode'][0].title())
		except:
			message('Server failed to supply the gamemode.',libtcod.orange)

		try: #/TG/ servers do not provide the station time or a list of players.
			station_time = str(status['roundduration'][0])
			station_time = station_time.split(":") #Split the string into hours and minutes.

			old_hour = self.hour #Store the old hour before updating
			self.hour = int(station_time[0])
			new_round_hour = self.hour

			self.minute = int(station_time[1])

			#Now we try to guess if a new round started or not.

			if new_round_hour < old_hour: #If round duration went from three hours to zero, it means we have a new round.
				print 'New round assumed to be true.'
				#message('A new round has started.',libtcod.cyan)
				User.notify_new_round()
				Server.alerted_end_of_round = False
		except:
			print 'Failed to get server time.'
			message('Server failed to supply the round duration.  The round duration is inaccurate, and notifications for the end of round will not work.',libtcod.orange)

		try:
			times_to_iterate = int(self.players_num)
			iterated = 0
			target = 'player' + str(iterated)
			self.players = []

			while iterated <= times_to_iterate - 1:
				player = str(status[target][0])
				self.players.append(player)
				iterated += 1
				target = 'player' + str(iterated)

			self.update_seen_friends()
			self.players.sort()
			sort_friends_list()
		except:
			print 'Failed to retrieve list of players.'
			message('Server failed to supply a list of players.  Friends list checking will be disabled.',libtcod.orange)
		libtcod.console_clear(con)
		message('Data synchronized with the server.',libtcod.grey)



	def Export_threaded(self, msg, get_reply = True):
		t = threading.Thread(target=self.Export,args=[msg, get_reply])
		t.start()

	def update_seen_friends(self):
		User.most_recent_friends = []
		#First, we add people we just saw.
		for player in self.players:
			if player in User.friends_list: #Are they our friends?
				if player not in User.seen_friends: #Are they also not already on the list?
					User.seen_friends.append(player)
					User.most_recent_friends.append(player)
		#Now we remove friends who aren't on from the online list.
		for friend in User.seen_friends:
			if friend not in self.players:
				User.seen_friends.remove(friend)
		User.notify_friends()


	def count_time(self):
		#Asking the server for what time it is every second will get costly, annoying, and slow, so instead we count locally and resync every time we query the server.
		second_str = ""
		minute_str = ""
		hour_str = ""

		self.second += 1
		if self.second >= 60:
			self.minute += 1
			self.second = 0
		if self.minute >= 60:
			self.hour += 1
			self.minute = 0
		if self.hour >= 24:
			self.hour = 0

		#Now we handle converting to 12h format, if that is what the user wants.
		if User.convert_to_12_hours is True:
			if self.hour >= 12:
				converted_hour = self.hour - 12
			else:
				converted_hour = self.hour
		else:
			converted_hour = self.hour


		#Now to add zeros for padding, if needed.
		second_str = str(self.second)
		minute_str = str(self.minute)
		hour_str = str(converted_hour)

		if self.second <= 9:
			second_str = '0' + str(self.second)
		if self.minute <= 9:
			minute_str = '0' + str(self.minute)
		if converted_hour <= 9:
			hour_str = '0' + str(converted_hour)

		#I don't expect rounds to literally last days, so we don't need to count higher.
		self.time = str(hour_str) + ':' + str(minute_str) + ':' + str(second_str)

	def reload_address(self):
		self.server = self.address,self.port

	def disconnect(self):
		self.failed_sync = True
		self.disconnect_attempts = 3
		self.players_num = 0
		self.admins_num = 0
		self.players = []
		self.admins = []
		self.reconnect = False
		message('Disconnected from ' + self.address + ':' + str(self.port) + '.')

	def is_player_online(self, ckey):
		if ckey in self.players:
			return True
		return False

class User_Data():
	#Holds config options and other client-related stuff.
	name = "User"
	friend_notify = True
	roundend_notify = True
	convert_to_12_hours = True
	autosync_frequency = 10 #minutes
	autosync_index = 1
	server_dict = 	{
					'Baystation12' : 'baystation12.net:8000',
					'/TG/Station13 1' : 'game.tgstation13.org:1337',
					'/TG/Station13 2' : 'game.tgstation13.org:2337'
					}
	current_server_dict_index = 0
	friends_list = []
	sorted_friends_list = []
	seen_friends = []
	most_recent_friends = []

	def is_friend(self, ckey):
		if ckey in self.friends_list:
			return True
		return False

	def add_friend(self, ckey):
		if ckey:
			if ckey == "":
				return
			if self.is_friend(ckey):
				message(ckey + ' is already on your friends list.')
			else:
				self.friends_list.append(ckey)
				message(ckey + ' was added to your friends list.')
			libtcod.console_clear(con)
			sort_friends_list()

	def remove_friend(self, ckey):
		if self.is_friend(ckey):
			self.friends_list.remove(ckey)
			message(ckey + ' was removed from your friends list.')
		else:
			message(ckey + ' was not on your friends list to begin with.')
		libtcod.console_clear(con)
		sort_friends_list()

	def notify_friends(self):
		if self.friend_notify is False: #Don't annoy the user if they don't want to see/hear the notifications.
			return
		if not self.most_recent_friends: #Empty list
			return
		recent_friends = ', '.join(self.most_recent_friends)
		msg = recent_friends + ' is online at ' + str(Server.address) + ':' + str(Server.port) + '.'
		message(msg,libtcod.green)
		balloon_tip('SS13 Server Monitor',msg)
		sound.playWAV_threaded('friend_log_in.wav')
		most_recent_friends = [] #Since we just declared that they're online, they're not considered 'recent'.

	def notify_roundend(self):
		if self.roundend_notify is False: #Don't annoy the user if they don't want to see this one too.
			return
		msg = 'The round on ' + str(Server.address) + ':' + str(Server.port) + ' may have a vote to end the round soon.'
		message(msg,libtcod.green)
		balloon_tip('SS13 Server Monitor',msg)
		sound.playWAV_threaded('friend_log_in.wav')
		print 'Notifed of round ending.'

	def notify_new_round(self):
		if self.roundend_notify is False: #Don't annoy the user if they don't want to see this one too.
			return
		msg = 'There is a new round on ' + str(Server.address) + ':' + str(Server.port) + '.  The gamemode is ' + Server.gamemode + '.'
		message(msg,libtcod.cyan)
		balloon_tip('SS13 Server Monitor',msg)
		sound.playWAV_threaded('friend_log_in.wav')
		print 'Notifed of new round.'

class Timer():
	#Handles doing stuff every so often.
	tick_total = 0
	def tick(self):
		if self.tick_total is None:
			self.tick_total = 0
		self.tick_total += 1
		self.interpolate_time()
	def interpolate_time(self):
		if self.tick_total % (20) == 0: #one second
			Server.count_time() #Make the estimated game time tick.
		if self.tick_total % (User.autosync_frequency * 1200) == 0 and Server.reconnect is True: #ten minutes by default
			Server.Export_threaded('status',True) #Resync with the server
		#print 'Hour: ' + str(Server.hour) + '  Minute: ' + str(Server.minute)
		if Server.hour >= 2 and Server.hour != 12 and Server.minute >= 50 and Server.alerted_end_of_round is False: #A dirty hack until I can figure out a futureproof'd way
			User.notify_roundend()
			Server.alerted_end_of_round = True

def text_input():
	timer = 0
	x = 0
	window_x = 1
	window_y = SCREEN_HEIGHT - 1
	command = ''
	libtcod.console_print_ex(0, window_x-1, window_y, libtcod.BKGND_NONE, libtcod.LEFT, '>')
	libtcod.console_set_char_foreground(0, window_x-1, window_y, libtcod.white)
	while not libtcod.console_is_window_closed():

		key = libtcod.console_check_for_keypress(libtcod.KEY_PRESSED)

		timer += 1
		if timer % (LIMIT_FPS // 4) == 0:
			if timer % (LIMIT_FPS // 2) == 0:
				timer = 0
				libtcod.console_set_char(0,  window_x+x,  window_y, "_")
				libtcod.console_set_char_foreground(0, window_x+x, window_y, libtcod.white)
			else:
				libtcod.console_set_char(0, window_x+x,  window_y, " ")
				libtcod.console_set_char_foreground(0, window_x+x, window_y, libtcod.white)

		if key.vk == libtcod.KEY_BACKSPACE and x > 0:
			libtcod.console_set_char(0, window_x+x,  window_y, " ")
			libtcod.console_set_char_foreground(0, window_x+x, window_y, libtcod.white)
			command = command[:-1]
			x -= 1
		elif key.vk == libtcod.KEY_ENTER:
			break
		elif key.vk == libtcod.KEY_ESCAPE:
			command = ""
			break
		elif key.c > 0:
			letter = chr(key.c)
			libtcod.console_set_char(0, window_x+x, window_y, letter)  #print new character at appropriate position on screen
			libtcod.console_set_char_foreground(0, window_x+x, window_y, libtcod.white)
			command += letter  #add to the string
			x += 1

		libtcod.console_flush()

	libtcod.console_clear(0)
	return command


def message(new_msg, color = libtcod.white, timestamp = True, append = True, ):
	if timestamp is True:
		new_msg = str(time.strftime('[%H:%M:%S %p] ')) + str(new_msg)
	#split the message if necessary, among multiple lines
	new_msg_lines = textwrap.wrap(new_msg, MSG_WIDTH)

	for line in new_msg_lines:
		#if the buffer is full, remove the first line to make room for the new one
		if len(messages) == MSG_HEIGHT:
			del messages[0]

		#add the new line as a tuple, with the text and the color
		if append:
			messages.append( (line, color) )
		else: #We want multiple messages on the same line, if possible.
			if messages:
				new_msg = messages.pop()
				if color == libtcod.white and new_msg[1] is not color:
					color = new_msg[1]
				new_msg = new_msg[0]

				messages.append( (new_msg + '  ' + line, color) )
			else: #We have an empty list
				messages.append( (line, color) )

def render_all():
	global player_pos
	y = player_pos
	f_y = player_pos

	P = Server.players[:]

	first_column_x = 10
	second_column_x = 25
	third_column_x = 40
	amount_per_column = Server.players_num // 3 + 1
	size_of_column = 0
	x = first_column_x
	switched_to_second_column = False
	switched_to_third_column = False

	line = Server.players
	n = amount_per_column
	columns_list = [line[i:i+n] for i in range(0, len(line), n)]
	#print columns_list

	every_other = False


	for player in Server.players:
		#The ckey is colored different depending on if they're on the user's friends list or not.
		color = libtcod.white
		if every_other is True:
			color = libtcod.lightest_grey
		every_other = not every_other
		if User.is_friend(player):
			color = libtcod.green
		if User.name == player: #Give an ego boost if the player's on the server
			color = libtcod.cyan

		libtcod.console_set_default_foreground(con, color)

		#We want the player list to be split into two columns if possible.
		if player in columns_list[0]:
			x = first_column_x
		elif player in columns_list[1]:
			x = second_column_x
			if switched_to_second_column is False:
				y = player_pos
				switched_to_second_column = True
		else:
			x = third_column_x
			if switched_to_third_column is False:
				y = player_pos
				switched_to_third_column = True

		#split the message if necessary, among multiple lines.  Some ckeys are stupid long.
		new_lines = textwrap.wrap(player, PLAYER_WIDTH)
		for line in new_lines:
			#Now we display the ckey, wrapping around multiple lines if needed.
			libtcod.console_print_ex(con, x, y, libtcod.BKGND_NONE, libtcod.CENTER, line)
			y += 1
		size_of_column += 1
	size_of_columns = 0

	for friend in User.sorted_friends_list:
		color = libtcod.grey
		if Server.is_player_online(friend): #If the user's friend is online, highlight them in green.
			color = libtcod.green

		libtcod.console_set_default_foreground(con, color)

		new_lines = textwrap.wrap(friend, PLAYER_WIDTH)
		for line in new_lines:
			#Now we display the ckey, wrapping around multiple lines if needed.
			libtcod.console_print_ex(con, SCREEN_WIDTH-SCREEN_WIDTH/5, f_y, libtcod.BKGND_NONE, libtcod.CENTER, line)
			f_y += 1

	#Make some boxes around the GUI
	libtcod.console_set_default_foreground(con, libtcod.white)

	libtcod.console_print_frame(con, 50, 5, CON_WIDTH - 50 , CON_HEIGHT - 15, False, libtcod.BKGND_NONE, 'Friends')
	libtcod.console_print_frame(con, 0, 5, CON_WIDTH - 30, CON_HEIGHT // 2, False, libtcod.BKGND_NONE, 'Player List')

	#blit the contents of "con" to the root console
	libtcod.console_blit(con, 0, 0, CON_WIDTH, CON_HEIGHT, 0, 0, 0)

	#prepare to render the GUI panel
	libtcod.console_set_default_background(status, libtcod.black)
	libtcod.console_clear(status)
	libtcod.console_clear(log)

	#print the game messages, one line at a time
	libtcod.console_set_default_foreground(log, libtcod.white)
	libtcod.console_print_frame(log, 0, 0, LOG_WIDTH , LOG_HEIGHT // 2, False, libtcod.BKGND_NONE, 'Log')
	y = 1
	for (line, color) in messages:
		libtcod.console_set_default_foreground(log, color)
		libtcod.console_print_ex(log, MSG_X, y, libtcod.BKGND_NONE, libtcod.LEFT, line)
		y += 1

	libtcod.console_print_ex(status, 0, 0, libtcod.BKGND_NONE, libtcod.LEFT, 'Server Address: ' + Server.address + ':' + str(Server.port))

	libtcod.console_print_ex(status, 0, 1, libtcod.BKGND_NONE, libtcod.LEFT, 'Version: ')
	if Server.failed_sync is False:
		libtcod.console_set_default_foreground(status, libtcod.white)
		libtcod.console_print_ex(status, 9, 1, libtcod.BKGND_NONE, libtcod.LEFT, Server.name)
	else:
		libtcod.console_set_default_foreground(status, libtcod.red)
		libtcod.console_print_ex(status, 9, 1, libtcod.BKGND_NONE, libtcod.LEFT, 'UNKNOWN')
	libtcod.console_set_default_foreground(status, libtcod.white)

	libtcod.console_print_ex(status, 0, 2, libtcod.BKGND_NONE, libtcod.LEFT, 'Players: ')
	if Server.players_num == 0:
		libtcod.console_set_default_foreground(status, libtcod.red)
	else:
		libtcod.console_set_default_foreground(status, libtcod.white)
	libtcod.console_print_ex(status, 9, 2, libtcod.BKGND_NONE, libtcod.LEFT, str(Server.players_num))
	libtcod.console_set_default_foreground(status, libtcod.white)

	libtcod.console_print_ex(status, 20, 2, libtcod.BKGND_NONE, libtcod.LEFT, 'Admins: ')
	if Server.admins_num == 0:
		libtcod.console_set_default_foreground(status, libtcod.red)
	else:
		libtcod.console_set_default_foreground(status, libtcod.white)
	libtcod.console_print_ex(status, 28, 2, libtcod.BKGND_NONE, libtcod.LEFT, str(Server.admins_num))
	libtcod.console_set_default_foreground(status, libtcod.white)

	libtcod.console_print_ex(status, 0, 3, libtcod.BKGND_NONE, libtcod.LEFT, 'Gamemode: ')
	if Server.failed_sync is False:
		libtcod.console_print_ex(status, 10, 3, libtcod.BKGND_NONE, libtcod.LEFT, Server.gamemode)
	else:
		libtcod.console_set_default_foreground(status, libtcod.red)
		libtcod.console_print_ex(status, 10, 3, libtcod.BKGND_NONE, libtcod.LEFT, 'UNKNOWN')
	libtcod.console_set_default_foreground(status, libtcod.white)

	libtcod.console_print_ex(status, 0, 4, libtcod.BKGND_NONE, libtcod.LEFT, 'Status: ')
	if Server.failed_sync is False:
		libtcod.console_set_default_foreground(status, libtcod.green)
		libtcod.console_print_ex(status, 8, 4, libtcod.BKGND_NONE, libtcod.LEFT, 'Connected')
	else:
		libtcod.console_set_default_foreground(status, libtcod.red)
		libtcod.console_print_ex(status, 8, 4, libtcod.BKGND_NONE, libtcod.LEFT, 'DISCONNECTED')
	libtcod.console_set_default_foreground(status, libtcod.white)
	if User.convert_to_12_hours is False:
		libtcod.console_print_ex(status, SCREEN_WIDTH - 1, 0, libtcod.BKGND_NONE, libtcod.RIGHT, 'Sys Time: ' + str(time.strftime('%H:%M:%S %p')))
	else:
		libtcod.console_print_ex(status, SCREEN_WIDTH - 1, 0, libtcod.BKGND_NONE, libtcod.RIGHT, 'Sys Time: ' + str(time.strftime('%I:%M:%S %p')))

	if Server.failed_sync is False:
		libtcod.console_print_ex(status, SCREEN_WIDTH - 4, 1, libtcod.BKGND_NONE, libtcod.RIGHT, 'Round Duration: ' + str(Server.time))
	else:
		libtcod.console_print_ex(status, SCREEN_WIDTH - 4, 1, libtcod.BKGND_NONE, libtcod.RIGHT, 'Round Duration: ??:??:??')

	if User.autosync_frequency % 60 == 0: #So we can display hours instead of minutes.
		libtcod.console_print_ex(status, SCREEN_WIDTH - 1, 2, libtcod.BKGND_NONE, libtcod.RIGHT, 'Auto-sync interval: ' + str(User.autosync_frequency // 60) + 'h')
	else:
		libtcod.console_print_ex(status, SCREEN_WIDTH - 1, 2, libtcod.BKGND_NONE, libtcod.RIGHT, 'Auto-sync interval: ' + str(User.autosync_frequency) + 'm')

	if User.friend_notify is True:
		libtcod.console_print_ex(status, SCREEN_WIDTH - 1, 3, libtcod.BKGND_NONE, libtcod.RIGHT, 'Notify on friend log-in: On')
	else:
		libtcod.console_print_ex(status, SCREEN_WIDTH - 1, 3, libtcod.BKGND_NONE, libtcod.RIGHT, 'Notify on friend log-in: Off')

	if User.roundend_notify is True:
		libtcod.console_print_ex(status, SCREEN_WIDTH - 1, 4, libtcod.BKGND_NONE, libtcod.RIGHT, 'Notify on estimated end of round: On')
	else:
		libtcod.console_print_ex(status, SCREEN_WIDTH - 1, 4, libtcod.BKGND_NONE, libtcod.RIGHT, 'Notify on estimated end of round: Off')

	libtcod.console_set_default_background(log, libtcod.black)

	#blit the contents of "status" to the root console
	libtcod.console_blit(status, 0, 0, STATUS_WIDTH, STATUS_HEIGHT, 0, 0, 0)

	#blit the contents of "log" to the root console
	libtcod.console_blit(log, 0, 0, LOG_WIDTH, LOG_HEIGHT, 0, 0, SCREEN_HEIGHT - LOG_Y)

def handle_keys():
	global player_pos

	if key.vk == libtcod.KEY_ESCAPE:
		return 'exit'  #exit game

	elif key.vk == libtcod.KEY_ENTER:
		if Server.failed_sync == True:
			message('Attempting to query ' + Server.address + ':' + str(Server.port) +  ' . . .', libtcod.white)
			Server.Export_threaded('status',True)
		else:
			message('You are already connected to a server.  If you want to see another server\'s stats, you must disconnect first.', libtcod.white)

	elif key.vk == libtcod.KEY_SPACE:
		'''
		print 'Last queried: ' + str(Server.last_queried)
		print 'Current tick total: ' + str(Time.tick_total)
		print 'Conditional: ' + str(Time.tick_total - 1200)
		'''
		if Server.failed_sync == True:
			message('You need to connect to the server first.  Press [Enter].')
			return
		if Server.last_queried >= Time.tick_total - 1200: #One minute
			message('You already queried the server less then a minute ago, be patient!')
			return
		message('Manually querying ' + str(Server.address) + ':' + str(Server.port) + '.', libtcod.white)
		Server.Export_threaded('status',True) #Resync with the server

	elif key.vk == libtcod.KEY_UP:
		if player_pos <= 5:
			player_pos += 1
		libtcod.console_clear(con)

	elif key.vk == libtcod.KEY_DOWN:
		player_pos -= 1
		libtcod.console_clear(con)


	else:
		#test for other keys
		key_char = chr(key.c)
		if key_char == '?':
			#message('Press [Enter] to connect to the selected server.  Press [D] to disconnect from the server.  Press [Space] to do a manual query.  Press [F] to add a ckey to your friends list.  Press [G] to launch Dreamseeker and connect to the server you\'re monitoring.  Press [1] to enter a new target IP.  Press [2] to enter a new target port number.  Press [N] to choose a new username.  Press [P] to toggle friend notifications.  Press [UP] or [DOWN] to scroll, or use the [Scrollwheel].  Press [Esc] to quit the application.',libtcod.cyan)
			message('Connecting: Press [Enter] to connect to the selected server.  Press [D] to disconnect from the server. Press [Space] to do a manual query.  Press [+] or [-] to adjust the autosync frequency.  Press [G] to launch Dreamseeker and connect to the server you\'re monitoring.  Press [Esc] to quit the application.',libtcod.cyan, False)
			message('Friends: Press [F] to add a ckey to your friends list.  Press [R] to remove a ckey from your friends list.  Press [P] to toggle friend notifications.  Press [N] to choose a new username.',libtcod.green, False)
			message('Navigation: Press [UP] or [DOWN], or use the [Scrollwheel] to scroll.',libtcod.white, False)

		if key_char == '1':
			if Server.failed_sync is False:
				message('Disconnect from the server first.  You can do so by pressing [D].')
				return
			Server.address = str(text_input())
			Server.reload_address()

		if key_char == '2':
			if Server.failed_sync is False:
				message('Disconnect from the server first.  You can do so by pressing [D].')
				return
			try:
				Server.port = int(text_input())
				Server.reload_address()
			except:
				message('Ports can only consist of numbers.  Please try again.')

		if key_char == 'd':
			Server.disconnect()
			libtcod.console_clear(con)

		if key_char == 'n':
			User.name = text_input()
			message('Your new name is '+ User.name + '.')

		if key_char == 'f':
			friend = text_input()
			User.add_friend(friend)
			save_config()

		if key_char == 'r':
			ex_friend = text_input()
			User.remove_friend(ex_friend)
			save_config()

		if key_char == 'g':
			message('Attempting to launch Dreemseeker and connect to the server.')
			try:
				url = "byond://" + str(Server.address) + ":" + str(Server.port)
				webbrowser.open(url)
			except:
				message('Could not launch Dreemseeker.',libtcod.red)

		if key_char == 'p':
			User.friend_notify = not User.friend_notify
			if User.friend_notify:
				message('You will now be notified if a friend is seen.')
			else:
				message('You will no longer be notified if a friend is seen.')

		if key_char == 'o':
			User.roundend_notify = not User.roundend_notify
			if User.roundend_notify:
				message('You will now be notified when the round is about to end and when a new rounds starts.')
			else:
				message('You will no longer be notified when the round is about to end and when a new rounds starts.')

		if key_char == '+':
			if User.autosync_index != len(AUTOSYNC_OPTIONS) - 1: #Prevent out of bound errors.
				User.autosync_index += 1
				User.autosync_frequency = AUTOSYNC_OPTIONS[User.autosync_index]
			else:
				message('Autosync cannot go any higher than ' + str(AUTOSYNC_OPTIONS[User.autosync_index]) + ' minutes.')

		if key_char == '-':
			if User.autosync_index != 0: #Prevent out of bound errors.
				User.autosync_index -= 1
				User.autosync_frequency = AUTOSYNC_OPTIONS[User.autosync_index]
			else:
				message('Autosync cannot go any lower than ' + str(AUTOSYNC_OPTIONS[User.autosync_index]) + ' minutes.')

		if key_char == 't':
			User.convert_to_12_hours = not User.convert_to_12_hours
			if User.convert_to_12_hours:
				message('Your times will now be displayed in twelve hour format.')
			else:
				message('Your times will now be displayed in twenty four hour format.')



def balloon_tip(title='Beep', msg='Boop'):
	my_os = platform.system()
	if my_os is not 'Windows':
		print 'balloon tips are a windows only feature.  Sorry.'
		return
	else:
		balloontip.WindowsBalloonTip(title, msg)

def sort_friends_list():
	half_sorted_friends_list = []
	half_sorted_friends_list = sorted(User.friends_list)
	User.sorted_friends_list = []
	online_friends = []
	offline_friends = []
	for ckey in half_sorted_friends_list:
		if Server.is_player_online(ckey):
			online_friends.append(ckey)
		else:
			offline_friends.append(ckey)

	User.sorted_friends_list = online_friends + offline_friends

#	print "Sorted friends"
#	print(User.sorted_friends_list)
#	print "Unsorted friends"
#	print(User.friends_list)
#	print "Online friends"
#	print(online_friends)
#	print "Offline friends"
#	print(offline_friends)

def save_config():
	#open a new empty shelve (possibly overwriting an old one) to write the config data
	file = shelve.open('config', 'n')
	file['user'] = User
	file['friends_list'] = User.friends_list
	file['friend_notify'] = User.friend_notify
	file['server'] = Server
	file['address'] = Server.address
	file['port'] = Server.port
	file.close()

def load_config():
	#open the previously saved shelve and load the config data
	global User, Server

	file = shelve.open('config', 'r')
	User = file['user']
	User.friends_list = file['friends_list']
	User.friend_notify = file['friend_notify']
	Server = file['server']
	Server.address = file['address']
	Server.port = file['port']
	file.close()

	message('Welcome back, '+ User.name + '!', libtcod.green)

def start():
	player_action = None
	global player_pos
	while not libtcod.console_is_window_closed():
		#render the screen
		libtcod.sys_check_for_event(libtcod.EVENT_KEY_PRESS|libtcod.EVENT_MOUSE,key,mouse)
		render_all()
		Time.tick()

		libtcod.console_flush()


		#handle keys and exit if needed

		player_action = handle_keys()

		if mouse.wheel_up:
			if player_pos <= 5:
				player_pos += 1
			libtcod.console_clear(con)

		elif mouse.wheel_down:
			player_pos -= 1
			libtcod.console_clear(con)

		if player_action == 'exit':
			Server.disconnect()
			save_config()
			break

def initialize():
	global messages, Server, User, Time, The_Server
	Server = Server_Data()
	User = User_Data()
	Time = Timer()
	#create the list of messages and their colors, starts empty
	messages = []
	try:
		load_config()
	except:
		message('No config file found.  One will be made for you soon.')
		message('Hello, ' + User.name + '!', libtcod.green)
	message('Not connected to the server.  Press [Enter] to attempt to connect, or press [Escape] to exit the program.  Press [?] to a list of keys.', libtcod.grey)


if __name__ == '__main__':
	libtcod.console_set_custom_font('terminal8x12_gs_tc.png', libtcod.FONT_TYPE_GREYSCALE | libtcod.FONT_LAYOUT_TCOD)
	libtcod.console_init_root(SCREEN_WIDTH, SCREEN_HEIGHT, 'SS13 Server Monitor', False)
	libtcod.sys_set_fps(LIMIT_FPS)

	key=libtcod.Key()
	mouse=libtcod.Mouse()
	con = libtcod.console_new(CON_WIDTH, CON_HEIGHT)
	log = libtcod.console_new(LOG_WIDTH, LOG_HEIGHT)
	status = libtcod.console_new(STATUS_WIDTH, STATUS_HEIGHT)
	initialize()
	start()
