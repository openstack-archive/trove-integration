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
from proboscis.asserts import *
from proboscis import test
from proboscis import SkipTest
from reddwarf.tests.config import CONFIG
from reddwarf.tests.api.instances import GROUP
from reddwarf.tests.api.instances import GROUP_STOP
from reddwarf.tests.api.instances import DeleteInstance
from reddwarf.tests.api.instances import instance_info
from tests.util import rpc

# (cp16net) turn this test off because rpc code has no delete_queue method
@test(depends_on=[DeleteInstance], groups=[GROUP, GROUP_STOP])
class AdditionalDeleteInstanceTests(object):
    """Run some more tests on the deleted instance."""

    @test(enabled=rpc.DIRECT_ACCESS and not CONFIG.fake_mode)
    def queue_is_deleted(self):
        """Makes sure the queue is cleaned up."""
        raise SkipTest("We need delete_queue in RPC oslo code")

        rabbit = rpc.Rabbit()
        queue_name = "guestagent.%s" % instance_info.id
        count = rabbit.get_queue_items(queue_name)
        assert_is_none(count)
