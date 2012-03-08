import sys
import time
import re

from nova import context
from nova import db
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
from tests.util import process
from tests.util import string_in_list
from tests.util import assert_mysql_connection_fails


@test(depends_on_groups=[GROUP_START], groups=[GROUP_TEST, "dbaas.guest.ovz"])
class TestMultiNic(object):
    """
        Test that the created instance has 2 nics with the specified ip
        address as allocated to it.
    """

    @before_class
    def setUp(self):
        instance_info.user_ip = get_vz_ip_for_device(instance_info.local_id,
                                                      "eth0")

    @test
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


@test(depends_on_classes=[TestMultiNic], groups=[GROUP_TEST, "dbaas.guest.mysql"])
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

    @test
    def test_zfirst_db(self):
        if not instance_info.check_database("firstdb"):
            fail("Database 'firstdb' was not created")
