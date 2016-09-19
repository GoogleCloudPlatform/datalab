/*
 * Copyright 2015 Google Inc. All rights reserved.
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

/// <reference path="../../../externs/ts/node/node.d.ts" />
/// <reference path="../../../externs/ts/node/node-http-proxy.d.ts" />
/// <reference path="common.d.ts" />

import fs = require('fs');
import http = require('http');
import logging = require('./logging');
import path = require('path');
import settings = require('./settings');
import url = require('url');
import userManager = require('./userManager');

var JUPYTER_DIR = '/usr/local/lib/python2.7/dist-packages/notebook';
var CONTENT_TYPES: common.Map<string> = {
  '.js': 'text/javascript',
  '.css': 'text/css',
  '.png': 'image/png',
  '.ico': 'image/x-icon',
  '.txt': 'text/plain',
  '.html': 'text/html'
};
var CUSTOM_THEME_FILE = 'custom.css';
var DEFAULT_THEME_FILE = 'light.css';

var contentCache: common.Map<Buffer> = {};
var watchedDynamicContent: common.Map<boolean> = {};

function getContent(filePath: string, cb: common.Callback<Buffer>, isDynamic: boolean = false): void {
  var content = contentCache[filePath];
  if (content != null) {
    process.nextTick(function() {
      cb(null, content);
    });
  }
  else {
    fs.readFile(filePath, function(error, content) {
      if (error) {
        cb(error, null);
      }
      else {
        if (isDynamic && !watchedDynamicContent[filePath]) {
          fs.watch(filePath, function(eventType, filename) {
            logging.getLogger().info('Clearing cache for updated file: %s', filePath);
            contentCache[filePath] = null;
            if (eventType == 'rename') {
              watchedDynamicContent[filePath] = false;
            }
          });
          watchedDynamicContent[filePath] = true;
        }
        contentCache[filePath] = content;
        cb(null, content);
      }
    });
  }
}

/**
 * Sends a static file as the response.
 * @param filePath the full path of the static file to send.
 * @param response the out-going response associated with the current HTTP request.
 * @param alternatePath the path to a static Datalab file to send if the given file is missing.
 * @param isDynamic indication of whether or not the file contents might change.
 */
function sendFile(filePath: string, response: http.ServerResponse,
                  alternatePath: string = "", isDynamic: boolean = false) {
  var extension = path.extname(filePath);
  var contentType = CONTENT_TYPES[extension.toLowerCase()] || 'application/octet-stream';

  getContent(filePath, function(error, content) {
    if (error) {
      logging.getLogger().error(error, 'Unable to send static file: %s', filePath);

      if (alternatePath != "") {
        sendDataLabFile(alternatePath, response);
      } else {
        response.writeHead(500);
        response.end();
      }
    }
    else {
      response.writeHead(200, { 'Content-Type': contentType });
      response.end(content);
    }
  }, isDynamic);
}

/**
 * Sends a static file located within the DataLab static directory.
 * @param filePath the relative file path of the static file to send.
 * @param response the out-going response associated with the current HTTP request.
 */
function sendDataLabFile(filePath: string, response: http.ServerResponse) {
  sendFile(path.join(__dirname, 'static', filePath), response);
}

/**
 * Sends a static file located within the Jupyter install.
 * @param filePath the relative file path of the static file within the Jupyter directory to send.
 * @param response the out-going response associated with the current HTTP request.
 */
function sendJupyterFile(relativePath: string, response: http.ServerResponse) {
  var filePath = path.join(JUPYTER_DIR, relativePath);
  fs.stat(filePath, function(e, stats) {
    if (e || !stats.isFile()) {
      response.writeHead(404);
      response.end();
    }

    sendFile(filePath, response);
  });
}

/**
 * Checks whether a requested static file exists in DataLab.
 * @param filePath the relative path of the file.
 */
function datalabFileExists(filePath: string) {
    return fs.existsSync(path.join(__dirname, 'static', filePath));
}

/**
 * Sends a static 'custom.css' file located within the user's config directory.
 *
 * @param userId the ID of the current user.
 * @param response the out-going response associated with the current HTTP request.
 */
function sendUserCustomTheme(userId: string, response: http.ServerResponse): void {
    var customThemePath = path.join(settings.getUserConfigDir(userId), CUSTOM_THEME_FILE);
    sendFile(customThemePath, response, DEFAULT_THEME_FILE, true);
}

/**
 * Implements static file handling.
 * @param request the incoming file request.
 * @param response the outgoing file response.
 */
function requestHandler(request: http.ServerRequest, response: http.ServerResponse): void {
  var path = url.parse(request.url).pathname;

  if (path.lastIndexOf('/favicon.ico') > 0) {
    sendDataLabFile('datalab.ico', response);
  }
  else if (path.lastIndexOf('/logo.png') > 0) {
    sendDataLabFile('datalab.png', response);
  }
  else if (path.lastIndexOf('/about.txt') > 0) {
    sendDataLabFile('datalab.txt', response);
  }
  else if (path.lastIndexOf('/reporting.html') > 0) {
    sendDataLabFile('reporting.html', response);
  }
  else if (path.lastIndexOf('/datalab.css') > 0) {
    sendDataLabFile('datalab.css', response);
  }
  else if (path.lastIndexOf('/appbar.html') > 0) {
    sendDataLabFile('appbar.html', response);
  }
  else if (path.indexOf('/codemirror/mode/') > 0) {
    var split = path.lastIndexOf('/');
    var newPath = 'codemirror/mode/' + path.substring(split + 1);
    if (datalabFileExists(newPath)) {
      sendDataLabFile(newPath, response);
    } else {
      sendJupyterFile(path.substr(1), response);
    }
  }
  else if (path.lastIndexOf('/custom.js') >= 0) {
    // NOTE: Uncomment to use external content mapped into the container.
    //       This is only useful when actively developing the content itself.
    // var text = fs.readFileSync('/sources/datalab/static/datalab.js', { encoding: 'utf8' });
    // response.writeHead(200, { 'Content-Type': 'text/javascript' });
    // response.end(text);

    sendDataLabFile('datalab.js', response);
  }
  else if (path.lastIndexOf('/custom.css') > 0) {
    var userId: string = userManager.getUserId(request);
    var userSettings: common.Map<string> = settings.loadUserSettings(userId);
    if ('theme' in userSettings) {
      var theme: string = userSettings['theme'];
      if (theme == 'custom') {
        sendUserCustomTheme(userId, response);
      } else if (theme == 'dark') {
        sendDataLabFile('dark.css', response);
      } else {
        sendDataLabFile('light.css', response);
      }
    } else {
      sendDataLabFile(DEFAULT_THEME_FILE, response);
    }
  }
  else if ((path.indexOf('/static/extensions/') == 0) ||
           (path.indexOf('/static/require/') == 0)) {
    // Strip off the leading '/static/' to turn path into a relative path within the
    // static directory.
    sendDataLabFile(path.substr(8), response);
  } else {
    // Strip off the leading slash to turn path into a relative file path
    sendJupyterFile(path.substr(1), response);
  }
}

/**
 * Creates the static content request handler.
 * @param settings configuration settings for the application.
 * @returns the request handler to handle static requests.
 */
export function createHandler(settings: common.Settings): http.RequestHandler {
  return requestHandler;
}
