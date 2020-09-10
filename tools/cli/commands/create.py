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

from __future__ import absolute_import

import json
import os
import subprocess
import sys
import tempfile

from . import connect, utils

try:
    # If we are running in Python 2, builtins is available in 'future'.
    from builtins import input as read_input
except Exception:
    # We don't want to require the installation of future, so fallback
    # to using raw_input from Py2.
    read_input = raw_input  # noqa: F821


description = ("""`{0} {1}` creates a new Datalab instances running in a Google
Compute Engine VM.

This command also creates the 'datalab-network' network if necessary.

By default, the command creates a persistent connection to the newly
created instance. You can disable that behavior by passing in the
'--no-connect' flag.""")


_DATALAB_NETWORK = 'datalab-network'
_DATALAB_NETWORK_DESCRIPTION = 'Network for Google Cloud Datalab instances'

_DATALAB_FIREWALL_RULE_TEMPLATE = '{0}-allow-ssh'
_DATALAB_FIREWALL_RULE_DESCRIPTION = 'Allow SSH access to Datalab instances'
_DATALAB_UNEXPECTED_FIREWALLS_WARNING_TEMPLATE = (
    'The network `{0}` has firewall rules that were not created by the '
    '`datalab` command line tool. Instances created in that network may '
    'be open to traffic that they should not be exposed to.')

_DATALAB_NO_FIREWALL_WARNING = (
    '\nWarning: --no-firewall-rule requires firewall rules to be '
    'configured in advance. \n'
    'Incorrect configuration may result in errors like: \n'
    'ssh_exchange_identification: Connection closed by remote host \n\n'
)

_DATALAB_DEFAULT_DISK_SIZE_GB = 200
_DATALAB_DISK_DESCRIPTION = (
    'Persistent disk for a Google Cloud Datalab instance')

_DATALAB_NOTEBOOKS_REPOSITORY = 'datalab-notebooks'

_DATALAB_STARTUP_SCRIPT = """#!/bin/bash

# First, make sure the `datalab` and `logger` users exist with their
# home directories setup correctly.
useradd datalab -u 2000 || useradd datalab
useradd logger -u 2001 || useradd logger

# In case the instance has started before, the `/home/datalab` directory
# may already exist, but with the incorrect user ID (since `/etc/passwd`
# is saved in a tmpfs and changes after restarts). To account for that,
# we should force the file ownership under `/home/datalab` to match
# the current UID for the `datalab` user.
chown -R datalab /home/datalab
chown -R logger /home/logger

PERSISTENT_DISK_DEV="/dev/disk/by-id/google-datalab-pd"
MOUNT_DIR="/mnt/disks/datalab-pd"
MOUNT_CMD="mount -o discard,defaults ${{PERSISTENT_DISK_DEV}} ${{MOUNT_DIR}}"

download_docker_image() {{
  # Since /root/.docker is not writable on the default image,
  # we need to set HOME to be a writable directory. This same
  # directory is used later on by the datalab.service.
  export OLD_HOME=$HOME
  export HOME=/home/datalab
  echo "Getting Docker credentials"
  docker-credential-gcr configure-docker
  echo "Pulling latest image: {0}"
  docker pull {0}
  export HOME=$OLD_HOME
}}

clone_repo() {{
  echo "Creating the datalab directory"
  mkdir -p ${{MOUNT_DIR}}/content/datalab
  echo "Cloning the repo {1}"
  docker run --rm -v "${{MOUNT_DIR}}/content:/content" \
    --entrypoint "/bin/bash" {0} \
    gcloud source repos clone {1} /content/datalab/notebooks
}}

repo_is_populated() {{
  cd ${{MOUNT_DIR}}/content/datalab/notebooks
  git show-ref --quiet
}}

populate_repo() {{
  echo "Populating datalab-notebooks repo"
  docker run --rm -v "${{MOUNT_DIR}}/content:/content" \
    --workdir=/content/datalab/notebooks \
    --entrypoint "/bin/bash" {0} -c "\
        echo '.ipynb_checkpoints' >> .gitignore; \
        echo '*.pyc' >> .gitignore; \
        echo '# Project Notebooks' >> README.md; \
        git add .gitignore README.md; \
        git -c user.email=nobody -c user.name=Datalab \
          commit --message='Set up initial notebook repo.'; \
        git push origin master; \
    "
}}

format_disk() {{
  echo "Formatting the persistent disk"
  mkfs.ext4 -F \
    -E lazy_itable_init=0,lazy_journal_init=0,discard \
    ${{PERSISTENT_DISK_DEV}}
  ${{MOUNT_CMD}}
  clone_repo
  if ! repo_is_populated; then
    populate_repo
  fi
}}

checked_format_disk() {{
  echo "Checking if the persistent disk needs to be formatted"
  if [ -z "$(blkid ${{PERSISTENT_DISK_DEV}})" ]; then
    format_disk
  else
    echo "Disk already formatted, but mounting failed; rebooting..."

    # The mount failed, but the disk seems to already
    # be formatted. Reboot the machine to try again.
    reboot now
  fi
}}

mount_and_prepare_disk() {{
  echo "Trying to mount the persistent disk"
  mkdir -p "${{MOUNT_DIR}}"
  ${{MOUNT_CMD}} || checked_format_disk

  if [ -z "$(mount | grep ${{MOUNT_DIR}})" ]; then
    echo "Failed to mount the persistent disk; rebooting..."
    reboot now
  fi

  chmod a+w "${{MOUNT_DIR}}"
  mkdir -p "${{MOUNT_DIR}}/content"

  old_dir="${{MOUNT_DIR}}/datalab"
  new_dir="${{MOUNT_DIR}}/content/datalab"
  if [ -d "${{old_dir}}" ] && [ ! -d "${{new_dir}}" ]; then
    echo "Moving ${{old_dir}} to ${{new_dir}}"
    mv "${{old_dir}}" "${{new_dir}}"
  else
    echo "Creating ${{new_dir}}"
    mkdir -p "${{new_dir}}"
  fi
}}

configure_swap() {{
  if [ "{2}" == "false" ]; then
    return
  fi
  mem_total_line=`cat /proc/meminfo | grep MemTotal`
  mem_total_value=`echo "${{mem_total_line}}" | cut -d ':' -f 2`
  memory_kb=`echo "${{mem_total_value}}" | cut -d 'k' -f 1 | tr -d '[:space:]'`

  # Before proceeding, check if we have more disk than memory.
  # Specifically, if the free space on disk is not N times the
  # size of memory, then enabling swap makes no sense.
  #
  # Arbitrarily choosing a value of N=10
  disk_kb_cutoff=`expr 10 "*" ${{memory_kb}}`
  disk_kb_available=`df --output=avail ${{MOUNT_DIR}} | tail -n 1`
  if [ "${{disk_kb_available}}" -lt "${{disk_kb_cutoff}}" ]; then
    return
  fi

  swapfile="${{MOUNT_DIR}}/swapfile"

  # Create the swapfile if it is either missing or not big enough
  current_size="0"
  if [ -e "${{swapfile}}" ]; then
    current_size=`ls -s ${{swapfile}} | cut -d ' ' -f 1`
  fi
  if [ "${{memory_kb}}" -gt "${{current_size}}" ]; then
    echo "Creating a ${{memory_kb}} kilobyte swapfile at ${{swapfile}}"
    dd if=/dev/zero of="${{swapfile}}" bs=1024 count="${{memory_kb}}"
  fi
  chmod 0600 "${{swapfile}}"
  mkswap "${{swapfile}}"

  # Enable swap
  sysctl vm.disk_based_swap=1
  swapon "${{swapfile}}"
}}

cleanup_tmp() {{
  tmpdir="${{MOUNT_DIR}}/tmp"

  # First, make sure the temporary directory exists.
  mkdir -p "${{tmpdir}}"

  # Remove all files from it.
  #
  # We do not remove the directory itself, as that could lead to a broken
  # volume mount if the Docker container has already started).
  #
  # We also do not just use `rm -rf ${{tmpdir}}/*`, as that would leave
  # behind any hidden files.
  find "${{tmpdir}}/" -mindepth 1 -delete
}}

download_docker_image
mount_and_prepare_disk
configure_swap
cleanup_tmp

journalctl -u google-startup-scripts --no-pager > /var/log/startupscript.log
"""

_DATALAB_CLOUD_CONFIG = """
#cloud-config

users:
- name: datalab
  uid: 2000
  groups: docker
- name: logger
  uid: 2001
  groups: docker

write_files:
- path: /etc/systemd/system/wait-for-startup-script.service
  permissions: 0755
  owner: root
  content: |
    [Unit]
    Description=Wait for the startup script to setup required directories
    Requires=network-online.target gcr-online.target
    After=network-online.target gcr-online.target

    [Service]
    User=root
    Type=oneshot
    RemainAfterExit=true
    ExecStart=/bin/bash -c 'while [ ! -e /mnt/disks/datalab-pd/tmp ]; do \
        sleep 1; \
        done'

- path: /etc/systemd/system/datalab.service
  permissions: 0644
  owner: root
  content: |
    [Unit]
    Description=datalab docker container
    Requires=network-online.target gcr-online.target \
             wait-for-startup-script.service
    After=network-online.target gcr-online.target \
          wait-for-startup-script.service

    [Service]
    Environment="HOME=/home/datalab"
    ExecStartPre=/usr/bin/docker-credential-gcr configure-docker
    ExecStart=/usr/bin/docker run --rm -u 0 \
       --name=datalab \
       -p 127.0.0.1:8080:8080 \
       -v /mnt/disks/datalab-pd/content:/content \
       -v /mnt/disks/datalab-pd/tmp:/tmp \
       --env=HOME=/content \
       --env=DATALAB_ENV=GCE \
       --env=DATALAB_DEBUG=true \
       --env='DATALAB_SETTINGS_OVERRIDES={{ \
            "enableAutoGCSBackups": {1}, \
            "consoleLogLevel": "{2}" \
       }}' \
       --env='DATALAB_GIT_AUTHOR={3}' \
       --env='DATALAB_INITIAL_USER_SETTINGS={4}' \
       {0}
    ExecStop=-/usr/bin/docker stop datalab
    ExecStopPost=-/usr/bin/docker rm -f datalab
    Restart=always
    RestartSec=1

- path: /etc/google-fluentd/fluentd.conf
  permissions: 0644
  owner: root
  content: |
    # This config comes from a heavily trimmed version of the
    # container-engine-customize-fluentd project. The upstream config is here:
    # https://github.com/GoogleCloudPlatform/container-engine-customize-fluentd/blob/6a46d72b29f3d8e8e495713bc3382ce28caf744e/kubernetes/fluentd-configmap.yaml
    <source>
      type tail
      format json
      time_key time
      path /var/lib/docker/containers/*/*.log
      pos_file /var/log/google-fluentd/containers.log.pos
      time_format %Y-%m-%dT%H:%M:%S.%N%Z
      tag containers
      read_from_head true
    </source>
    <match **>
      @type copy
       <store>
        @type google_cloud
        # Set the buffer type to file to improve the reliability
        # and reduce the memory consumption
        buffer_type file
        buffer_path /var/log/google-fluentd/cos-system.buffer
        # Set queue_full action to block because we want to pause gracefully
        # in case of the off-the-limits load instead of throwing an exception
        buffer_queue_full_action block
        # Set the chunk limit conservatively to avoid exceeding the GCL limit
        # of 10MiB per write request.
        buffer_chunk_limit 2M
        # Cap the combined memory usage of this buffer and the one below to
        # 2MiB/chunk * (6 + 2) chunks = 16 MiB
        buffer_queue_limit 6
        # Never wait more than 5 seconds before flushing logs in the non-error
        # case.
        flush_interval 5s
        # Never wait longer than 30 seconds between retries.
        max_retry_wait 30
        # Disable the limit on the number of retries (retry forever).
        disable_retry_limit
        # Use multiple threads for processing.
        num_threads 2
      </store>
    </match>

- path: /etc/systemd/system/logger.service
  permissions: 0644
  owner: root
  content: |
    [Unit]
    Description=logging docker container
    Requires=network-online.target
    After=network-online.target

    [Service]
    Environment="HOME=/home/logger"
    ExecStartPre=/usr/share/google/dockercfg_update.sh
    ExecStartPre=/bin/mkdir -p /var/log/google-fluentd/
    ExecStartPre=-/usr/bin/docker rm -fv logger
    ExecStart=/usr/bin/docker run --rm -u 0 \
       --name=logger \
       -v /var/log/:/var/log/ \
       -v /var/lib/docker/containers:/var/lib/docker/containers \
       -v /etc/google-fluentd/:/etc/fluent/config.d/ \
       --env='FLUENTD_ARGS=-q' \
       gcr.io/google-containers/fluentd-gcp:2.0.17
    Restart=always
    RestartSec=1

runcmd:
- systemctl daemon-reload
- systemctl start datalab.service
- systemctl start logger.service
"""


class RepositoryException(Exception):

    _MESSAGE = (
        'Failed to find or create the repository `{}`.'
        '\n\n'
        'Ask a project owner to create it for you.')

    def __init__(self, repo_name):
        super(RepositoryException, self).__init__(
            RepositoryException._MESSAGE.format(repo_name))


class SubnetException(Exception):

    _MESSAGE = (
        'Failed to find the subnet `{}`.'
        '\n\n'
        'Ask a project owner to create it for you, '
        'or double check your gcloud config for the correct region.')

    def __init__(self, subnet_name):
        super(SubnetException, self).__init__(
            SubnetException._MESSAGE.format(subnet_name))


class NoSubnetsFoundException(Exception):

    _MESSAGE = (
        'Failed to find a subnet for the network `{}` in the region `{}`.'
        '\n\n'
        'Ask a network admin to check it for you.'
        '\n\n'
        'Note that if this is a legacy network, then an '
        'external IP address is required.')

    def __init__(self, network_name, region):
        super(NoSubnetsFoundException, self).__init__(
            NoSubnetsFoundException._MESSAGE.format(network_name, region))


class PrivateIpGoogleAccessException(Exception):

    _MESSAGE = (
        'The subnet `{}` in the region `{}` is not configured to '
        'allow private IP addresses to access Google services.'
        '\n\n'
        'Either ask a network admin to configure it for you, or '
        'create the instance with an external IP address.')

    def __init__(self, subnet_name, region):
        super(PrivateIpGoogleAccessException, self).__init__(
            PrivateIpGoogleAccessException._MESSAGE.format(
                subnet_name, region))


class CancelledException(Exception):

    _MESSAGE = 'Operation cancelled.'

    def __init__(self):
        super(CancelledException, self).__init__(CancelledException._MESSAGE)


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
        default='gcr.io/cloud-datalab/datalab:latest',
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
        '--network-name',
        dest='network_name',
        default=_DATALAB_NETWORK,
        help='name of the network to which the instance will be attached.')
    parser.add_argument(
        '--subnet-name',
        dest='subnet_name',
        default=None,
        help='name of the subnet to which the instance will be attached.')

    parser.add_argument(
        '--idle-timeout',
        dest='idle_timeout',
        default=None,
        help=(
            'interval after which an idle Datalab instance will shut down.'
            '\n\n'
            'You can specify a mix of days, hours, minutes and seconds\n'
            'using those names or d, h, m and s, for example "1h 30m".\n'
            'Specify 0s to disable.'))

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
        '--no-swap',
        dest='no_swap',
        action='store_true',
        default=False,
        help='do not enable swap on the newly created instance')

    parser.add_argument(
        '--no-backups',
        dest='no_backups',
        action='store_true',
        default=False,
        help='do not automatically backup the disk contents to GCS')

    parser.add_argument(
        '--beta-no-external-ip',
        dest='no_external_ip',
        action='store_true',
        default=False,
        help=(
            'do not assign the instance an external IP address.'
            '\n\n'
            'If specified, you must make sure that the machine where you '
            'run `datalab connect` is on the same VPC as the instance '
            '(the one specified via the `--network-name` flag).'
            '\n\n'
            'Additionally, you must pass the `--beta-internal-ip` flag '
            'to the `datalab connect` command.'
            '\n\n'
            'Note that this is a beta feature and unsupported.'))

    parser.add_argument(
        '--no-firewall-rule',
        dest='no_firewall_rule',
        action='store_true',
        default=False,
        help='Disable the automatic creation of a firewall rule'
    )

    parser.add_argument(
        '--no-create-repository',
        dest='no_create_repository',
        action='store_true',
        default=False,
        help='do not create the datalab-notebooks repository if it is missing')

    parser.add_argument(
        '--log-level',
        dest='log_level',
        choices=['trace', 'debug', 'info', 'warn', 'error', 'fatal'],
        default='warn',
        help=(
            'the log level for Datalab instance.'
            '\n\n'
            'This is the threshold under which log entries from the '
            'Datalab instance will not be written to StackDriver logging.'
            '\n\n'
            'The default log level is "warn".'))

    parser.add_argument(
        '--for-user',
        dest='for_user',
        help='create the datalab instance on behalf of the specified user')

    parser.add_argument(
        '--service-account',
        dest='service_account',
        help=('A service account is an identity attached to the instance. '
              'Its access tokens can be accessed through the instance '
              'metadata server and are used to authenticate API calls made '
              'from Datalab. The account can be either an email address or '
              'an alias corresponding to a service account. You can '
              'explicitly specify the Compute Engine default service account '
              'using the \'default\' alias.'
              '\n\n'
              'If not provided, the instance will get project\'s default '
              'service account.'))

    connect.connection_flags(parser)
    return


def get_region_name(args, gcloud_compute):
    """Lookup the name of the GCP region.

    Args:
      args: The Namespace returned by argparse
      gcloud_compute: Function that can be used for invoking `gcloud compute`
    Raises:
      subprocess.CalledProcessError: If a `gcloud` command fails
    """

    get_zone_cmd = ['zones', 'describe', '--format=value(region)', args.zone]
    with tempfile.TemporaryFile() as stdout, \
            tempfile.TemporaryFile() as stderr:
        try:
            gcloud_compute(args, get_zone_cmd, stdout=stdout, stderr=stderr)
            stdout.seek(0)
            region_uri = stdout.read().decode('utf-8').strip()
        except subprocess.CalledProcessError:
            stderr.seek(0)
            sys.stderr.write(stderr.read())
            raise
    get_region_cmd = [
        'regions', 'describe', '--format=value(name)', region_uri]
    with tempfile.TemporaryFile() as stdout, \
            tempfile.TemporaryFile() as stderr:
        try:
            gcloud_compute(args, get_region_cmd, stdout=stdout, stderr=stderr)
            stdout.seek(0)
            return stdout.read().decode('utf-8').strip()
        except subprocess.CalledProcessError:
            stderr.seek(0)
            sys.stderr.write(stderr.read())
            raise


def create_network(args, gcloud_compute, network_name):
    """Create the specified network.

    Args:
      args: The Namespace returned by argparse
      gcloud_compute: Function that can be used for invoking `gcloud compute`
      network_name: The name of the network
    Raises:
      subprocess.CalledProcessError: If the `gcloud` command fails
    """
    if utils.print_info_messages(args):
        print('Creating the network {0}'.format(network_name))
    create_cmd = [
        'networks', 'create', network_name,
        '--description', _DATALAB_NETWORK_DESCRIPTION]
    utils.call_gcloud_quietly(args, gcloud_compute, create_cmd)
    return


def ensure_network_exists(args, gcloud_compute, network_name):
    """Create the specified network if it does not already exist.

    Args:
      args: The Namespace returned by argparse
      gcloud_compute: Function that can be used for invoking `gcloud compute`
      network_name: The name of the network
    Raises:
      subprocess.CalledProcessError: If the `gcloud` command fails
    """
    get_cmd = ['networks', 'describe', '--format', 'value(name)', network_name]
    try:
        utils.call_gcloud_quietly(
            args, gcloud_compute, get_cmd, report_errors=False)
    except subprocess.CalledProcessError:
        create_network(args, gcloud_compute, network_name)
    return


def get_subnet_name(args, gcloud_compute, network_name, region):
    """Lookup the name of the subnet.

    The specified network must be either an `auto` or `custom` mode network;
    legacy networks are not supported.

    Args:
      args: The Namespace returned by argparse
      gcloud_compute: Function that can be used for invoking `gcloud compute`
      network_name: Name of the VPC network
      region: Name of the GCP region
    Raises:
      subprocess.CalledProcessError: If a `gcloud` command fails
    """
    get_subnet_cmd = ['networks', 'subnets', 'list',
                      '--filter=network~/{}$ region~/{}$'.format(
                          network_name, region),
                      '--format=value(name)']
    with tempfile.TemporaryFile() as stdout, \
            tempfile.TemporaryFile() as stderr:
        try:
            gcloud_compute(args, get_subnet_cmd, stdout=stdout, stderr=stderr)
            stdout.seek(0)
            subnet_name = stdout.read().decode('utf-8').strip()
            if not subnet_name:
                raise NoSubnetsFoundException(network_name, region)
            if utils.print_debug_messages(args):
                print('Using the subnet {0}'.format(subnet_name))
            return subnet_name
        except subprocess.CalledProcessError:
            stderr.seek(0)
            sys.stderr.write(stderr.read())
            raise


def ensure_private_ip_google_access(args, gcloud_compute, subnet_name, region):
    """Ensure that the subnet allows private IPs to access Google services.

    Args:
      args: The Namespace returned by argparse
      gcloud_compute: Function that can be used for invoking `gcloud compute`
      subnet_name: Name of the VPC sub-network
      region: Name of the GCP region
    Raises:
      subprocess.CalledProcessError: If a `gcloud` command fails
      subprocess.PrivateIpGoogleAccessException: If the check fails
    """
    if utils.print_debug_messages(args):
        print('Checking private IP access to Google services for '
              'the subnet `{0}` in the region `{1}`'.format(
                  subnet_name, region))
    get_subnet_cmd = ['networks', 'subnets', 'describe', subnet_name,
                      '--region', region,
                      '--format=get(privateIpGoogleAccess)']
    with tempfile.TemporaryFile() as stdout, \
            tempfile.TemporaryFile() as stderr:
        try:
            gcloud_compute(args, get_subnet_cmd, stdout=stdout, stderr=stderr)
            stdout.seek(0)
            has_access = stdout.read().decode('utf-8').strip()
            if utils.print_debug_messages(args):
                print('Private IP Google access allowed: `{0}`'.format(
                    has_access))
            if not (has_access == 'True'):
                raise PrivateIpGoogleAccessException(subnet_name, region)
        except subprocess.CalledProcessError:
            stderr.seek(0)
            sys.stderr.write(stderr.read())
            raise


def ensure_subnet_exists(args, gcloud_compute, subnet_region, subnet_name):
    """Check the specified subnet if it does not exit with error.

    Args:
      args: The Namespace returned by argparse
      gcloud_compute: Function that can be used for invoking `gcloud compute`
      subnet_region: The name of the region of the subnet
      subnet_name: The name of the subnet
    Raises:
      subprocess.CalledProcessError: If the `gcloud` command fails
    """
    get_cmd = [
        'networks', 'subnets', 'describe',
        '--format', 'value(name)', '--region', subnet_region, subnet_name]
    try:
        utils.call_gcloud_quietly(
            args, gcloud_compute, get_cmd, report_errors=False)
    except subprocess.CalledProcessError:
        raise SubnetException(subnet_name)
    return


def create_firewall_rule(args, gcloud_compute, network_name, rule_name):
    """Create the specified firewall rule to allow SSH access.

    Args:
      args: The Namespace returned by argparse
      gcloud_compute: Function that can be used for invoking `gcloud compute`
      network_name: The name of the network on which to allow SSH access
      rule_name: The name of the firewall rule
    Raises:
      subprocess.CalledProcessError: If the `gcloud` command fails
    """
    firewall_args = get_firewall_args(args, network_name)
    if utils.print_info_messages(args):
        print('Creating the firewall rule {0}'.format(rule_name))
    create_cmd = [
        'firewall-rules', 'create', rule_name,
        '--allow', 'tcp:22',
        '--network', network_name,
        '--description', _DATALAB_FIREWALL_RULE_DESCRIPTION]
    utils.call_gcloud_quietly(firewall_args, gcloud_compute, create_cmd)
    return


def has_unexpected_firewall_rules(args, gcloud_compute, network_name):
    rule_name = generate_firewall_rule_name(network_name)
    firewall_args = get_firewall_args(args, network_name)
    list_cmd = [
        'firewall-rules', 'list',
        '--filter', 'network~.^*{0}$'.format(network_name),
        '--format', 'value(name)']
    with tempfile.TemporaryFile() as tf:
        gcloud_compute(firewall_args, list_cmd, stdout=tf)
        tf.seek(0)
        matching_rules = tf.read().decode('utf-8').strip()
        if matching_rules and (matching_rules != rule_name):
            return True
    return False


def prompt_on_unexpected_firewall_rules(args, gcloud_compute, network_name):
    if has_unexpected_firewall_rules(args, gcloud_compute, network_name):
        warning = _DATALAB_UNEXPECTED_FIREWALLS_WARNING_TEMPLATE.format(
            network_name)
        print(warning)
        resp = read_input('Do you still want to use this network? (y/[n]): ')
        if len(resp) < 1 or (resp[0] != 'y' and resp[0] != 'Y'):
            raise CancelledException()
    return


def ensure_firewall_rule_exists(args, gcloud_compute, network_name):
    """Create a firewall rule to allow SSH access if necessary.

    Args:
      args: The Namespace returned by argparse
      gcloud_compute: Function that can be used for invoking `gcloud compute`
      network_name: The name of the network on which to allow SSH access
    Raises:
      subprocess.CalledProcessError: If the `gcloud` command fails
    """
    firewall_args = get_firewall_args(args, network_name)
    rule_name = generate_firewall_rule_name(network_name)
    get_cmd = [
        'firewall-rules', 'describe', rule_name, '--format', 'value(name)']
    try:
        utils.call_gcloud_quietly(
            firewall_args, gcloud_compute, get_cmd, report_errors=False)
    except subprocess.CalledProcessError:
        create_firewall_rule(args, gcloud_compute, network_name, rule_name)
    return


def generate_firewall_rule_name(network_name):
    """Converts network name to a valid rule name to support shared vpc"""
    if "/" in network_name:
        return _DATALAB_FIREWALL_RULE_TEMPLATE.format(
            network_name.split("/")[-1])
    else:
        return _DATALAB_FIREWALL_RULE_TEMPLATE.format(network_name)


def get_firewall_args(args, network_name):
    """
    Shared VPCs firewall rules need to be created in the host project.
    This modifies the args to the host project for commands that need it.
    """
    if "/" in network_name:
        project_name = network_name.split("/")[1]
        args.project = project_name

    return args


def create_disk(args, gcloud_compute, disk_name):
    """Create the user's persistent disk.

    Args:
      args: The Namespace returned by argparse
      gcloud_compute: Function that can be used for invoking `gcloud compute`
      disk_name: The name of the persistent disk to create
    Raises:
      subprocess.CalledProcessError: If the `gcloud` command fails
    """
    if utils.print_info_messages(args):
        print('Creating the disk {0}'.format(disk_name))
    create_cmd = ['disks', 'create']
    if args.zone:
        create_cmd.extend(['--zone', args.zone])
    create_cmd.extend([
        '--size', str(args.disk_size_gb) + 'GB',
        '--description', _DATALAB_DISK_DESCRIPTION,
        disk_name])
    utils.call_gcloud_quietly(args, gcloud_compute, create_cmd)
    return


def ensure_disk_exists(args, gcloud_compute, disk_name):
    """Create the given persistent disk if it does not already exist.

    Args:
      args: The Namespace returned by argparse
      gcloud_compute: Function that can be used for invoking `gcloud compute`
      disk_name: The name of the persistent disk
    Raises:
      subprocess.CalledProcessError: If the `gcloud` command fails
    """
    get_cmd = [
        'disks', 'describe', disk_name, '--format', 'value(name)']
    if args.zone:
        get_cmd.extend(['--zone', args.zone])
    try:
        utils.call_gcloud_quietly(
            args, gcloud_compute, get_cmd, report_errors=False)
    except subprocess.CalledProcessError:
        create_disk(args, gcloud_compute, disk_name)
    return


def create_repo(args, gcloud_repos, repo_name):
    """Create the given repository.

    Args:
      args: The Namespace returned by argparse
      gcloud_repos: Function that can be used for invoking
        `gcloud source repos`
      repo_name: The name of the repository to create
    Raises:
      subprocess.CalledProcessError: If the `gcloud` command fails
    """
    if utils.print_info_messages(args):
        print('Creating the repository {0}'.format(repo_name))

    create_cmd = ['create', repo_name]
    utils.call_gcloud_quietly(args, gcloud_repos, create_cmd)


def ensure_repo_exists(args, gcloud_repos, repo_name):
    """Create the given repository if it does not already exist.

    Args:
      args: The Namespace returned by argparse
      gcloud_repos: Function that can be used for invoking
        `gcloud source repos`
      repo_name: The name of the repository to check
    Raises:
      subprocess.CalledProcessError: If the `gcloud` command fails
    """
    list_cmd = ['list', '--quiet',
                '--filter', 'name~^.*/repos/{}$'.format(repo_name),
                '--format', 'value(name)']
    with tempfile.TemporaryFile() as tf:
        gcloud_repos(args, list_cmd, stdout=tf)
        tf.seek(0)
        matching_repos = tf.read().decode('utf-8').strip()
        if not matching_repos:
            try:
                create_repo(args, gcloud_repos, repo_name)
            except Exception:
                raise RepositoryException(repo_name)


def prepare(args, gcloud_compute, gcloud_repos):
    """Run preparation steps for VM creation.

    Args:
      args: The Namespace instance returned by argparse
      gcloud_compute: Function that can be used to invoke `gcloud compute`
      gcloud_repos: Function that can be used to invoke
        `gcloud source repos`
    Returns:
      The disk config
    Raises:
      subprocess.CalledProcessError: If a nested `gcloud` calls fails
    """
    network_name = args.network_name
    ensure_network_exists(args, gcloud_compute, network_name)
    if args.no_firewall_rule:
        print(_DATALAB_NO_FIREWALL_WARNING)
    else:
        prompt_on_unexpected_firewall_rules(args, gcloud_compute, network_name)
        ensure_firewall_rule_exists(args, gcloud_compute, network_name)

    disk_name = args.disk_name or '{0}-pd'.format(args.instance)
    ensure_disk_exists(args, gcloud_compute, disk_name)
    disk_cfg = (
        'auto-delete=no,boot=no,device-name=datalab-pd,mode=rw,name=' +
        disk_name)
    region = get_region_name(args, gcloud_compute)

    if args.subnet_name:
        ensure_subnet_exists(args, gcloud_compute, region, args.subnet_name)

    if args.no_external_ip:
        subnet_name = args.subnet_name or get_subnet_name(
            args, gcloud_compute, network_name, region)
        ensure_private_ip_google_access(
            args, gcloud_compute, subnet_name, region)

    if not args.no_create_repository:
        ensure_repo_exists(args, gcloud_repos, _DATALAB_NOTEBOOKS_REPOSITORY)

    return disk_cfg


def run(args, gcloud_compute, gcloud_repos,
        email='', in_cloud_shell=False, gcloud_zone=None,
        sdk_version='UNKNOWN', datalab_version='UNKNOWN', **kwargs):
    """Implementation of the `datalab create` subcommand.

    Args:
      args: The Namespace instance returned by argparse
      gcloud_compute: Function that can be used to invoke `gcloud compute`
      gcloud_repos: Function that can be used to invoke
        `gcloud source repos`
      email: The user's email address
      in_cloud_shell: Whether or not the command is being run in the
        Google Cloud Shell
      gcloud_zone: The zone that gcloud is configured to use
      sdk_version: The version of the Cloud SDK being used
      datalab_version: The version of the datalab CLI being used
    Raises:
      subprocess.CalledProcessError: If a nested `gcloud` calls fails
    """
    if (not args.zone) and (not args.disk_name):
        args.zone = gcloud_zone
    if (not args.zone) and (not args.quiet):
        args.zone = utils.prompt_for_zone(args, gcloud_compute)
    disk_cfg = prepare(args, gcloud_compute, gcloud_repos)

    print('Creating the instance {0}'.format(args.instance))
    cmd = ['instances', 'create']
    if args.zone:
        cmd.extend(['--zone', args.zone])

    if args.subnet_name:
        cmd.extend(['--subnet', args.subnet_name])

    enable_swap = "false" if args.no_swap else "true"
    enable_backups = "false" if args.no_backups else "true"
    idle_timeout = args.idle_timeout
    console_log_level = args.log_level or "warn"
    user_email = args.for_user or email
    service_account = args.service_account or "default"
    # We have to escape the user's email before using it in the YAML template.
    escaped_email = user_email.replace("'", "''")
    initial_user_settings = json.dumps({"idleTimeoutInterval": idle_timeout}) \
        if idle_timeout else ''
    with tempfile.NamedTemporaryFile(mode='w', delete=False) \
            as startup_script_file, \
            tempfile.NamedTemporaryFile(mode='w', delete=False) \
            as user_data_file, \
            tempfile.NamedTemporaryFile(mode='w', delete=False) \
            as for_user_file, \
            tempfile.NamedTemporaryFile(mode='w', delete=False) \
            as os_login_file, \
            tempfile.NamedTemporaryFile(mode='w', delete=False) \
            as sdk_version_file, \
            tempfile.NamedTemporaryFile(mode='w', delete=False) \
            as datalab_version_file:
        try:
            startup_script_file.write(_DATALAB_STARTUP_SCRIPT.format(
                args.image_name, _DATALAB_NOTEBOOKS_REPOSITORY, enable_swap))
            startup_script_file.close()
            user_data_file.write(_DATALAB_CLOUD_CONFIG.format(
                args.image_name, enable_backups,
                console_log_level, escaped_email, initial_user_settings))
            user_data_file.close()
            for_user_file.write(user_email)
            for_user_file.close()
            os_login_file.write("FALSE")
            os_login_file.close()
            sdk_version_file.write(sdk_version)
            sdk_version_file.close()
            datalab_version_file.write(datalab_version)
            datalab_version_file.close()
            metadata_template = (
                'startup-script={0},' +
                'user-data={1},' +
                'for-user={2},' +
                'enable-oslogin={3},' +
                'created-with-sdk-version={4},' +
                'created-with-datalab-version={5}')
            metadata_from_file = (
                metadata_template.format(
                    startup_script_file.name,
                    user_data_file.name,
                    for_user_file.name,
                    os_login_file.name,
                    sdk_version_file.name,
                    datalab_version_file.name))
            cmd.extend([
                '--format=none',
                '--boot-disk-size=20GB',
                '--network', args.network_name,
                '--image-family', 'cos-stable',
                '--image-project', 'cos-cloud',
                '--machine-type', args.machine_type,
                '--metadata-from-file', metadata_from_file,
                '--tags', 'datalab',
                '--disk', disk_cfg,
                '--service-account', service_account,
                '--scopes', 'cloud-platform',
                args.instance])
            if args.no_external_ip:
                cmd.extend(['--no-address'])
            gcloud_compute(args, cmd)
        finally:
            os.remove(startup_script_file.name)
            os.remove(user_data_file.name)
            os.remove(for_user_file.name)
            os.remove(os_login_file.name)
            os.remove(sdk_version_file.name)
            os.remove(datalab_version_file.name)

    if (not args.no_connect) and (not args.for_user):
        if args.no_external_ip:
            args.internal_ip = True
        connect.connect(args, gcloud_compute, email, in_cloud_shell)
    return
