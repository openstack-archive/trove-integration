# Copyright 2011 OpenStack LLC.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import time
from tests import util

GROUP='dbaas.compute.reboot.vz'

from novaclient.exceptions import NotFound

from proboscis import after_class
from proboscis import before_class
from proboscis import test
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_false
from proboscis.asserts import assert_is_not_none
from proboscis.asserts import assert_true
from proboscis.asserts import fail
from proboscis.decorators import expect_exception
from proboscis.decorators import time_out

from tests.api.instances import GROUP_START
from tests.api.instances import GROUP_TEST
from tests.api.instances import instance_info

from tests.util import TestClient
from tests.util import check_database
from tests.util import count_notifications
from tests.util import create_dns_entry
from tests.util import create_test_client
from tests.util import process
from tests.util import restart_compute_service
from tests.util import string_in_list
from tests.util import test_config
from tests.util.instance import InstanceTest
from tests.util.users import Requirements

from tests import wb_test
from tests import WHITE_BOX

if WHITE_BOX:
    from nova import context
    from nova import flags
    from nova import utils
    from nova.compute import power_state
    from nova.compute import vm_states
    from nova.exception import VolumeNotFound
    from nova.notifier import api as notifier
    from nova.scheduler.driver import Scheduler
    from nova.virt import openvz_conn

    from reddwarf.api.common import dbaas_mapping
    from reddwarf.db import api as dbapi
    from reddwarf.utils import poll_until
    from reddwarf.scheduler import simple # import used for FLAG values
    from reddwarf.compute.manager import ReddwarfInstanceMetaData

    FLAGS = flags.FLAGS

@test(depends_on_groups=[GROUP_START], groups=[GROUP_TEST, GROUP])
class VerifyRebootRestartsTheVZ(InstanceTest):

    @before_class
    def before_tests(self):
        """Sets up the reboot tests."""
        self.init('VERIFY_REBOOT_VZ_')
        print("instance info local_id %s" % instance_info.local_id)
        self.local_id = instance_info.local_id
        self.name = "instance-00000001"
        self.conn = openvz_conn.OpenVzConnection(False)

    def ensure_vz_power_state(self, power_state):
        """Ensures the database has the correct state"""
        poll_until(self._get_compute_instance_state, 
                   lambda state : state == power_state,
                   sleep_time=2, time_out=60)

    def ensure_vz_actual_state(self, power_state):
        """Ensures the hypervisor has the correct state"""
        def get_info_from_conn():
            return self.conn.get_info(self.name)['state']
        poll_until(get_info_from_conn, 
                   lambda state : state == power_state,
                   sleep_time=2, time_out=60)

    def stop_vz(self):
        """Manually shuts down the VZ. This does not use the _stop
           method in the driver since we need the status to _not_ 
           be updated to shutdown for the resume case to work in
           the managers reboot path in the compute manager init_host"""
        utils.execute('vzctl', 'stop', self.local_id,
                      run_as_root=True)

    def logout_iscsi(self):
        """Forcing a iscsi logout to simulate a power shutoff. This 
           will not take corruption into account at present."""
        utils.execute('iscsiadm', '-m', 'node', '--logout',
                      run_as_root=True)

    @test()
    @time_out(300)
    def wait_for_vz_to_restart(self):
        """Tests Compute managers init_host to bring the VZ online.
           This test manually stops the vz and iscsi, and then restarts
           compute and waits for the init_host to update the status."""
        self.stop_vz()
        self.logout_iscsi()
        restart_compute_service()
        self.ensure_vz_power_state(power_state.RUNNING)
        # Also make sure the actual VZ has the same running state
        self.ensure_vz_actual_state(power_state.RUNNING)
