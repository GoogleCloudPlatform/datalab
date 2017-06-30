/*
 * Copyright 2017 Google Inc. All rights reserved.
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

/**
 * This file contains a collection of functions that call the Jupyter server APIs, and are
 * wrapped in the ApiManager class. It also defines a set of interfaces to interact with
 * these APIs to help with type checking.
 */

/**
 * Represents a cell in a Jupyter notebook.
 */
interface JupyterNotebookCellModel {
  cell_type: string,
  execution_count: number,
  metadata: object,
  outputs: Array<string>,
  source: string,
}

/**
 * Represents a Jupyter notebook model.
 */
interface JupyterNotebookModel {
  cells: Array<JupyterNotebookCellModel>,
  metadata: object,
  nbformat: number,
  nbformat_minor: number,
}

/**
 * Represents a file object as returned from Jupyter's files API.
 */
interface JupyterFile {
  content: Array<JupyterFile> | JupyterNotebookModel | string,
  created: string,
  format: string,
  last_modified: string,
  mimetype: string,
  name: string,
  path: string,
  type: string,
  writable: boolean
}

/**
 * Lists all user settings.
 */
interface UserSettings {
  startuppath: string,
  theme: string,
}

/**
 * Represents a Jupyter terminal object.
 */
interface JupyterTerminal {
  name: string,
}

/**
 * Represents an augmented version of a file obect that contains extra metadata.
 */
interface ApiFile extends JupyterFile {
  status: string
}

/**
 * Represents a session object as returned from Jupyter's sessions API.
 */
interface Session {
  id: string,
  kernel: {
    id: string,
    name: string
  },
  notebook: {
    path: string
  }
}

/** Options for _xhr call, contains the following optional fields:
 *  - method: The HTTP method to use; default is 'GET'.
 *  - errorCallback: A function to call if the XHR completes
 *      with a status other than 2xx.
 */
interface XhrOptions {
  method?: string,
  errorCallback?: Function,
  parameters?: string,
  successCode?: number,
  noCache?: boolean,
}

/**
 * Handles different API calls to the backend notebooks server and Jupyter instance.
 */
class ApiManager {

  /**
   * URL for querying files
   */
  static readonly contentApiUrl = '/api/contents';

  /**
   * URL for querying sessions
   */
  static readonly sessionsApiUrl = '/api/sessions';

  /**
   * URL for starting terminals
   */
  static readonly terminalApiUrl = '/api/terminals';

  /**
   * Returns a list of currently running sessions, each implementing the Session interface
   */
  static listSessionsAsync(): Promise<Array<Session>> {
    const xhrOptions: XhrOptions = {
      noCache: true,
    };
    return <Promise<Session[]>>ApiManager._xhrAsync(this.sessionsApiUrl, xhrOptions);
  }

  /**
   * Terminates a running session.
   */
  static shutdownSessionAsync(sessionId: string) {
    const xhrOptions: XhrOptions = {
      method: 'DELETE',
      successCode: 204,
    };
    return ApiManager._xhrAsync(ApiManager.sessionsApiUrl + '/' + sessionId, xhrOptions);
  }

  /**
   * Returns a JupyterFile object representing the file or directory requested
   * @param path string path to requested file
   */
  static getJupyterFile(path: string): Promise<JupyterFile> {
    if (path.startsWith('/')) {
      path = path.substr(1);
    }
    const xhrOptions: XhrOptions = {
      noCache: true,
    };
    return <Promise<JupyterFile>>ApiManager._xhrAsync(this.contentApiUrl + '/' + path, xhrOptions);
  }

  /**
   * Returns a list of files at the target path, each implementing the ApiFile interface.
   * Two requests are made to /api/contents and /api/sessions to get this data.
   * @param path current path to list files under
   */ 
  static listFilesAsync(path: string): Promise<Array<ApiFile>> {

    const filesPromise = ApiManager.getJupyterFile(path)
      .then((file: JupyterFile) => {
        if (file.type !== 'directory') {
          throw new Error('Can only list files in a directory. Found type: ' + file.type);
        }
        return <JupyterFile[]>file.content;
      });

    const sessionsPromise: Promise<Array<Session>> = ApiManager.listSessionsAsync();

    // Combine the return values of the two requests to supplement the files
    // array with the status value.
    return Promise.all([filesPromise, sessionsPromise])
      .then(values => {
        let files = values[0];
        const sessions = values[1];
        let runningPaths: Array<string> = [];
        sessions.forEach(session => {
          runningPaths.push(session.notebook.path);
        });
        files.forEach((file: ApiFile) => {
          file.status = runningPaths.indexOf(file.path) > -1 ? 'running' : '';
        });
        return <ApiFile[]>files;
      });
  }

  /**
   * Creates a new notebook or directory.
   * @param type string type of the created item, can be 'notebook' or 'directory'
   */
  static createNewItem(type: string, path?: string) {
    const xhrOptions: XhrOptions = {
      method: 'POST',
      successCode: 201,
      parameters: JSON.stringify({
        type: type,
        ext: 'ipynb'
      }),
    };
    let createPromise = ApiManager._xhrAsync(ApiManager.contentApiUrl, xhrOptions);

    // If a path is provided for naming the new item, request the rename, and
    // delete it if failed.
    if (path) {
      let notebookPathPlaceholder = '';
      createPromise = createPromise
        .then((notebook: JupyterFile) => {
          notebookPathPlaceholder = notebook.path;
          return ApiManager.renameItem(notebookPathPlaceholder, path);
        })
        .catch((error: string) => {
          // If the rename fails, remove the temporary item
          ApiManager.deleteItem(notebookPathPlaceholder);
          throw error;
        });
    }
    return createPromise;
  }

  /**
   * Renames an item
   * @param oldPath source path of the existing item
   * @param newPath destination path of the renamed item
   */
  static renameItem(oldPath: string, newPath: string) {
    oldPath = ApiManager.contentApiUrl + '/' + oldPath;
    const xhrOptions: XhrOptions = {
      method: 'PATCH',
      parameters: JSON.stringify({
        path: newPath
      }),
    };

    return ApiManager._xhrAsync(oldPath, xhrOptions);
  }

  /**
   * Deletes an item
   * @param path item path to delete
   */
  static deleteItem(path: string) {
    path = ApiManager.contentApiUrl + '/' + path;
    const xhrOptions: XhrOptions = {
      method: 'DELETE',
      successCode: 204,
    };

    return ApiManager._xhrAsync(path, xhrOptions);
  }

  /**
   * Gets the user settings JSON from the server.
   */
  static getUserSettings() {
    return ApiManager._xhrAsync('/_settings');
  }

  /**
   * Sets a user setting.
   * @param setting name of the setting to change.
   * @param value new setting value.
   */
  static setUserSetting(setting: string, value: string) {
    const xhrOptions: XhrOptions = {
      method: 'POST',
    };
    return ApiManager._xhrAsync('/_settings?key=' + setting + '&value=' + value, xhrOptions);
  }

  /*
   * Copies an item from source to destination. Item name collisions at the destination
   * are handled by Jupyter.
   * @param itemPath path to copied item
   * @param destinationDirectory directory to copy the item into
   */
  static copyItem(itemPath: string, destinationDirectory: string) {
    destinationDirectory = ApiManager.contentApiUrl + '/' + destinationDirectory;
    const xhrOptions: XhrOptions = {
      method: 'POST',
      successCode: 201,
      parameters: JSON.stringify({
        copy_from: itemPath
      })
    };

    return ApiManager._xhrAsync(destinationDirectory, xhrOptions);
  }

  /**
   * Initializes a terminal session.
   */
  static startTerminalAsync() {
    const xhrOptions: XhrOptions = {
      method: 'POST',
    }
    return ApiManager._xhrAsync(ApiManager.terminalApiUrl, xhrOptions);
  }

  /**
   * Returns a list of active terminal sessions.
   */
  static listTerminalsAsync() {
    return ApiManager._xhrAsync(ApiManager.terminalApiUrl);
  }

  /**
   * Sends an XMLHttpRequest to the specified URL, and parses the
   * the response text. This method returns immediately with a promise
   * that resolves with the parsed object when the request completes.
   */
  static _xhrAsync(url: string, options?: XhrOptions) {

    options = options || {};
    const method = options.method || 'GET';
    const params = options.parameters;
    const successCode = options.successCode || 200;
    const request = new XMLHttpRequest();
    const noCache = options.noCache || false;

    return new Promise((resolve, reject) => {
      request.onreadystatechange = () => {
        if (request.readyState === 4) {
          if (request.status === successCode) {
            try {
              resolve(JSON.parse(request.responseText || 'null'));
            } catch (e) {
              reject(e);
            }
          } else {
            reject(request.responseText);
          }
        }
      };

      request.open(method, url);
      if (noCache) {
        request.setRequestHeader('Cache-Control', 'no-cache');
      }
      request.send(params);
    });
  }

}
