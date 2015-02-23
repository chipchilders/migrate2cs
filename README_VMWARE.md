% VMware to CloudPlatform Migration Tool
% Will Stevens
% 2014/04/30


INSTALL & SETUP
===============

The Source VMware Environment
-----------------------------
- We should not have to change anything in the source VMware environment.
- The tool requires a user to be configured who has access to the whole VMware environment in order do the migration.
- Support connecting to an ESX host, vSphere or vCenter.
- Review the configuration setup details for the `./settings.conf` file.


The Migration Machine
---------------------
- The migration tool is configured on this machine and the migrations are run from this machine.
- A server will run on this machine which will serve a web based migration UI for migrating to CloudPlatform.

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
- To simplify later instructions, it is assumed that the code is pulled into the '~/' directory.
- The location of the code is not important since it is run in place and is not installed.

``` bash
$ cd ~/
$ git clone git@bitbucket.org:cloudops_code/migrate2cs.git
```

### Install the OVFtool
- This tool is used to export VMs from VMware.

``` bash
$ cd ~/migrate2cs/extras
$ chmod u+x VMware-ovftool-3.5.0-1274719-lin.x86_64.sh
$ ./VMware-ovftool-3.5.0-1274719-lin.x86_64.sh
```

### Setup where the OVA files will be stored
- This is the location where the exported OVA files will be copied to and then served from for CloudPlatform to access.
- The migration tool needs file system access to this location to save and modify the OVA files.
- It is recommended that you use something like an NFS mount point to ensure you have enough space.
- You need 3-4 times the amount of space as the largest VM (total of all its disks) you will be migrating.
- This documentation assumes that an NFS share is being used and is mounted at '/mnt/share' with a target directory of 'ova' in that share.

``` bash
$ mkdir -p /mnt/share
$ mount -t nfs NFS_IP_OR_HOST:/PATH/TO/NFS/SHARE /mnt/share
$ mkdir -p /mnt/share/ovas
```

### Setup a file server to serve the OVAs
- In order for CloudPlatform to access the OVA files, there needs to be a file server exposing the '/mnt/share/ova' directory.
- The file server MUST serve the files on either port 80 or 443 for CloudPlatform to access them.
- The type of file server is not important, but in order to simplify the deployment documentation, I have included a file server.
- The following instructions will use the file server I have included to expose the files in the '/mnt/share/ova' directory.

``` bash
$ cp ~/migrate2cs/extras/file_server.py /mnt/share/ovas
$ cd /mnt/share/ovas
$ nohup python file_server.py -x .out &
```

### Setup the config file `./settings.conf`
- This file is in INI format and is used to pass configurable parameters to the application.
- All of the fields that are labeled as OPTIONAL are showing the default values that are being used.

**NOTE:** All the values in the REQUIRED fields are only placeholders so you understand the format.  They must be replaced with your settings.

``` ini
### NOTES: both '#' and ';' are used for comments.  only ';' can be used for inline comments.

[VMWARE]
### REQUIRED: this is the details for the VMware which is being migrated from
endpoint = 10.223.130.53
username = administrator@vsphere.local
password = Passw0rd1!

### OPTIONAL: these are defined in the code, change them as needed
## log_file = ./logs/vmware_api.log
## max_virtual_hardware_version = 8


[CloudPlatform]
### REQUIRED: this is the details for the CloudPlatform/CloudPlatform which is being migrated to
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
### REQUIRED: this is where the OVA files will be copied to and then served from for CloudPlatform to access
host = 10.223.130.146          ; this is the ip of the migration machine
port = 80                      ; this needs to be 80 or 443 for CloudPlatform to use it
base_uri = /                   ; the file name will be appended to this path in the url
files_path = /mnt/share/ovas   ; this is where the files will get saved to and served from


[WEBSERVER]
### OPTIONAL: will work with the default settings.  this is the migration ui web server.
## debug = False
## port = 8787
```


HOWTO USE THE TOOL
==================
- Once everything is installed and `./settings.conf` has been configured, you can use the package.

Start the migration UI server
-----------------------------
``` bash
$ cd ~/migrate2cs
$ nohup python ui_server_vmware.py &
```

Starting a migration from the UI
--------------------------------
- Navigate to: http://MIGRATION_MACHINE_IP:8787
- On load, it will discover both the VMware and CloudPlatform enironments, so it will take some time to load.
- When the page loads, the CloudPlatform details will be available in the dropdowns and the VMware VMs will be listed below.
- You can click on the VM name to expand it to show more details.
- To apply a specific CloudPlatform configuration to a group of VMs, select the VMs and specify the CloudPlatform details in the dropdowns, then click the 'Apply to Selected VMs' button.
- You can review the CloudPlatform details in the expanded view of the VMs.
- To begin the migration, make sure there are CloudPlatform details applied to all the selected VMs, then click 'Migrate Selected VMs'.


View the progress of a migration
--------------------------------
- The 'Select and Migrate VMs' section will collapse and the 'Migration Progress' section will open when the 'Migrate Selected VMs' is clicked.
- The textarea in this section will update with the migration progress every 10 seconds.
- A list of recent logs is listed below the current migration progress textarea.
- Clicking a link in the recent logs section will download that log.
- There are 4 types of logs in the section:
    - 'vmware_migration_TIMESTAMP.log' - These logs show the details for previous migrations.
    - 'vmware_api.log' (default name) - This log captures the information that VMware returns when the VMs are discovered (on page load).
    - 'cs_request.log' (default name) - This log captures the details of the api calls to CloudPlatform.
    - 'help.txt' - This is a help file to explain the different stages the migration progress goes through.


Limitations and special considerations
--------------------------------------
- The tool fully supports VMs with SCSI controllers.
- The tool only partially supports VMs with IDE controllers.  The VM will import correctly, but it will crash on boot due to a problem locating the root partition.  Manual manipulation is required to complete the migration.
- The tool supports VMs with both single and multiple disks.
	- The additional disks will be uploaded to CloudPlatform as data volumes and will be attached to the VM after it launches.
- The tool supports VMs with spaces in the name ONLY if they show up in the OVFtool vm inventory list
	- eg: vi://USER:PASSWORD@VMWARE_ENDPOINT/DATACENTER/vm
- If the VM does not show up in the OVFtool vm inventory list, then a different export method is used.  This second attempt will only work if the VMs VMX Path does NOT have any spaces (other than the space between the datasource and the path).
- If the VM does not show up in the OVFtool vm inventory list and the VMX Path has spaces, there is no way for the tool to export the VM.
- When migrating from a more recent version of VMware to a previous version of VMware, you will need to specify the 'max_virtual_hardware_version' setting to reflect the destination VMware version.  The possible settings and the respective VMware version supported is listed below.  The default setting is '8'...
	- 10 - Supports: ESXi 5.5, Fusion 6.x, Workstation 10.x, Player 6.x
	- 9 - Supports: ESXi 5.1, Fusion 5.x, Workstation 9.x, Player 5.x
	- 8 - Supports: ESXi 5.0, Fusion 4.x, Workstation 8.x, Player 4.x
	- 7 - Supports: ESXi/ESX 4.x, Fusion 3.x, Fusion 2.x, Workstation 7.x, Workstation 6.5.x, Player 3.x, Server 2.x
	- 6 - Supports: Workstation 6.0.x
	- 4 - Supports: ACE 2.x, ESX 3.x, Fusion 1.x, Player 2.x
	- 3 and 4 - Supports: ACE 1.x, Lab Manager 2.x, Player 1.x, Server 1.x, Workstation 5.x, Workstation 4.x
	- 3 - Supports: ESX 2.x, GSX Server 3.x



UNDER THE HOOD
==============

The migration states
--------------------
- <no state> - The default migration state is an empty string which means the migration process needs to start from the beginning.
- exported - The VM has been exported and the OVA is ready to be imported.
- imported - The VM has been imported into CloudPlatform and the upload process has been kicked off.
- launched - A transition state after the VM is launched in CloudPlatform and before the migration has been cleaned up.
- migrated - The VM has been successfully migrated to CloudPlatform and is up and running.


Migration state management
--------------------------
- The state of the migration is stored in the `./running.conf` file.
- The `./running.conf` file is a superset of the parameters configured in `./settings.conf` and maintains the current state of the migration.
- If the `./running.conf` file is removed, the migration UI will be reset to its defaults plus the contents of the `./settings.conf` file.
- It is NOT recommended to modify the `./running.conf` file unless you really understand what the implications are.
- The `./running.conf` includes all of the configuration specified in the `./settings.conf` file, the defaults specified in code as well as:
    - vms - The details for all the discovered VMs and the information stored associated with the VMs durring the migration.
    - cs_objs - The details for the available CloudPlatform objects that VMs can be applied to.
    - vm_order - The order of the VMs so the order is consistent between reloads.
    - migrate - An array of VMs that are currently being migrated.
    - migrate_error - A boolean that tracks if the current migration has errors.
    - migration_timestamp - The timestamp associated with the last migration.
    - active_migration - A boolean to specify if there is a migration currently happening.

