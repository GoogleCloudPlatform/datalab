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
/// <reference path="../../node_modules/@types/codemirror/index.d.ts" />

/**
 * Editor element for Datalab.
 * Contains a <datalab-toolbar> element at the top, and a full screen editor
 * that uses CodeMirror.
 */
class DatalabEditorElement extends Polymer.Element {

  /**
   * FileId object for the file to load in the editor.
   */
  public fileId: DatalabFileId;

  private _busy: boolean;
  private _editor: CodeMirror.Editor;
  private _file: DatalabFile | null;
  private _fileContent: DatalabFileContent | null;
  private _fileManager: FileManager;
  private _theme: string;

  static get is() { return 'datalab-editor'; }

  static get properties() {
    return {
      _busy: {
        type: Boolean,
        value: false
      },
      _file: {
        type: Object,
        value: null,
      },
      _fileContent: {
        type: Object,
        value: null,
      },
      fileId: {
        notify: true,
        type: Object,
        value: '',
      },
    };
  }

  async ready() {
    super.ready();

    // Get the theme.
    const settings = await SettingsManager.getUserSettingsAsync()
      .catch(() => console.error('Could not load user settings.'));

    if (settings && settings.theme) {
      this._theme = settings.theme;
    }

    // Get the file contents, or empty string if no path is specified or the
    // file could not be found.
    let content = '';
    if (this.fileId) {
      this._fileManager = FileManagerFactory.getInstanceForType(this.fileId.source);

      this._busy = true;
      // Get the file object and its contents
      this._file = await this._fileManager.get(this.fileId)
        .catch((e: Error) => {
          Utils.showErrorDialog('Error', e.message);
          return null;
        });
      if (this._file) {
        this._fileContent = await this._fileManager.getContent(this.fileId, true /*asText*/)
          .catch((e: Error) => {
            Utils.showErrorDialog('Error', e.message);
            return null;
          });
      }

      this._busy = false;

      if (this._fileContent) {
        content = this._fileContent.getEditorText();
      }
    } else {
      // TODO: Make this more flexible instead of assuming the default destination is jupyter.
      this._fileManager = FileManagerFactory.getInstanceForType(FileManagerType.JUPYTER);
    }

    // Create the codemirror element and fill it with the file content.
    // TODO: try to detect the language of the file before creating
    //       the codemirror element. Perhaps use the file extension?
    // TODO: load the mode dynamically instead of starting out with python.
    const editorConfig: CodeMirror.EditorConfiguration = {
      autofocus: true,
      lineNumbers: true,
      lineWrapping: true,
      mode: 'python',
      theme: this._getCodeMirrorTheme(this._theme),
      value: content,
    };

    this._editor = CodeMirror(this.$.editorContainer, editorConfig);
  }

  /**
   * Saves the currently open file.
   */
  async _saveAsync() {
    // If the file isn't defined, this means it's a blank editor, we'll need
    // to save a new file. Open a file picker dialog here to get the file path.
    if (!this._file) {
      const options: DirectoryPickerDialogOptions = {
        big: true,
        okLabel: 'Save',
        title: 'New File',
        withFileName: true,
      };
      const closeResult = await Utils.showDialog(DirectoryPickerDialogElement, options) as
          DirectoryPickerDialogCloseResult;

      if (closeResult.confirmed) {
        // TODO: Prevent the dialog from closing if the input field is empty
        if (closeResult.fileName) {
          try {
            this._file = await this._fileManager.create(DatalabFileType.FILE,
                closeResult.selectedDirectory.id, closeResult.fileName);
          } catch (e) {
            Utils.showErrorDialog('Error saving file', 'A file with the name ' +
                closeResult.fileName + ' already exists in this directory.');
            throw e;
          }
        }
      }
    } else {
      // If _file is defined, we're saving to an existing file

      // We can only save text files.
      let content = '';
      if (this._file.type === DatalabFileType.DIRECTORY) {
        Utils.showErrorDialog('Error Saving', 'Cannot save edits to directories.');
        return;
      } else {
        content = this._editor.getDoc().getValue();
      }
    }
    if (this._file) {
      await this._fileManager.saveText(this._file, this._editor.getDoc().getValue());
      await this.dispatchEvent(new NotificationEvent('Saved.'));
    }
  }

  /**
   * Returns the directory containing a file given its full path.
   */
  _getDirNameFromPath(path: string) {
    const tokens = path.split('/');
    tokens.pop();
    return tokens.join('/');
  }

  /**
   * Rename the currently open file.
   */
  async _renameAsync() {
    // If the open file isn't saved, save it instead
    // if (!this._file) {
    //   this._saveAsync();
    // } else {
    //   const options: InputDialogOptions = {
    //     inputLabel: 'New file name',
    //     inputValue: this._file.name,
    //     okLabel: 'Rename',
    //     title: 'Rename File',
    //   };

    //   const closeResult =
    //       await Utils.showDialog(InputDialogElement, options) as InputDialogCloseResult;

    //   // TODO: Prevent the dialog from closing if the input field is empty
    //   if (closeResult.confirmed && closeResult.userInput) {
    //     this._fileManager.rename(this.fileId, closeResult.userInput)
    //       .then((savedModel) => {
    //         this.dispatchEvent(new NotificationEvent('Renamed to ' + closeResult.userInput));
    //         this.set('_file.name', savedModel.name);
    //         this.set('_file.path', savedModel.path);
    //         this.set('filePath', savedModel.path);
    //       })
    //       .catch((e: Error) => Utils.showErrorDialog('Error', e.message));
    //   }
    // }
  }

  /**
   * Changes the editor theme according to the Datalab theme provided.
   * @param datalabTheme Datalab theme value
   */
  setEditorTheme(datalabTheme: string) {
    this._editor.setOption('theme', this._getCodeMirrorTheme(datalabTheme));
  }

  /**
   * Translates the Datalab theme value (e.g. "light") into one of the
   * CodeMirror's themes. This theme's stylesheet needs to be loaded in
   * the element's light DOM.
   * @param datalabTheme Datalab theme value
   */
  _getCodeMirrorTheme(datalabTheme: string) {
    return datalabTheme === 'dark' ? 'icecoder' : 'eclipse';
  }
}

customElements.define(DatalabEditorElement.is, DatalabEditorElement);
