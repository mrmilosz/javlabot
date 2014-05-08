#!/usr/bin/env python3

import socket
import signal
import sys
import argparse
import datetime
import unicodedata
import string
import errno

def main():
	global args, irc, listening, turkeys, normalized_triggers, normalized_nicks

	try:
		parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter, description='An IRC bot that swears at people in Swedish when they talk too much.')
		parser.add_argument('--host'         , default='localhost', type=str,            help='the IRC server to which to connect')
		parser.add_argument('--port'         , default=6667       , type=int,            help='the port on which to connect')
		parser.add_argument('--channels'     , default='#javla'   , type=str,            help='the channel(s) to join')
		parser.add_argument('--username'     , default='javlabot' , type=str,            help='the username that the bot will use')
		parser.add_argument('--realname'     , default='JävlaBot' , type=str,            help='the WHOIS name for the bot')
		parser.add_argument('--critical_mass', default=20         , type=int,            help='after how many posts to insult')
		parser.add_argument('--bad_word'     , default='jävla'    , type=str,            help='the word with which the bot responds')
		parser.add_argument('--triggers'     , default=['javla']  , type=str, nargs='+', help='words that set the bot off')
		args = parser.parse_args()

		# What sets the bot off
		normalized_triggers = [normalize(trigger) for trigger in args.triggers]
		normalized_nicks = [normalize(nick) for nick in (args.username, args.realname)]

		# For keeping track of who is talking the most
		turkeys = {}

		# For control over the listening loop
		listening = False

		# The socket
		irc = None

		connect()

		while True:
			try:
				listen()
			except socket.error as e:
				if e.errno != errno.ECONNRESET:
					raise
				disconnect()
				connect()

	except Exception as e:
		log(e)
		return 1

	return 0

# Connects to the IRC server
def connect():
	global args, irc

	irc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
	irc.connect((args.host, args.port))
	signal.signal(signal.SIGINT, exit_gracefully)

	# Identify
	send('NICK %s' % args.username)
	send('USER %s 0 * :%s' % (args.username, args.realname))

# Closes the connection and halts the listen function; unblocks the thread
def disconnect():
	global irc, listening

	irc.close()
	signal.signal(signal.SIGINT, signal.SIG_DFL)
	listening = False

# Handles a single line from the server
def handle_message(message):
	global args

	command, tail = get_token(message)

	# First we have to get the ping out of the way
	if command == b'PING':
		ident, tail = get_token(tail)
		if ident is not None:
			send('PONG %s' % ident.lstrip(b':').decode('utf8', 'ignore'))
		else:
			send('PONG')

	# Reconnect on timeout
	elif command == b'ERROR':
		if tail.startswith(b':Closing Link'):
			disconnect()
			connect()
			listen()

	elif command.startswith(b':'):
		source = command.lstrip(b':')
		command, tail = get_token(tail)

		decoded_username = source.split(b'!', 1)[0].decode('utf8', 'ignore')

		# 001 is the welcome code, and it means we can join channels
		if command == b'001':
			send('JOIN %s' % args.channels)

		# KICK means we say sorry, rejoin, and give the mad guy a bit of a break
		elif command == b'KICK':
			channel, tail = get_token(tail)
			decoded_channel = channel and channel.decode('utf8', 'ignore')
			victim_username, tail = get_token(tail)
			decoded_victim_username = victim_username and victim_username.decode('utf8', 'ignore')

			if decoded_victim_username == args.username:
				send('JOIN %s' % decoded_channel)
				send('PRIVMSG %s :sorry, %s, i will try to be a better bot' % (decoded_channel, decoded_username))
				update_turkey(decoded_channel, decoded_username, 'set', -args.critical_mass)

		# PRIVMSG is the turkey-hunting code
		elif command == b'PRIVMSG':
			channel, tail = get_token(tail)
			if channel and channel.startswith(b'#'):
				decoded_channel = channel.decode('utf8', 'ignore')
			else:
				decoded_channel = decoded_username
			text = tail.lstrip(b':')

			if find_trigger(text):
				send('PRIVMSG %s :%s %s' % (decoded_channel, args.bad_word, decoded_username))
				update_turkey(decoded_channel, decoded_username, 'set', 0)

			# Otherwise increment the turkey count and check for critical mass
			else:
				update_turkey(decoded_channel, decoded_username, 'add', 1)

				if turkey_cooked(decoded_channel, decoded_username):
					send('PRIVMSG %s :%s %s' % (decoded_channel, args.bad_word, decoded_username))
					reset_turkeys(decoded_channel)

# This is a blocking function, which listens for data from the IRC server forever
def listen():
	global irc, listening

	listening = True
	# Since responses may be broken up over packets, we use a buffer to wait for the next newline
	data_buffer = b''
	while listening:
		lines = irc.recv(4096).split(b'\r\n')
		lines[0] = data_buffer + lines[0]
		data_buffer = lines.pop()

		for message in lines:
			log('SERVER: %s' % message.decode('utf8', 'replace'))
			handle_message(message)

# Go through here to send messages to the IRC server
def send(message):
	global irc

	log('CLIENT: %s' % message)
	irc.send(('%s\r\n' % message).encode('utf8'))

# Makes sure to disconnect cleanly on program exit
def exit_gracefully(signal, frame):
	global args

	print()
	send('QUIT %s %s' % (args.bad_word, args.username))
	sys.exit(0)

# Returns whether or not the trigger text is in the PRIVMSG text
def find_trigger(text):
	global normalized_triggers, normalized_nicks

	try:
		decoded_message = text.decode('utf8', 'strict')
	except UnicodeError:
		decoded_message = text.decode('latin1', 'ignore')

	tokens = normalize(decoded_message).split(None)

	for first_token, second_token in zip(tokens[:-1], tokens[1:]):
		if first_token in normalized_triggers and second_token in normalized_nicks:
			return True
	return False

# Resets the turkey count
def reset_turkeys(channel):
	global turkeys

	turkeys[channel] = {}

# Modifies the turkey count
def update_turkey(channel, username, action, value):
	global turkeys

	if channel not in turkeys:
		turkeys[channel] = {}
	if username not in turkeys[channel]:
		turkeys[channel][username] = 0

	if action == 'set':
		turkeys[channel][username] = value
	elif action == 'add':
		turkeys[channel][username] += value

# Returns whether the turkey is ripe for hunting
def turkey_cooked(channel, username):
	global args, turkeys

	return channel in turkeys and username in turkeys[channel] and turkeys[channel][username] > args.critical_mass

# Returns the current ISO UTC date without miliseconds or timezone
def get_timestamp():
	return datetime.datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')

# Go through here to log things to the console
def log(*messages):
	print('%s %s' % (get_timestamp(), ''.join('[%s]' % message for message in messages)))

# Returns the first token and the tail
def get_token(bts):
	if bts is None:
		return (None, None)
	tokens = bts.split(None, 1)
	return tuple(tokens) if len(tokens) == 2 else (tokens[0], None)

# Returns the string without capitals or marks
def normalize(stri):
	return collate(stri).lower()

# Removes all marks from a string
def collate(stri):
	return ''.join(collate_char(c) for c in stri)

# Removes all marks from a character
def collate_char(char):
	try:
		return unicodedata.lookup(unicodedata.name(char).split(' WITH ', 1)[0])
	except (KeyError, ValueError):
		return char


if __name__ == '__main__':
	sys.exit(main())
