# Simple Server API with Users
# Copyright Brett Hartshorn 2012-2013
# License: "New" BSD

import os, sys, ctypes, time, json, struct, inspect
import random
import bpy

## make sure we can import and load data from same directory ##
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path: sys.path.append( SCRIPT_DIR )

import core
import Server
import simple_action_api
import api_gen
from api_gen import BlenderProxy, UserProxy, Animation, Animations
from websocket import websocksimplify


class UserServer( websocksimplify.WebSocketServer ):
	pass


class BlenderServer( core.BlenderHack ):

	def start_server(self):
		self.websocket_server = s = UserServer()
		host = Server.HOST_NAME
		port = 8080
		for arg in sys.argv:
			if arg.startswith('--port='):
				port = int( arg.split('=')[-1] )
			if arg.startswith('--ip='):
				a = arg.split('=')
				if len(a) == 2 and a[-1]:
					host = a[-1]

		Server.set_host_and_port( host, port )

		s.initialize(
			listen_host=host, 
			listen_port=port,
			read_callback=self.on_websocket_read_update,
			write_callback=self.on_websocket_write_update,
			new_client_callback=self.on_new_client,
		)
		lsock = s.create_listener_socket()
		s.start_listener_thread()


	def on_new_client(self, sock):
		addr = sock.getpeername()
		print('[on new client]', addr)

		if addr in Server.GameManager.clients:
			print('[websocket] RELOADING CLIENT:', addr )
			raise SystemExit
		else:
			print('_'*80)
			print('[websocket] NEW CLIENT:', addr )
			Server.GameManager.add_player( addr, websocket=sock )



	def on_websocket_read_update(self, sock, frames):
		'''
		protocol:
			if first byte is null, then the next 24 bytes is the camera location as packed floats,
			if its a single byte then its a keystroke,
			if it begins with "{" and ends with "}" then its a json message/request,
			otherwise it is part of the generated websocket api.
		'''

		player = Server.GameManager.get_player_by_socket( sock )
		if not player: return
		addr = player.address

		for frame in frames:
			if not frame: continue
			if frame[0] == 0:
				frame = frame[1:]
				if len(frame)!=24:
					print(frame)
					continue

				x1,y1,z1, x2,y2,z2 = struct.unpack('<ffffff', frame)
				#print(x1,y1,z1)
				if addr in Server.GameManager.clients:
					player = Server.GameManager.clients[ addr ]
					player.set_focal_point( (x2,y2,z2) )
					player.set_location( (x1,y1,z1) )    # callbacks get triggered
				else:
					print('[websocket ERROR] client address not in GameManager.clients')
					raise RuntimeError

			elif len(frame) == 1: ## TODO unicode 2bytes
				print(frame)
				print( frame.decode('utf-8') ) 

			elif len(frame) > 2 and chr(frame[0]) == '{' and chr(frame[-1]) == '}':
				jmsg = json.loads( frame.decode('utf-8') )
				print('client sent json data', jmsg)
				player.on_websocket_json_message( jmsg )

			else:
				print('doing custom action...', frame)
				## action api ##
				code = chr( frame[0] )
				action = player.new_action(code, frame[1:])
				## logic here can check action before doing it.
				if action:
					#assert action.calling_object
					action.do()


	_bps = 0
	_bps_start = None
	_debug_kbps = True
	def on_websocket_write_update(self, sock):
		player = Server.GameManager.get_player_by_socket( sock )
		msg = player.create_message_stream( bpy.context )
		if msg is None:
			#return None
			return bytes(0)

		rawbytes = json.dumps( msg ).encode('utf-8')
		if self._debug_kbps:
			now = time.time()
			self._bps += len( rawbytes )
			#print('frame Kbytes', len(rawbytes)/1024 )
			if self._bps_start is None or now-self._bps_start > 1.0:
				print('kilobytes per second', self._bps/1024)
				self._bps_start = now
				self._bps = 0
		return rawbytes


	def setup_websocket_callback_api(self, api):
		simple_action_api.create_callback_api( api )



class App( BlenderServer ):
	def __init__(self, api):
		print('init server app')
		self.setup_server(api)

	def setup_server(self, api):
		api.update( api_gen.get_decorated() )
		self.setup_websocket_callback_api(api)
		self.setup_blender_hack( bpy.context, use_gtk=False, headless=True )
		print('blender hack setup ok')
		Server.set_api( self )
		print('custom api set')

	def mainloop_poll(self, now, dt):  ## for subclasses to overload ##
		time.sleep(0.01)

	def mainloop(self):
		print('enter main')
		drops = 0
		self._mainloop_prev_time = time.time()
		self.active = True
		while self.active:
			now = time.time()
			dt = 1.0 / 30.0
			if now - self._mainloop_prev_time:
				dt = 1.0 / ( now - self._mainloop_prev_time )
			self._mainloop_prev_time = now
			#print('FPS', dt)

			for ob in bpy.data.objects:  ## this is threadsafe?
				#ob.update_tag( {'OBJECT', 'DATA', 'TIME'} )  ## super slow
				ob.update_tag( {'OBJECT'} )

			api_gen.AnimationManager.tick()
			bpy.context.scene.update()  ## required for headless mode

			fully_updated = self.update_blender()
			self.mainloop_poll(now, dt)


def default_click_callback( user=UserProxy, ob=BlenderProxy ):
	print('select callback', user, ob)
	w = api_gen.get_wrapped_objects()[ ob ]
	view = w( user )
	view['selected'] = time.time()  ## allow multiple selections, the server can filter to most recent to.
	if 0:
		view['location'] = list( ob.location.to_tuple() )
		#view['location'] = Animation( seconds=3.0, y=-5.0) # TODO relative and absolute
		view['location'] = Animations(
			Animation( seconds=3.0, y=-5.0),
			Animation( seconds=3.0, y=5.0),
			Animation( seconds=3.0, z=1.0),
			Animation( seconds=3.0, z=-1.0),
		)
		view['rotation_euler'] = list( ob.rotation_euler )
		view['rotation_euler'] = Animations(
			Animation( seconds=3.0, x=-5.0),
			Animation( seconds=3.0, x=5.0),
		)
		view().on_click = api_gen.get_callback( 'next1')

def next1( user=UserProxy, ob=BlenderProxy ):
	print('next click callback1')
	w = api_gen.get_wrapped_objects()[ ob ]
	view = w( user )
	view['color'] = [1,1,0, 1]
	view().on_click = api_gen.get_callback( 'next2')


def next2( user=UserProxy, ob=BlenderProxy ):
	print('next click callback2')
	w = api_gen.get_wrapped_objects()[ ob ]
	view = w( user )
	view['color'] = [0,1,1, 1]
	view().on_click = api_gen.get_callback( 'next3')


def next3( user=UserProxy, ob=BlenderProxy ):
	print('next click callback3')
	w = api_gen.get_wrapped_objects()[ ob ]
	view = w( user )
	view['color'] = Animations(
		Animation( seconds=2.0, x=0.5, y=0.5, z=0.1),
		Animation( seconds=2.0, x=1.0, y=0.1, z=0.5),
		Animation( seconds=2.0, z=1.0),
		Animation( seconds=2.0, z=-1.0),
	)
	#view[ '.modifiers["Bevel"].width' ] = 0.5  # this style is simple ## TODO mesh streaming so this can be tested, support bevel in dump_collada


def default_input_callback( user=UserProxy, ob=BlenderProxy, input_string=ctypes.c_char_p ):
	print( 'default INPUT CALLBACK', user, ob, input_string )
	#if ob.name == 'login':
	#	if 'login.input' not in bpy.data.objects:
	#		a = bpy.data.objects.new(
	#			name="[data] %s"%name, 
	#			object_data= a.data 
	#		)
	#		bpy.context.scene.objects.link( a )
	#		a.parent = ob
	w = api_gen.get_wrapped_objects()[ ob ]
	view = w( user )

API = {
	'default_click': default_click_callback,
	'default_input'	: default_input_callback,
	'next1' : next1,
	'next2' : next2,
	'next3' : next3,
}


if __name__ == '__main__':
	app = App( API )
	app.start_server()
	print('-----main loop------')
	app.mainloop()
