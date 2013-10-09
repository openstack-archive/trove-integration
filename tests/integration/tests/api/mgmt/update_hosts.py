import time

from proboscis import after_class
from proboscis import before_class
from proboscis import test
from proboscis.asserts import assert_not_equal
from proboscis.decorators import time_out

from troveclient.compat import exceptions
from tests import util
from tests.util import create_dbaas_client
from tests.util import test_config
from trove.tests.util.users import Requirements


class TestBase(object):

    def set_up(self):
        reqs = Requirements(is_admin=True)
        self.user = test_config.users.find_user(reqs)
        self.dbaas = create_dbaas_client(self.user)

    def delete_instances(self):
        chunk = 0
        while True:
            chunk += 1
            attempts = 0
            instances = self.dbaas.instances.list()
            if len(instances) == 0:
                break
            # Sit around and try to delete this chunk.
            while True:
                instance_results = []
                attempts += 1
                deleted_count = 0
                for instance in instances:
                    try:
                        instance.delete()
                        result = "[w]"
                    except exceptions.UnprocessableEntity:
                        result = "[W]"
                    except exceptions.NotFound:
                        result = "[O]"
                        deleted_count += 1
                    except Exception:
                        result = "[X]"
                    instance_results.append(result)
                print("Chunk %d, attempt %d : %s"
                      % (chunk, attempts, ",".join(instance_results)))
                if deleted_count == len(instances):
                    break

    def create_instances(self):
        self.ids = []
        for index in range(self.max):
            name = "multi-%03d" % index
            result = self.dbaas.instances.create(name, 1,
                                   {'size': 1}, [], [])
            self.ids.append(result.id)
        self.ids.sort()

    def wait_for_instances(self):
        while True:
            total_instances = 0
            hosts = self.dbaas.hosts.index()
            for host in hosts:
                total_instances += host.instanceCount
            if total_instances >= self.max:
                break
            time.sleep(1)

    def test_update(self):
        before_versions = {}
        for id in self.ids:
            diagnostics = self.dbaas.diagnostics.get(id)
            before_versions[id] = diagnostics.version

        hosts = self.dbaas.hosts.index()
        for host in hosts:
            self.dbaas.hosts.update_all(host.name)

        after_versions = {}
        for id in self.ids:
            diagnostics = self.dbaas.diagnostics.get(id)
            after_versions[id] = diagnostics.version

        for id in after_versions:
            assert_not_equal(before_versions[id], after_versions[id])


@test(depends_on_groups=["services.initialize"],
      groups=['dbaas.api.mgmt.hosts.update'])
class HostUpdate(TestBase):
    max = 5

    @before_class
    def set_up(self):
        """Create instances."""
        super(HostUpdate, self).set_up()
        self.delete_instances()
        self.create_instances()

    @test
    @time_out(60)
    def wait_for_all_instances(self):
        self.wait_for_instances()

    @test(depends_on=[wait_for_all_instances])
    def update(self):
        self.test_update()

    @after_class(always_run=True)
    @time_out(60)
    def tear_down(self):
        self.delete_instances()
