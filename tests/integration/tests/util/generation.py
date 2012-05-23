

class InstanceGenerator(object):

    def __init__(self, client, status=None, name=None, flavor=None,
                account_id=None, created_at=None, databases=None, users=None,
                volume_size=None):
        self.client = client
        self.status = status
        self.name = name
        self.flavor = flavor
        self.account_id = account_id
        self.databases = databases
        self.users = users
        self.volume_size = volume_size

    def create_instance(self):
        #make the call to create the instance
        instance = self.client.instances.create(self.name, self.flavor,
                                self.volume_size, self.databases, self.users)
        self.client.assert_http_code(200)

        #verify we are in a build state
        assert_equal(instance.status, "BUILD")
        #pull out the ID
        self.id = instance.id

        return instance

    def wait_for_build_to_finish(self):
        poll_until(lambda : self.client.instance.get(self.id),
                   lambda instance : instance.status != "BUILD",
                   time_out=instance_create_time)

    def get_active_instance(self):
        instance = self.client.instance.get(self.id)
        self.client.assert_http_code(200)

        #check the container name
        assert_equal(instance.name, self.name)

        #pull out volume info and verify
        assert_equal(str(instance.volume_size), str(self.volume_size))

        #pull out the flavor and verify
        assert_equal(str(instance.flavor), str(self.flavor))

        return instance
