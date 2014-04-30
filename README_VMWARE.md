% VMware to CloudStack Migration
% Will Stevens
% 2014/04/30


INSTALL & SETUP
===============

On VMware Machine
-----------------
- Requires a VMware user to access the environment in order to do migrations.
- Review the configuration setup details below in regards to the `./settings.conf` file.


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

### Install pysphere and cherrypy and argparse
``` bash
$ pip install pysphere
$ pip install cherrypy
$ pip install argparse
```

### Get the source code
- To simplify later instructions, I will just assume you are in the '~/' directory when you run this.

``` bash
$ cd ~/
$ git clone git@bitbucket.org:cloudops_code/migrate2cs.git
```
(no need to actually install the code, you can run it inplace)


### Install the OVFtool
``` bash
$ cd ~/migrate2cs/extras
$ chmod u+x VMware-ovftool-3.5.0-1274719-lin.x86_64.sh
$ ./VMware-ovftool-3.5.0-1274719-lin.x86_64.sh
```

### Setup OVA file location
- This is the location where the exported OVA files will be copied to and then served from to CloudStack.
- It is recommended that you use something like an NFS mount point to ensure you have enough space.
- I will detail the commands assuming you are using an NSF share at '/mnt/share'.
- The example `./settings.conf` file shows what the config would be if the files where saved to an 'ovas' directory in this mount.

``` bash
$ mkdir -p /mnt/share
$ mount -t nfs NFS_IP_OR_HOST:/PATH/TO/NFS/SHARE /mnt/share
$ mkdir -p /mnt/share/ovas
```

### Setup the file server to server the OVAs
- This file server is how the templates and volumes are accessed by CloudStack.
- This server MUST serve on either port 80 or 443 for CloudStack to accept it.
- I have included a basic file server that can be used by dropping it in the OVAs directory and starting it.

``` bash
$ cp ~/migrate2cs/extras/file_server.py /mnt/share/ovas
$ cd /mnt/share/ovas
$ nohup python file_server.py -x .out &
```

### Setup the config `./settings.conf` file
- This file is in INI format and is used to pass configurable parameters to the application.
- All of the fields that are labeled as OPTIONAL are showing the default values that are being used.

**NOTE:** All of the REQUIRED fields are filled with placeholder values so the format of the variables can be understood

``` ini
### NOTES: both '#' and ';' are used for comments.  only ';' can be used for inline comments.

[VMWARE]
### REQUIRED: this is the details for the VMware which is being migrated from
endpoint = 10.223.130.53
username = administrator@vsphere.local
password = Passw0rd1!

### OPTIONAL: these are defined in the code, change them as needed
## log_file = ./logs/vmware_api.log


[CLOUDSTACK]
### REQUIRED: this is the details for the CloudStack/CloudPlatform which is being migrated to
host = 10.223.130.192:8080

# these keys are for the 'admin' user so he can act on behalf of other users
api_key = 8hJuKwAWm4m0d4czQFv9CrhF_atGg6PB-kQX1Net8xv6B_H_7B8dJa6M60U-4yFPrAgt3KzqTFU8V-VX6XvMRA
secret_key = an96yMkcWrfyexdJ-McpeUdsQtWp_QEZlDk7jbbBcf1yDn3UNmF5J4XDYaDswn5klp0RK91tzP_-lSCMMO2hWw

### OPTIONAL: these are defined in the code, change them as needed
## protocol = http
## uri = /client/api
## async_poll_interval = 5
## logging = True
## log_file = ./logs/cs_request.log


[FILESERVER]
### REQUIRED: this is where the OVA files will be copied to and then served from for CloudStack to access
host = 10.223.130.146
username = root
password = password
port = 80                      ; this needs to be 80 or 443 for CloudStack to use it
base_uri = /                   ; the file name will be appended to this path in the url
files_path = /mnt/share/ovas   ; this is where the files will get saved to and served from


[WEBSERVER]
### OPTIONAL: will work with the default settings.  this is the migration ui web server.
## debug = False
## port = 8787
```


HOWTO USE THE PACKAGE
=====================
- Once everything is installed and the `./settings.conf` file has been configured, you can use the package.

Start the migration UI server
-----------------------------
``` bash
$ cd ~/migrate2cs
$ nohup python ui_server_vmware.py &
```

Using the migration UI
----------------------
- Navigate to: http://MIGRATION_MACHINE_IP:8787
- On load, it will discover both the VMware and CloudStack enironments, so it may take some time to load.
- When the page loads, the CloudStack details will be available in the dropdowns and the VMware VMs will be listed below.
- You can click on the VM name to expand it and get more detail.
- To apply a specific CloudStack configuration to a group of VMs, select the VMs and the CloudStack details from the dropdowns and click on the 'Apply to Selected VMs' button.
- You can now see the CloudStack details in the expanded view of the VMs.
- To begin the migration, make sure there is CloudStack details applied to all selected VMs and then click on 'Migrate Selected VMs'.
- The 'Select and Migrate VMs' section will collapse and the 'Migration Progress' section will open up.
- The textarea in this section will update with the migration progress.
- Under the textarea is a list of logs from previous migrations which can be downloaded.
- The 'Recent Logs' section is not updated after each run.  In order to get an updated list, you need to reload the page.
- Clicking on a link in the 'Recent Logs' section will start downloading that log.



