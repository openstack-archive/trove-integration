# vim: tabstop=4 shiftwidth=4 softtabstop=4

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

"""
:mod:`tests` -- Utility methods for tests.
===================================

.. automodule:: utils
   :platform: Unix
   :synopsis: Tests for Nova.
.. moduleauthor:: Nirmal Ranganathan <nirmal.ranganathan@rackspace.com>
.. moduleauthor:: Tim Simpson <tim.simpson@rackspace.com>
"""


from nose.tools import assert_false
from nose.tools import assert_true

from tests.util import report


CALLED_MONKEY_PATCH = False


def add_report_event_to(home, name):
    """Takes a module, class, etc, and an attribute name to decorate."""
    func = getattr(home, name)

    def __cb(*args, **kwargs):
        # While %s turns a var into a string but in some rare cases explicit
        # str() is less likely to raise an exception.
        arg_strs = [repr(arg) for arg in args]
        arg_strs += ['%s=%s' % (repr(key), repr(value))
                     for (key, value) in kwargs.items()]
        report.log("[RDC] Calling : %s(%s)..." % (name, ','.join(arg_strs)))
        value = func(*args, **kwargs)
        report.log("[RDC]     returned %s." % str(value))
        return value
    setattr(home, name, __cb)


def monkey_patch_reddwarf_client():
    """Make some methods in RDC add to the test report."""
    global CALLED_MONKEY_PATCH
    if CALLED_MONKEY_PATCH:
        raise RuntimeError("monkey_patch_reddwarf_client called twice!")
    CALLED_MONKEY_PATCH = True
    from reddwarfclient import instances
    add_report_event_to(instances.Instances, "create")
    add_report_event_to(instances.Instances, "delete")
    add_report_event_to(instances.Instances, "resize_instance")
    add_report_event_to(instances.Instances, "resize_volume")
    add_report_event_to(instances.Instances, "restart")


class TestClient(object):
    """Decorates the rich clients with some extra methods.

    These methods are filled with test asserts, meaning if you use this you
    get the tests for free.

    """

    def __init__(self, real_client):
        """Accepts a normal client."""
        self.real_client = real_client

    @staticmethod
    def find_flavor_self_href(flavor):
        self_links = [link for link in flavor.links if link['rel'] == 'self']
        assert_true(len(self_links) > 0, "Flavor had no self href!")
        flavor_href = self_links[0]['href']
        assert_false(flavor_href is None, "Flavor link self href missing.")
        return flavor_href

    def find_flavors_by_ram(self, ram, flavor_manager=None):
        flavor_manager = flavor_manager or self.flavors
        assert_false(ram is None)
        flavors = flavor_manager.list()
        return [flavor for flavor in flavors if flavor.ram == ram]

    def find_flavor_and_self_href(self, flavor_id, flavor_manager=None):
        """Given an ID, returns flavor and its self href."""
        flavor_manager = flavor_manager or self.flavors
        assert_false(flavor_id is None)
        flavor = flavor_manager.get(flavor_id)
        assert_false(flavor is None)
        flavor_href = self.find_flavor_self_href(flavor)
        return flavor, flavor_href

    def find_image_and_self_href(self, image_id):
        """Given an ID, returns tuple with image and its self href."""
        assert_false(image_id is None)
        image = self.images.get(image_id)
        assert_true(image is not None)
        self_links = [link['href'] for link in image.links
                      if link['rel'] == 'self']
        assert_true(len(self_links) > 0,
                        "Found image with ID %s but it had no self link!" %
                        str(image_id))
        image_href = self_links[0]
        assert_false(image_href is None, "Image link self href missing.")
        return image, image_href

    def __getattr__(self, item):
        return getattr(self.real_client, item)
