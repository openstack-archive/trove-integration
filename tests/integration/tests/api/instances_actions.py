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

from proboscis import after_class
from proboscis import before_class
from proboscis import test
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_false
from proboscis.asserts import assert_not_equal
from proboscis.asserts import assert_raises
from proboscis.asserts import assert_true
from proboscis.asserts import fail
from proboscis.decorators import time_out

import tests
from tests.util.check import Checker
from novaclient.exceptions import BadRequest
from reddwarfclient.exceptions import UnprocessableEntity
from tests.api.instances import GROUP as INSTANCE_GROUP
from tests.api.instances import GROUP_START
from tests.api.instances import instance_info
from tests.api.instances import assert_unprocessable
from tests import util
from tests import WHITE_BOX

if WHITE_BOX:
    from nova import context
    from nova import db
    from nova.compute import power_state
    from sqlalchemy import create_engine
    from sqlalchemy import exc as sqlalchemy_exc
    from sqlalchemy.sql.expression import text
    from reddwarf.api.common import dbaas_mapping
    from reddwarf.guest.dbaas import LocalSqlClient
    from reddwarf.utils import poll_until




GROUP = "dbaas.api.instances.actions"
MYSQL_USERNAME = "test_user"
MYSQL_PASSWORD = "abcde"

class MySqlConnection(object):

    def __init__(self, host):
        self.host = host

    def connect(self):
        """Connect to MySQL database."""
        self.client = LocalSqlClient(util.init_engine(
            MYSQL_USERNAME, MYSQL_PASSWORD, self.host), use_flush=False)

    def is_connected(self):
        try:
            with self.client:
                self.client.execute(text("""SELECT "Hello.";"""))
            return True
        except (sqlalchemy_exc.OperationalError,
                sqlalchemy_exc.DisconnectionError,
                sqlalchemy_exc.TimeoutError):
            return False
        except Exception as ex:
            print("EX WAS:")
            print(type(ex))
            print(ex)
            raise ex


TIME_OUT_TIME = 4 * 60

class RebootTestBase(object):
    """Tests restarting MySQL."""

    def call_reboot(self):
        raise NotImplementedError()

    @property
    def instance(self):
        return self.dbaas.instances.get(self.instance_id)

    @property
    def instance_local_id(self):
        return instance_info.get_local_id()

    @property
    def instance_id(self):
        return instance_info.id

    def find_mysql_proc_on_instance(self):
        return util.find_mysql_procid_on_instance(self.instance_local_id)

    def set_up(self):
        address = instance_info.get_address()
        assert_equal(1, len(address), "Instance must have one fixed ip.")
        self.connection = MySqlConnection(address[0])
        self.dbaas = instance_info.dbaas

    def create_user(self):
        """Create a MySQL user we can use for this test."""

        users = [{"name": MYSQL_USERNAME, "password": MYSQL_PASSWORD,
                  "database": MYSQL_USERNAME}]
        self.dbaas.users.create(instance_info.id, users)

    def ensure_mysql_is_running(self):
        """Make sure MySQL is accessible before restarting."""
        with Checker() as check:
            self.connection.connect()
            check.true(self.connection.is_connected(),
                       "Able to connect to MySQL.")
            self.proc_id = self.find_mysql_proc_on_instance()
            check.true(self.proc_id is not None, "MySQL process can be found.")
            instance = self.instance
            check.false(instance is None)
            check.equal(instance.status, dbaas_mapping[power_state.RUNNING],
                        "REST API reports MySQL as RUNNING.")

    def wait_for_broken_connection(self):
        """Wait until our connection breaks."""
        poll_until(self.connection.is_connected,
                   lambda connected : not connected, time_out = TIME_OUT_TIME)

    def wait_for_successful_restart(self):
        """Wait until status becomes running."""
        def is_finished_rebooting():
            instance = self.instance
            if instance.status == "REBOOT":
                return False
            assert_equal("ACTIVE", instance.status)
            return True

        poll_until(is_finished_rebooting, time_out = TIME_OUT_TIME)

    def assert_mysql_proc_is_different(self):
        new_proc_id = self.find_mysql_proc_on_instance()
        assert_not_equal(new_proc_id, self.proc_id,
                         "MySQL process ID should be different!")

    def successful_restart(self):
        """Restart MySQL via the REST API successfully."""
        self.fix_mysql()
        self.call_reboot()
        self.wait_for_broken_connection()
        self.wait_for_successful_restart()
        self.assert_mysql_proc_is_different()

    def mess_up_mysql(self):
        """Ruin MySQL's ability to restart."""
        self.fix_mysql() # kill files
        cmd = """sudo vzctl exec %d 'echo "hi" > /var/lib/mysql/ib_logfile%d'"""
        for index in range(2):
            util.process(cmd % (self.instance_local_id, index))

    def fix_mysql(self):
        """Fix MySQL's ability to restart."""
        cmd = "sudo vzctl exec %d rm /var/lib/mysql/ib_logfile%d"
        for index in range(2):
            util.process(cmd % (self.instance_local_id, index))

    def wait_for_failure_status(self):
        """Wait until status becomes running."""
        def is_finished_rebooting():
            instance = self.instance
            if instance.status == "REBOOT":
                return False
            assert_equal("SHUTDOWN", instance.status)
            return True

        poll_until(is_finished_rebooting, time_out = TIME_OUT_TIME)

    def unsuccessful_restart(self):
        """Restart MySQL via the REST when it should fail, assert it does."""
        self.mess_up_mysql()
        self.call_reboot()
        self.wait_for_broken_connection()
        self.wait_for_failure_status()

    def restart_normally(self):
        """Fix iblogs and reboot normally."""
        self.fix_mysql()
        self.test_successful_restart()


@test(groups=[tests.INSTANCES, INSTANCE_GROUP, GROUP],
      depends_on_groups=[GROUP_START])
class RestartTests(RebootTestBase):
    """Tests restarting MySQL."""

    def call_reboot(self):
        self.instance.restart()

    @before_class
    def test_set_up(self):
        self.set_up()
        self.create_user()

    @test
    def test_ensure_mysql_is_running(self):
        """Make sure MySQL is accessible before restarting."""
        self.ensure_mysql_is_running()

    @test(depends_on=[test_ensure_mysql_is_running])
    def test_unsuccessful_restart(self):
        """Restart MySQL via the REST when it should fail, assert it does."""
        self.unsuccessful_restart()

    @after_class(always_run=True)
    def test_successful_restart(self):
        """Restart MySQL via the REST API successfully."""
        self.successful_restart()


@test(groups=[tests.INSTANCES, INSTANCE_GROUP, GROUP],
      depends_on_groups=[GROUP_START], depends_on=[RestartTests])
class RebootTests(RebootTestBase):
    """Tests restarting instance."""

    def call_reboot(self):
        instance_info.dbaas_admin.management.reboot(self.instance_id)

    @before_class
    def test_set_up(self):
        self.set_up()

    @test
    def test_ensure_mysql_is_running(self):
        """Make sure MySQL is accessible before restarting."""
        self.ensure_mysql_is_running()

    @test(depends_on=[test_ensure_mysql_is_running])
    def test_unsuccessful_restart(self):
        """Restart MySQL via the REST when it should fail, assert it does."""
        self.unsuccessful_restart()

    @after_class(always_run=True)
    def test_successful_restart(self):
        """Restart MySQL via the REST API successfully."""
        self.successful_restart()

@test(groups=[tests.INSTANCES, INSTANCE_GROUP, GROUP, GROUP + ".resize.instance"],
      depends_on_groups=[GROUP_START], depends_on=[RebootTests])
class ResizeInstanceTest(RebootTestBase):
    """
    Integration Test cases for resize instance
    """
    @property
    def flavor_id(self):
        return instance_info.dbaas_flavor_href

    def get_flavor_id(self, flavor_id=2):
        dbaas_flavor, dbaas_flavor_href = instance_info.dbaas.find_flavor_and_self_href(flavor_id)
        return dbaas_flavor_href

    def wait_for_resize(self):
        def is_finished_resizing():
            instance = self.instance
            if instance.status == "RESIZE":
                return False
            assert_equal("ACTIVE", instance.status)
            return True
        poll_until(is_finished_resizing, time_out = TIME_OUT_TIME)

    @before_class
    def setup(self):
        self.set_up()
        self.connection.connect()

    @test
    def test_instance_resize_same_size_should_fail(self):
        assert_raises(BadRequest, self.dbaas.instances.resize_instance,
            self.instance_id, self.flavor_id)

    @test(depends_on=[test_instance_resize_same_size_should_fail])
    def test_status_changed_to_resize(self):
        self.dbaas.instances.resize_instance(self.instance_id,
                                             self.get_flavor_id(flavor_id=2))
        #(WARNING) IF THE RESIZE IS WAY TOO FAST THIS WILL FAIL
        assert_unprocessable(self.dbaas.instances.resize_instance,
                             self.instance_id, self.get_flavor_id(flavor_id=2))

    @test(depends_on=[test_status_changed_to_resize])
    @time_out(TIME_OUT_TIME)
    def test_instance_returns_to_active_after_resize(self):
        self.wait_for_resize()

    @test(depends_on=[test_instance_returns_to_active_after_resize])
    def test_make_sure_mysql_is_running_after_resize(self):
        self.ensure_mysql_is_running()
        assert_equal(self.get_flavor_id(self.instance.flavor['id']),
                     self.get_flavor_id(flavor_id=2))

    @test(depends_on=[test_make_sure_mysql_is_running_after_resize])
    @time_out(TIME_OUT_TIME)
    def test_resize_down(self):
        self.dbaas.instances.resize_instance(self.instance_id,
                                             self.get_flavor_id(flavor_id=1))
        self.wait_for_resize()
        assert_equal(self.get_flavor_id(self.instance.flavor['id']), self.flavor_id)


@test(depends_on_classes=[ResizeInstanceTest], groups=[GROUP, tests.INSTANCES])
class ResizeInstanceVolume(object):
    """ Resize the volume of the instance """

    @before_class
    def setUp(self):
        volumes = db.volume_get_all_by_instance(context.get_admin_context(),
                                                instance_info.local_id)
        instance_info.volume_id = volumes[0].id
        self.old_volume_size = int(volumes[0].size)
        self.new_volume_size = self.old_volume_size + 1

        # Create some databases to check they still exist after the resize
        self.expected_dbs = ['salmon', 'halibut']
        databases = []
        for name in self.expected_dbs:
            databases.append({"name": name})
        instance_info.dbaas.databases.create(instance_info.id, databases)

    @test
    @time_out(60)
    def test_volume_resize(self):
        instance_info.dbaas.instances.resize_volume(instance_info.id, self.new_volume_size)

    @test
    @time_out(300)
    def test_volume_resize_success(self):

        def check_resize_status():
            instance = instance_info.dbaas.instances.get(instance_info.id)
            if instance.status == "ACTIVE":
                return True
            elif instance.status == "RESIZE":
                return False
            else:
                fail("Status should not be %s" % instance.status)

        poll_until(check_resize_status, sleep_time=2, time_out=300)
        volumes = db.volume_get(context.get_admin_context(),
                                instance_info.volume_id)
        assert_equal(volumes.status, 'in-use')
        assert_equal(volumes.size, self.new_volume_size)
        assert_equal(volumes.attach_status, 'attached')

    @test
    @time_out(300)
    def test_volume_resize_success_databases(self):
        databases = instance_info.dbaas.databases.list(instance_info.id)
        db_list = []
        for database in databases:
            db_list.append(database.name)
        for name in self.expected_dbs:
            if not name in db_list:
                fail("Database %s was not found after the volume resize. "
                     "Returned list: %s" % (name, databases))
