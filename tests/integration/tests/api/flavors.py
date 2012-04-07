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

import os

from nose.tools import assert_equal
from nose.tools import assert_false
from nose.tools import assert_true

from proboscis import before_class
from proboscis import test

import tests
from tests.util import create_dbaas_client
from tests.util import create_nova_client
from tests.util import test_config
from tests.util.users import Requirements


GROUP="dbaas.api.flavors"


servers_flavors=None
dbaas_flavors=None
user=None


def assert_attributes_are_equal(name, os_flavor, dbaas_flavor):
    """Given an attribute name and two objects ensures the attribute is equal."""
    assert_true(hasattr(os_flavor, name),
                "open stack flavor did not have attribute %s" % name)
    assert_true(hasattr(dbaas_flavor, name),
                "dbaas flavor did not have attribute %s" % name)
    expected = getattr(os_flavor, name)
    actual = getattr(dbaas_flavor, name)
    assert_equal(expected, actual,
                 'DBaas flavor differs from Open Stack on attribute ' + name)


def assert_flavors_are_roughly_equivalent(os_flavor, dbaas_flavor):
    assert_attributes_are_equal('name', os_flavor, dbaas_flavor)
    assert_attributes_are_equal('ram', os_flavor, dbaas_flavor)
    assert_false(hasattr(dbaas_flavor, 'disk'),
                 "The attribute 'disk' s/b absent from the dbaas API.")


def assert_link_list_is_equal(flavor):
    assert_true(hasattr(flavor, 'links'))
    assert_true(flavor.links)

    for link in flavor.links:
        href = link['href']
        if "self" in link['rel']:
            expected_href = os.path.join(test_config.dbaas.url, "flavors",
                                             str(flavor.id))
            assert_true(href.startswith(test_config.dbaas_url.replace('http:', 'https:', 1)),
                        "REL HREF %s doesn't start with %s" % (href, test_config.dbaas_url))
            assert_true(href.endswith(os.path.join("flavors", str(flavor.id))),
                        "REL HREF %s doesn't end in 'flavors/id'" % href)
        elif "bookmark" in link['rel']:
            base_url = test_config.version_url.replace('http:', 'https:', 1)
            expected_href = os.path.join(base_url, "flavors", str(flavor.id))
            assert_equal(href, expected_href,
                         'bookmark "href" must be %s, not %s' % (expected_href, href))
        else:
            assert_false(True, "Unexpected rel - %s" % link['rel'])


@test(groups=[tests.DBAAS_API, GROUP, tests.PRE_INSTANCES],
      depends_on_groups=["services.initialize"])
class Flavors(object):

    @before_class
    def setUp(self):
        nova_user = test_config.users.find_user(
            Requirements(is_admin=False, services=["nova"]))
        rd_user = test_config.users.find_user(
            Requirements(is_admin=False, services=["reddwarf"]))
        self.nova_client = create_nova_client(nova_user)
        self.rd_client = create_dbaas_client(rd_user)

    @test
    def confirm_flavors_lists_are_nearly_identical(self):
        os_flavors = self.nova_client.flavors.list()
        dbaas_flavors = self.rd_client.flavors.list()

        print("Open Stack Flavors:")
        print(os_flavors)
        print("DBaaS Flavors:")
        print(dbaas_flavors)
        assert_equal(len(os_flavors), len(dbaas_flavors),
                     "Length of both flavors list should be identical.")
        for os_flavor in os_flavors:
            found_index = None
            for index, dbaas_flavor in enumerate(dbaas_flavors):
                if os_flavor.name == dbaas_flavor.name:
                    assert_true(found_index is None,
                                "Flavor ID '%s' appears in elements #%s and #%d." %\
                                (dbaas_flavor.id, str(found_index), index))
                    assert_flavors_are_roughly_equivalent(os_flavor, dbaas_flavor)
                    found_index = index
            assert_false(found_index is None,
                         "Some flavors from OS list were missing in DBAAS list.")
        for flavor in dbaas_flavors:
            assert_link_list_is_equal(flavor)
