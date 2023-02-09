#!/usr/bin/env python3
"""
Copyright (C) 2023 Canonical Ltd.

Author
  Michael Reed <michael.reed@canonical.com/

This program is free software: you can redistribute it and/or modify
it under the terms of the GNU General Public License version 3,
as published by the Free Software Foundation.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.

Setup an iSCSI Target
usage: iscsi_target.py [-h] [--debug] -t TARGETIP [-u USERNAME] [-p PASSWORD]

"""

from argparse import ArgumentParser
import os
import logging
import shlex
from subprocess import (
    Popen,
    PIPE,
    DEVNULL,
)
import sys


class RunCommand(object):
    """
    Runs a command and can return all needed info:
    * stdout
    * stderr
    * return code
    * original command
    Convenince class to avoid the same repetitive code to run shell
    commands.
    """

    def __init__(self, cmd=None):
        self.stdout = None
        self.stderr = None
        self.returncode = None
        self.cmd = cmd
        self.run(self.cmd)

    def run(self, cmd):
        proc = Popen(shlex.split(cmd), stdout=PIPE, stderr=PIPE,
                     stdin=DEVNULL, universal_newlines=True)
        self.stdout, self.stderr = proc.communicate()
        self.returncode = proc.returncode


class IscsiTarget(object):

    def __init__(self, username, password, targetIP):
        self.username = username
        self.password = password
        self.ipaddr = targetIP
        self.iscsi_conf = "/etc/tgt/conf.d/iscsi.conf"
        self.device_dir = "/var/lib/iscsi_disks/"
        self.backing_device = self.device_dir + "disk01.img"

    def run_command(self, cmd):
        task = RunCommand(cmd)
        if task.returncode != 0:
            logging.error('Command {} returnd a code of {}'.format(
                task.cmd, task.returncode))
            logging.error(' STDOUT: {}'.format(task.stdout))
            logging.error(' STDERR: {}'.format(task.stderr))
            return False
        else:
            logging.debug('Command {}:'.format(task.cmd))
            if task.stdout != '':
                logging.debug(' STDOUT: {}'.format(task.stdout))
            elif task.stderr != '':
                logging.debug(' STDERR: {}'.format(task.stderr))
            else:
                logging.debug(' Command returned no output')
            return True

    def install_pkgs(self):
        logging.debug("Install tgt")
        cmd = "sudo apt-get update"
        if not self.run_command(cmd):
            return False
        # Install tgt - Linux SCSI target user-space daemon and tools
        cmd = "sudo apt-get install -y tgt net-tools"
        if not self.run_command(cmd):
            return False

    def setup_iscsi_target_device(self):
        logging.debug("Setup up device")
        cmd = "sudo mkdir -p {}".format(self.device_dir)
        if not self.run_command(cmd):
            return False

        cmd = "sudo dd if=/dev/zero of={} count=0 bs=1 seek=10G".\
              format(self.backing_device)
        if not self.run_command(cmd):
            return False

    def setup_iscsi_target_config(self):
        logging.debug("Create iSCSI conf file")

        target_conf = """
        <target iqn.2020-07.example.com:lun1>
         backing-store {}
         initiator-address {}
         incominguser iscsi-user {}
         outgoinguser iscsi-target {}
        </target>
        """.format(self.backing_device, self.ipaddr,
                   self.username, self.password)

        with open(self.iscsi_conf, "w") as conf_file:
            conf_file.write(target_conf)

    def cleanup(self):
        logging.debug("Clean previous iSCSI targets")

        if os.path.isfile(self.backing_device):
            os.remove(self.backing_device)
            logging.debug("Previous Target Removed")
        else:
            logging.debug("Previous Target Not detected")

        if os.path.isfile(self.iscsi_conf):
            os.remove(self.iscsi_conf)
            logging.debug("Previous Target Config file Removed")
        else:
            logging.debug("Previous Target Not detected")

    def run_tgt(self):
        logging.debug("Restart Tgt")
        # tgt - Linux SCSI target user-space daemon and tools

        cmd = "systemctl restart tgt"
        if not self.run_command(cmd):
            return False

        logging.debug("Show status")
        # Todo - add a check to grep for ready or online to verify it is
        # working correctly
        cmd = "tgtadm --mode target --op show"
        if not self.run_command(cmd):
            return False

        logging.debug("Grant access to ALL.")
        cmd = "tgtadm --lld iscsi --op bind --mode target --tid 1 -I ALL"
        if not self.run_command(cmd):
            return False
        logging.debug("iSCSI Target Creation Complete")


def run_target(args):
    logging.debug("Executing run_target")

    # Command line arguments.
    if args.username:
        username = args.username
    if args.password:
        password = args.password
    if args.targetIP:
        targetIP = args.targetIP

    iscsi_test = IscsiTarget(username, password, targetIP)
    iscsi_test.install_pkgs()
    iscsi_test.cleanup()
    iscsi_test.setup_iscsi_target_device()
    iscsi_test.setup_iscsi_target_config()
    iscsi_test.run_tgt()


def main():
    parser = ArgumentParser(description="iSCSI Test")
    parser.add_argument('--debug', dest='log_level',
                        action="store_const", const=logging.DEBUG,
                        default=logging.INFO)

    parser.add_argument(
        '-t', '--targetIP', required=True, type=str, default=None)
    parser.add_argument(
        '-u', '--username', type=str, default="ubuntu")
    parser.add_argument(
        '-p', '--password', type=str, default="ubuntu")
    parser.set_defaults(func=run_target)

    args = parser.parse_args()

    try:
        logging.basicConfig(level=args.log_level)
    except AttributeError:
        pass  # avoids exception when trying to run without specifying

    # silence normal output from requests module
    logging.getLogger("requests").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)

    # Verify args
    try:
        args.func(args)

    except AttributeError:
        parser.print_help()
        return 1

    return 0


if __name__ == '__main__':
    sys.exit(main())
