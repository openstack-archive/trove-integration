#    Copyright 2011 OpenStack LLC
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

from novaclient import exceptions as nova_exceptions

from proboscis import before_class
from proboscis import test
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_false
from proboscis.asserts import assert_not_equal
from proboscis.asserts import assert_raises
from proboscis.asserts import assert_true
from proboscis.asserts import fail
from proboscis.decorators import expect_exception
from proboscis.decorators import time_out

import tests

from tests import util
from tests.api.instances import instance_info
from tests.openvz.dbaas_ovz import TestMysqlAccess
from tests.util import test_config

GROUP="dbaas.api.databases"
FAKE = test_config.values['fake_mode']

@test(depends_on_classes=[TestMysqlAccess], groups=[tests.DBAAS_API, GROUP,
                                                    tests.INSTANCES])
class TestDatabases(object):
    """
    Test the creation and deletion of additional MySQL databases
    """

    dbname = "third #?@some_-"
    dbname_urlencoded = "third%20%23%3F%40some_-"

    dbname2 = "seconddb"
    created_dbs = [dbname, dbname2]
    system_dbs = ['information_schema','mysql', 'lost+found']

    @before_class
    def setUp(self):
        self.dbaas = util.create_dbaas_client(instance_info.user)
        self.dbaas_admin = util.create_dbaas_client(instance_info.admin_user)

    @test
    def test_create_database(self):
        databases = list()
        databases.append({"name": self.dbname, "charset": "latin2",
                          "collate": "latin2_general_ci"})
        databases.append({"name": self.dbname2})

        self.dbaas.databases.create(instance_info.id, databases)
        if not FAKE:
            time.sleep(5)

    @test
    def test_create_database_list(self):
        databases = self.dbaas.databases.list(instance_info.id)
        found = False
        for db in self.created_dbs:
            for result in databases:
                if result.name == db:
                    found = True
            assert_true(found, "Database '%s' not found in result" % db)
            found = False

    @test
    def test_create_database_list_system(self):
        #Databases that should not be returned in the list
        databases = self.dbaas.databases.list(instance_info.id)
        found = False
        for db in self.system_dbs:
            found = any(result.name == db for result in databases)
            assert_false(found, "Database '%s' SHOULD NOT be found in result" % db)
            found = False

    @test
    def test_create_database_on_missing_instance(self):
        databases = [{"name": "invalid_db", "charset": "latin2",
                      "collate": "latin2_general_ci"}]
        assert_raises(nova_exceptions.NotFound, self.dbaas.databases.create,
                      -1, databases)

    @test
    def test_delete_database_on_missing_instance(self):
        assert_raises(nova_exceptions.NotFound, self.dbaas.databases.delete,
                      -1, self.dbname_urlencoded)

    @test
    def test_delete_database(self):
        self.dbaas.databases.delete(instance_info.id, self.dbname_urlencoded)
        if not FAKE:
            time.sleep(5)
        dbs = self.dbaas.databases.list(instance_info.id)
        found = any(result.name == self.dbname_urlencoded for result in dbs)
        assert_false(found, "Database '%s' SHOULD NOT be found in result" %
                     self.dbname_urlencoded)

    @test
    def test_database_name_too_long(self):
        databases = []
        databases.append({"name": "aasdlkhaglkjhakjdkjgfakjgadgfkajsg34523dfkljgasldkjfglkjadsgflkjagsdd"})
        assert_raises(nova_exceptions.BadRequest, self.dbaas.databases.create,
                      instance_info.id, databases)

    @test
    def test_invalid_database_name(self):
        databases = []
        databases.append({"name": "sdfsd,"})
        assert_raises(nova_exceptions.BadRequest, self.dbaas.databases.create,
                      instance_info.id, databases)
