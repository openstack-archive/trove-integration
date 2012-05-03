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

from novaclient import exceptions

from proboscis import before_class
from proboscis import test
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_false
from proboscis.asserts import assert_not_equal
from proboscis.asserts import assert_true
from proboscis.asserts import fail

import tests
from tests.api.instances import CheckInstance
from tests.api.instances import instance_info
from tests.util import test_config
from tests.util import create_dbaas_client
from tests.util.users import Requirements

GROUP = "dbaas.api.mgmt.storage"


@test(groups=[tests.DBAAS_API, GROUP, tests.PRE_INSTANCES],
      depends_on_groups=["services.initialize"])
class StorageBeforeInstanceCreation(object):

    @before_class
    def setUp(self):
        self.user = test_config.users.find_user(Requirements(is_admin=True))
        self.client = create_dbaas_client(self.user)

    @test
    def test_storage_on_host(self):
        storage = self.client.storage.index()
        print("storage : %r" % storage)
        for device in storage:
            assert_true(hasattr(device, 'name'),
                        "device.name: %r" % device.name)
            assert_true(hasattr(device, 'availablesize'),
                        "device.availablesize: %r" % device.availablesize)
            assert_true(hasattr(device, 'totalsize'),
                        "device.totalsize: %r" % device.totalsize)
        instance_info.storage = storage


@test(groups=[tests.INSTANCES, GROUP], depends_on_groups=["dbaas.listing"])
class StorageAfterInstanceCreation(object):

    @before_class
    def setUp(self):
        self.user = test_config.users.find_user(Requirements(is_admin=True))
        self.client = create_dbaas_client(self.user)

    @test
    def test_storage_on_host(self):
        storage = self.client.storage.index()
        print("storage : %r" % storage)
        print("instance_info.storage : %r" % instance_info.storage)
        expected_attrs = ['name', 'availablesize', 'totalsize', 'type']
        for index, device in enumerate(storage):
            CheckInstance(None).attrs_exist(device._info, expected_attrs,
                                            msg="Storage")
            assert_equal(device.name, instance_info.storage[index].name)
            instance_totalsize = instance_info.storage[index].totalsize
            assert_equal(device.totalsize, instance_totalsize)
            assert_equal(device.type, instance_info.storage[index].type)
            avail = instance_info.storage[index].availablesize
            avail -= instance_info.volume['size']
            assert_equal(device.availablesize, avail)
