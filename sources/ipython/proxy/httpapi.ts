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

/// <reference path="../../../externs/ts/node/node.d.ts" />

import common = require('./common');
import http = require('http');
import https = require('https');
import qs = require('querystring');
import util = require('util');

var HTTP_PORT = 80;
var HTTPS_PORT = 443;

export function get(host: string, path: string, args: common.Map<any>,
                    token: string, headers: common.Map<string>,
                    callback: common.Callback<any>) {
  request(host, HTTP_PORT, 'GET', path, args, null, token, headers, callback);
}

export function gets(host: string, path: string, args: common.Map<any>,
                     token: string, headers: common.Map<string>,
                     callback: common.Callback<any>) {
  request(host, HTTPS_PORT, 'GET', path, args, null, token, headers, callback);
}

export function post(host: string, path: string, args: common.Map<any>, data: Object,
                     token: string, headers: common.Map<string>,
                     callback: common.Callback<any>) {
  request(host, HTTP_PORT, 'POST', path, args, null, token, headers, callback);
}

export function posts(host: string, path: string, args: common.Map<any>, data: Object,
                      token: string, headers: common.Map<string>,
                      callback: common.Callback<any>) {
  request(host, HTTPS_PORT, 'POST', path, args, null, token, headers, callback);
}

function request(host: string, port: number, method: string, path: string,
                 args: common.Map<any>, data: Object,
                 token: string, headers: common.Map<string>,
                 callback: common.Callback<any>) {
  if (args) {
    path = '?' + qs.stringify(args);
  }

  headers = headers || {};

  var requestBody = '';
  if (data) {
    requestBody = JSON.stringify(data);

    headers['Content-Type'] = 'application/json';
    headers['Content-Length'] = requestBody.length.toString();
  }
  if (token) {
    headers['Authorization'] = 'Bearer ' + token
  }

  var options: any = {
    method: method,
    hostname: host,
    port: port,
    path: path,
    headers: headers
  };

  function requestCallback(response: http.ClientResponse) {
    if (response.statusCode != 200) {
      var error = util.format('Failed %s %s%s: %d', method, host, path, response.statusCode);
      callback(new Error(error), null);
    }

    response.setEncoding('utf8');

    var data: string = '';
    response.on('data', function(chunk: string) {
      data += chunk;
    });
    response.on('end', function() {
      callback(null, JSON.parse(data));
    });
  }

  var request: http.ClientRequest;
  if (port == HTTP_PORT) {
    request = http.request(options, requestCallback);
  }
  else {
    request = https.request(options, requestCallback);
  }

  request.on('error', function(error: Error) {
    callback(error, null);
  });

  if (requestBody) {
    request.write(requestBody);
  }
  request.end();
}
