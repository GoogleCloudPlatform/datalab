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
 * This file contains a collection of functions that call the Google Drive APIs, and are
 * wrapped in the FileManager class.
 */

class DriveFile extends DatalabFile {
  lastModified?: string;
  owner?: string;

  getColumnValues() {
    return [this.name, this.lastModified || '', this.owner || ''];
  }
}

/**
 * An Google Drive specific file manager.
 */
class DriveFileManager extends BaseFileManager {

  private static readonly _directoryMimeType = 'application/vnd.google-apps.folder';
  private static readonly _notebookMimeType = 'application/json';

  public async get(fileId: DatalabFileId): Promise<DatalabFile> {
    const upstreamFile = await GapiManager.drive.getFile(fileId.path);
    return this._fromUpstreamFile(upstreamFile);
  }

  public async getStringContent(fileId: DatalabFileId, _asText?: boolean): Promise<string> {
    const [, content] = await GapiManager.drive.getFileWithContent(fileId.path);
    if (content === null) {
      throw new Error('Could not download file: ' + fileId.toString());
    }
    return content;
  }

  public async getRootFile(): Promise<DatalabFile> {
    const upstreamFile = await GapiManager.drive.getRoot();
    return this._fromUpstreamFile(upstreamFile);
  }

  public newFileNameError(fileName: string): string | null {
    // Must match _getWhitelistFilePredicates()
    if (fileName.indexOf('.ipynb') > -1 || fileName.indexOf('.txt') > -1) {
      return null;
    } else {
      return 'File name must include .txt';
    }
  }

  public saveText(file: DatalabFile, text: string): Promise<DatalabFile> {
    return GapiManager.drive.patchContent(file.id.path, text)
      .then((upstreamFile) => this._fromUpstreamFile(upstreamFile));
  }

  public async list(fileId: DatalabFileId): Promise<DatalabFile[]> {
    const queryPredicates = await this._getQueryPredicates(fileId);
    const fileFields = [
      'createdTime',
      'iconLink',
      'id',
      'mimeType',
      'modifiedTime',
      'name',
      'owners',
      'parents',
    ];

    const upstreamFiles = await GapiManager.drive.listFiles(fileFields, queryPredicates);
    return upstreamFiles.map((file) => this._fromUpstreamFile(file));
  }

  public getColumnNames() {
    return [
      Utils.constants.columns.name,
      Utils.constants.columns.lastModified,
      Utils.constants.columns.owner,
    ];
  }

  public async create(fileType: DatalabFileType, containerId?: DatalabFileId, name?: string)
      : Promise<DatalabFile> {
    let mimeType: string;
    switch (fileType) {
      case DatalabFileType.DIRECTORY:
        mimeType = DriveFileManager._directoryMimeType; break;
      case DatalabFileType.NOTEBOOK:
        mimeType = DriveFileManager._notebookMimeType; break;
      default:
        mimeType = 'text/plain';
    }
    const content = fileType === DatalabFileType.NOTEBOOK ?
        NotebookContent.EMPTY_NOTEBOOK_CONTENT : '';
    const upstreamFile = await GapiManager.drive.create(mimeType,
                                                        containerId ? containerId.path : 'root',
                                                        name || 'New Item',
                                                        content);
    return this._fromUpstreamFile(upstreamFile);
  }

  public rename(oldFileId: DatalabFileId, newName: string, newContainerId?: DatalabFileId)
      : Promise<DatalabFile> {
    const newContainerPath = newContainerId ? newContainerId.path : undefined;
    return GapiManager.drive.renameFile(oldFileId.path, newName, newContainerPath)
      .then((upstreamFile) => this._fromUpstreamFile(upstreamFile));
  }

  public delete(fileId: DatalabFileId): Promise<boolean> {
    return GapiManager.drive.deleteFile(fileId.path)
      .then(() => true, () => false);
  }

  public copy(file: DatalabFileId, destinationDirectoryId: DatalabFileId): Promise<DatalabFile> {
    return GapiManager.drive.copy(file.path, destinationDirectoryId.path)
      .then((upstreamFile) => this._fromUpstreamFile(upstreamFile));
  }

  public pathToPathHistory(path: string): DatalabFile[] {
    if (path === '') {
      return [];
    } else {
      // TODO - create the real path to this object, or figure out
      // a better way to handle not having the full path in the breadcrumbs
      const fileId = path;  // We assume the entire path is one fileId
      const datalabFile: DriveFile = new DriveFile(
        new DatalabFileId(fileId, FileManagerType.DRIVE),
        path,
        DatalabFileType.DIRECTORY,
      );
      return [datalabFile];
    }
  }

  protected _fromUpstreamFile(file: gapi.client.drive.File) {
    const driveFile = new DriveFile(
      new DatalabFileId(file.id, FileManagerType.DRIVE),
      file.name,
      file.mimeType === DriveFileManager._directoryMimeType ?
                              DatalabFileType.DIRECTORY :
                              DatalabFileType.FILE,
      file.mimeType === DriveFileManager._directoryMimeType ?
                              file.iconLink : 'editor:insert-drive-file',
    );
    if (driveFile.type === DatalabFileType.FILE && driveFile.name.endsWith('.ipynb')) {
      driveFile.type = DatalabFileType.NOTEBOOK;
    }
    driveFile.lastModified = new Date(file.modifiedTime).toLocaleString();
    if (file.owners) {
      driveFile.owner = file.owners[0].me ? Utils.constants.me : file.owners[0].displayName;
    }
    return driveFile;
  }

  protected _getWhitelistFilePredicates() {
    return [
      // Must match newFileNameIsValid()
      'name contains \'.ipynb\'',
      'name contains \'.txt\'',
      'mimeType = \'' + DriveFileManager._directoryMimeType + '\'',
    ];
  }

  protected async _getQueryPredicates(fileId: DatalabFileId) {
    return [
      '"' + fileId.path + '" in parents',
      'trashed = false',
      '(' + this._getWhitelistFilePredicates().join(' or ') + ')',
    ];
  }

}

class SharedDriveFileManager extends DriveFileManager {

  public pathToPathHistory(path: string) {
    const pathHistory = super.pathToPathHistory(path);
    pathHistory.forEach((f) => {
      f.id.source = FileManagerType.SHARED_DRIVE;
    });
    return pathHistory;
  }

  protected _fromUpstreamFile(file: gapi.client.drive.File) {
    const driveFile = super._fromUpstreamFile(file);
    driveFile.id.source = FileManagerType.SHARED_DRIVE;
    return driveFile;
  }

  /**
   * For shared files, the query should include the 'sharedWithMe' predicate
   * without any parents, but if the user wants to dig in on a specific
   * directory, it should be included as the parent, and `sharedWithMe` should
   * be removed.
   */
  protected async _getQueryPredicates(fileId: DatalabFileId) {
    const root = await this.getRootFile();
    if (root.id.path === fileId.path) {
      return [
        'trashed = false',
        'sharedWithMe',
        '(' + this._getWhitelistFilePredicates().join(' or ') + ')',
      ];
    } else {
      return super._getQueryPredicates(fileId);
    }
  }
}
