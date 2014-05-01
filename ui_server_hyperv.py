#!/usr/bin/env python

## Copyright (c) 2014 Citrix Systems, Inc. All Rights Reserved.
## You may only reproduce, distribute, perform, display, or prepare derivative works of this file pursuant to a valid license from Citrix.

## ----------------------
##  INSTALL DEPENDANCIES
## ----------------------
## $ pip install bottle
## $ pip install rocket or cherrypy
##
## Author: Will Stevens

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
