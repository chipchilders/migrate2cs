INSTALL
=======

On HyperV Machine
-----------------
### Configure winrm
	DOS> winrm quickconfig
	DOS> winrm set winrm/config/service/auth @{Basic="true"}
	DOS> winrm set winrm/config/service @{AllowUnencrypted="true"}


On Migration Machine
--------------------
### Install EPEL
	$ cd /tmp
	$ wget http://mirror-fpt-telecom.fpt.net/fedora/epel/6/i386/epel-release-6-8.noarch.rpm
	$ yum install epel-release-6-8.noarch.rpm


### Install PIP
	$ yum install python-pip


### Install pywinrm
	$ pip install http://github.com/diyan/pywinrm/archive/master.zip 