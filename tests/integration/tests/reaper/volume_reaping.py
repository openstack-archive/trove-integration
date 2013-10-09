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

from datetime import timedelta

from nose.tools import assert_raises

from troveclient.compat.exceptions import NotFound

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

from tests import WHITE_BOX
from tests.util import test_config
from tests.util import wait_for_compute_service
from tests.util.instance import InstanceTest

if WHITE_BOX:
    # TODO(tim.simpson): Restore this once white box functionality can be
    #                    added back to this test module.
    pass
    # from nova import context
    # from nova import flags
    # from nova import volume
    # from nova import utils
    # from nova.db import api as db_api

    # from trove.compute.manager import TroveInstanceInitializer
    # from trove.reaper import driver  # Do this to get the FLAG values.

    # FLAGS = flags.FLAGS

GROUP = 'trove.reaper'


@test(groups=[GROUP, GROUP + ".volume"],
      depends_on_groups=["services.initialize"])
class ReaperShouldKillOlderUnattachedVolumes(InstanceTest):
    """When the volume services starts """

    @before_class
    def set_up(self):
        """Sets up the client."""
        test_config.compute_service.stop()
        assert_false(test_config.compute_service.is_running)
        self.init("TEST_FAIL_VOLUME_")
        self.volume_api = volume.API()

    @after_class(always_run=True)
    def tearDown(self):
        """Be nice to other tests and restart the compute service normally."""
        if not test_config.compute_service.is_running:
            test_config.compute_service.start()
            wait_for_compute_service()

    @test
    def create_instance(self):
        self._create_instance()
        self.volume_id = self._get_instance_volume()

    @test(depends_on=[create_instance])
    def wait_for_volume(self):
        """Wait for the volume to become ready."""
        initializer = TroveInstanceInitializer(None, db_api,
                                                  context.get_admin_context(),
                                                  None, self.volume_id)
        initializer.wait_until_volume_is_ready(FLAGS.trove_volume_time_out)

    @test(depends_on=[wait_for_volume])
    def make_volume_look_old(self):
        """Set the volume's updated_at time to long ago."""
        expiration_time = FLAGS.trove_reaper_orphan_volume_expiration_time
        updated_at = utils.utcnow() - timedelta(seconds=expiration_time * 2)
        db_api.volume_update(context.get_admin_context(), self.volume_id,
                            {"updated_at": updated_at})

    @test(depends_on=[make_volume_look_old])
    def reaper_should_delete_volume(self):
        self._assert_volume_is_eventually_deleted()

    @test(depends_on=[reaper_should_delete_volume])
    def compute_manager_will_automatically_delete_volume_on_restart(self):
        test_config.compute_service.start()
        wait_for_compute_service()
        # When the compute service comes back online, periodic tasks will
        # see the instance and delete it.
        time_out = FLAGS.trove_volume_time_out + 30
        assert_raises(NotFound, self.dbaas.instances.get, self.id)
        #TODO: Make sure quotas aren't affected.
