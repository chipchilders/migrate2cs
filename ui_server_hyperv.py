#!/usr/bin/env python

## ----------------------
##  INSTALL DEPENDANCIES
## ----------------------
## $ pip install bottle
## $ pip install rocket or cherrypy
##
## Author: Will Stevens <wstevens@cloudops.com>

from ui_common import *

# migration page
@bottle.route('/')
@bottle.view('index')
def index():
	return dict({})


# start the server
bottle.run(
	server='cherrypy',
	host='0.0.0.0',
	port=8787,
	reloader=True,
	debug=False)
