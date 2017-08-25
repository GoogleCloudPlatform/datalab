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

/// <reference path="../../../common.d.ts" />

let userSettings: common.UserSettings;
let appSettings: common.AppSettings;

class MissingConfigUrlError extends Error {
  message = 'No configUrl value in appSettings';
}

/**
 * Handles API calls related to app/user settings, and manages a local cached copy
 * of the settings to avoid duplicate API calls.
 */
class SettingsManager {

  /**
   * Returns the user settings object, optionally after refreshing it from the backend
   * @param forceRefresh whether the settings cache should be refreshed before returning
   */
  public static getUserSettingsAsync(forceRefresh?: boolean) {
    if (!userSettings || forceRefresh === true) {
      return SettingsManager._getUserSettingsAsync()
        .then((settings: common.UserSettings) => {
          userSettings = settings;
          return userSettings;
        });
    } else {
      return Promise.resolve(userSettings);
    }
  }

  /**
   * Returns the app settings object, optionally after refreshing it from the backend
   * @param forceRefresh whether the settings cache should be refreshed before returning
   */
  public static getAppSettingsAsync(forceRefresh?: boolean) {
    if (!appSettings || forceRefresh === true) {
      return SettingsManager._getAppSettingsAsync()
        .then((settings: common.AppSettings) => {
          appSettings = settings;
          return appSettings;
        });
    } else {
      return Promise.resolve(appSettings);
    }
  }

  /**
   * Sets a user setting.
   * @param setting name of the setting to change.
   * @param value new setting value.
   */
  public static setUserSettingAsync(setting: string, value: string) {
    const xhrOptions: XhrOptions = {
      method: 'POST',
    };
    const apiManager = ApiManagerFactory.getInstance();
    const requestUrl = apiManager.getServiceUrl(ServiceId.USER_SETTINGS) +
        '?key=' + setting + '&value=' + value;
    return apiManager.sendRequestAsync(requestUrl, xhrOptions);
  }

  /**
   * Loads and executes the config file as specifed in appSettings.configUrl.
   * This sets values on window.datalab. Resolves immediately if window.datalab is already set.
   */
  public static loadConfigToWindowDatalab(): Promise<void> {
    if (window.datalab) {
      return Promise.resolve(); // Already loaded
    }
    if (window.datalab === undefined) {
      window.datalab = {};
    }
    return SettingsManager.getAppSettingsAsync()
      .then((settings: common.AppSettings) => {
        if (settings.configUrl) {
          return new Promise((resolve, reject) => {
            const configScript = document.createElement('script');
            configScript.src = settings.configUrl;
            configScript.onload = () => {
              resolve();
            };
            configScript.onerror = () => {
              reject(new Error('Failed to load config file ' + settings.configUrl));
            };
            // The config file we are loading reading the following body
            // attribute and calls split on it, so we need to set that attribute
            // to a string to avoid a runtime error when loading that file.
            if (!document.body.getAttribute('data-version-id')) {
              document.body.setAttribute('data-version-id', '');
            }
            document.head.appendChild(configScript);
          }) as Promise<void>;
        } else {
          throw new MissingConfigUrlError();
        }
      });
  }

  /**
   * Gets the user settings JSON from the server.
   */
  private static _getUserSettingsAsync() {
    const apiManager = ApiManagerFactory.getInstance();
    return apiManager.sendRequestAsync(apiManager.getServiceUrl(ServiceId.USER_SETTINGS));
  }

  /**
   * Gets the app settings JSON from the server.
   */
  private static _getAppSettingsAsync() {
    const apiManager = ApiManagerFactory.getInstance();
    return apiManager.sendRequestAsync(apiManager.getServiceUrl(ServiceId.APP_SETTINGS));
  }

}
