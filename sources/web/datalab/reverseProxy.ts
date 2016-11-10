/*
 * Copyright 2016 Google Inc. All rights reserved.
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


import http = require('http');
import httpProxy = require('http-proxy');
import logging = require('./logging');

var proxy: httpProxy.ProxyServer = httpProxy.createProxyServer(null);
var regex: any = new RegExp('\/_proxy\/([0-9]+)($|\/)');

function errorHandler(error: Error, request: http.ServerRequest, response: http.ServerResponse) {
  response.writeHead(500, 'Reverse Proxy Error.');
  response.end();
}

function getPort(url: string) {
  if (url) {
    var sr: any = regex.exec(url);
    if (sr) {
      return sr[1];
    }
  }
  return null;
}

/**
 * Get port from request. If the request should be handled by reverse proxy, returns
 * the port as a string. Othewise, returns null.
 */
export function getRequestPort(request: http.ServerRequest, path: string): string {
  var port: string = getPort(path) || getPort(request.headers.referer);
  return port;
}

/**
 * Checks if a request should be exempted from reverse proxying to the gateway
 */
function shouldSkipGateway(port: String) {
  // skip requests to 8083 for ungit
  if (port === '8083')
    return true;
  return false;
}

/**
 * Handle request by sending it to the internal http endpoint.
 */
export function handleRequest(request: http.ServerRequest,
                              response: http.ServerResponse,
                              port: String) {
  if (process.env.KG_URL && !shouldSkipGateway(port)) {
    proxy.web(request, response, { target: process.env.KG_URL });
  }
  else {
    request.url = request.url.replace(regex, '/');
    proxy.web(request, response, { target: 'http://127.0.0.1:' + port });
  }
}

/**
 * Initialize the handler.
 */
export function init() {
  proxy.on('error', errorHandler);
}
