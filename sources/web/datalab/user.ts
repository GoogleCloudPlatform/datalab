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
/// <reference path="common.d.ts" />

import http = require('http');
import logging = require('./logging');
import path = require('path');
import url = require('url');

/**
 * The application settings instance.
 */
var appSettings: common.Settings;

export function init(settings: common.Settings): void {
  appSettings = settings;
}

export function getUserId(request: http.ServerRequest): string {
  if (appSettings.environment == 'local') {
    var userFromQuery = url.parse(request.url, true).query['datalab_user'];
    if (userFromQuery != null && userFromQuery.length > 0) {
      return userFromQuery;
    } else if (request.headers.cookie != null) {
      var cookies = request.headers.cookie.split(';');
      for (var i = 0; i < cookies.length; ++i) {
        var parts = cookies[i].split('=');
        if (parts.length == 2 && parts[0] == 'datalab_user' &&
            parts[1].length > 0) {
          return parts[1];
        }
      }
    }
  }
  return request.headers['x-appengine-user-email'] ||
         appSettings.instanceUser || 'anonymous';
}

/**
 * Get user directory which stores the user's notebooks.
 * the directory is root_dir + email, such as '/content/user@domain.com'.
 */
export function getUserDir(userId: string): string {
  // Forward slash '/' is allowed in email but not in file system so replace it.
  return path.join(appSettings.contentDir, userId.replace('/', '_fsfs_'));
}

export function maybeSetUserIdCookie(request: http.ServerRequest,
                                     response: http.ServerResponse): void {
  if (appSettings.environment == 'local') {
    var userFromQuery = url.parse(request.url, true).query['datalab_user'];
    if (userFromQuery != null) {
      response.setHeader('set-cookie', 'datalab_user=' + userFromQuery);
      logging.getLogger().info('set userId %s to cookie', userFromQuery);
    }
  }
}
