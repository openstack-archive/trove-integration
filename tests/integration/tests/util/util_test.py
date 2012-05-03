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

import unittest

from tests.util.users import Requirements
from tests.util.users import ServiceUser
from tests.util.users import Users

USER_LIST = [
    {"auth_user":"admin",
     "auth_key":"admin",
     "requirements": {
        "is_admin":True
      }
    },
    {"auth_user":"anne",
     "auth_key":"secret",
     "requirements": {
        "is_admin":True
      }
    },
    {"auth_user":"dan",
     "auth_key":"password",
     "requirements": {
        "is_admin":True
      }
    },
    {"auth_user":"tim",
     "auth_key":"12345",
     "requirements": {
        "is_admin":False
      }
    },
    {"auth_user":"mike",
     "auth_key":"bike",
     "requirements": {
        "is_admin":False
      }
    }
]

NUMBER_OF_ADMINS = 3
NUMBER_OF_NORMALS = len(USER_LIST) - NUMBER_OF_ADMINS


class TestUsers(unittest.TestCase):

    NUMBER_OF_USER_TESTS = 12

    def setUp(self):
        self.users = Users(USER_LIST)

    def test_should_find_five_users(self):
        self.assertEqual(5, len(self.users.users))

    def test_initially_test_counts_are_zero(self):
        for user in self.users.users:
            self.assertEqual(0, user.test_count)

    def test_all_admin_users_are_found(self):
        admins = set()
        for x in range(self.NUMBER_OF_USER_TESTS):
            user = self.users.find_user(Requirements(is_admin=True))
            if user not in admins:
                admins.add(user)
        self.assertEqual(NUMBER_OF_ADMINS, len(admins))
        admin_names = list(user.auth_user for user in admins)
        self.assertTrue("admin" in admin_names)
        self.assertTrue("anne" in admin_names)
        self.assertTrue("dan" in admin_names)
        expected_test_count = self.NUMBER_OF_USER_TESTS / NUMBER_OF_ADMINS
        for user in admins:
            self.assertTrue(user.requirements.is_admin)
            self.assertEqual(expected_test_count, user.test_count)

    def test_all_non_admin_users_are_found(self):
        normals = set()
        for x in range(self.NUMBER_OF_USER_TESTS):
            user = self.users.find_user(Requirements(is_admin=False))
            if user not in normals:
                normals.add(user)
        self.assertEqual(NUMBER_OF_NORMALS, len(normals))
        normal_names = list(user.auth_user for user in normals)
        self.assertTrue("mike" in normal_names)
        self.assertTrue("tim" in normal_names)
        expected_test_count = self.NUMBER_OF_USER_TESTS / NUMBER_OF_NORMALS
        for user in normals:
            self.assertFalse(user.requirements.is_admin)
            self.assertEqual(expected_test_count, user.test_count)
