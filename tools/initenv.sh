#!/bin/sh

# This script initializes an dev prompt with the required environment variables
# and any other environment customizations.

# This indicates local dev environment. When running inside docker, this
# variable will be set to docker.
export DATALAB_ENV=dev

# Export a variable corresponding to the root of the repository
SCRIPT=$0
if [ "$SCRIPT" == "-bash" ]; then
  SCRIPT=${BASH_SOURCE[0]}
fi
export REPO_DIR=$(git rev-parse --show-toplevel)

# These control where the local emulation of the GCE metadata service exists.
export METADATA_HOST=localhost
export METADATA_PORT=8089

# Turn off python's default behavior of generating .pyc files, so that we don't
# end up picking up stale code when running samples or tests during development.
export PYTHONDONTWRITEBYTECODE=1

# Add this tools directory to the path
export PATH=$PATH:$REPO_DIR/tools

# Add aliases
alias pylint='pylint --rcfile=$REPO_DIR/tools/pylint.rc'

# Add all common presubmit hooks
ln -sf $REPO_DIR/tools/githooks/* $REPO_DIR/.git/hooks/

