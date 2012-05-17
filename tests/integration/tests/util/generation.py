

class InstanceGenerator(object):

    '''
    def __init__(self, id = None, status = None, name = None, flavor = None,
                    updated = None, created = None, hostname = None,
                    volume_size = None, volume_used = None,
                    rootenabled = None, flavor_links = None, links = None,
                    account_id = None, created_at = None, deleted = None, deleted_at = None,
                    flavorid = None, host = None, ips = None, volumes = None, addresses = None,
                    usernet = None, usernet_addr = None, usernet_version = None, databases = None,
                    guest_status = None, guest_status_created_at = None, guest_status_deleted = None,
                    guest_status_deleted_at = None, guest_status_instance_id = None, guest_status_state = None,
                    guest_status_state_desc = None, guest_status_updated_at = None, root_enabled_at = None, root_enabled_by = None,
                    server_state_description = None, users = None, volume = None,
                    volume_desc = None, volume_id = None, volume_name = None):
        self.id = id
        self.status = status
        self.name = name
        self.flavor = flavor
        self.updated = updated
        self.created = created
        self.hostname = hostname
        self.volume_size = volume_size
        self.rootenabled = rootenabled
        self.flavor_links = flavor_links
        self.links = links
        self.volume_used = volume_used
        self.account_id = account_id
        self.created_at = created_at
        self.deleted = deleted
        self.deleted_at = deleted_at
        self.flavorid = flavorid
        self.host = host
        self.ips = ips
        self.volumes = volumes
        self.addresses = addresses
        self.usernet = usernet
        self.usernet_addr = usernet_addr
        self.usernet_version = usernet_version
        self.databases = databases
        self.guest_status = guest_status
        self.guest_status_created_at = guest_status_created_at
        self.guest_status_deleted = guest_status_deleted
        self.guest_status_deleted_at = guest_status_deleted_at
        self.guest_status_instance_id = guest_status_instance_id
        self.guest_status_state = guest_status_state
        self.guest_status_state_desc = guest_status_state_desc
        self.guest_status_updated_at = guest_status_updated_at
        self.root_enabled_at = root_enabled_at
        self.root_enabled_by = root_enabled_by
        self.server_state_description = server_state_description
        self.users = users
        self.volume = volume
        self.volume_desc = volume_desc
        self.volume_id = volume_id
        self.volume_name = volume_name

    '''

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
