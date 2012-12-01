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


GROUP = 'dbaas.guest.initialize.failure'

from proboscis import after_class
from proboscis import before_class
from proboscis import test
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_false
from proboscis.asserts import assert_true
from proboscis.asserts import assert_is_not_none
from proboscis.asserts import fail
from proboscis.decorators import expect_exception
from proboscis.decorators import time_out

from tests.util import test_config
from tests.util import test_config
from tests.util import check_database
from tests.util import count_notifications
from tests.util import create_dns_entry
from tests.util import process
from tests.util import restart_compute_service
from tests.util import string_in_list
from tests.util import TestClient
from reddwarf.tests.util.users import Requirements

from tests.util.instance import InstanceTest
from tests import WHITE_BOX


if WHITE_BOX:
    # TODO(tim.simpson): Restore this once white box functionality can be
    #                    added back to this test module.
    pass
    # from nova.exception import VolumeNotFound
    # from nova.scheduler.driver import Scheduler
    # from nova import context
    # from nova import utils
    # from nova.compute import power_state
    # from nova.compute import vm_states
    # from nova.notifier import api as notifier
    # from reddwarf.api.common import dbaas_mapping
    # from reddwarf.db import api as dbapi
    # from reddwarf.utils import poll_until
    # from reddwarf.scheduler import simple  # import used for FLAG values
    # from nova import flags
    # from reddwarf.compute.manager import ReddwarfInstanceMetaData
    # FLAGS = flags.FLAGS

VOLUME_TIME_OUT = 30


# TODO(tim.simpson): Tests are needed for the following cases:
#
# When provisioning an instance:
# A volume fails to provision:
#     This can be because there is not sufficient space or the account limits
#     are exceeded. There is another trickier third case where the volume
#     might be provisioning but is timed out, and must be deleted.
#   In these cases the status must be FAIL. No resources should be counted
#     against the user's account, unless it was via a time-out (this is so the
#     volume can finish creating and we can look at it). However when deleted
#     the volume should also be deleted, and after this point not count against
#     the user's quotas.
#
# The compute instance fails to provision, as an error occurs. The state must
#     be set to FAIL. In this case the compute instance is set to suspended
#     but not deleted (if it even exists in any state) so this may or may not
#     count against a user's quotas
#   When deleted the instance should vanish along with the volumes and all
#     quotas be returned to where they were before.
#
# The guest install times out. In this case the state must be set to FAIL and
#     must stay there! When delete is called, the instance and volume should
#     disappear.
#
# In addition to GETs and LISTs returning FAIL as the state, attempts to
# add databases should fail.


#TODO: Change volume timeout to something very low, and make sure the instance
# is set to fail.  If it isn't possible to make sure the volume never
# provisions this could also be a reaper test.

def wait_until_scheduler_is_ready():
    """
    Make sure the scheduler has finished marking volumes as deleted and
    returned memory to its quota, otherwise it will fail to provision a new
    instance.
    """
    #TODO(tim.simpson): This is a hack; we need a proper solution but this is
    #                   better than nothing.
    time.sleep(30)


@test(groups=[GROUP, GROUP + ".volume"],
      depends_on_groups=["services.initialize"])
class VerifyManagerAbortsInstanceWhenVolumeFails(InstanceTest):

    @before_class
    def setUp(self):
        """Sets up the client."""
        wait_until_scheduler_is_ready()
        test_config.volume_service.stop()
        assert_false(test_config.volume_service.is_running)
        restart_compute_service(['--reddwarf_volume_time_out=%d'
                                 % VOLUME_TIME_OUT])
        self.init("TEST_FAIL_VOLUME_")
        self.instance_exists = False

    @after_class(always_run=True)
    def tearDown(self):
        """Be nice to other tests and restart the compute service normally."""
        # Wipe the instance from the DB so it won't count against us.
        test_config.volume_service.start()
        restart_compute_service()
        if self.instance_exists:
            self.db.instance_destroy(context.get_admin_context(),
                                     self.local_id)

    @test
    def create_instance(self):
        """Create a new instance."""
        self.abort_count = count_notifications(notifier.ERROR,
            "reddwarf.instance.abort.volume")
        self._create_instance()
        # Use an admin context to avoid the possibility that in between the
        # previous line and this one the request goes through and the instance
        # is deleted.
        metadata = ReddwarfInstanceMetaData(self.db,
            context.get_admin_context(), self.local_id)
        self.volume_id = metadata.volume_id

    @test(depends_on=[create_instance])
    def wait_for_failure(self):
        """Make sure the Reddwarf Compute Manager FAILS a timed-out volume."""
        self.instance_exists = True
        self.wait_for_rest_api_to_show_status_as_failed(VOLUME_TIME_OUT + 30)
        abort_count2 = count_notifications(notifier.ERROR,
                                           "reddwarf.instance.abort.volume")
        assert_true(self.abort_count < abort_count2)

    @test(depends_on=[wait_for_failure])
    @time_out(2 * 60)
    def delete_instance(self):
        """Delete the instance."""
        #TODO: This will fail because the OpenVZ driver's destroy() method
        # raises an exception when the volume doesn't exist.
        #self._delete_instance()
        #TODO: Use the method above once it won't result in a loop.
        self.dbaas.instances.delete(self.id)

    @test(depends_on=[wait_for_failure])
    def volume_should_be_deleted(self):
        """Make sure the volume is gone."""
        #TODO: Test that the volume, when it comes up, is eventually deleted
        # by the Reaper.
        #@expect_exception(VolumeNotFound)
        #self._assert_volume_is_eventually_deleted()


#TODO: Find some way to get the compute instance creation to fail.

GUEST_INSTALL_TIMEOUT = 60 * 2


@test(groups=[GROUP, GROUP + ".guest"],
      depends_on_groups=["services.initialize"])
class VerifyManagerAbortsInstanceWhenGuestInstallFails(InstanceTest):
    """Stores new instance information used by dependent tests."""

    @before_class
    def setUp(self):
        """Sets up the client."""
        wait_until_scheduler_is_ready()
        restart_compute_service(['--reddwarf_guest_initialize_time_out=%d'
                                 % GUEST_INSTALL_TIMEOUT])
        self.init("TEST_FAIL_GUEST_")

    @after_class(always_run=True)
    def tearDown(self):
        """Be nice to other tests and restart the compute service normally."""
        restart_compute_service()

    @test
    def wait_for_compute_host_up(self):
        """Wait for the compute host to appear as ready again.

        If we don't do this, the scheduler will fail it.

        """
        def ready():
            results = dbapi.service_get_all_compute_memory(
                context.get_admin_context())
            for result in results:
                (service, memory_mb) = result
                needed_memory = memory_mb + 512
                if needed_memory <= FLAGS.max_instance_memory_mb and \
                   Scheduler.service_is_up(service):
                    return True
            return False
        poll_until(ready, sleep_time=2, time_out=60)

    @test(depends_on=[wait_for_compute_host_up])
    def create_instance(self):
        self.abort_count = count_notifications(notifier.ERROR,
                                               "reddwarf.instance.abort.guest")
        self._create_instance()
        metadata = ReddwarfInstanceMetaData(self.db,
            context.get_admin_context(), self.local_id)
        self.volume_id = metadata.volume_id
        assert_is_not_none(metadata.volume)

    @test(depends_on=[create_instance])
    @time_out(60 * 6)
    def wait_for_pid(self):
        """Wait for instance PID."""
        pid = None
        while pid is None:
            guest_status = dbapi.guest_status_get(self.local_id)
            rest_api_result = self.dbaas.instances.get(self.id)
            cmd = ("pstree -ap | grep init | cut -d',' -f2 | vzpid - | "
                   "grep %s | awk '{print $1}'")
            out, err = process(cmd % str(self.local_id))
            pid = out.strip()
            if not pid:
                # Make sure the guest status is BUILDING during this time.
                assert_equal(guest_status.state, power_state.BUILDING)
                # REST API should return BUILDING as the status as well.
                assert_equal(dbaas_mapping[power_state.BUILDING],
                             rest_api_result.status)
                time.sleep(10)

    @test(depends_on=[wait_for_pid])
    @time_out(60 * 6)
    def wait_for_compute_instance_to_start(self):
        """Wait for the compute instance to begin."""
        while True:
            status, err = process("sudo vzctl status %s | awk '{print $5}'"
                                  % str(self.local_id))

            if not string_in_list(status, ["running"]):
                time.sleep(5)
            else:
                assert_equal("running", status.strip())
                break

    @test(depends_on=[wait_for_compute_instance_to_start, wait_for_pid])
    def should_have_created_volume(self):
        #TODO: Make sure volume exists here
        #TODO: Make sure memory is allocated
        pass

    @test(depends_on=[should_have_created_volume])
    def destroy_guest_and_wait_for_failure(self):
        """Make sure the Reddwarf Compute Manager FAILS a timed-out guest."""

        # Utterly kill the guest install.
        process("sudo rm -rf /vz/private/%s/bin" % str(self.local_id))

        # Make sure that before the timeout expires the guest state in the
        # internal API and the REST API instance status is set to FAIL.
        self.wait_for_rest_api_to_show_status_as_failed(
            time_out=GUEST_INSTALL_TIMEOUT + 30)

        # At this point there is a tiny chance the compute API will spend a
        # little bit of time trying to suspend the instance. We need it to
        # because, while in this case we know the guest is dead, in the real
        # world where this might happen for less-predictable reasons we want
        # to make sure the misbehaving or just slow Nova-Guest daemon doesn't
        # change its status to something besides FAILED before the instance is
        # shut-off. So we have to make sure that the instance turns off, and
        # the manager sets the guest state to FAILED afterwards.
        self.wait_for_compute_instance_to_suspend()

        #TODO(tim.simpson): It'd be really cool if we could somehow coax the
        #                   guest to repeatedly setting its state in the db to
        #                   something besides failed, so we could assert that
        #                   no matter what after it was suspended it was set
        #                   to such.  Although maybe that's overkill.
        self._assert_status_failure(self._get_status_tuple())
        abort_count2 = count_notifications(notifier.ERROR,
                                           "reddwarf.instance.abort.guest")
        assert_true(self.abort_count < abort_count2)

    @test(depends_on=[destroy_guest_and_wait_for_failure])
    def test_volume_detached(self):
        poll_until(self._check_volume_detached, sleep_time=1, time_out=3 * 60)

    @test(depends_on=[test_volume_detached])
    @time_out(2 * 60)
    def delete_instance(self):
        self._delete_instance()

    @test(depends_on=[delete_instance])
    def test_volume_still_detached_after_delete(self):
        if not self._check_volume_detached():
            fail(message="Volume should be in a detached state")
