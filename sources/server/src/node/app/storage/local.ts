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


import fs = require('fs');
import pathlib = require('path');


/**
 * Manages storage operations backed by a local file system
 */
export class LocalFileSystemStorage implements app.IStorage {

  _storageRootPath: string;

  constructor(storageRootPath: string) {
    this._storageRootPath = storageRootPath;
  }

  /**
   * Synchronously opens and reads from the file at the given path
   *
   * Returns undefined if no file exists at the given path
   */
  read(path: string, callback: app.Callback<string>) {
    fs.readFile(this._getAbsolutePath(path), { encoding: 'utf8' }, (error: any, data: string) => {
      if (error) {
        // No file exists at the given path, just leave data undefined for caller to handle
        callback(error);
      } else {
        callback(null, data);
      }
    });
  }

  /**
   * Asynchronously writes the given data string to the file referenced by the given path
   */
  write(path: string, data: string, callback: app.ErrorCallback) {
    fs.writeFile(this._getAbsolutePath(path), data, (error) => {
      if (error) {
        callback(error, false);
      } else {
        callback(null, true);
      }
    });
  }

  /**
   * Synchronously deletes the file at the given path
   *
   * Returns boolean to indicate success of the operation.
   * TODO(bryantd): make this an idempotent operation
   */
  delete(path: string, callback: app.ErrorCallback) {
    fs.unlink(path, callback);
  }

  _getAbsolutePath (path: string) {
    return pathlib.join(this._storageRootPath, path);
  }

  _handleError (error: any) {
    if (error) {
      console.log('ERROR during FileIO', error);
      // TODO(bryantd): eventually add some nicer error handling here to surface persistence
      // issues to the server/user
    } else {
      // Success
      //
      // TODO(bryantd): eventually it would be nice to surface an ack that a file has been
      // persisted successfully, along with the persisted-at timestamp, so that it can be
      // surfaced in the UI as (Last saved at <timestamp>)
    }
  }

}
