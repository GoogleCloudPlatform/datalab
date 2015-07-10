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

# Publishes the built docker image to the registry

if [ "$#" != "1" ]; then
  echo "Usage: $0 <tag>"
  exit 1
fi

# Grant read permissions to all users on all objects added in the GCS bucket
# that holds docker image files by ACLing the bucket and setting the default
# for any new items added
gsutil acl ch -g all:R gs://artifacts.cloud-datalab.appspot.com
gsutil defacl ch -u all:R gs://artifacts.cloud-datalab.appspot.com

LOCAL_IMAGE=gcp-datalab
REG_IMAGE=gcr.io/cloud_datalab/gcp-datalab:$1

echo "Publishing $LOCAL_IMAGE to $REG_IMAGE ..."
docker tag -f $LOCAL_IMAGE $REG_IMAGE
gcloud docker push $REG_IMAGE
