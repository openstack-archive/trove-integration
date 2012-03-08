import time
import unittest

from proboscis import test
from proboscis.decorators import time_out

from reddwarfclient import Dbaas
from nova import flags
from nova import utils

from reddwarf import exception
from reddwarf.utils import poll_until

import rsdns
from tests.api.instances import instance_info
from tests.api.instances import GROUP_START as INSTANCE_START
from tests.api.instances import GROUP_TEST
from tests.api.instances import GROUP_STOP as INSTANCE_STOP

dns_driver = None

FLAGS = flags.FLAGS
GROUP = "dbaas.guest.dns"


@test(groups=[GROUP, GROUP_TEST])
class Setup(unittest.TestCase):
    """Creates the DNS Driver and entry factory used in subsequent tests."""

    def test_create_rs_dns_driver(self):
        global dns_driver
        dns_driver = utils.import_object(FLAGS.dns_driver)


@test(depends_on_classes=[Setup],
      depends_on_groups=[INSTANCE_START],
      groups=[GROUP, GROUP_TEST])
class WhenInstanceIsCreated(unittest.TestCase):
    """Make sure the DNS name was provisioned.

    This class actually calls the DNS driver to confirm the entry that should
    exist for the given instance does exist.

    """

    def test_dns_entry_should_exist(self):
        entry = instance_info.expected_dns_entry()
        if entry:
            def get_entries():
                return dns_driver.get_entries_by_name(entry.name)
            try:
                poll_until(get_entries, lambda entries: len(entries) > 0,
                                 sleep_time=2, time_out = 60)
            except exception.PollTimeOut:
                self.fail("Did not find name " + entry.name + \
                          " in the entries, which were as follows:"
                          + str(dns_driver.get_entries()))


@test(depends_on_classes=[Setup, WhenInstanceIsCreated],
      depends_on_groups=[INSTANCE_STOP],
      groups=[GROUP])
class AfterInstanceIsDestroyed(unittest.TestCase):
    """Make sure the DNS name is removed along with an instance.

    Because the compute manager calls the DNS manager with RPC cast, it can
    take awhile.  So we wait for 30 seconds for it to disappear.

    """

    def test_dns_entry_exist_should_be_removed_shortly_thereafter(self):
        entry = instance_info.expected_dns_entry()

        if not entry:
            return

        def get_entries():
            return dns_driver.get_entries_by_name(entry.name)

        try:
            poll_until(get_entries, lambda entries : len(entries) == 0,
                             sleep_time=2, time_out=60)
        except exception.PollTimeOut:
            # Manually delete the rogue item
            dns_driver.delete_entry(entry.name, entry.type, entry.dns_zone)
            self.fail("The DNS entry was never deleted when the instance "
                      "was destroyed.")
