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

/// <reference path="../datalab-notification/datalab-notification.ts" />

/**
 * Shell element for Datalab.
 * It contains a <datalab-toolbar> element at the top, a <datalab-sidebar>
 * element beneath that to the left, and a paged view to switch between
 * different pages. It holds references to the different datalab page
 * elements, and uses a local router element to switch between
 * these according to the current page location.
 * All pages referenced by this element should be named following the
 * convention `datalab-element/datalab-element.html`.
 */
class DatalabAppElement extends Polymer.Element {

  /**
   * Current displayed page name
   */
  public page: string;

  /**
   * Pattern for extracting current pathname component. This is matched
   * against current location to extract the page name.
   */
  public rootPattern: string;

  /**
   * Current matching result from the window.location against the
   * root pattern. This gets re-evaluated every time the current page
   * changes, and can be used to get the current active page's name.
   */
  public routeData: object;

  private _boundResizeHandler: EventListenerObject;

  constructor() {
    super();

    // Set the pattern once to be the current document pathname.
    this.rootPattern = (new URL(this.rootPath)).pathname;

    this._boundResizeHandler = this._resizeHandler.bind(this);
    window.addEventListener('resize', this._boundResizeHandler, true);

    const apiManager = ApiManagerFactory.getInstance();

    apiManager.disconnectedHandler = () => {
      this.dispatchEvent(new NotificationEvent('Failed to connect to the server.',
                                               true /* show */,
                                               true /* sticky */));
    };

    apiManager.connectedHandler = () => {
      this.dispatchEvent(new NotificationEvent('', false /* show */));
    };
  }

  static get is() { return 'datalab-app'; }

  static get properties() {
    return {
      page: {
        observer: '_pageChanged',
        type: String,
        value: 'files',
      },
      rootPattern: String,
      routeData: Object,
    };
  }

  static get observers() {
    return [
      // We need a complex observer for changes to the routeData
      // object's page property.
      '_routePageChanged(routeData.page)',
    ];
  }

  ready() {
    super.ready();

    window.addEventListener('focus', () => this._focusHandler());
  }

  /**
   * Called when the element is detached from the DOM. Cleans up event listeners.
   */
  disconnectedCallback() {
    if (this._boundResizeHandler) {
      window.removeEventListener('resize', this._boundResizeHandler);
    }
  }

  /**
   * On changes to the current route, explicitly sets the page property
   * so it can be used by other elements.
   */
  _routePageChanged(page: string) {
    // Defaults to the files view
    this.page = page || 'files';
  }

  /**
   * On changes to the page property, resolves the new page's uri, and
   * tells Polymer to load it.
   * We do this to lazy load pages as the user clicks them instead of letting
   * the browser pre-load all the pages on the first request.
   */
  _pageChanged(newPage: string, oldPage: string) {
    // Build the path using the page name as suffix for directory
    // and file names.
    const subpath = 'datalab-' + newPage;
    const resolvedPageUrl = this.resolveUrl('../' + subpath + '/' + subpath + '.html');
    Polymer.importHref(resolvedPageUrl, undefined, undefined, true);

    const newElement = this._getPageElement(newPage);
    const oldElement = this._getPageElement(oldPage);

    // Call proper event handlers on changed pages.
    // TODO: Explore making all datalab pages extend a custom element that has
    // these event handlers defined to keep things consistent and get rid of the checks.
    if (newElement) {
      if (newElement._focusHandler) {
        newElement._focusHandler();
      }
      if (newElement._resizeHandler) {
        newElement._resizeHandler();
      }
    }
    if (oldElement && oldElement._blurHandler) {
      oldElement._blurHandler();
    }

  }

  /**
   * Given a page name, returns its HTML element.
   * @param pageName name of the page whose element to return
   */
  _getPageElement(pageName: string) {
    const elName = 'datalab-' + pageName;
    return this.$.pages.items.find((element: HTMLElement) => element.localName === elName);
  }

  /**
   * If the selected page has a resize handler, calls it.
   */
  _resizeHandler() {
    const selectedPage = this.$.pages.selectedItem;
    if (selectedPage && selectedPage._resizeHandler) {
      selectedPage._resizeHandler();
    }
  }

  /**
   * If the selected page has a focus handler, calls it.
   */
  _focusHandler() {
    const selectedPage = this.$.pages.selectedItem;
    if (selectedPage && selectedPage._focusHandler) {
      selectedPage._focusHandler();
    }
  }

}

customElements.define(DatalabAppElement.is, DatalabAppElement);
