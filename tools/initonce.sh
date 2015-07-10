#!/bin/sh

# Script to initialize a dev workstation. Installs required packages/tools.

# Check for local metadata service host configuration.
if [[ -n $(grep metadata /etc/hosts) ]]; then
    echo "Metadata host names configured."
else
    echo "Add the following to your /etc/hosts file to support running the local metadata service"
    echo "127.0.0.1   metadata.google.internal"
    echo "127.0.0.1   metadata"
fi

# Python package manager installation
# This is the approach recommended by PyPI
pip_dir='/tmp/pip-install';
script_path=${pip_dir}/git-pip.py;
if which pip >/dev/null; then
  echo "Installing pip...";
  mkdir -p $pip_dir &&
  curl https://bootstrap.pypa.io/get-pip.py > ${script_path} &&
  python ${script_path};
fi

# Python Linter (http://www.pylint.org)
pip install pylint

# Node.js check (DataLab server)
if which node >/dev/null; then
  echo "NodeJS installed"
else
  echo "Please install NodeJS 0.10.x: http://nodejs.org/download"
fi

# TypeScript compiler (DataLab server)
if which npm >/dev/null; then
  npm install -g typescript
else
  echo "Please install NodeJS and then re-run this script to install the TypeScript compiler."
fi

# Jasmine test runner for DataLab server-side tests
if which npm >/dev/null; then
  npm install -g jasmine-node
else
  echo "Please install NodeJS and then re-run this script to install the Jasmine NodeJS test runner."
fi

# Karma test runner for DataLab client-side tests
if which npm >/dev/null; then
  npm install -g karma
else
  echo "Please install NodeJS and then re-run this script to install the Karma test runner."
fi
