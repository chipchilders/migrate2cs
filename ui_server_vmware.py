#!/usr/bin/env python

## ----------------------
##  INSTALL DEPENDANCIES
## ----------------------
## $ pip install bottle
## $ pip install rocket
##
## Author: Will Stevens <wstevens@cloudops.com>

import json
from ui_common import *

# migration page
@bottle.route('/')
@bottle.view('index')
def index():
	output = {}
	output['cs_objs'] = json.dumps(cs_discover_accounts())
	#pprint.pprint(output['cs_objs'])
	return dict(output)


# start the server
bottle.run(
	server='rocket',
	host='0.0.0.0',
	port=8787,
	reloader=True,
	debug=False)
