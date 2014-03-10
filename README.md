INSTALL
=======

On HyperV Machine
-----------------
### Configure winrm
	DOS> winrm quickconfig
	DOS> winrm set winrm/config/service/auth @{Basic="true"}
	DOS> winrm set winrm/config/service @{AllowUnencrypted="true"}
	DOS> winrm e winrm/config/listener
(record the details of the listener to be used in `./settings.conf`)



On Migration Machine
--------------------
### Install EPEL
	$ cd /tmp
	$ wget http://mirror-fpt-telecom.fpt.net/fedora/epel/6/i386/epel-release-6-8.noarch.rpm
	$ yum install epel-release-6-8.noarch.rpm


### Install PIP and Git
	$ yum install python-pip git


### Install pywinrm
	$ pip install http://github.com/diyan/pywinrm/archive/master.zip 


### Get the source code
	$ git clone git@bitbucket.org:cloudops_code/migrate2cs.git
	(no need to actually install anything, you can run the code inplace)



HOWTO USE THE PACKAGE
=====================
### Create 	`./migrate_hyperv_input.json`
This file is used to specify which VMs from HyperV to export and where they should be imported into CloudStack.  

The file is in the following format.

	[
		{
			"hyperv_vm_name":"Windows_Server_2003",
			"hyperv_server":"HYPERV1"
		},
		{
			"hyperv_vm_name":"CentOS65",
			"hyperv_server":"HYPERV1",
			"cs_zone":"20968383-8fc3-484f-801c-c9b8676f9181",
			"cs_account":"78c6760a-89ea-11e3-ac97-fa7d389a3dd1",
			"cs_domain":"78c65c9c-89ea-11e3-ac97-fa7d389a3dd1",
			"cs_network":"5eaa9b3e-fd1f-4107-aa7f-6a0653a51ffe",
			"cs_service_offering":"303ccee7-5fb9-4955-962e-45e25bda2b03"
		}
	]

* The first entry is only specifying the minimum required fields.  All of the CloudStack details will be pulled from the default values in the `./settings.conf` file (covered later).
* The second entry specifies all possible options.  These entries will override the defaults in the `./settings.conf` file.  If any field is left out it will be replaced with the default as in the first example.
**NOTE:** Be sure not to include a comma after the last entry in an object or level.  Notice that there is no comma after the last key:value in each object as well as after the last object in the list.


### Convenience file `./discover_cs.py`
Because it is a lot of work to generate the `./migrate_hyperv_input.json` file, I have created this convenience file.  This script uses the connection details described in the `./settings.conf` file and does a discovery of the target CloudStack environment and outputs all of the different resources in the following format.  This makes it much easier to copy and paste when creating the input file.

	ZONES:
	------
	=> Example Zone <=
	"cs_zone":"20968383-8fc3-484f-801c-c9b8676f9181",


	ACCOUNTS:
	---------
	=> ROOT/admin <=
	"cs_account":"78c6760a-89ea-11e3-ac97-fa7d389a3dd1",
	"cs_domain":"78c65c9c-89ea-11e3-ac97-fa7d389a3dd1",


	NETWORKS:
	---------
	=> Example Network - 10.0.32.0/20 <=
	"cs_network":"6bc51faa-7dc8-47d0-95fb-d16022a9da85",


	SERVICE OFFERINGS:
	------------------
	=> Medium Instance - 1x1000Mhz, 1024M <=
	"cs_service_offering":"303ccee7-5fb9-4955-962e-45e25bda2b03",

	=> Small Instance - 1x500Mhz, 512M <=
	"cs_service_offering":"2de2cc7f-abf2-4576-8ef9-e35c9431001d",


### Setup the config `./settings.conf`
This file is in INI format and is used to pass configurable parameters to the different scripts.  All of the scripts use this settings file.


