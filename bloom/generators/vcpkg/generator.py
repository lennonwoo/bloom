# Software License Agreement (BSD License)
#
# Copyright (c) 2013, Willow Garage, Inc.
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions
# are met:
#
#  * Redistributions of source code must retain the above copyright
#    notice, this list of conditions and the following disclaimer.
#  * Redistributions in binary form must reproduce the above
#    copyright notice, this list of conditions and the following
#    disclaimer in the documentation and/or other materials provided
#    with the distribution.
#  * Neither the name of Willow Garage, Inc. nor the names of its
#    contributors may be used to endorse or promote products derived
#    from this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS
# "AS IS" AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT
# LIMITED TO, THE IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS
# FOR A PARTICULAR PURPOSE ARE DISCLAIMED. IN NO EVENT SHALL THE
# COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR ANY DIRECT, INDIRECT,
# INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES (INCLUDING,
# BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
# LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT
# LIABILITY, OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN
# ANY WAY OUT OF THE USE OF THIS SOFTWARE, EVEN IF ADVISED OF THE
# POSSIBILITY OF SUCH DAMAGE.

from __future__ import print_function

import datetime
import os
import re
import sys
import traceback

from dateutil import tz
from pkg_resources import parse_version

from bloom.generators.common import PackageManagerGenerator
from bloom.generators.common import process_template_files

from bloom.logging import debug
from bloom.logging import enable_drop_first_log_prefix
from bloom.logging import error
from bloom.logging import info
from bloom.logging import is_debug
from bloom.logging import warning

from bloom.util import to_unicode
from bloom.util import execute_command
from bloom.util import get_rfc_2822_date
from bloom.util import maybe_continue

try:
    from catkin_pkg.changelog import get_changelog_from_path
    from catkin_pkg.changelog import CHANGELOG_FILENAME
except ImportError as err:
    debug(traceback.format_exc())
    error("catkin_pkg was not detected, please install it.", exit=True)

try:
    import rosdistro
except ImportError as err:
    debug(traceback.format_exc())
    error("rosdistro was not detected, please install it.", exit=True)

# Drop the first log prefix for this command
enable_drop_first_log_prefix(True)


def format_depends(depends, resolved_deps):
    formatted = []
    for d in depends:
        for resolved_dep in resolved_deps[d.name]:
            formatted.append(resolved_dep)
    return formatted


def vcpkgize_string(value):
    markup_remover = re.compile(r'<.*?>')
    value = markup_remover.sub('', value)
    value = re.sub('\s+', ' ', value)
    value = value.strip()
    return value


# TODO check the vcpkg description format
def format_description(value):
    """
    Format proper <synopsis, long desc> string following Debian control file
    formatting rules. Treat first line in given string as synopsis, everything
    else as a single, large paragraph.

    Future extensions of this function could convert embedded newlines and / or
    html into paragraphs in the Description field.

    https://www.debian.org/doc/debian-policy/ch-controlfields.html#s-f-Description
    """
    value = vcpkgize_string(value)
    # NOTE: bit naive, only works for 'properly formatted' pkg descriptions (ie:
    #       'Text. Text'). Extra space to avoid splitting on arbitrary sequences
    #       of characters broken up by dots (version nrs fi).
    parts = value.split('. ', 1)
    if len(parts) == 1 or len(parts[1]) == 0:
        # most likely single line description
        return value
    # format according to rules in linked field documentation
    return u"{0}.\n {1}".format(parts[0], parts[1].strip())


class VcpkgGenerator(PackageManagerGenerator):
    title = 'vcpkg'
    package_manager = 'vcpkg'
    description = "Generates vcpkg from the catkin meta data"

    def prepare_arguments(self, parser):
        add = parser.add_argument
        add('--os-name', default='windows',
            help="overrides os_name, set to 'windows' by default")
        return PackageManagerGenerator.prepare_arguments(self, parser)

    def handle_arguments(self, args):
        self.os_name = args.os_name
        ret = PackageManagerGenerator.handle_arguments(self, args)
        return ret

    def pre_modify(self):
        error_msg = ''.join([
            "Some of the dependencies for packages in this repository could not be resolved by rosdep.\n",
            "You can try to address the issues which appear above and try again if you wish."
        ])
        PackageManagerGenerator.check_all_keys_are_valid(self, error_msg)

    def generate_package(self, package, os_version):
        info("Generating {0} for {1}...".format(self.package_manager, os_version))
        # Generate substitution values
        subs = self.get_subs(package, os_version, format_description, format_depends)
        # Use subs to create and store releaser history
        releaser_history = [(v, (n, e)) for v, _, _, n, e in subs['changelogs']]
        self.set_releaser_history(dict(releaser_history))
        # Template files
        template_files = process_template_files(".", subs, self.package_manager)
        # Remove any residual template files
        execute_command('git rm -rf ' + ' '.join("'{}'".format(t) for t in template_files))
        # Add changes to the package system folder
        execute_command('git add {0}'.format(self.package_manager))
        # Commit changes
        execute_command('git commit -m "Generated {0} files for {1}"'
                        .format(self.package_manager, os_version))
        # Return the subs for other use
        return subs

    @staticmethod
    def get_subs_hook(subs, package, ros_distro, releaser_history=None):
        build_type = package.get_build_type()
        if build_type != "ament_cmake":
            error("Build type '{}' is not supported by this version of bloom.".
                  format(build_type), exit=True)

        # Get pacakge's release url from rosdistro repository
        index = rosdistro.get_index(rosdistro.get_index_url())
        distribution_file = rosdistro.get_distribution_file(index, ros_distro)
        repo = distribution_file.repositories[package.name]
        release_url = repo.release_repository.url

        vcpkg_support_git_sources = ["github", "gitlab", "bitbucket"]
        for git_source in vcpkg_support_git_sources:
            if git_source in release_url:
                subs['git_source'] = git_source
                break
        else:
            error("Currently Bloom don't support release url: {0} currently"
                  .format(release_url), exit=True)
        # release url format: https://github.com/<user_name>/<repo_name><maybe .git>
        subs["user_name"] = release_url.split('/')[-2]
        subs["repo_name"] = release_url.split('/')[-1]
        if ".git" in subs["repo_name"]:
            subs["repo_name"] = subs["repo_name"][:-4]

        subs['tag_name'] = VcpkgGenerator.generate_tag_name(subs)

        return subs

    @staticmethod
    def generate_tag_name(subs):
        tag_name = '{Package}_{Version}-{Inc}_{Distribution}'
        tag_name = VcpkgGenerator.package_manager + '/' + tag_name.format(**subs)
        return tag_name
