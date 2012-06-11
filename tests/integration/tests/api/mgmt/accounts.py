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

from reddwarfclient import exceptions

from nose.plugins.skip import SkipTest

from proboscis import before_class
from proboscis import test
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_false
from proboscis.asserts import assert_is_not_none
from proboscis.asserts import assert_not_equal
from proboscis.asserts import assert_raises
from proboscis.asserts import assert_true
from proboscis.asserts import fail

import tests
from tests import CLEAN_SLATE
from tests.api.instances import instance_info
from tests.util import test_config
from tests.util import create_dbaas_client
from tests.util.users import Requirements

GROUP = "dbaas.api.mgmt.accounts"


@test(groups=[tests.DBAAS_API, GROUP, tests.PRE_INSTANCES],
      depends_on_groups=["services.initialize"])
class AccountsBeforeInstanceCreation(object):

    @before_class
    def setUp(self):
        self.user = test_config.users.find_user(Requirements(is_admin=True))
        self.client = create_dbaas_client(self.user)

    @test
    def test_invalid_account(self):
        raise SkipTest("Don't have a good way yet to know if accounts are valid")
        assert_raises(exceptions.NotFound, self.client.accounts.show,
                      "asd#4#@fasdf")

    @test
    def test_invalid_account_fails(self):
        account_info = self.client.accounts.show("badaccount")
        assert_not_equal(self.user.tenant_id, account_info.id)

    @test
    def test_account_zero_instances(self):
        account_info = self.client.accounts.show(self.user.tenant_id)
        assert_equal(0, len(account_info.instances))
        assert_equal(self.user.tenant_id, account_info.id)


@test(groups=[tests.INSTANCES, GROUP], depends_on_groups=["dbaas.listing"])
class AccountsAfterInstanceCreation(object):

    @before_class
    def setUp(self):
        self.user = test_config.users.find_user(Requirements(is_admin=True))
        self.client = create_dbaas_client(self.user)

    @test
    def test_account_details_available(self):
        account_info = self.client.accounts.show(instance_info.user.tenant_id)
        # Now check the results.
        assert_equal(account_info.id, instance_info.user.tenant_id)
        # Instances: Here we know we've only created one instance.
        assert_equal(1, len(account_info.instances))
        assert_is_not_none(account_info.instances[0]['host'])
        # We know the there's only 1 instance
        instance = account_info.instances[0]
        print("instances in account: %s" % instance)
        assert_equal(instance['id'], instance_info.id)
        assert_equal(instance['name'], instance_info.name)
        assert_equal(instance['status'], "ACTIVE")
        assert_is_not_none(instance['host'])


@test(groups=[tests.POST_INSTANCES, GROUP],
      depends_on_groups=["dbaas.guest.shutdown"])
class AccountsAfterInstanceDeletion(object):

    @before_class
    def setUp(self):
        self.user = test_config.users.find_user(Requirements(is_admin=True))
        self.client = create_dbaas_client(self.user)

    @test
    def test_no_details_empty_account(self):
        account_info = self.client.accounts.show(instance_info.user.tenant_id)
        assert_equal(0, len(account_info.instances))
