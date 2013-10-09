from proboscis.decorators import time_out
from proboscis import after_class
from proboscis import before_class
from proboscis import test
from proboscis.asserts import assert_equal
from proboscis.asserts import assert_false
from proboscis.asserts import assert_is
from proboscis.asserts import assert_is_not
from proboscis.asserts import assert_is_none
from proboscis.asserts import assert_not_equal
from proboscis.asserts import assert_raises
from proboscis.asserts import assert_true
from proboscis.asserts import Check
from proboscis.asserts import fail

from troveclient.compat import exceptions
from tests import util
from tests.util import create_dbaas_client
from tests.util import test_config
from trove.tests.util.users import Requirements
from tests.util import report


class TestBase(object):

    def set_up(self):
        """Create a ton of instances."""
        reqs = Requirements(is_admin=False)
        self.user = test_config.users.find_user(reqs)
        self.dbaas = create_dbaas_client(self.user)

    def delete_instances(self):
        attempts = 0
        while True:
            instances = self._list_all()
            # Sit around and try to delete this chunk.
            instance_results = []
            attempts += 1
            deleted_count = 0
            for instance in instances:
                try:
                    instance.delete()
                    result = "[.]"
                except exceptions.UnprocessableEntity:
                    result = "[o]"
                except exceptions.NotFound:
                    result = "[O]"
                    deleted_count += 1
                except Exception:
                    result = "[X]"
                instance_results.append(result)
            print("Delete Attempt %d : %s"
                  % (attempts, ",".join(instance_results)))
            if deleted_count == len(instances):
                break

    def create_instances(self):
        self.ids = []
        for index in range(self.max):
            name = "multi-%03d" % index
            result = self.dbaas.instances.create(name, 1,
                                   {'size': 1}, [], [])
            self.ids.append(result.id)
        # Sort the list of IDs in order, so we can confirm the lists pagination
        # returns is also sorted correctly.
        self.ids.sort()

    def _list_all(self):
        """Get all items back as a list."""
        instances = []
        for id in self.ids:
            try:
                instance = self.dbaas.instances.get(id)
                instances.append(instance)
            except exceptions.NotFound:
                pass
        return instances

    @staticmethod
    def assert_instances_sorted_by_ids(instances):
        # Assert that the strings are always increasing.
        last_id = ""
        for instance in instances:
            assert_true(last_id < instance.id)

    def print_list(self, instances):
        print("Length = %d" % len(instances))
        print(",".join([instance.id for instance in instances]))


@test(runs_after_groups=["dbaas.guest.shutdown"],
      groups=['recreates.create_11'])
class Create_11(TestBase):
    """
    This test creates some number of instances and waits for them to all
    reach an ACTIVE status before deleting them.
    """

    max = 11

    @before_class
    def set_up(self):
        """Create a ton of instances."""
        super(Create_11, self).set_up()
        #self.delete_instances()
        self.create_instances()
        report.log("Create_11: Created the following batch of instances:")
        for id in self.ids:
            report.log(id)

    def _wait_for_all_active(self):
        chunk = 0
        attempts = 0
        quit = False
        while not quit:
            attempts += 1
            instances = self._list_all()
            quit = True
            instance_results = []
            for instance in instances:
                if instance.status == "BUILD":
                    result = "[.]"
                    quit = False
                elif instance.status == "ACTIVE":
                    result = "[O]"
                else:
                    result = "[X]"
                instance_results.append(result)
            print("Wait attempt %d : %s"
                      % (attempts, ",".join(instance_results)))

    @test
    def wait_for_all_active(self):
        self._wait_for_all_active()

    @test(depends_on=[wait_for_all_active])
    def tear_down(self):
        """Tear down all instances."""
        with Check() as check:
            for instance in self._list_all():
                check.equal(instance.status, "ACTIVE",
                            "Instance %s not active but is %s!"
                            % (instance.id, instance.status))
        self.delete_instances()
