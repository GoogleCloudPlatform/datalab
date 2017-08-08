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

declare function assert(condition: boolean): null;
declare function assert(condition: boolean, message: string): null;

/// <reference path="../node_modules/@types/mocha/index.d.ts" />
/// <reference path="../node_modules/@types/chai/index.d.ts" />

describe('SettingsManager', () => {

  describe('loadConfigToWindowDatalab', () => {
    const initialWindowDatalab = window.datalab;
    beforeEach(() => {
      window.datalab = initialWindowDatalab;  // Reset to undefined
    });

    it('resolves immediately if window.datalab is already set', async () => {
      window.datalab = { foo: 'bar' };
      SettingsManager.getAppSettingsAsync = () => {
        return Promise.reject(new Error('should not be loading settings'));
      };
      await SettingsManager.loadConfigToWindowDatalab();
    });

    it('rejects the promise if there is no configUrl field', (done: () => void) => {
      SettingsManager.getAppSettingsAsync = () => {
        return Promise.resolve({});
      };
      SettingsManager.loadConfigToWindowDatalab()
        .then(() => {
          assert(false, 'should have failed');
        }, () => {
          done();
        });
    });

    it('loads and appends the file specified by appSettings.configUrl', (done: () => void) => {
      let documentHeadCalled = false;
      const fakeAppSettings = {
        configUrl: '/fake/config/url/path'
      };
      SettingsManager.getAppSettingsAsync = () => {
        return Promise.resolve(fakeAppSettings);
      };
      document.head.appendChild = (element: HTMLScriptElement) => {
        assert(element.src.endsWith('/fake/config/url/path'), 'script element should have the expected src');
        documentHeadCalled = true;
        const fakeEvent = document.createEvent("Event");
        element.onload(fakeEvent); // Resolve our promise
      };
      assert(window.datalab === undefined, 'window.datalab should not be defined');
      SettingsManager.loadConfigToWindowDatalab()
        .then(() => {
          assert(documentHeadCalled, 'asserts in mock document.head.appendChild should run');
          done();
        });
      });
  });
});
