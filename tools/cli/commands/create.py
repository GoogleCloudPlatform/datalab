# Copyright 2016 Google Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Methods for implementing the `datalab create` command."""

import os
import subprocess
import tempfile

import connect
import utils


description = ("""{0} {1} creates a new Datalab instances running in a Google
Compute Engine VM.

This command also creates the 'datalab-network' network if necessary.

By default, the command creates a persistent connection to the newly
created instance. You can disable that behavior by passing in the
'--no-connect' flag.""")


_DATALAB_NETWORK = 'datalab-network'
_DATALAB_NETWORK_DESCRIPTION = 'Network for Google Cloud Datalab instances'

_DATALAB_FIREWALL_RULE = 'datalab-network-allow-ssh'
_DATALAB_FIREWALL_RULE_DESCRIPTION = 'Allow SSH access to Datalab instances'

_DATALAB_DEFAULT_DISK_SIZE_GB = 200
_DATALAB_DISK_DESCRIPTION = (
    'Persistent disk for a Google Cloud Datalab instance')

_DATALAB_NOTEBOOKS_REPOSITORY = 'datalab-notebooks'

_DATALAB_STARTUP_SCRIPT = """#!/bin/bash

PERSISTENT_DISK_DEV="/dev/disk/by-id/google-datalab-pd"
MOUNT_DIR="/mnt/disks/datalab-pd"
MOUNT_CMD="mount -o discard,defaults ${{PERSISTENT_DISK_DEV}} ${{MOUNT_DIR}}"

clone_repo() {{
  echo "Creating the datalab directory"
  mkdir -p ${{MOUNT_DIR}}/datalab
  echo "Cloning the repo {0}"
  docker run -v "${{MOUNT_DIR}}:/content" \
    --entrypoint "/bin/bash" {0} \
    gcloud source repos clone {1} /content/datalab/notebooks
}}

format_disk() {{
  echo "Formatting the persistent disk"
  mkfs.ext4 -F \
    -E lazy_itable_init=0,lazy_journal_init=0,discard \
    ${{PERSISTENT_DISK_DEV}}
  ${{MOUNT_CMD}}
  clone_repo
}}

mount_disk() {{
  echo "Trying to mount the persistent disk"
  mkdir -p "${{MOUNT_DIR}}"
  ${{MOUNT_CMD}} || format_disk
  chmod a+w "${{MOUNT_DIR}}"
}}

mount_disk
"""

_DATALAB_CONTAINER_MANIFEST_URL = (
    'http://metadata.google.internal/' +
    'computeMetadata/v1/instance/attributes/google-container-manifest')

_DATALAB_CLOUD_CONFIG = """
#cloud-config

runcmd:
- ['curl', '-X', 'GET', '-H', 'Metadata-Flavor: Google','{0}',
   '-o', '/tmp/podspec.yaml']
- ['kubelet', '--pod-manifest-path', '/tmp/podspec.yaml']
""".format(_DATALAB_CONTAINER_MANIFEST_URL)

_DATALAB_CONTAINER_SPEC = """
apiVersion: v1
kind: Pod
metadata:
  name: 'datalab-server'
spec:
  containers:
    - name: datalab
      image: {0}
      command: ['/datalab/run.sh']
      imagePullPolicy: IfNotPresent
      ports:
        - containerPort: 8080
          hostPort: 8080
          hostIP: 127.0.0.1
      env:
        - name: DATALAB_ENV
          value: GCE
        - name: DATALAB_SETTINGS_OVERRIDES
          value: '{{"enableAutoGCSBackups": {1} }}'
        - name: DATALAB_GIT_AUTHOR
          value: '{2}'
      volumeMounts:
        - name: home
          mountPath: /content
    - name: logger
      image: gcr.io/google_containers/fluentd-gcp:1.18
      env:
        - name: FLUENTD_ARGS
          value: -q
      volumeMounts:
        - name: varlog
          mountPath: /var/log
        - name: varlibdockercontainers
          mountPath: /var/lib/docker/containers
          readOnly: true
  volumes:
    - name: home
      hostPath:
        path: /mnt/disks/datalab-pd
    - name: varlog
      hostPath:
        path: /var/log
    - name: varlibdockercontainers
      hostPath:
        path: /var/lib/docker/containers
"""


def flags(parser):
    """Add command line flags for the `create` subcommand.

    Args:
      parser: The argparse parser to which to add the flags.
    """
    parser.add_argument(
        'instance',
        metavar='NAME',
        help='a name for the newly created instance')
    parser.add_argument(
        '--image-name',
        dest='image_name',
        default='gcr.io/cloud-datalab/datalab:local',
        help=(
            'name of the Datalab image to run.'
            '\n\n'
            'If not specified, this defaults to the most recently\n'
            'published image.'))
    parser.add_argument(
        '--disk-name',
        dest='disk_name',
        default=None,
        help=(
            'name of the persistent disk used to store notebooks.'
            '\n\n'
            'If not specified, this defaults to having a name based\n'
            'on the instance name.'))
    parser.add_argument(
        '--disk-size-gb',
        type=int,
        dest='disk_size_gb',
        default=_DATALAB_DEFAULT_DISK_SIZE_GB,
        help='size of the persistent disk in GB.')
    parser.add_argument(
        '--machine-type',
        dest='machine_type',
        default='n1-standard-1',
        help=(
            'the machine type of the instance.'
            '\n\n'
            'To get a list of available machine types, run '
            '\'gcloud compute machine-types list\'.'
            '\n\n'
            'If not specified, the default type is n1-standard-1.'))

    parser.add_argument(
        '--no-connect',
        dest='no_connect',
        action='store_true',
        default=False,
        help='do not connect to the newly created instance')

    parser.add_argument(
        '--no-backups',
        dest='no_backups',
        action='store_true',
        default=False,
        help='do not automatically backup the disk contents to GCS')

    parser.add_argument(
        '--no-create-repository',
        dest='no_create_repository',
        action='store_true',
        default=False,
        help='do not create the datalab-notebooks repository if it is missing')

    connect.connection_flags(parser)
    return


def call_gcloud_quietly(args, gcloud_compute, cmd, report_errors=True):
    """Call `gcloud` and silence any output unless it fails.

    Normally, the `gcloud` command line tool can output a lot of
    messages that are relevant to users in general, but may not
    be relevant to the way a Datalab instance is created.

    For example, creating a persistent disk will result in a
    message that the disk needs to be formatted before it can
    be used. However, the instance we create formats the disk
    if necessary, so that message is erroneous in our case.

    These messages are output regardless of the `--quiet` flag.

    This method allows us to avoid any confusion from those
    messages by redirecting them to a temporary file.

    In the case of an error in the `gcloud` invocation, we
    still print the messages by reading from the temporary
    file and printing its contents.

    Args:
      args: The Namespace returned by argparse
      gcloud_compute: Function that can be used for invoking `gcloud compute`
      cmd: The subcommand to run
      report_errors: Whether or not to report errors to the user
    Raises:
      subprocess.CalledProcessError: If the `gcloud` command fails
    """
    with tempfile.TemporaryFile() as tf:
        try:
            gcloud_compute(args, cmd, stdout=tf, stderr=tf)
        except subprocess.CalledProcessError:
            if report_errors:
                tf.seek(0)
                print(tf.read())
            raise
    return


def create_network(args, gcloud_compute):
    """Create the `datalab-network` network.

    Args:
      args: The Namespace returned by argparse
      gcloud_compute: Function that can be used for invoking `gcloud compute`
    Raises:
      subprocess.CalledProcessError: If the `gcloud` command fails
    """
    print('Creating the network {0}'.format(_DATALAB_NETWORK))
    create_cmd = [
        'networks', 'create', '--quiet', _DATALAB_NETWORK,
        '--description', _DATALAB_NETWORK_DESCRIPTION]
    call_gcloud_quietly(args, gcloud_compute, create_cmd)
    return


def ensure_network_exists(args, gcloud_compute):
    """Create the `datalab-network` network if it does not already exist.

    Args:
      args: The Namespace returned by argparse
      gcloud_compute: Function that can be used for invoking `gcloud compute`
    Raises:
      subprocess.CalledProcessError: If the `gcloud` command fails
    """
    get_cmd = ['networks', 'describe', '--format', 'value(name)',
               _DATALAB_NETWORK]
    try:
        with tempfile.TemporaryFile() as tf:
            gcloud_compute(args, get_cmd, stdout=tf, stderr=tf)
            return
    except subprocess.CalledProcessError:
        create_network(args, gcloud_compute)
    return


def create_firewall_rule(args, gcloud_compute):
    """Create the `datalab-network-allow-ssh` firewall rule.

    Args:
      args: The Namespace returned by argparse
      gcloud_compute: Function that can be used for invoking `gcloud compute`
    Raises:
      subprocess.CalledProcessError: If the `gcloud` command fails
    """
    print('Creating the firewall rule {0}'.format(_DATALAB_FIREWALL_RULE))
    create_cmd = [
        'firewall-rules', 'create', '--quiet', _DATALAB_FIREWALL_RULE,
        '--allow', 'tcp:22',
        '--network', _DATALAB_NETWORK,
        '--description', _DATALAB_FIREWALL_RULE_DESCRIPTION]
    call_gcloud_quietly(args, gcloud_compute, create_cmd)
    return


def ensure_firewall_rule_exists(args, gcloud_compute):
    """Create the `datalab-network-allow-ssh` firewall rule if it necessary.

    Args:
      args: The Namespace returned by argparse
      gcloud_compute: Function that can be used for invoking `gcloud compute`
    Raises:
      subprocess.CalledProcessError: If the `gcloud` command fails
    """
    get_cmd = [
        'firewall-rules', 'describe', _DATALAB_FIREWALL_RULE,
        '--format', 'value(name)']
    try:
        with tempfile.TemporaryFile() as tf:
            gcloud_compute(args, get_cmd, stdout=tf, stderr=tf)
            return
    except subprocess.CalledProcessError:
        create_firewall_rule(args, gcloud_compute)
    return


def create_disk(args, gcloud_compute, disk_name, report_errors):
    """Create the user's persistent disk.

    Args:
      args: The Namespace returned by argparse
      gcloud_compute: Function that can be used for invoking `gcloud compute`
      disk_name: The name of the persistent disk to create
      report_errors: Whether or not to report errors to the end user
    Raises:
      subprocess.CalledProcessError: If the `gcloud` command fails
    """
    print('Creating the disk {0}'.format(disk_name))
    create_cmd = ['disks', 'create', '--quiet']
    if args.zone:
        create_cmd.extend(['--zone', args.zone])
    create_cmd.extend([
        '--size', str(args.disk_size_gb) + 'GB',
        '--description', _DATALAB_DISK_DESCRIPTION,
        disk_name])
    call_gcloud_quietly(args, gcloud_compute, create_cmd, report_errors)
    return


def ensure_disk_exists(args, gcloud_compute, disk_name, report_errors=False):
    """Create the given persistent disk if it does not already exist.

    Args:
      args: The Namespace returned by argparse
      gcloud_compute: Function that can be used for invoking `gcloud compute`
      disk_name: The name of the persistent disk
    Raises:
      subprocess.CalledProcessError: If the `gcloud` command fails
    """
    get_cmd = [
        'disks', 'describe', '--quiet', disk_name, '--format', 'value(name)']
    if args.zone:
        get_cmd.extend(['--zone', args.zone])
    try:
        with tempfile.TemporaryFile() as tf:
            gcloud_compute(args, get_cmd, stdout=tf, stderr=tf)
            return
    except subprocess.CalledProcessError:
        try:
            create_disk(args, gcloud_compute, disk_name, report_errors)
        except:
            if args.zone:
                raise
            else:
                # We take this failure as a sign that gcloud might need
                # to prompt for a zone. As such, we do that prompting
                # for it, and then try again.
                args.zone = utils.prompt_for_zone(args, gcloud_compute)
                ensure_disk_exists(args, gcloud_compute, disk_name,
                                   report_errors=True)
    return


def create_repo(args, gcloud_repos, repo_name):
    """Create the given repository.

    Args:
      args: The Namespace returned by argparse
      gcloud_repos: Function that can be used for invoking
        `gcloud alpha source repos`
      repo_name: The name of the repository to create
    Raises:
      subprocess.CalledProcessError: If the `gcloud` command fails
    """
    create_cmd = ['create', '--quiet', repo_name]
    with tempfile.TemporaryFile() as tf:
        try:
            gcloud_repos(args, create_cmd, stdout=tf, stderr=tf)
        except subprocess.CalledProcessError:
            tf.seek(0)
            print(tf.read())
            raise


def ensure_repo_exists(args, gcloud_repos, repo_name):
    """Create the given repository if it does not already exist.

    Args:
      args: The Namespace returned by argparse
      gcloud_repos: Function that can be used for invoking
        `gcloud alpha source repos`
      repo_name: The name of the repository to check
    Raises:
      subprocess.CalledProcessError: If the `gcloud` command fails
    """
    list_cmd = ['list', '--quiet',
                '--filter', 'name:{}'.format(repo_name),
                '--format', 'value(name)']
    with tempfile.TemporaryFile() as tf:
        gcloud_repos(args, list_cmd, stdout=tf)
        tf.seek(0)
        matching_repos = tf.read().strip()
        if not matching_repos:
            create_repo(args, gcloud_repos, repo_name)


def run(args, gcloud_compute, gcloud_repos, email='', **kwargs):
    """Implementation of the `datalab create` subcommand.

    Args:
      args: The Namespace instance returned by argparse
      gcloud_compute: Function that can be used to invoke `gcloud compute`
      gcloud_repos: Function that can be used to invoke
        `gcloud alpha source repos`
      email: The user's email address
    Raises:
      subprocess.CalledProcessError: If a nested `gcloud` calls fails
    """
    ensure_network_exists(args, gcloud_compute)
    ensure_firewall_rule_exists(args, gcloud_compute)

    instance = args.instance
    disk_name = args.disk_name or '{0}-pd'.format(instance)
    ensure_disk_exists(args, gcloud_compute, disk_name)

    if not args.no_create_repository:
        ensure_repo_exists(args, gcloud_repos, _DATALAB_NOTEBOOKS_REPOSITORY)

    print('Creating the instance {0}'.format(instance))
    cmd = ['instances', 'create']
    if args.zone:
        cmd.extend(['--zone', args.zone])
    disk_cfg = (
        'auto-delete=no,boot=no,device-name=datalab-pd,mode=rw,name=' +
        disk_name)
    enable_backups = "false" if args.no_backups else "true"
    with tempfile.NamedTemporaryFile(delete=False) as startup_script_file:
        with tempfile.NamedTemporaryFile(delete=False) as user_data_file:
            with tempfile.NamedTemporaryFile(delete=False) as manifest_file:
                try:
                    startup_script_file.write(_DATALAB_STARTUP_SCRIPT.format(
                        args.image_name, _DATALAB_NOTEBOOKS_REPOSITORY))
                    startup_script_file.close()
                    user_data_file.write(_DATALAB_CLOUD_CONFIG)
                    user_data_file.close()
                    manifest_file.write(
                        _DATALAB_CONTAINER_SPEC.format(
                            args.image_name, enable_backups, email))
                    manifest_file.close()
                    metadata_template = (
                        'startup-script={0},' +
                        'user-data={1},' +
                        'google-container-manifest={2}')
                    metadata_from_file = (
                        metadata_template.format(
                            startup_script_file.name,
                            user_data_file.name,
                            manifest_file.name))
                    cmd.extend([
                        '--network', _DATALAB_NETWORK,
                        '--image-family', 'gci-stable',
                        '--image-project', 'google-containers',
                        '--machine-type', args.machine_type,
                        '--metadata-from-file', metadata_from_file,
                        '--tags', 'datalab',
                        '--disk', disk_cfg,
                        '--scopes', 'cloud-platform',
                        instance])
                    gcloud_compute(args, cmd)
                finally:
                    os.remove(startup_script_file.name)
                    os.remove(user_data_file.name)
                    os.remove(manifest_file.name)

    if not args.no_connect:
        connect.connect(args, gcloud_compute)
    return
