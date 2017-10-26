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
 * Options for opening a delete dialog.
 */
interface DeleteDialogOptions extends BaseDialogOptions {
  deletedList: ItemListRow[];
}

/**
 * Delete Dialog element for Datalab, extends the Base dialog element.
 * This element is a modal dialog that presents the user with list of items to
 * be deleted.
 */
class DeleteDialogElement extends BaseDialogElement {

  private static _memoizedTemplate: PolymerTemplate;

  /**
   * List of items to be deleted
   */
  public deletedList: ItemListRow[];

  static get is() { return 'input-dialog'; }

  static get properties() {
    return Object.assign(super.properties, {
      deletedList: Array,
    });
  }

  open() {
    super.open();

    // Wait for the dialog to open, then set its items.
    this.$.theDialog.addEventListener('iron-overlay-opened', () => {
      const listElement = this.$.list as ItemListElement;
      listElement.rows = this.deletedList;
    });
  }

  /**
   * This template is calculated once in run time based on the template of  the
   * super class, then saved in a local variable for memoization.
   * See https://www.polymer-project.org/2.0/docs/devguide/dom-template#inherited-templates
   */
  static get template() {
    if (!this._memoizedTemplate) {
      this._memoizedTemplate = Utils.stampInBaseTemplate(this.is, super.is, '#body');
    }
    return this._memoizedTemplate;
  }

}

customElements.define(InputDialogElement.is, InputDialogElement);
