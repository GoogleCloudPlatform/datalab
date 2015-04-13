/*
 * Copyright 2014 Google Inc. All rights reserved.
 *
 * Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except
 * in compliance with the License. You may obtain a copy of the License at
 *
 * http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software distributed under the License
 * is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
 * or implied. See the License for the specific language governing permissions and limitations under
 * the License.
 */


/// <reference path="../../../../externs/ts/express/express.d.ts" />
/// <reference path="../../../../externs/ts/node/node.d.ts" />
/// <reference path="../../../../externs/ts/node/nomnom.d.ts" />
/// <reference path="../../../../externs/ts/node/socket.io.d.ts" />
import config = require('./app/config');
import express = require('express');
import http = require('http');
import msgproc = require('./app/sessions/messageprocessors');
import nomnom = require('nomnom');
import sessions = require('./app/sessions/manager');
import socketio = require('socket.io');


/**
 * Configure and parse command line arguments with defaults.
 */
var options = nomnom.option(
  'notebookPath', {
    abbr: 'n',
    full: 'notebook-path',
    help: 'notebook loading root path',
    default: './notebooks'
  }
).parse();

/**
 * Main entry point for the server.
 *
 * Starts an HTTP server on port that can be overridden by environment variable defined in
 * app.Settings (see: app/config)
 *
 * Initializes the messaging system to listen for incoming user connections via socket.io
 */
export function start (settings: app.Settings, apiRouter: express.Router) {
  var expressApp = express();
  expressApp.use('/api', apiRouter);
  expressApp.use(express.static(__dirname + '/static'));

  var httpServer = http.createServer(expressApp);

  console.log("Starting HTTP server on port " + settings.httpPort);
  httpServer.listen(settings.httpPort);

  var sessionManager = new sessions.SessionManager(
    config.getKernelManager(),
    msgproc.getMessageProcessors(),
    config.getNotebookStorage(),
    socketio.listen(httpServer)
  );
}

// Ensure that the notebook storage system is fully initialized
config.initStorage(options.notebookPath);

// Start the DataLab server running
start(config.getSettings(), config.getApiRouter());
