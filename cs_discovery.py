#!/usr/bin/env python

# Author: Will Stevens - wstevens@cloudops.com
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#   http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from cs_api import cs
from cs_api import conf
import pprint
import time

  
###########################################################
### EXECUTED WHEN THE FILE IS RUN FROM THE COMMAND LINE ###
###########################################################
if __name__ == "__main__":
    # comment out the following line to keep a history of the requests over multiple runs (cloudstack requests log will get large).
    open(conf.get('CLOUDSTACK', 'log_file'), 'w').close() # cleans the cloudstack requests log before execution so it only includes this run.
    
    
    ## LIST
    
    #api.request(dict({'command':'listAccounts'}))
    pprint.pprint(api.request(dict({'command':'listZones'})))
    #api.request(dict({'command':'listVPCOfferings'}))
    #api.request(dict({'command':'listNetworkOfferings', 'forVpc':True}))
    #api.request(dict({'command':'listVPCs'}))
    #api.request(dict({'command':'listNetworks', 'listAll':True}))
    #api.request(dict({'command':'listPublicIpAddresses'}))
    #api.request(dict({'command':'listVirtualMachines'}))
    #api.request(dict({'command':'listLoadBalancerRules'}))
    #api.request(dict({'command':'listPrivateGateways', 'listAll':True}))
    #api.request(dict({'command':'listStaticRoutes', 'listAll':True}))
    
    #api.request(dict({'command':'queryAsyncJobResult', 'jobId':'87d438be-b7cc-466d-828f-e02595ad536d'}))
    
