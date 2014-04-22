% VMware to CloudStack Migration
% Will Stevens
% 2014/03/20


INSTALL
=======


On VMware Machine
-----------------
TBD


On Migration Machine
--------------------
### Install EPEL
``` bash
$ cd /tmp
$ wget http://mirror-fpt-telecom.fpt.net/fedora/epel/6/i386/epel-release-6-8.noarch.rpm
$ yum install epel-release-6-8.noarch.rpm
```


### Install PIP and Git
``` bash
$ yum install python-pip git
```


### Install pysphere and cherrypy
``` bash
$ pip install pysphere
$ pip install cherrypy
```


### Get the source code
``` bash
$ git clone git@bitbucket.org:cloudops_code/migrate2cs.git
```
(no need to actually install anything, you can run the code inplace)



HOWTO USE THE PACKAGE
=====================
TBD


Setup the config `./settings.conf`
----------------------------------
This file is in INI format and is used to pass configurable parameters to the different scripts.  All of the scripts use this settings file.

All of the fields that are labeled as OPTIONAL are showing the default values that are being used.

**NOTE:** All of the REQUIRED fields are filled with placeholder values so the format of the variables can be understood



