#!/usr/bin/env python3

import socket
import signal
import sys
import re
import argparse

parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter, description='An IRC bot that swears at people in Swedish when they talk too much.')
parser.add_argument('--host'         , default='localhost', type=str, help='the IRC server to which to connect')
parser.add_argument('--port'         , default=6667       , type=int, help='the port on which to connect')
parser.add_argument('--channels'     , default='#javla'   , type=str, help='the channel(s) to join')
parser.add_argument('--username'     , default='javlabot' , type=str, help='the username that the bot will use')
parser.add_argument('--realname'     , default='JävlaBot' , type=str, help='the WHOIS name for the bot')
parser.add_argument('--critical_mass', default=20         , type=int, help='after how many posts to insult')
args = parser.parse_args()

# For keeping track of who is talking the most
turkeys = {}

# Each line from the server represents a message, which we should somehow handle
def handle_message(message):

	# First we have to get the ping out of the way
	if message.startswith('PING'):
		send('PONG %s' % re.sub(r'[^\d]*', '', message))

	elif message.startswith(':'):
		tokens = message.split(' ', 2)

		if len(tokens) == 3:
			sender, code, body = tokens

			# 001 is the welcome code, and it means we can join channels
			if code == '001':
				send('JOIN %s' % args.channels)

			# PRIVMSG is the turkey-hunting code
			elif code == 'PRIVMSG':
				tokens = body.split(' ', 1)

				if len(tokens) == 2:
					channel, text = tokens

					# FORMAT: ":username!~user@host PRIVMSG #channel :the message"
					matches = re.match(r':([^!]*)!', sender)
					if matches is not None:
						username = matches.group(1)

						# Ensure that the current turkey is being tracked
						global turkeys
						if channel not in turkeys:
							turkeys[channel] = {}
						if username not in turkeys[channel]:
							turkeys[channel][username] = 0

						# If the turkey addressed the bot directly, respond in kind
						if re.search(r'\b[Jj][äa?]vla\b\s+(?:%s|%s)' % (args.username, args.realname), text):
							send('PRIVMSG %s :jävla %s' % (channel, username))
							turkeys[channel][username] = 0

						# Otherwise increment the turkey count and check for critical mass
						else:
							turkeys[channel][username] += 1

							if turkeys[channel][username] > args.critical_mass:
								send('PRIVMSG %s :jävla %s' % (channel, username))
								turkeys[channel] = {}

# This is a blocking function, which listens for data from the IRC server forever
def listen():
	# Since responses may be broken up over packets, we use a buffer to wait for the next newline
	data_buffer = ''
	while True:
		lines = irc.recv(4096).decode('UTF-8', 'replace').split('\r\n')
		lines[0] = data_buffer + lines[0]
		data_buffer = lines.pop()

		for message in lines:
			print('SERVER: %s' % message)
			handle_message(message)

# Go through here to send messages to the IRC server
def send(message):
	print('CLIENT: %s' % message)
	irc.send(('%s\r\n' % message).encode('UTF-8'))

# Make sure to disconnect cleanly on program exit
def exit_gracefully(signal, frame):
	print()
	send('QUIT jävla %s' % args.username)
	sys.exit(0)


# Connect to the IRC server
irc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
irc.connect((args.host, args.port))
signal.signal(signal.SIGINT, exit_gracefully)

# Identify
send('NICK %s' % args.username)
send('USER %s 0 * :%s' % (args.username, args.realname))

# Start botting
listen()
