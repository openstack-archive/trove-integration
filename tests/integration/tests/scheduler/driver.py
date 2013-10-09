# Copyright (c) 2011 OpenStack, LLC.
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
from datetime import datetime

import time
import unittest

from nose.tools import assert_almost_equal
from nose.tools import assert_equal
from nose.tools import assert_not_almost_equal
from nose.tools import assert_true
from troveclient.compat import exceptions
from proboscis import test
from proboscis.decorators import expect_exception
from proboscis.decorators import time_out

from tests import WHITE_BOX
from tests import initialize
from tests.scheduler import SCHEDULER_DRIVER_GROUP
from tests.util import TestClient
from tests.util import count_notifications
from tests.util import create_dbaas_client
from tests.util import test_config
from trove.tests.util.users import Requirements
from tests.volumes import VOLUMES_DRIVER

if WHITE_BOX:
    # TODO(tim.simpson): Restore this once white box functionality can be
    #                    added back to this test module.
    pass
    # from nova import db
    # from nova import exception
    # from nova import flags
    # from nova.notifier import api as notifier
    # from nova.utils import LoopingCall

    # from trove.utils import poll_until
    # FLAGS = flags.FLAGS

GROUP = SCHEDULER_DRIVER_GROUP

# Test variables
client = None
flavor_href = None
initial_instance = None
original_notification_count = None


def out_of_instance_memory_nofication_count():
    """Counts the times an OutOfInstanceMemory notification has been raised."""
    return count_notifications(notifier.ERROR, "out.of.instance.memory")


@test(groups=[GROUP], depends_on_groups=["services.initialize"])
def setUp():
    """Set up vars needed by this story."""
    user = test_config.users.find_user(Requirements(is_admin=True))
    global client
    client = create_dbaas_client(user)
    flavors = client.find_flavors_by_ram(ram=8192)
    assert_true(len(flavors) >= 1, "No flavor found!")
    flavor = flavors[0]
    global flavor_href
    flavor_href = client.find_flavor_self_href(flavor)
    global original_notification_count
    original_notification_count = out_of_instance_memory_nofication_count()


@test(groups=[GROUP, GROUP + ".create"], depends_on=[setUp])
def create_instance():
    """Create the instance. Expect the scheduler to fail the request."""
    #TODO(tim.simpson): Try to get this to work using a direct instance
    #                   creation call.
    #    instance = instance_info.client.servers.create(
    #        name="My Instance",
    #        image=test_config.dbaas_image,
    #        flavor=1
    #    )
    now = datetime.utcnow()
    global initial_instance
    initial_instance = client.instances.create(
        "sch_test_" + str(now),
        flavor_href,
        {"size": 1},
        [{"name": "firstdb", "charset": "latin2",
          "collate": "latin2_general_ci"}])


def confirm_instance_is_dead(self):
    """Retrieve the instance and make sure it failed."""
    instance = client.servers.get(initial_instance.id)
    assert_equal("FAILED", instance.status)


@test(groups=[GROUP], depends_on=[create_instance])
def find_evidence_scheduler_failed_in_logs():
    """Eavesdrop on the logs until we see the scheduler failed, or time-out."""
    evidence = "Error scheduling " + initial_instance.name
    poll_until(lambda: file(FLAGS.logfile, 'r').read(),
               lambda log: evidence in log, sleep_time=3, time_out=60)


@test(groups=[GROUP], depends_on=[find_evidence_scheduler_failed_in_logs])
class AfterSchedulingHasFailed(unittest.TestCase):

    def test_confirm_ops_was_notified(self):
        current_count = out_of_instance_memory_nofication_count()
        # Additional ops notifications should have been added.
        poll_until(out_of_instance_memory_nofication_count,
                   lambda count: original_notification_count < count,
                   sleep_time=1, time_out=60)

    def test_confirm_instance_is_in_error_state(self):
        """Retrieve the instance and make sure its status is 'ERROR.'"""
        instance = client.instances.get(initial_instance.id)
        assert_equal("ERROR", instance.status)


@test(groups=[GROUP, GROUP + ".end"], depends_on_groups=[GROUP + ".create"])
@time_out(30)
def destroy_instance():
    """Delete the instance we tried to create for this test."""
    client.instances.delete(initial_instance)
    id = initial_instance.id
    try:
        lc = LoopingCall(f=lambda: client.instances.get(id)).start(2, True)
        lc.wait()
        self.fail("Expected exception.NotFound.")
    except exceptions.NotFound:
        pass
