#!/bin/bash -e
# Copyright 2015 Google Inc. All rights reserved.
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

# Runs the Google Cloud DataLab docker image with vcrpy and urllib
# added.
#

CONTENT=$HOME
ENTRYPOINT="/datalab/run.sh"
if [ "$1" != "" ]; then
  if [ "$1" != "shell" ]; then
    CONTENT=$1
    shift
  fi
  if [ "$1" == "shell" ]; then
    ENTRYPOINT="/bin/bash"
  fi
fi

# On linux docker runs directly on host machine, so bind to 127.0.0.1 only
# to avoid it being accessible from network.
# On other platform, it needs to bind to all ip addresses so VirtualBox can
# access it. Users need to make sure in their VirtualBox port forwarding
# settings only 127.0.0.1 is bound.
if [ "$OSTYPE" = "linux"* ]; then
  PORTMAP="127.0.0.1:8081:8080"
else
  PORTMAP="8081:8080"
fi

mkdir -p $CONTENT/datalab/.config/eula
docker run -i -d --entrypoint=$ENTRYPOINT \
  -p $PORTMAP \
  -v $CONTENT:/content \
  -e "PROJECT_ID=$PROJECT_ID" \
  -e "DATALAB_ENV=local" \
  -e "PROXY_WEB_SOCKETS=true" \
  -t datalab-test
