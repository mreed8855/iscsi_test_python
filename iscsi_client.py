#!/usr/bin/env python3
"""
    Test iSCSI
"""

from argparse import ArgumentParser
import os
import os.path
import logging
import shlex
import apt
from subprocess import (
    Popen,
    PIPE,
    DEVNULL
)
import sys
import parted


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

    def check_package(self, pkg_name):
        cache = apt.Cache()

        pkg = cache[pkg_name]
        if pkg.is_installed:
            print("{} already installed".format(pkg_name))
        else:
            pkg.mark_install()

        try:
            cache.commit()
        except Exception:
            print("Install of {} failed".format(sys.stderr))


class IscsiTest(object):

    def __init__(self, username=None, password=None, targetIP=None):
        self.username = username
        self.password = password
        self.targetIP = targetIP
        self.ISCSI_INIT = "/etc/iscsi/initiatorname.iscsi"
        self.ISCSI_ISCSID = "/etc/iscsi/iscsid.conf"
        self.SFDISK_PART = "/tmp/sdpart.out"
        self.MOUNTED_DIR = "/mnt/iscsi_test"
        self.NODE_CHAP = "node.session.auth.authmethod = CHAP"
        self.set_username = "node.session.auth.username = "
        self.set_password = "node.session.auth.password = "
        self.cmd_output = None
        self.ISCSI_DEV = None

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
                self.cmd_output = task.stdout
            elif task.stderr != '':
                logging.debug(' STDERR: {}'.format(task.stderr))
            else:
                logging.debug(' Command returned no output')
            return True

    def partition(self, device, file_system):
        logging.debug('Partition drive')

        cmd = ("sudo parted -s {} mklabel gpt".format(device))
        if not self.run_command(cmd):
            return False
        cmd = ("sudo parted -a opt {} mkpart primary {} 0% 100%".format(device, file_system))
        if not self.run_command(cmd):
            return False
        device = device + "1"
        cmd = ("mkfs.ext4 -F {}".format(device))
        if not self.run_command(cmd):
            return False

    def comment_out_line(self, filename, search_string):
        comment_symbol = "#"  # the comment symbol to remove

        # read the file into a list of lines
        with open(filename, "r") as file:
            lines = file.readlines()

        # find the line(s) that match the search string and remove the comment symbol
        for i, line in enumerate(lines):
            if search_string in line and line.startswith(comment_symbol):
                lines[i] = line.lstrip(comment_symbol)

        # write the modified list of lines back to the file
        with open(filename, "w") as file:
            file.writelines(lines)

    def setup_iscsi_initiator_configure(self):
        self.comment_out_line("/etc/iscsi/iscsid.conf", "node.session.auth.authmethod = CHAP")
        logging.debug("Setup iscsi conf configure")
        # Check if the username and password are already set in iscsid.conf
        with open("/etc/iscsi/iscsid.conf", "r") as f:
            content = f.read()
            if "node.session.auth.username = " + self.username in content and \
               "node.session.auth.password = " + self.password in content:
                print("Username and password already set in iscsid.conf.")
            else:
                logging.debug("Append iscsid.conf")
                # Append the username and password to the iscsid.conf file
                with open("/etc/iscsi/iscsid.conf", "a") as f:
                    f.write("node.session.auth.username = " + self.username + "\n")
                    f.write("node.session.auth.password = " + self.password + "\n")

    def setup_iscsi_initiator_conf(self):
        logging.debug("Setup iscsi conf")
        iscsi_setting = []
        iscsi_setting.append(self.set_username+self.username)
        iscsi_setting.append(self.set_password+self.password)

        for setting in iscsi_setting:
            cmd = ("grep -q \"{}\" {}".format(setting, self.ISCSI_ISCSID))
            if not self.run_command(cmd):
                logging.debug("Adding username or password")
                cmd = ("sudo echo \"{}\" >> {}".format(setting, self.ISCSI_ISCSID))
                if not self.run_command(cmd):
                    return False

        logging.debug("Configure CHAP Settings")
        cmd = ("grep -F -q  \"{}\" {}".
               format(self.NODE_CHAP, self.ISCSI_ISCSID))
        if self.run_command(cmd):
            logging.debug("Uncomment CHAP Setting")
            cmd = ("sudo sed -i /^# {} /c{} {}".
                   format(self.NODE_CHAP, self.NODE_CHAP, self.ISCSI_ISCSID))
            print(cmd)
            if not self.run_command(cmd):
                return False

    def setup_iscsi_initiator(self):
        logging.debug("Comment out previous InitiatiorName")
        cmd = ("sed -i \'/InitiatorName/s/^/#/g\' {}".format(self.ISCSI_INIT))
        if not self.run_command(cmd):
            return False

        cmd = ("/sbin/iscsi-iname")
        if not self.run_command(cmd):
            return False
        self.ISCSI_LUN = self.cmd_output

        initiatorName = ("InitiatorName={} ".format(self.ISCSI_LUN))
        with open(self.ISCSI_INIT, "r") as f:
            content = f.read()
            if initiatorName in content:
                print("Username and password already set in iscsid.conf.")
            else:
                logging.debug("Append iscsid.conf")
                # Append the username and password to the iscsid.conf file
                with open(self.ISCSI_INIT, "a") as f:
                    f.write(initiatorName + "\n")

#        cmd = ("sudo iscsiadm -m discovery -t st -p {} | cut -d\" \" -f 2").format(self.targetIP)
        cmd = ("sudo iscsiadm -m discovery -t st -p {}").format(self.targetIP)
        if not self.run_command(cmd):
            return False
        self.ISCSI_LUN = self.cmd_output.split(" ")
        print(self.ISCSI_LUN[1])

        cmd = ("sudo iscsiadm -m node --targetname {} --portal {} \
        --login".format(self.ISCSI_LUN[1], self.targetIP))
        if not self.run_command(cmd):
            return False

    def test_iscsi(self):
        cmd = ("lsscsi | grep dev | awk \'{print $6}\'")
        if not self.run_command(cmd):
            return False
        self.ISCSI_DEV = self.cmd_output
#        self.ISCSI_DEV = self.ISCSI_DEV+"1"

        cmd = ("mkdir -p {}".format(self.MOUNTED_DIR))
        if not self.run_command(cmd):
            return False
        if os.path.ismount(self.ISCSI_DEV):
            cmd = ("umount {}".format(self.ISCSI_DEV))
        else:
            cmd = ("mount {} {}".format(self.ISCSI_DEV, self.MOUNTED_DIR))
            if not self.run_command(cmd):
                return False

    def cleanup(self):
        logging.debug("Unmount, Remove partion and Logout")
        logging.debug("Unmount")

        if os.path.ismount(self.MOUNTED_DIR):
            cmd = "sudo umount {}".format(self.MOUNTED_DIR)
            if not self.run_command(cmd):
                return False
        else:
            print(self.MOUNTED_DIR)

        logging.debug("Remove Partition")
#        cmd = "sudo sfdisk --delete {}".format(self.SFDISK_PART)
#        if not self.run_command(cmd):
#            return False

        print(self.ISCSI_LUN)
        print(self.targetIP)
        logging.debut("Logout of Target")
        cmd = "sudo iscsiadm -m node --targetname {} --portal {} --logout".format(self.ISCSI_LUN, self.targetIP)
        if not self.run_command(cmd):
            return False

    def print_var(self):
        logging.debug("Print Var")
        print(self.username)
        print(self.password)
        print(self.targetIP)


def run_client(args):
    logging.debug("Executing run_client")
    username = None
    password = None
    targetIP = None

    print("Run Client before")
    # First in priority are environment variables.
    if 'ISCSI_USERNAME' in os.environ:
        username = os.environ['ISCSI_USERNAME']
    if 'ISCSI_PASSWORD' in os.environ:
        password = os.environ['ISCSI_PASSWORD']
    if 'TARGET_IPADDR' in os.environ:
        targetIP = os.environ['TARGET_IPADDR']

    # Finally, highest-priority are command line arguments.
    if args.username:
        username = args.username
    if args.password:
        password = args.password
    if args.targetIP:
        targetIP = args.targetIP

    iscsi_test = IscsiTest(username, password, targetIP)
#    iscsi_test.cleanup()
    iscsi_test.setup_iscsi_initiator_configure()
    iscsi_test.setup_iscsi_initiator()
#    iscsi_test.setup_iscsi_initiator_conf()
#    iscsi_test.setup_iscsi_initiator_configure()
#    iscsi_test.partition("/dev/sda", "ext4")
    iscsi_test.print_var()

    print("Run Client")


def main():
    parser = ArgumentParser(description="iSCSI Test")
    parser.add_argument('--debug', dest='log_level',
                        action="store_const", const=logging.DEBUG,
                        default=logging.INFO)

    parser.add_argument(
        '-t', '--targetIP', type=str, default=None)
    parser.add_argument(
        '-u', '--username', type=str, default=None)
    parser.add_argument(
        '-p', '--password', type=str, default=None)
    parser.set_defaults(func=run_client)

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
