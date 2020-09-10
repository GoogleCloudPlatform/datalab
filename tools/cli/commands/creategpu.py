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

"""Methods for implementing the `datalab beta creategpu` command."""

from __future__ import absolute_import

import json
import os
import tempfile

from . import create, connect, utils


description = ("""`{0} {1}` creates a new Datalab instance running in a Google
Compute Engine VM with a GPU.

This command also creates the 'datalab-network' network if necessary.

By default, the command creates a persistent connection to the newly
created instance. You can disable that behavior by passing in the
'--no-connect' flag.""")

_THIRD_PARTY_SOFTWARE_DIALOG = (
    """By accepting below, you will download and install the
following third-party software onto your managed GCE instances:
    NVidia GPU Driver: NVIDIA-Linux-x86_64-390.46""")

# The config for the 'cos-gpu-installer.service'
# services comes from the 'GoogleCloudPlatform/cos-gpu-installer' project
# here: https://github.com/GoogleCloudPlatform/cos-gpu-installer

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
    ExecStartPre=docker-credential-gcr configure-docker
    ExecStart=/bin/bash -c 'while [ ! -e /mnt/disks/datalab-pd/tmp ]; do \
        sleep 1; \
        done'

- path: /etc/nvidia-installer-env
  permissions: 0755
  owner: root
  content: |
    NVIDIA_DRIVER_VERSION=418.67
    COS_NVIDIA_INSTALLER_CONTAINER=gcr.io/cos-cloud/cos-gpu-installer:latest
    NVIDIA_INSTALL_DIR_HOST=/var/lib/nvidia
    NVIDIA_INSTALL_DIR_CONTAINER=/usr/local/nvidia
    ROOT_MOUNT_DIR=/root

- path: /etc/systemd/system/cos-gpu-installer.service
  permissions: 0755
  owner: root
  content: |
    [Unit]
    Description=Run the GPU driver installer container
    Requires=network-online.target gcr-online.target \
             wait-for-startup-script.service
    After=network-online.target gcr-online.target \
          wait-for-startup-script.service

    [Service]
    User=root
    Type=oneshot
    RemainAfterExit=true
    Environment="HOME=/home/datalab"
    EnvironmentFile=/etc/nvidia-installer-env
    ExecStartPre=/usr/bin/docker-credential-gcr configure-docker
    ExecStartPre=/bin/bash -c 'mkdir -p "${{NVIDIA_INSTALL_DIR_HOST}}" && \
        mount --bind "${{NVIDIA_INSTALL_DIR_HOST}}" \
        "${{NVIDIA_INSTALL_DIR_HOST}}" && \
        mount -o remount,exec "${{NVIDIA_INSTALL_DIR_HOST}}"'
    ExecStart=/usr/bin/docker run --privileged --net=host --pid=host \
        --volume \
        "${{NVIDIA_INSTALL_DIR_HOST}}":"${{NVIDIA_INSTALL_DIR_CONTAINER}}" \
        --volume /dev:/dev --volume "/":"${{ROOT_MOUNT_DIR}}" \
        --env-file /etc/nvidia-installer-env \
        "${{COS_NVIDIA_INSTALLER_CONTAINER}}"
    StandardOutput=journal+console
    StandardError=journal+console

- path: /etc/systemd/system/datalab.service
  permissions: 0644
  owner: root
  content: |
    [Unit]
    Description=datalab docker container
    Requires=network-online.target gcr-online.target \
             wait-for-startup-script.service cos-gpu-installer.service
    After=network-online.target gcr-online.target \
          wait-for-startup-script.service cos-gpu-installer.service

    [Service]
    Environment="HOME=/home/datalab"
    ExecStartPre=/usr/bin/docker-credential-gcr configure-docker
    ExecStart=/usr/bin/docker run \
       --name=datalab \
       -p '127.0.0.1:8080:8080' \
       -v /mnt/disks/datalab-pd/content:/content \
       -v /mnt/disks/datalab-pd/tmp:/tmp \
       --volume /var/lib/nvidia:/usr/local/nvidia \
       {5} \
       --device /dev/nvidia-uvm:/dev/nvidia-uvm \
       --device /dev/nvidia-uvm-tools:/dev/nvidia-uvm-tools \
       --device /dev/nvidiactl:/dev/nvidiactl \
       --env=HOME=/content \
       --env=DATALAB_ENV=GCE \
       --env=DATALAB_DEBUG=true \
       --env='DATALAB_SETTINGS_OVERRIDES={{ \
           "enableAutoGCSBackups": {1}, \
           "consoleLogLevel": "{2}" \
       }}' \
       --env='DATALAB_GIT_AUTHOR={3}' \
       --env='DATALAB_INITIAL_USER_SETTINGS={4}' \
       {0} -c /datalab/run.sh
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
- systemctl enable cos-gpu-installer.service
- systemctl start cos-gpu-installer.service
- systemctl start datalab.service
- systemctl start logger.service
"""


def flags(parser):
    """Add command line flags for the `create` subcommand.

    Args:
      parser: The argparse parser to which to add the flags.
    """
    create.flags(parser)
    parser.set_defaults(image_name='gcr.io/cloud-datalab/datalab-gpu:latest')

    parser.add_argument(
        '--accelerator-type',
        dest='accelerator_type',
        default='nvidia-tesla-k80',
        help=(
            'the accelerator type of the instance.'
            '\n\n'
            'Datalab currently only supports nvidia-tesla-k80.'
            '\n\n'
            'If not specified, the default type is none.'))

    parser.add_argument(
        '--accelerator-count',
        dest='accelerator_count',
        type=int,
        default=1,
        help=(
            'the accelerator count of the instance, used if '
            'accelerator-type is specified.'
            '\n\n'
            'If not specified, the default type is 1.'))
    return


def run(args, gcloud_beta_compute, gcloud_repos,
        email='', in_cloud_shell=False, gcloud_zone=None,
        sdk_version='UNKNOWN', datalab_version='UNKNOWN', **kwargs):
    """Implementation of the `datalab create` subcommand.

    Args:
      args: The Namespace instance returned by argparse
      gcloud_beta_compute: Function that can be used to invoke `gcloud compute`
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
    if not utils.prompt_for_confirmation(
            args=args,
            message=_THIRD_PARTY_SOFTWARE_DIALOG,
            question='Do you accept',
            accept_by_default=False):
        print('Installation not accepted; Exiting.')
        return

    if (not args.zone) and (not args.disk_name):
        args.zone = gcloud_zone
    if (not args.zone) and (not args.quiet):
        args.zone = utils.prompt_for_zone(args, gcloud_beta_compute)
    disk_cfg = create.prepare(args, gcloud_beta_compute, gcloud_repos)

    print('Creating the instance {0}'.format(args.instance))
    print('\n\nDue to GPU Driver installation, please note that '
          'Datalab GPU instances take significantly longer to '
          'startup compared to non-GPU instances.')
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
    # We need to map all of the GPUs.
    device_mapping = ""
    for i in range(min(args.accelerator_count, 32)):
        device_mapping += (" --device /dev/nvidia" + str(i) +
                           ":/dev/nvidia" + str(i) + " ")
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
            startup_script_file.write(create._DATALAB_STARTUP_SCRIPT.format(
                args.image_name, create._DATALAB_NOTEBOOKS_REPOSITORY,
                enable_swap))
            startup_script_file.close()
            user_data_file.write(_DATALAB_CLOUD_CONFIG.format(
                args.image_name, enable_backups,
                console_log_level, escaped_email, initial_user_settings,
                device_mapping))
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
                '--accelerator',
                'type=' + args.accelerator_type + ',count='
                + str(args.accelerator_count),
                '--maintenance-policy', 'TERMINATE', '--restart-on-failure',
                '--metadata-from-file', metadata_from_file,
                '--tags', 'datalab',
                '--disk', disk_cfg,
                '--service-account', service_account,
                '--scopes', 'cloud-platform',
                args.instance])
            if args.no_external_ip:
                cmd.extend(['--no-address'])
            gcloud_beta_compute(args, cmd)
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
        connect.connect(args, gcloud_beta_compute, email, in_cloud_shell)
    return
