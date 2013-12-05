#!/usr/bin/env python
# vim: tabstop=4 shiftwidth=4 softtabstop=4
#
# # Copyright (c) 2011 OpenStack, LLC.
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


"""Runs the tests.

There are a few initialization issues to deal with.
The first is flags, which must be initialized before any imports. The test
configuration has the same problem (it was based on flags back when the tests
resided outside of the Nova code).

The command line is picked apart so that Nose won't see commands it isn't
compatable with, such as "--flagfile" or "--group".

This script imports all other tests to make them known to Proboscis before
passing control to proboscis.TestProgram which itself calls nose, which then
call unittest.TestProgram and exits.

If "repl" is a command line argument, then the original stdout and stderr is
saved and sys.exit is neutralized so that unittest.TestProgram will not exit
and instead sys.stdout and stderr are restored so that interactive mode can
be used.

"""


from __future__ import absolute_import
import atexit
import gettext
import logging
import os
import time
import unittest
import sys
import proboscis

from nose import config
from nose import core

from tests.colorizer import NovaTestRunner


if os.environ.get("PYDEV_DEBUG", "False") == 'True':
    from pydev import pydevd
    pydevd.settrace('10.0.2.2', port=7864, stdoutToServer=True,
                    stderrToServer=True)


def add_support_for_localization():
    """Adds support for localization in the logging.

    If ../nova/__init__.py exists, add ../ to Python search path, so that
    it will override what happens to be installed in
    /usr/(local/)lib/python...

    """
    path = os.path.join(os.path.abspath(sys.argv[0]), os.pardir, os.pardir)
    possible_topdir = os.path.normpath(path)
    if os.path.exists(os.path.join(possible_topdir, 'nova', '__init__.py')):
        sys.path.insert(0, possible_topdir)

    gettext.install('nova', unicode=1)


MAIN_RUNNER = None


def initialize_rdl_config(config_file):
    from trove.common import cfg
    from trove.openstack.common import log
    from trove.db import get_db_api
    conf = cfg.CONF
    cfg.parse_args(['int_tests'], default_config_files=[config_file])
    log.setup(None)
    try:
        get_db_api().configure_db(conf)
        conf_file = conf.find_file(conf.api_paste_config)
    except RuntimeError as error:
        import traceback
        print traceback.format_exc()
        sys.exit("ERROR: %s" % error)


def initialize_nova_flags(config_file):
    from nova import flags
    from nova import log as logging
    from nova import service
    from nova import utils

    flags.parse_args(['int_tests'], default_config_files=[config_file])
    logging.setup()
    utils.monkey_patch()


def _clean_up():
    """Shuts down any services this program has started and shows results."""
    from tests.util import report
    report.update()
    if MAIN_RUNNER is not None:
        MAIN_RUNNER.on_exit()
    from tests.util.services import get_running_services
    for service in get_running_services():
        sys.stderr.write("Stopping service ")
        for c in service.cmd:
            sys.stderr.write(c + " ")
        sys.stderr.write("...\n\r")
        service.stop()


def import_tests():

    # TODO(tim.simpson): Import these again once white box test functionality
    #                    is restored.
    # from tests.dns import check_domain
    # from tests.dns import concurrency
    # from tests.dns import conversion

    # The DNS stuff is problematic. Not loading the other tests allow us to
    # run its functional tests only.
    ADD_DOMAINS = os.environ.get("ADD_DOMAINS", "False") == 'True'
    if not ADD_DOMAINS:
        from tests import initialize
        from tests.api import delete_all
        from trove.tests.api import flavors
        from trove.tests.api import versions
        from trove.tests.api import instances
        from trove.tests.api import instances_actions
        from trove.tests.api import instances_mysql_down
        from tests.api import instances_pagination
        from trove.tests.api import instances_delete
        from tests.api import instances_quotas
        from tests.api import instances_states
        from trove.tests.api import databases
        from trove.tests.api import root
        from trove.tests.api import users
        from trove.tests.api import user_access
        from trove.tests.api import backups
        from trove.tests.api import configurations
        from trove.tests.api.mgmt import accounts
        from trove.tests.api.mgmt import admin_required
        from trove.tests.api.mgmt import hosts
        from trove.tests.api.mgmt import instances as mgmt_instances
        from trove.tests.api.mgmt import storage
        from tests.dns import dns
        from tests.volumes import driver
        from tests.smoke import instance

        black_box_groups = [
            flavors.GROUP,
            users.GROUP,
            user_access.GROUP,
            databases.GROUP,
            root.GROUP,
            "services.initialize",
            instances.GROUP_START,
            "dbaas_quotas",
            "dbaas.api.security_groups",
            backups.GROUP,
            configurations.GROUP,
            "dbaas.api.instances.actions.resize.instance",
            # TODO(SlickNik): The restart tests fail intermittently so pulling
            # them out of the blackbox group temporarily. Refer to Trove bug:
            # https://bugs.launchpad.net/trove/+bug/1204233
            # "dbaas.api.instances.actions.restart",
            instances_actions.GROUP_STOP_MYSQL,
            instances.GROUP_STOP,
            versions.GROUP,
            "dbaas.guest.start.test",
            ]
        proboscis.register(groups=["blackbox"],
                           depends_on_groups=black_box_groups)

        simple_black_box_groups = [
            "services.initialize",
            flavors.GROUP,
            versions.GROUP,
            instances.GROUP_START_SIMPLE,
            "dbaas.api.mgmt.admin",
        ]
        proboscis.register(groups=["simple_blackbox"],
                           depends_on_groups=simple_black_box_groups)

        black_box_mgmt_groups = [
            accounts.GROUP,
            hosts.GROUP,
            storage.GROUP,
            instances_actions.GROUP_REBOOT,
            admin_required.GROUP,
            mgmt_instances.GROUP,
            ]
        proboscis.register(groups=["blackbox_mgmt"],
                           depends_on_groups=black_box_mgmt_groups)
        heavy_black_box_groups = [
            "dbaas.api.instances.pagination",
            "dbaas.api.instances.delete",
            "dbaas.api.instances.status",
            "dbaas.api.instances.down",
            "dbaas.api.mgmt.hosts.update",
            "fake.dbaas.api.mgmt.instances",
            "fake.dbaas.api.mgmt.accounts.broken",
            "fake.dbaas.api.mgmt.allaccounts"
        ]
        proboscis.register(groups=["heavy_blackbox"],
                           depends_on_groups=heavy_black_box_groups)


def run_main(test_importer):

    add_support_for_localization()

    # Strip non-nose arguments out before passing this to nosetests

    repl = False
    nose_args = []
    conf_file = "~/test.conf"
    show_elapsed = True
    groups = []
    print("RUNNING TEST ARGS :  " + str(sys.argv))
    extra_test_conf_lines = []
    rdl_config_file = None
    nova_flag_file = None
    index = 0
    while index < len(sys.argv):
        arg = sys.argv[index]
        if arg[:2] == "-i" or arg == '--repl':
            repl = True
        elif arg[:7] == "--conf=":
            conf_file = os.path.expanduser(arg[7:])
            print("Setting TEST_CONF to " + conf_file)
            os.environ["TEST_CONF"] = conf_file
        elif arg[:8] == "--group=":
            groups.append(arg[8:])
        elif arg == "--test-config":
            if index >= len(sys.argv) - 1:
                print('Expected an argument to follow "--test-conf".')
                sys.exit()
            conf_line = sys.argv[index + 1]
            extra_test_conf_lines.append(conf_line)
        elif arg[:11] == "--flagfile=":
            pass
        elif arg[:14] == "--config-file=":
            rdl_config_file = arg[14:]
        elif arg[:13] == "--nova-flags=":
            nova_flag_file = arg[13:]
        elif arg.startswith('--hide-elapsed'):
            show_elapsed = False
        else:
            nose_args.append(arg)
        index += 1

    # Many of the test decorators depend on configuration values, so before
    # start importing modules we have to load the test config followed by the
    # flag files.
    from trove.tests.config import CONFIG

    # Find config file.
    if not "TEST_CONF" in os.environ:
        raise RuntimeError("Please define an environment variable named " +
                           "TEST_CONF with the location to a conf file.")
    file_path = os.path.expanduser(os.environ["TEST_CONF"])
    if not os.path.exists(file_path):
        raise RuntimeError("Could not find TEST_CONF at " + file_path + ".")
        # Load config file and then any lines we read from the arguments.
    CONFIG.load_from_file(file_path)
    for line in extra_test_conf_lines:
        CONFIG.load_from_line(line)

    if CONFIG.white_box:  # If white-box testing, set up the flags.
        # Handle loading up RDL's config file madness.
        initialize_rdl_config(rdl_config_file)
        if nova_flag_file:
            initialize_nova_flags(nova_flag_file)

    # Set up the report, and print out how we're running the tests.
    from tests.util import report
    from datetime import datetime
    report.log("Trove Integration Tests, %s" % datetime.now())
    report.log("Invoked via command: " + str(sys.argv))
    report.log("Groups = " + str(groups))
    report.log("Test conf file = %s" % os.environ["TEST_CONF"])
    if CONFIG.white_box:
        report.log("")
        report.log("Test config file = %s" % rdl_config_file)
    report.log("")
    report.log("sys.path:")
    for path in sys.path:
        report.log("\t%s" % path)

    # Now that all configurations are loaded its time to import everything
    test_importer()

    atexit.register(_clean_up)

    c = config.Config(stream=sys.stdout,
                      env=os.environ,
                      verbosity=3,
                      plugins=core.DefaultPluginManager())
    runner = NovaTestRunner(stream=c.stream,
                            verbosity=c.verbosity,
                            config=c,
                            show_elapsed=show_elapsed,
                            known_bugs=CONFIG.known_bugs)
    MAIN_RUNNER = runner

    if repl:
        # Turn off the following "feature" of the unittest module in case
        # we want to start a REPL.
        sys.exit = lambda x: None

    proboscis.TestProgram(argv=nose_args, groups=groups,
                          testRunner=MAIN_RUNNER).run_and_exit()
    sys.stdout = sys.__stdout__
    sys.stderr = sys.__stderr__


if __name__ == "__main__":
    run_main(import_tests)
