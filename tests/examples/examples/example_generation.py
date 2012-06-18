import httplib2
import json
import os
import re
import sys
import time
from urlparse import urlparse
import xml.dom.minidom


class ExampleGenerator(object):

    def __init__(self, config_file):
        if not os.path.exists(config_file):
            raise RuntimeError("Could not find Example CONF at %s." %
                               config_file)
        file_contents = open(config_file, "r").read()
        try:
            config = json.loads(file_contents)
        except Exception as exception:
            msg = 'Error loading config file "%s".' % config_file
            raise RuntimeError(msg, exception)

        self.directory = config.get("directory", None)
        if not self.directory.endswith('/'):
            self.directory += '/'
        print "directory = %s" % self.directory
        self.api_url = config.get("api_url", None)
        print "api_url = %s" % self.api_url
        #auth
        auth_url = config.get("auth_url", None)
        print "auth_url = %s" % auth_url
        username = config.get("username", None)
        print "username = %s" % username
        password = config.get("password", None)
        print "password = %s" % password
        self.tenant = config.get("tenant", None)
        self.replace_host = config.get("replace_host", None)
        print "tenant = %s" % self.tenant
        self.replace_dns_hostname = config.get("replace_dns_hostname", None)
        auth_id, tenant_id = self.get_auth_token_id_tenant_id(auth_url,
                                                              username,
                                                              password)
        print "id = %s" % auth_id
        self.headers = {
            'X-Auth-Token': str(auth_id)
        }
        print "tenantID = %s" % tenant_id
        self.tenantID = tenant_id
        self.dbaas_url = "%s/v1.0/%s" % (self.api_url, self.tenantID)

    # print_req and print_resp for debugging purposes
    def http_call(self, name, method, json, xml, 
                  output=True, print_req=False, print_resp=False):
        name = name.replace('_', '-')
        print "http call for %s" % name
        http = httplib2.Http(disable_ssl_certificate_validation=True)
        req_headers = {'User-Agent': "python-example-client",
                       'Content-Type': "application/json",
                       'Accept': "application/json"
                      }
        req_headers.update(self.headers)


        content_type = 'json'
        request_body = json.get('body', None)
        url = json.get('url')
        if output:
            filename = "%sdb-%s-request.%s" % (self.directory, name,
                                               content_type)
            with open(filename, "w") as file:
                output = self.output_request(url, req_headers, request_body,
                                             content_type, method)
                output = output.replace(self.tenantID, '1234')
                if self.replace_host:
                    output = output.replace(self.api_url, self.replace_host)
                    pre_host_port = urlparse(self.api_url).netloc
                    post_host = urlparse(self.replace_host).netloc
                    output = output.replace(pre_host_port, post_host)
                file.write(output)
                if print_req:
                    print "\tJSON req url:", url
                    print "\tJSON req method:", method
                    print "\tJSON req headers:", req_headers
                    print "\tJSON req body:", request_body

        resp, resp_content = http.request(url, method, body=request_body,
                                          headers=req_headers)
        json_resp = resp, resp_content
        if output:
            filename = "%sdb-%s-response.%s" % (self.directory, name,
                                                content_type)
            with open(filename, "w") as file:
                output = self.output_response(resp, resp_content, content_type)
                output = output.replace(self.tenantID, '1234')
                if self.replace_host:
                    output = output.replace(self.api_url, self.replace_host)
                    pre_host_port = urlparse(self.api_url).netloc
                    post_host = urlparse(self.replace_host).netloc
                    output = output.replace(pre_host_port, post_host)
                file.write(output)
                if print_resp:
                    print "\tJSON resp:", resp
                    print "\tJSON resp content:", resp_content
                    print "\n"


        content_type = 'xml'
        req_headers['Accept'] = 'application/xml'
        req_headers['Content-Type'] = 'application/xml'
        request_body = xml.get('body', None)
        url = xml.get('url')
        if output:
            filename = "%sdb-%s-request.%s" % (self.directory, name,
                                               content_type)
            with open(filename, "w") as file:
                output = self.output_request(url, req_headers, request_body,
                                             content_type, method)
                if self.replace_host:
                    output = output.replace(self.api_url, self.replace_host)
                    pre_host_port = urlparse(self.api_url).netloc
                    post_host = urlparse(self.replace_host).netloc
                    output = output.replace(pre_host_port, post_host)
                file.write(output)
                if print_req:
                    print "\tXML req url:", url
                    print "\tXML req method:", method
                    print "\tXML req headers:", req_headers
                    print "\tXML req body:", request_body
        resp, resp_content = http.request(url, method, body=request_body,
                                          headers=req_headers)
        xml_resp = resp, resp_content
        if output:
            filename = "%sdb-%s-response.%s" % (self.directory, name,
                                                content_type)
            with open(filename, "w") as file:
                output = self.output_response(resp, resp_content, content_type)
                if self.replace_host:
                    output = output.replace(self.api_url, self.replace_host)
                    pre_host_port = urlparse(self.api_url).netloc
                    post_host = urlparse(self.replace_host).netloc
                    output = output.replace(pre_host_port, post_host)
                file.write(output)
                if print_resp:
                    print "\tXML resp:", resp
                    print "\tXML resp content:", resp_content
                    print "\n"


        return json_resp, xml_resp

    def _indent_xml(self, my_string):
        my_string = my_string.encode("utf-8")
        # convert to plain string without indents and spaces
        my_re = re.compile('>\s+([^\s])', re.DOTALL)
        my_string = myre.sub('>\g<1>', my_string)
        my_string = xml.dom.minidom.parseString(my_string).toprettyxml()
        # remove line breaks
        my_re = re.compile('>\n\s+([^<>\s].*?)\n\s+</', re.DOTALL)
        my_string = my_re.sub('>\g<1></', my_string)
        return my_string

    def output_request(self, url, output_headers, body, content_type, method,
                       static_auth_token=True):
        output_list = []
        parsed = urlparse(url)
        if parsed.query:
            method_url = parsed.path + '?' + parsed.query
        else:
            method_url = parsed.path
        output_list.append("%s %s HTTP/1.1" % (method, method_url))
        output_list.append("User-Agent: %s" % output_headers['User-Agent'])
        output_list.append("Host: %s" % parsed.netloc)
        # static_auth_token option for documentation purposes
        if static_auth_token:
            output_token = '87c6033c-9ff6-405f-943e-2deb73f278b7'
        else:
            output_token = output_headers['X-Auth-Token']
        output_list.append("X-Auth-Token: %s" % output_token)
        output_list.append("Accept: %s" % output_headers['Accept'])
        output_list.append("Content-Type: %s" % output_headers['Content-Type'])
        output_list.append("")
        pretty_body = self.format_body(body, content_type)
        output_list.append("%s" % pretty_body)
        output_list.append("")
        return '\n'.join(output_list)

    def output_response(self, resp, body, content_type):
        output_list = []
        version = "1.1" if resp.version == 11 else "1.0"
        lines = [
            ["HTTP/%s %s %s" % (version, resp.status, resp.reason)],
            ["Content-Type: %s" % resp['content-type']],
            ["Content-Length: %s" % resp['content-length']],
            ["Date: %s" % resp['date']]]
        new_lines = [x[0] for x in lines]
        joined_lines = '\n'.join(new_lines)
        output_list.append(joined_lines)
        if body:
            output_list.append("")
            pretty_body = self.format_body(body, content_type)
            output_list.append("%s" % pretty_body)
        output_list.append("")
        return '\n'.join(output_list)

    def format_body(self, body, content_type):
        if content_type == 'json':
            try:
                if self.replace_dns_hostname:
                    before = r'\"hostname\": \"[a-zA-Z0-9-_\.]*\"'
                    after = '\"hostname\": \"%s\"' % self.replace_dns_hostname
                    body = re.sub(before, after, body)
                return json.dumps(json.loads(body), sort_keys=True, indent=4)
            except Exception:
                return body if body else ''
        else:
            # expected type of body is xml
            try:
                if self.replace_dns_hostname:
                    hostname = 'hostname=\"%s\"' % self.replace_dns_hostname,
                    body = re.sub(r'hostname=\"[a-zA-Z0-9-_\.]*\"',
                                  hostname, body)
                return self._indent_xml(body)
            except Exception as ex:
                return body if body else ''

    def get_auth_token_id_tenant_id(self, url, username, password):
        body = ('{"auth":{"tenantName": "%s", "passwordCredentials": '
                '{"username": "%s", "password": "%s"}}}')
        body = body % (self.tenant, username, password)
        http = httplib2.Http(disable_ssl_certificate_validation=True)
        req_headers = {'User-Agent': "python-example-client",
                       'Content-Type': "application/json",
                       'Accept': "application/json",
                      }
        resp, body = http.request(url, 'POST', body=body, headers=req_headers)
        auth = json.loads(body)
        auth_id = auth['access']['token']['id']
        tenant_id = auth['access']['token']['tenant']['id']
        return auth_id, tenant_id

    # default to two for json and xml instances
    def wait_for_instances(self, num=2):
        example_instances = []
        # wait for instances
        while True:
            req_json = {"url": "%s/instances" % self.dbaas_url}
            req_xml = {"url": "%s/instances" % self.dbaas_url}
            resp = self.http_call("get_instances", 'GET', req_json, req_xml,
                                  output=False)
            resp_json, resp_xml = resp
            resp_content = json.loads(resp_json[1])
            instances = resp_content['instances']
            print_list = [(instance['id'], instance['status']) for instance
                          in instances]
            print "checking  for : %s\n" % print_list
            bad_status = ['ACTIVE', 'ERROR', 'FAILED', 'SHUTDOWN']
            list_id_status = [(instance['id'], instance['status']) for instance
                              in instances if instance['status'] in bad_status]
            # TODO(pdmars): because of pagination we're now creating 2
            # instances again at the end of main
            if len(list_id_status) == num:
                statuses = [item[1] for item in list_id_status]
                if statuses.count('ACTIVE') != num:
                    break
                example_instances = [inst[0] for inst in list_id_status]
                print "\nusing instance ids ---\n%s\n" % example_instances
                # instances should be ready now.
                break
            else:
                time.sleep(15)
        return example_instances

    def check_clean(self):
        req_json = {"url": "%s/instances" % self.dbaas_url}
        req_xml = {"url": "%s/instances" % self.dbaas_url}
        resp_json, resp_xml = self.http_call("get_instances", 'GET',
                                             req_json, req_xml, output=False)
        resp_content = json.loads(resp_json[1])
        instances = resp_content['instances']
        if len(instances) > 0:
            msg = "Environment must be clean to run the example generator."
            raise Exception(msg)
        print "\n\nClean environment building examples...\n\n"

    def get_versions(self):
        #no auth required
        req_json = {"url": "%s/" % self.api_url}
        req_xml = {"url": "%s/" % self.api_url}
        self.http_call("versions", 'GET', req_json, req_xml)

    def get_version(self):
        req_json = {"url": "%s/v1.0/" % self.api_url}
        req_xml = {"url": "%s/v1.0/" % self.api_url}
        self.http_call("version", 'GET', req_json, req_xml)

    def get_flavors(self):
        req_json = {"url": "%s/flavors" % self.dbaas_url}
        req_xml = {"url": "%s/flavors" % self.dbaas_url}
        self.http_call("flavors", 'GET', req_json, req_xml)

    def get_flavor_details(self):
        req_json = {"url": "%s/flavors/detail" % self.dbaas_url}
        req_xml = {"url": "%s/flavors/detail" % self.dbaas_url}
        self.http_call("flavors_detail", 'GET', req_json, req_xml)

    def get_flavor_by_id(self):
        req_json = {"url": "%s/flavors/1" % self.dbaas_url}
        req_xml = {"url": "%s/flavors/1" % self.dbaas_url}
        self.http_call("flavors_by_id", 'GET', req_json, req_xml)

    def post_create_instance(self):
        req_json = {"url": "%s/instances" % self.dbaas_url}
        req_xml = {"url": "%s/instances" % self.dbaas_url}
        JSON_DATA = {
            "instance": {
                "name": "json_rack_instance",
                "flavorRef": "%s/flavors/1" % self.dbaas_url,
                "databases": [
                        {
                        "name": "sampledb",
                        "character_set": "utf8",
                        "collate": "utf8_general_ci"
                    },
                        {
                        "name": "nextround"
                    }
                ],
                "volume":
                        {
                        "size": "2"
                    }
            }
        }
        XML_DATA = ('<?xml version="1.0" ?>'
                    '<instance xmlns='
                    '"http://docs.openstack.org/database/api/v1.0"'
                    ' name="xml_rack_instance" flavorRef="%s/flavors/1">'
                    '<databases>'
                    '<database name="sampledb" character_set="utf8" '
                    'collate="utf8_general_ci" />'
                    '<database name="nextround" />'
                    '</databases>'
                    '<volume size="2" />'
                    '</instance>') % self.dbaas_url
        req_json['body'] = json.dumps(JSON_DATA)
        req_xml['body'] = XML_DATA
        self.http_call("create_instance", 'POST', req_json, req_xml)

    def post_create_databases(self, database_name, instance_ids):
        req_json = {"url": "%s/instances/%s/databases"
                            % (self.dbaas_url, instance_ids['json'])}
        req_xml = {"url": "%s/instances/%s/databases"
                            % (self.dbaas_url, instance_ids['xml'])}
        JSON_DATA = {
            "databases": [
                    {
                    "name": "testingdb",
                    "character_set": "utf8",
                    "collate": "utf8_general_ci"
                },
                    {
                    "name": "anotherdb"
                },
                    {
                    "name": "oneMoreDB"
                }
            ]
        }
        XML_DATA = ('<?xml version="1.0" ?>'
                    '<Databases xmlns="'
                    'http://docs.openstack.org/database/api/v1.0">'
                    '<Database name="%s" character_set="utf8" collate='
                    '"utf8_general_ci" />'
                    '<Database name="anotherexampledb" />'
                    '<Database name="oneMoreExampledb" />'
                    '</Databases>') % database_name
        req_json['body'] = json.dumps(JSON_DATA)
        req_xml['body'] = XML_DATA
        self.http_call("create_databases", 'POST', req_json, req_xml)

    def get_list_databases(self, instance_ids):
        req_json = {"url": "%s/instances/%s/databases"
                            % (self.dbaas_url, instance_ids['json'])}
        req_xml = {"url": "%s/instances/%s/databases"
                            % (self.dbaas_url, instance_ids['xml'])}
        self.http_call("list_databases", 'GET', req_json, req_xml)

    def get_list_databases_limit_two(self, instance_ids):
        req_json = {"url": "%s/instances/%s/databases?limit=1"
                            % (self.dbaas_url, instance_ids['json'])}
        req_xml = {"url": "%s/instances/%s/databases?limit=2"
                            % (self.dbaas_url, instance_ids['xml'])}
        self.http_call("list_databases_pagination", 'GET', req_json, req_xml)


    def delete_databases(self, database_name, instance_ids):
        req_json = {"url": "%s/instances/%s/databases/%s"
                            % (self.dbaas_url, instance_ids['json'],
                               database_name)}
        req_xml = {"url": "%s/instances/%s/databases/%s"
                            % (self.dbaas_url, instance_ids['xml'],
                               database_name)}
        self.http_call("delete_databases", 'DELETE', req_json, req_xml)

    def post_create_users(self, instance_ids, user_name):
        req_json = {"url": "%s/instances/%s/users"
                            % (self.dbaas_url, instance_ids['json'])}
        req_xml = {"url": "%s/instances/%s/users"
                            % (self.dbaas_url, instance_ids['xml'])}
        JSON_DATA = {
            "users": [
                {
                    "name": "dbuser3",
                    "password": "password",
                    "database": "databaseA"
                    },
                {
                    "name": "dbuser4",
                    "password": "password",
                    "databases": [
                        {
                            "name": "databaseB"
                            },
                        {
                            "name": "databaseC"
                            }
                        ]
                    },
                {
                    "name": "dbuser5",
                    "password": "password",
                    "database": "databaseD"
                    }
                ]
            }
        XML_DATA = ('<?xml version="1.0" ?>'
                    '<users xmlns='
                    '"http://docs.openstack.org/database/api/v1.0">'
                    '<user name="%s" password="password" '
                    'database="databaseC"/>'
                    '<user name="userwith2dbs" password="password">'
                    '<databases>'
                    '<database name="databaseA"/>'
                    '<database name="databaseB"/>'
                    '</databases>'
                    '</user>'
                    '<user name="userwith3db" password="password">'
                    '<databases>'
                    '<database name="databaseD"/>'
                    '<database name="databaseE"/>'
                    '<database name="databaseF"/>'
                    '</databases>'
                    '</user>'
                    '</users>') % user_name
        req_json['body'] = json.dumps(JSON_DATA)
        req_xml['body'] = XML_DATA
        self.http_call("create_users", 'POST', req_json, req_xml)

    def instance_restart(self, instance_ids):
        req_json = {"url": "%s/instances/%s/action"
                            % (self.dbaas_url, instance_ids['json'])}
        req_xml = {"url": "%s/instances/%s/action"
                            % (self.dbaas_url, instance_ids['xml'])}
        JSON_DATA = {'restart': {}}
        XML_DATA = """<?xml version="1.0" encoding="UTF-8"?>
            <restart xmlns="http://docs.openstack.org/database/api/v1.0"/>"""
        req_json['body'] = json.dumps(JSON_DATA)
        req_xml['body'] = XML_DATA
        self.http_call('instance_restart', 'POST', req_json, req_xml)
        time.sleep(60)

    def instance_resize_volume(self, instance_ids):
        req_json = {"url": "%s/instances/%s/action"
                            % (self.dbaas_url, instance_ids['json'])}
        req_xml = {"url": "%s/instances/%s/action"
                            % (self.dbaas_url, instance_ids['xml'])}
        json_data = {'resize': {'volume': {'size': 4}}}
        xml_data = """<?xml version="1.0" encoding="UTF-8"?>
                <resize xmlns="http://docs.openstack.org/database/api/v1.0">
                <volume size="4"/></resize>"""
        req_json['body'] = json.dumps(json_data)
        req_xml['body'] = xml_data
        self.http_call('instance_resize_volume', 'POST', req_json, req_xml)
        time.sleep(120)

    def instance_resize_flavor(self, instance_ids):
        req_json = {"url": "%s/instances/%s/action"
                            % (self.dbaas_url, instance_ids['json'])}
        req_xml = {"url": "%s/instances/%s/action"
                            % (self.dbaas_url, instance_ids['xml'])}
        json_data = {'resize': {'flavorRef': '%s/flavors/3' % self.dbaas_url}}
        xml_data = """<?xml version="1.0" encoding="UTF-8"?>
                <resize xmlns="http://docs.openstack.org/database/api/v1.0"
                flavorRef="%s/flavors/3"></resize>""" % self.dbaas_url
        req_json['body'] = json.dumps(json_data)
        req_xml['body'] = xml_data
        self.http_call('instance_resize_flavor', 'POST', req_json, req_xml)
        time.sleep(60)

    def get_list_users(self, instance_ids):
        req_json = {"url": "%s/instances/%s/users"
                            % (self.dbaas_url, instance_ids['json'])}
        req_xml = {"url": "%s/instances/%s/users"
                            % (self.dbaas_url, instance_ids['xml'])}
        self.http_call("list_users", 'GET', req_json, req_xml)

    def get_list_users_limit_two(self, instance_ids):
        req_json = {"url": "%s/instances/%s/users?limit=2"
                            % (self.dbaas_url, instance_ids['json'])}
        req_xml = {"url": "%s/instances/%s/users?limit=2"
                            % (self.dbaas_url, instance_ids['xml'])}
        self.http_call("list_users_pagination", 'GET', req_json, req_xml)

    def delete_users(self, instance_ids, user_name):
        req_json = {"url": "%s/instances/%s/users/%s"
                    % (self.dbaas_url, instance_ids['json'], user_name)}
        req_xml = {"url": "%s/instances/%s/users/%s"
                   % (self.dbaas_url, instance_ids['xml'], user_name)}
        self.http_call("delete_users", 'DELETE', req_json, req_xml)

    def post_enable_root_access(self, instance_ids):
        req_json = {"url": "%s/instances/%s/root"
                            % (self.dbaas_url, instance_ids['json'])}
        req_xml = {"url": "%s/instances/%s/root"
                            % (self.dbaas_url, instance_ids['xml'])}
        self.http_call("enable_root_user", 'POST', req_json, req_xml)

    def get_check_root_access(self, instance_ids):
        req_json = {"url": "%s/instances/%s/root"
                            % (self.dbaas_url, instance_ids['json'])}
        req_xml = {"url": "%s/instances/%s/root"
                            % (self.dbaas_url, instance_ids['xml'])}
        self.http_call("check_root_user", 'GET', req_json, req_xml)

    def get_list_instance_index(self):
        req_json = {"url": "%s/instances" % self.dbaas_url}
        req_xml = {"url": "%s/instances" % self.dbaas_url}
        self.http_call("instances_index", 'GET', req_json, req_xml)

    def get_list_instance_index_limit_two(self):
        req_json = {"url": "%s/instances?limit=2" % self.dbaas_url}
        req_xml = {"url": "%s/instances?limit=2" % self.dbaas_url}
        self.http_call("instances_index_pagination", 'GET', req_json, req_xml)

    def get_list_instance_details(self):
        req_json = {"url": "%s/instances/detail" % self.dbaas_url}
        req_xml = {"url": "%s/instances/detail" % self.dbaas_url}
        self.http_call("instances_detail", 'GET', req_json, req_xml)

    def get_instance_details(self, instance_ids):
        req_json = {"url": "%s/instances/%s"
                            % (self.dbaas_url, instance_ids['json'])}
        req_xml = {"url": "%s/instances/%s"
                            % (self.dbaas_url, instance_ids['xml'])}
        self.http_call("instance_status_detail", 'GET', req_json, req_xml)

    def delete_instance(self, instance_ids):
        req_json = {"url": "%s/instances/%s"
                            % (self.dbaas_url, instance_ids['json'])}
        req_xml = {"url": "%s/instances/%s"
                            % (self.dbaas_url, instance_ids['xml'])}
        self.http_call("delete_instance", 'DELETE', req_json, req_xml)

    def mgmt_delete_configs(self, config_id):
        req_json = {"url": "%s/mgmt/configs/%s" % (self.dbaas_url, config_id)}
        req_xml = {"url": "%s/mgmt/configs/%s" % (self.dbaas_url, config_id)}
        self.http_call("mgmt_delete_config", 'DELETE', req_json, req_xml)
        req_json = {"url": "%s/mgmt/configs/%s" %
                    (self.dbaas_url, "xmlconfig")}
        req_xml = {"url": "%s/mgmt/configs/%s" % (self.dbaas_url, "xmlconfig")}
        self.http_call("mgmt_delete_config", 'DELETE', req_json, req_xml,
                       output=False)

    def mgmt_get_config(self, config_id):
        req_json = {"url": "%s/mgmt/configs/%s" % (self.dbaas_url, config_id)}
        req_xml = {"url": "%s/mgmt/configs/%s" % (self.dbaas_url, config_id)}
        self.http_call("mgmt_get_config", 'GET', req_json, req_xml)

    def mgmt_list_configs(self):
        req_json = {"url": "%s/mgmt/configs" % self.dbaas_url}
        req_xml = {"url": "%s/mgmt/configs" % self.dbaas_url}
        self.http_call("mgmt_list_configs", 'GET', req_json, req_xml)

    def mgmt_update_config(self, config_id):
        req_json = {"url": "%s/mgmt/configs/%s" % (self.dbaas_url, config_id)}
        req_xml = {"url": "%s/mgmt/configs/%s" % (self.dbaas_url, config_id)}
        JSON_DATA = {
            "config": {
                "key": "%s" % config_id,
                "value": "testval_update",
                "description": "updated some config value used in the system"
            }
        }
        XML_DATA = ('<?xml version="1.0" ?>'
                    '<config key="xmlconfig" value="XML" description='
                    '"updated config value set with xml"/>')
        req_json['body'] = json.dumps(JSON_DATA)
        req_xml['body'] = XML_DATA
        self.http_call("mgmt_update_config", 'PUT', req_json, req_xml)

    def mgmt_create_config(self, config_id):
        req_json = {"url": "%s/mgmt/configs" % self.dbaas_url}
        req_xml = {"url": "%s/mgmt/configs" % self.dbaas_url}
        JSON_DATA = {
            "configs": [
                    {
                    "key": "%s" % config_id,
                    "value": "testval",
                    "description": "some config value used in the system"
                }
            ]
        }
        XML_DATA = ('<?xml version="1.0" ?>'
                    '<configs>'
                    '<config key="xmlconfig" value="xml" description='
                    '"config value set with xml"/>'
                    '</configs>')
        req_json['body'] = json.dumps(JSON_DATA)
        req_xml['body'] = XML_DATA
        self.http_call("mgmt_create_config", 'POST', req_json, req_xml)

    def mgmt_get_root_details(self, instance_ids):
        req_json = {"url": "%s/mgmt/instances/%s/root"
                            % (self.dbaas_url, instance_ids['json'])}
        req_xml = {"url": "%s/mgmt/instances/%s/root"
                            % (self.dbaas_url, instance_ids['xml'])}
        self.http_call("mgmt_get_root_details", 'GET', req_json, req_xml)

    def mgmt_get_instance_details(self, instance_ids):
        req_json = {"url": "%s/mgmt/instances/%s"
                            % (self.dbaas_url, instance_ids['json'])}
        req_xml = {"url": "%s/mgmt/instances/%s"
                            % (self.dbaas_url, instance_ids['xml'])}
        self.http_call("mgmt_get_instance_details", 'GET', req_json, req_xml)

    def mgmt_get_account_details(self):
        req_json = {"url": "%s/mgmt/accounts/examples" % self.dbaas_url}
        req_xml = {"url": "%s/mgmt/accounts/examples" % self.dbaas_url}
        self.http_call("mgmt_get_account_details", 'GET', req_json, req_xml)

    def mgmt_get_storage(self):
        req_json = {"url": "%s/mgmt/storage" % self.dbaas_url}
        req_xml = {"url": "%s/mgmt/storage" % self.dbaas_url}
        self.http_call("mgmt_get_storage", 'GET', req_json, req_xml)

    def mgmt_get_host_detail(self):
        req_json = {"url": "%s/mgmt/hosts/host" % self.dbaas_url}
        req_xml = {"url": "%s/mgmt/hosts/host" % self.dbaas_url}
        self.http_call("mgmt_get_host_detail", 'GET', req_json, req_xml)

    def mgmt_instance_index(self, deleted=None):
        req_json = {"url": "%s/mgmt/instances" % self.dbaas_url}
        req_xml = {"url": "%s/mgmt/instances" % self.dbaas_url}
        if deleted is not None:
            if deleted:
                req_json['url'] = "%s?deleted=true" % req_json['url']
                req_xml['url'] = "%s?deleted=true" % req_xml['url']
            else:
                req_json['url'] = "%s?deleted=false" % req_json['url']
                req_xml['url'] = "%s?deleted=false" % req_xml['url']
        self.http_call("mgmt_instance_index", 'GET', req_json, req_xml)

    def mgmt_get_instance_diagnostics(self, instance_ids):
        req_json = {"url": "%s/mgmt/instances/%s/diagnostics"
                            % (self.dbaas_url, instance_ids['json'])}
        req_xml = {"url": "%s/mgmt/instances/%s/diagnostics"
                            % (self.dbaas_url, instance_ids['xml'])}
        self.http_call("mgmt_instance_diagnostics", 'GET', req_json, req_xml)

    def mgmt_list_hosts(self):
        req_json = {"url": "%s/mgmt/hosts" % self.dbaas_url}
        req_xml = {"url": "%s/mgmt/hosts" % self.dbaas_url}
        self.http_call("mgmt_list_hosts", 'GET', req_json, req_xml)

    def mgmt_instance_reboot(self, instance_ids):
        req_json = {"url": "%s/mgmt/instances/%s/action"
                            % (self.dbaas_url, instance_ids['json'])}
        req_xml = {"url": "%s/mgmt/instances/%s/action"
                            % (self.dbaas_url, instance_ids['xml'])}
        JSON_DATA = {'reboot': {}}
        XML_DATA = """<?xml version="1.0" encoding="UTF-8"?>
            <reboot xmlns="http://docs.openstack.org/database/api/v1.0"/>"""
        req_json['body'] = json.dumps(JSON_DATA)
        req_xml['body'] = XML_DATA
        self.http_call('instance_reboot', 'POST', req_json, req_xml)
        time.sleep(60)

    def main(self):

        # Verify this is a clean environment to work on
        self.check_clean()

        # no auth required
        self.get_versions()

        # requires auth
        # TODO(pdmars): is this a bug with get_version? the others seem to work
        #self.get_version()
        self.get_flavors()
        self.get_flavor_details()
        self.get_flavor_by_id()

        self.post_create_instance()
        # this will be used later to make instance related calls
        example_instances = self.wait_for_instances(num=2)

        if len(example_instances) != 2:
            print("-" * 60)
            print("-" * 60)
            print("SOMETHING WENT WRONG CREATING THE INSTANCES FOR THE "
                  "EXAMPLES")
            print("-" * 60)
            print("-" * 60)
            return 1

        instance_ids = {"json": example_instances[0],
                        "xml": example_instances[1]}

        database_name = "exampledb"
        user_name = "testuser"
        print "\nUsing instance id(%s) for JSON calls\n" % instance_ids['json']
        print "\nUsing instance id(%s) for XML calls\n" % instance_ids['xml']

        self.post_create_databases(database_name, instance_ids)
        self.get_list_databases(instance_ids)
        self.get_list_databases_limit_two(instance_ids)
        self.delete_databases(database_name, instance_ids)
        self.post_create_users(instance_ids, user_name)
        self.get_list_users(instance_ids)
        self.get_list_users_limit_two(instance_ids)
        self.delete_users(instance_ids, user_name)
        self.post_enable_root_access(instance_ids)
        self.get_check_root_access(instance_ids)
        self.get_list_instance_index()
        self.get_list_instance_details()
        self.get_instance_details(instance_ids)

        # Need to wait after each of these calls for
        # the instance to return back to active
        self.instance_restart(instance_ids)
        self.wait_for_instances(num=2)
        self.instance_resize_volume(instance_ids)
        self.wait_for_instances(num=2)
        self.instance_resize_flavor(instance_ids)
        self.wait_for_instances(num=2)

        # Test instance pagination.
        # Database and user pagination is tested above (see limit_two methods).
        # Since we are limiting to two instances and the create instance method
        # creates two instances (xml and json), another two instances are 
        # created. This is very hacky because the two new instances have the 
        # same names as the previous ones; but they have different ids.
        self.post_create_instance()
        example_instances = self.wait_for_instances(num=4)
        self.get_list_instance_index_limit_two()

        # TODO(pdmars): most of these don't exist yet
        """
        # Do some mgmt calls before deleting the instances
        self.mgmt_list_hosts()
        self.mgmt_get_host_detail()
        self.mgmt_get_storage()
        self.mgmt_get_account_details()
        self.mgmt_get_instance_details(instance_ids)
        self.mgmt_get_root_details(instance_ids)
        self.mgmt_instance_index(False)
        self.mgmt_get_instance_diagnostics(instance_ids)
        self.mgmt_instance_reboot(instance_ids)
        self.wait_for_instances(num=2)

        # Configs
        config_id = "myconf"
        self.mgmt_create_config(config_id)
        self.mgmt_update_config(config_id)
        self.mgmt_list_configs()
        self.mgmt_get_config(config_id)
        self.mgmt_delete_configs(config_id)
        """

        # Because of the above Test instance pagination hack,
        # instances must be deleted like so
        self.delete_instance(instance_ids) # delete initial pair
        last_example_instances = self.wait_for_instances(num=2)
        last_instance_ids = {"json": last_example_instances[0],
                        "xml": last_example_instances[1]}
        self.delete_instance(last_instance_ids) # delete last pair


if __name__ == "__main__":
    print("RUNNING ARGS :  " + str(sys.argv))
    for arg in sys.argv[1:]:
        conf_file = os.path.expanduser(arg)
        print("Setting conf to " + conf_file)
        examples = ExampleGenerator(conf_file)
        examples.main()
