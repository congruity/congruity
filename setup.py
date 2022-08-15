# Copyright 2018 Scott Talbert
#
# This file is part of congruity.
#
# congruity is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# congruity is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with congruity.  If not, see <http://www.gnu.org/licenses/>.

from setuptools import setup
import setuptools.command.install
import os

class install(setuptools.command.install.install):
    user_options = setuptools.command.install.install.user_options + [
        ('skip-update-desktop-db', None, 'skip updating desktop database')
    ]
    boolean_options = setuptools.command.install.install.boolean_options + [
        'skip-update-desktop-db'
    ]

    def initialize_options(self):
        setuptools.command.install.install.initialize_options(self)
        self.skip_update_desktop_db = None

    def run(self):
        setuptools.command.install.install.run(self)
        if not self.skip_update_desktop_db:
            os.system('update-desktop-database >/dev/null 2>&1')

setup(
    name='congruity',
    version='21',
    description='Applications for programming Logitech Harmony remote controls',
    url='https://sourceforge.net/projects/congruity/',
    packages=['congruity'],
    zip_safe=False,
    package_data={
        '': ['*.gif', '*.png', '*.wsdl', '*.xsd']
    },
    data_files=[
        ('share/man/man1', ['congruity.1', 'mhgui.1']),
        ('share/applications', ['congruity.desktop', 'mhgui.desktop'])
    ],
    entry_points={
        'gui_scripts': [
            'congruity = congruity.congruity:main',
            'mhgui = congruity.mhgui:main'
        ]
    },
    cmdclass={
        'install': install,
    },
)
