# Simple Server API with Users
# Copyright Brett Hartshorn 2012-2013
# License: "New" BSD

import os, sys, ctypes, time, json, struct
import random
import bpy

## make sure we can import and load data from same directory ##
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path: sys.path.append( SCRIPT_DIR )

import core
import Server
import simple_action_api
import api_gen
from api_gen import BlenderProxy, UserProxy
from websocket import websocksimplify

def default_click_callback( user=UserProxy, ob=BlenderProxy ):
	print('select callback', user, ob)
	w = api_gen.get_wrapper_objects()[ ob ]


def default_input_callback( user=UserProxy, ob=BlenderProxy, input_string=ctypes.c_char_p ):
	print( 'default INPUT CALLBACK', user, ob, input_string )
	if ob.name == 'login':
		if 'login.input' not in bpy.data.objects:
			a = bpy.data.objects.new(
				name="[data] %s"%name, 
				object_data= a.data 
			)
			bpy.context.scene.objects.link( a )
			a.parent = ob


API = {
	'default_click': default_click_callback,
	'default_input'	: default_input_callback,
}
simple_action_api.create_callback_api( API )

class UserServer( websocksimplify.WebSocketServer ):
	pass


class App( core.BlenderHack ):
	def __init__(self):
		print('init server app')
		self.setup_blender_hack( bpy.context, use_gtk=False, headless=True )
		print('blender hack setup ok')
		Server.set_api( self )
		print('custom api set')

	def start_server(self, use_threading=True):
		self._threaded = use_threading
		self.websocket_server = s = UserServer()
		s.initialize(
			listen_host=Server.HOST_NAME, 
			listen_port=8080,
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
		print('on websocket read update')
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
				print(x1,y1,z1)
				if addr in Server.GameManager.clients:
					player = Server.GameManager.clients[ addr ]
					player.set_location( (x1,y1,z1) )
					player.set_focal_point( (x2,y2,z2) )
				else:
					print('[websocket ERROR] client address not in GameManager.clients')
			elif len(frame) == 1:
				print( frame.decode('utf-8') ) 
			else:
				print('doing custom action...', frame)
				## action api ##
				code = chr( frame[0] )
				action = player.new_action(code, frame[1:])
				## logic here can check action before doing it.
				if action:
					#assert action.calling_object
					action.do()



	def on_websocket_write_update(self, sock):
		player = Server.GameManager.get_player_by_socket( sock )
		msg = player.create_message_stream( bpy.context )
		print('sending', msg)
		return json.dumps( msg ).encode('utf-8')



	def mainloop(self):
		print('enter main')
		drops = 0
		self._mainloop_prev_time = time.time()
		self.active = True
		while self.active:
			now = time.time()
			dt = 1.0 / ( now - self._mainloop_prev_time )
			self._mainloop_prev_time = now
			#print('FPS', dt)

			#for ob in bpy.data.objects:
			#	ob.location.x = random.uniform(-0.2, 0.2)

			fully_updated = self.update_blender()

			#if ENGINE and ENGINE.active and not ENGINE.paused: self.update_physics( now, drop_frame )

			#win = Blender.Window( self.context.window )
			#print(win, win.winid, win.grabcursor, win.windowstate, win.modalcursor)
			#self.context.blender_has_cursor = bool( win.grabcursor )
			#if self.physics_running and self.context.scene.frame_current==1:
			#	if self.context.screen.is_animation_playing:
			#		clear_cloth_caches()

			if not fully_updated:
				# ImageEditor redraw callback will update http-server,
				# if ImageEditor is now shown, still need to update the server.
				#self.server.update( self.context )
				pass

			#if not self._threaded:
			#	self.websocket_server.update( self.context, timeout=0.1 )

			time.sleep(0.01)

if __name__ == '__main__':
	app = App()
	app.start_server( use_threading=False )
	print('-----main loop------')
	app.mainloop()