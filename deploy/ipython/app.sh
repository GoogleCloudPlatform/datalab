#!/bin/sh
# Copyright 2014 Google Inc. All rights reserved.
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

function show_help() {
  echo "Usage: app.sh <command> <cloud project> [<docker registry>]"
  echo "                        [<module>] [<version>]"
  echo
  echo "  command        : deploy | run "
  echo "  cloud project  : the cloud project to deploy to."
  echo "  docker registry: the registry containing the docker image to deploy."
  echo "  module         : the managed VM module to deploy to."
  echo "  version        : the managed VM module version to deploy to."
  echo
}

# Starts an IPython container as a managed VM application.

if [ "$#" -lt 1 ]; then
  show_help
  exit
fi

# Fault-tolerant cleanup
function cleanup {
  rm -f Dockerfile
  rm -rf gcloud
  rm app.js
  rm app.yaml
}
trap cleanup EXIT


# Variables
IMAGE_NAME="gcp-ipython"
CLOUD_PROJECT=$2
APP_MODULE=$4
APP_VERSION=$5


if [ "$3" = "" ]; then
  DOCKER_IMAGE=$IMAGE_NAME
else
  DOCKER_IMAGE="$3/$IMAGE_NAME"
fi

if [ "$APP_MODULE" = "" ]; then
  APP_MODULE=ipython
fi
if [ "$APP_VERSION" = "" ]; then
  APP_VERSION=preview1
fi

if [ "$CLOUD_PROJECT" != "" ]; then
  echo "Project: $CLOUD_PROJECT"
fi
echo "Module : $APP_MODULE"
echo "Version: $APP_VERSION"
echo "Image  : $DOCKER_IMAGE"


# Generate supporting files

cat > Dockerfile << EOF1
FROM $DOCKER_IMAGE

EOF1

cat > app.yaml << EOF2
api_version: 1
module: $APP_MODULE
version: $APP_VERSION

vm: true
manual_scaling:
  instances: 1

runtime: custom
threadsafe: true

handlers:
- url: /.*
  script: app.js
  login: admin
  secure: always

EOF2

cat > app.js << EOF3
// Stub script referenced by app.yaml
//

EOF3

# Build the local docker image
docker build -t gcp-ipython-instance .

# NOTE: Might need to run this once, to use gcloud to deploy managed VM
#       applications.
# docker pull google/docker-registry

# Copy a snapshot of gcloud configuration.
# -L in case user is using linked gcloud
cp -Lr ~/.config/gcloud gcloud

# Deploy to the cloud (as a managed VM application)
if [ "$1" == "deploy" ]; then
  if [ "$CLOUD_PROJECT" == "" ]; then
    show_help
    exit
  fi
  gcloud preview app deploy . --force \
    --project $CLOUD_PROJECT \
    --server preview.appengine.google.com
else
  if [ "$CLOUD_PROJECT" == "" ]; then
    gcloud preview app run .
  else
    gcloud preview app run . \
      --project $CLOUD_PROJECT
  fi
fi
