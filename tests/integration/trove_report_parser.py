# Copyright 2016 Tesora Inc.
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

import urllib2
import sys
import os

import binascii
from itertools import groupby
import xmltodict


IGNORED_GROUPS = {'Flavors', 'start_trove_api', 'start_nova_api',
                  'start_nova_network', 'start_scheduler', 'Versions',
                  'start_glance_registry', 'start_glance_api', 'start_compute',
                  'InstanceSetup'}


class TestRunRecord():

    def __init__(self, name):
        self.name = name
        self.group_records = []

    def add_group(self, group_record):
        self.group_records.append(group_record)

    def is_pass(self):
        return not any(group.is_fail() for group in self.group_records)

    def get_group(self, group_name):
        for group in self.group_records:
            if group.name == group_name:
                return group
        return None

    def get_group_names(self):
        return [group.name for group in self.group_records]

    def __str__(self):
        return self.name

    def __repr__(self):
        return 'TestRunRecord(%s)' % self.name


class GroupRecord():

    def __init__(self, name, desc=''):
        self.name = name
        self.desc = desc
        self.test_records = []
        self._id = binascii.crc32(str(hash(self)))

    def add_test(self, test_record):
        self.test_records.append(test_record)

    def is_pass(self):
        return not any(test.is_fail() for test in self.test_records)

    def is_empty(self):
        return len(self.test_records) == 0

    def to_html(self):
        result = 'N/A'
        color = 'gray'
        if not self.is_empty():
            if self.is_pass():
                result = 'OK'
                color = 'green'
            else:
                result = 'FAIL'
                color = 'red'

        detail_html = ['<table style="display:none" id="%s">' % self._id]
        for test in self.test_records:
            detail_html.append('<tr>')
            detail_html.extend(test.to_html())
            detail_html.append('</tr>')
        detail_html.extend(['</table>'])

        html = (['<td style="background-color:%s">' % color,
                 '<div onclick="showhide(%s)">' % self._id, result, '</div>'] +
                detail_html +
                ['</td>'])
        return html

    def __str__(self):
        return '%s (%s)' % (self.name, self.desc)

    def __repr__(self):
        return 'GroupRecord(%s, desc=%s)' % (self.name, self.desc)


class TestRecord():

    def __init__(self, name, result, desc='', msg=''):
        self.name = name
        self.result = result
        self.desc = desc
        self.msg = msg

    def is_pass(self):
        return int(self.result) == 0

    def is_skip(self):
        return int(self.result) < 0

    def is_fail(self):
        return int(self.result) > 0

    def to_html(self):
        result = "N/A"
        if self.is_pass():
            result = "OK"
        elif self.is_skip():
            result = "SKIP"
        elif self.is_fail():
            result = "FAIL"
        return ['<td>', self.name, '</td>', '<td>', result, '</td>']

    def __str__(self):
        return '%s (%s)' % (self.name, self.desc)

    def __repr__(self):
        return 'TestRecord(%s, %s, desc=%s, msg=%s)' % (
            self.name, self.result, self.desc, self.msg)


def read_report(report_file):
    if os.path.exists(report_file):
        with open(report_file, 'r') as fp:
            return xmltodict.parse(fp, encoding='utf-8')
    else:
        response = urllib2.urlopen(urllib2.quote(''))
        try:
            return response.read()
        finally:
            response.close()


def to_html(test_runs):
    html = (['<html>', '<head>', '</head>', '<script type="text/javascript">',
             'function showhide(id) { var e = document.getElementById(id);'
             'e.style.display = (e.style.display == "block") ? '
             '"none" : "block";}',
             '</script>',
             '<table>', '<tr>', '<th>', '&nbsp;', '</th>'])
    found_group_names = set()
    for run in test_runs:
        found_group_names.update(run.get_group_names())
        html.extend(['<th>', run.name, '</th>'])
    html.extend(['</tr>'])

    for group_name in found_group_names:
        html.extend(['<tr>', '<th>',
                     group_name,
                     '</th>'])
        for run in test_runs:
            group = run.get_group(group_name)
            if not group:
                group = GroupRecord(group_name)
            html.extend(group.to_html())
        html.extend(['</tr>'])

    html.extend(['</table>', '</html>'])
    return html


def save_as_html(out_html_file, test_runs):
    with open(out_html_file, 'w') as fp:
        fp.write('\n'.join(to_html(test_runs)))


def _get_prefix(group_name):
    ups = [i for i, c in enumerate(group_name) if c.isupper()]
    if len(ups) > 1:
        return group_name[0:ups[1]]
    return group_name


def parse_report(report_file):
    report = read_report(report_file)
    results = report['Report']
    for key in IGNORED_GROUPS:
        if key in results:
            del results[key]
    return results


def parse_test_results(results, out_group_template):
    test_run = TestRunRecord(results['@datastore'])
    for group_display_name, test_group_names in out_group_template.items():
        if not group_display_name.startswith('@'):
            group = GroupRecord(group_display_name)
            for test_group in test_group_names:
                group_results = results[test_group]
                for k, v in group_results.items():
                    if not k.startswith('@'):
                        result = v['@result']
                        desc = v['@desc']
                        msg = v['@msg']
                        group.add_test(
                            TestRecord(k, result, desc=desc, msg=msg))
            test_run.add_group(group)
    return test_run


if __name__ == '__main__':
    if len(sys.argv) < 3:
        raise Exception("USAGE: report, [report, ...], output")

    report_files = sys.argv[1:-1]
    output_file = sys.argv[-1]

    test_runs = []
    for report_file in report_files:
        results = parse_report(report_file)

        out_group_template = {
            k: list(v) for k, v in groupby(sorted(results.keys()),
                                           key=_get_prefix)}

        test_run = parse_test_results(results, out_group_template)
        test_runs.append(test_run)

    save_as_html(output_file, test_runs)
