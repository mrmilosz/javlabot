#!/usr/bin/env python3

import socket
import signal
import sys
import re


network = 'irc.quakenet.org'
port = 6667
username = 'javlabot'
realname = 'JävlaBot'
channel = '#dfmap'


turkeys = {}
turkey_critical_mass = 20


# Each line from the server represents a message, which we should somehow handle
def handle_message(message):
	try:
		# First we have to get the ping out of the way
		if message.startswith('PING'):
			send('PONG ' + re.sub(r'[^\d]*', '', message))

		elif message.startswith(':'):
			sender, code, body = message.split(' ', 2)

			# 001 is the welcome code, and it means we can join channels
			if code == '001':
				send('JOIN ' + channel)

			# PRIVMSG is the turkey-hunting code
			elif code == 'PRIVMSG':
				print(sender)
				global turkeys
				turkey_name = re.match(r':([^!]*)!', sender).group(1)	
				if not turkey_name in turkeys:
					turkeys[turkey_name] = 0
				turkeys[turkey_name] += 1
				if turkeys[turkey_name] > turkey_critical_mass:
					send('PRIVMSG %s :jävla %s' % (channel, turkey_name))
					turkeys = {}

	except Exception as e:
		print('Exception: %s' % e)

# This is a blocking function, which listens for data from the IRC server forever
def listen():
	# Since responses may be broken up over packets, we use a buffer to wait for the next newline
	data_buffer = ''
	while True:
		lines = irc.recv(4096).decode('UTF-8').split('\r\n')
		lines[0] = data_buffer + lines[0]
		data_buffer = lines.pop()

		for message in lines:
			print('SERVER: ' + message)
			handle_message(message)

# Go through here to send messages to the IRC server
def send(message):
	print('CLIENT: ' + message)
	irc.send(bytes(message + '\r\n', 'UTF-8'))

# Make sure to disconnect cleanly on program exit
def exit_gracefully(signal, frame):
	print()
	send('QUIT')
	sys.exit(0)


# Connect to the IRC server
irc = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
irc.connect((network, port))
signal.signal(signal.SIGINT, exit_gracefully)

# Identify
send('NICK %s' % (username))
send('USER %s 0 * :%s' % (username, realname))

# Start botting
listen()
