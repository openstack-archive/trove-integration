# Copyright (c) 2012 OpenStack, LLC.
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

import sys
import time
import re

from nose.plugins.skip import SkipTest
from proboscis import before_class
from proboscis import test
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_false
from proboscis.asserts import assert_not_equal
from proboscis.asserts import assert_raises
from proboscis.asserts import assert_true
from proboscis.asserts import fail
from proboscis.decorators import time_out

from tests.api.instances import instance_info
from tests.api.instances import GROUP_START
from tests.api.instances import GROUP_TEST
from tests.util import get_vz_ip_for_device
from tests.util import init_engine
from tests.util import poll_until
from tests.util import process
from tests.util import string_in_list
from tests.util import assert_mysql_connection_fails
from tests.util import test_config

from tests import WHITE_BOX

if WHITE_BOX:
    from nova import context
    from nova import db

@test(depends_on_groups=[GROUP_START], groups=[GROUP_TEST, "dbaas.guest.ovz"])
class TestMultiNic(object):
    """
        Test that the created instance has 2 nics with the specified ip
        address as allocated to it.
    """

    @before_class
    def setUp(self):
        if test_config.values['openvz_disabled']:
            raise SkipTest("OpenVZ not implemented yet")
        instance_info.user_ip = get_vz_ip_for_device(instance_info.local_id,
                                                      "eth0")

    @test(enabled=not test_config.values['fake_mode'])
    def test_get_ip(self):
        # wait for a few seconds for the IP to sync up
        # is there a better way to do this?
        def get_ip_for_instance():
            result = instance_info.dbaas.instances.get(instance_info.id)
            if hasattr(result, 'ip'):
                instance_info.user_ip = result.ip[0]
                return True
            return False
        poll_until(get_ip_for_instance, sleep_time=5, time_out=20)

    @test(enabled=WHITE_BOX)
    def test_multi_nic(self):
        """
        Multinic - Verify that nics as specified in the database are created
        in the guest
        """
        vifs = db.virtual_interface_get_by_instance(context.get_admin_context(),
                                                    instance_info.local_id)
        for vif in vifs:
            fixed_ip = db.fixed_ip_get_by_virtual_interface(context.get_admin_context(),
                                                            vif['id'])
            vz_ip = get_vz_ip_for_device(instance_info.local_id,
                                         vif['network']['bridge_interface'])
            assert_equal(vz_ip, fixed_ip[0]['address'])


@test(depends_on_classes=[TestMultiNic], groups=[GROUP_TEST, "dbaas.guest.mysql"],
      enabled=not test_config.values['fake_mode'])
class TestMysqlAccess(object):
    """
        Make sure that MySQL server was secured.
    """

    @time_out(60 * 2)
    @test
    def test_mysql_admin(self):
        """Ensure we aren't allowed access with os_admin and wrong password."""
        assert_mysql_connection_fails("os_admin", "asdfd-asdf234",
                                      instance_info.user_ip)

    @test
    def test_mysql_root(self):
        """Ensure we aren't allowed access with root and wrong password."""
        assert_mysql_connection_fails("root", "dsfgnear",
                                      instance_info.user_ip)

    @test(enabled=WHITE_BOX)
    def test_zfirst_db(self):
        if not instance_info.check_database("firstdb"):
            fail("Database 'firstdb' was not created")
