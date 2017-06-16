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

class InputDialogElement extends Polymer.Element {

  public title: string;
  public body: string;
  public withInput: boolean;
  public inputLabel: string;
  public inputValue: string;
  public okTitle: string;
  public cancelTitle: string;

  private _closeCallback: Function;
  private _inputTarget: object;

  static get is() { return "input-dialog"; }

  static get properties() {
    return {
      title: {
        type: String,
        value: '',
      },
      body: {
        type: String,
        value: '',
      },
      withInput: {
        type: Boolean,
        value: false,
      },
      inputLabel: {
        type: String,
        value: '',
      },
      inputValue: {
        type: String,
        value: '',
      },
      okTitle: {
        type: String,
        value: 'Ok',
      },
      cancelTitle: {
        type: String,
        value: 'Cancel'
      },
      _inputTarget: {
        type: Object,
      },
    }
  }

  ready() {
    super.ready();
    this._inputTarget = this.$.inputBox;
  }

  open() {
    const self = this;
    if (this.withInput && this.inputValue) {
      this.$.theDialog.addEventListener('iron-overlay-opened', function() {
        const inputElement = self.$.inputBox.$.nativeInput;
        inputElement.focus();
        inputElement.selectionStart = 0;
        inputElement.selectionEnd = self.inputValue.lastIndexOf('.');
      });
    }
    this.$.theDialog.open();
  }

  openAndWaitAsync(callback: Function) {
    if (callback) {
      this._closeCallback = callback;
    }
    this.open();
  }

  _dialogClosed() {
    if (this._closeCallback) {
      this._closeCallback({
        confirmed: this.$.theDialog.closingReason.confirmed,
        canceled: this.$.theDialog.closingReason.canceled,
        userInput: this.withInput ? this.$.inputBox.value : undefined,
      });
    }
  }

  _onEnter() {
    this.$.theDialog.close();
  }

}

customElements.define(InputDialogElement.is, InputDialogElement);
