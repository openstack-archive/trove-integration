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

"""Handles configuration options for the tests."""

import json
import os

from tests.util.services import Service
from tests.util.services import WebService

__all__ = [
    "auth_url",
    "compute_service",
    "dbaas",
    "dbaas_image",
    "glance_code_root",
    "glance_image",
    "nova",
    "nova_code_root",
    "python_cmd_list",
    "typical_nova_image_name",
    "users",
    "use_venv",
    "values",
    "volume_service",
    "keystone_service",
    "whitebox",
    "test_mgmt"
]


def load_configuration():
    """Loads and returns the configuration file as a dictionary.

    The file to load is found by looking for a value in the environment
    variable TEST_CONF.  The file itself is stored as JSON.

    """
    if not "TEST_CONF" in os.environ:
        raise RuntimeError("Please define an environment variable named " +
                           "TEST_CONF with the location to a conf file.")
    file_path = os.path.expanduser(os.environ["TEST_CONF"])
    if not os.path.exists(file_path):
        raise RuntimeError("Could not find TEST_CONF at " + file_path + ".")
    file_contents = open(file_path, "r").read()
    try:
        return json.loads(file_contents)
    except Exception as exception:
        raise RuntimeError("Error loading conf file \"" + file_path + "\".",
                           exception)


def glance_code_root():
    """The file path to the Glance source code."""
    return str(values.get("glance_code_root"))

def glance_bin_root():
    """The file path to the Glance bin directory."""
    return str(values.get("glance_code_root")) + "/bin/"

def glance_images_directory():
    """The path to images that will be uploaded by Glance."""
    return str(values.get("glance_images_directory"))


def nova_code_root():
    """The path to the Nova source code."""
    return str(values.get("nova_code_root"))

def keystone_code_root():
    """The path to the Keystone source code."""
    return str(values.get("keystone_code_root"))

def keystone_bin(service):
    """The path of the specific keystone service"""
    default_path = os.path.join(keystone_code_root(), service)
    if os.path.exists(default_path):
        path = default_path
    else:
        path = os.path.join("/keystone/bin/", service)
    return path


def python_cmd_list():
    """The start of a command list to use when running Python scripts."""
    global use_venv
    global nova_code_root
    commands = []
    if use_venv:
        commands.append("%s/tools/with_venv.sh" % nova_code_root)
        return list
    commands.append("python")
    return commands


def _setup():
    """Initializes the module."""
    from tests.util.users import Users
    global nova_auth_url
    global reddwarf_auth_url
    global compute_service
    global dbaas
    global nova
    global users
    global dbaas_image
    global typical_nova_image_name
    global use_venv
    global values
    global dbaas_url
    global version_url
    global volume_service
    global keystone_service
    global glance_image
    global use_reaper
    global clean_slate
    global white_box
    global test_mgmt
    clean_slate = os.environ.get("CLEAN_SLATE", "False") == "True"
    values = load_configuration()
    if os.environ.get("FAKE_MODE", "False") == "True":
        values["fake_mode"] = True
    use_venv = values.get("use_venv", True)
    nova_auth_url = str(values.get("nova_auth_url", "http://localhost:5000/v2.0"))
    reddwarf_auth_url = str(values.get("reddwarf_auth_url", "http://localhost:5000/v1.1"))
    dbaas_url = str(values.get("dbaas_url", "http://localhost:8775/v1.0/dbaas"))
    version_url = str(values.get("version_url", "http://localhost:8775/"))
    nova_url = str(values.get("nova_url", "http://localhost:8774/v1.1"))
    nova_code_root = str(values["nova_code_root"])
    nova_conf = str(values["nova_conf"])
    keystone_conf = str(values["keystone_conf"])
    reddwarf_code_root = str(values["reddwarf_code_root"])
    reddwarf_conf = str(values["reddwarf_conf"])
    glance_image = str(values["glance_image"])
    use_reaper = values["use_reaper"]
    if not nova_conf:
        raise ValueError("Configuration value \"nova_conf\" not found.")

    if str(values.get("reddwarf_api_format", "new")) == "old":
        dbaas = WebService(cmd=python_cmd_list() +
                               ["%s/bin/reddwarf-api" % reddwarf_code_root,
                                "--flagfile=%s" % reddwarf_conf],
                            url=dbaas_url)
    else:
        dbaas = WebService(cmd=python_cmd_list() +
                               ["%s/bin/reddwarf-server" % reddwarf_code_root,
                                "--config-file=%s" % reddwarf_conf],
                            url=dbaas_url)
    nova = WebService(cmd=python_cmd_list() +
                          ["%s/bin/nova-api" % nova_code_root,
                           "--flagfile=%s" % nova_conf],
                      url=nova_url)
    volume_service = Service(cmd=python_cmd_list() +
                             ["%s/bin/nova-volume" % nova_code_root,
                              "--flagfile=%s" % nova_conf ])
    compute_service = Service(cmd=python_cmd_list() +
                              ["%s/bin/nova-compute" % nova_code_root,
                               "--flagfile=%s" % nova_conf ])
    keystone_service = Service(python_cmd_list() +
                               [keystone_bin("keystone-auth"),
                                "-c %s" % keystone_conf])

    users = Users(values["users"])
    dbaas_image = values.get("dbaas_image", None)
    typical_nova_image_name = values.get("typical_nova_image_name", None)

    # If true, we import certain classes and test using internal code.
    white_box = values.get("white_box", False)
    # If true, we run the mgmt tests, if not we don't.
    test_mgmt = values.get("test_mgmt", False)

_setup()
