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

# Builds all components.

function install_node() {
  echo "Installing NodeJS"

  mkdir -p /tools/node
  wget -nv https://nodejs.org/dist/v6.10.0/node-v6.10.0-linux-x64.tar.gz -O node.tar.gz
  tar xzf node.tar.gz -C /tools/node --strip-components=1
  rm node.tar.gz
  export "PATH=${PATH}:/tools/node/bin"
}

function install_typescript() {
  npm -h >/dev/null 2>&1 || install_node

  echo "Installing Typescript"
  /tools/node/bin/npm install -g typescript
}

function install_prereqs() {
  tsc -h >/dev/null 2>&1  || install_typescript
  rsync -h >/dev/null 2>&1  || apt-get install -y -qq rsync
  source ./tools/initenv.sh
}

pushd ./
cd $(dirname "${BASH_SOURCE[0]}")/../
install_prereqs
popd

SRC_PATHS=(
  "web"
)

BUILD_DIR=$REPO_DIR/build
LOG_FILE=$BUILD_DIR/build.log

rm -rf $BUILD_DIR
mkdir -p $BUILD_DIR

for SRC in "${SRC_PATHS[@]}"
do
  echo "Building $SRC ... " | tee -a $LOG_FILE

  SRC_DIR=$REPO_DIR/sources/$SRC
  pushd $SRC_DIR >> /dev/null

  ./build.sh >> $LOG_FILE 2>&1

  if [ "$?" -ne "0" ]; then
    echo "failed" | tee -a $LOG_FILE
    echo "Build aborted." | tee -a $LOG_FILE
    exit 1
  else
    echo "succeeded" | tee -a $LOG_FILE
  fi

  popd >> /dev/null
  echo | tee -a $LOG_FILE
done

echo "Build completed." | tee -a $LOG_FILE
