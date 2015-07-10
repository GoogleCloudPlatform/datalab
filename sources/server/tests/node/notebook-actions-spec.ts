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


/// <reference path="../../../../externs/ts/jasmine.d.ts"/>
import actions = require('./app/shared/actions');
import nb = require('./app/notebooks/session');
import updates = require('./app/shared/updates');


describe('Notebook model state', () => {
  var notebook: app.INotebookSession;
  var worksheetId: string;

  beforeEach(() => {
    var notebookData: app.notebooks.Notebook = {
      "id": "nb-id",
      "metadata": {},
      "worksheets": [
        {
          "id": "ws-id",
          "name": "Untitled Worksheet",
          "metadata": {},
          "cells": []
        }
      ]
    };
    notebook = new nb.NotebookSession(notebookData);
    worksheetId = getFirstWorksheet(notebook).id;
  });

  afterEach(() => {
    notebook = undefined;
    worksheetId = undefined;
  });

  it('should be an empty notebook with one worksheet and zero cells', () => {
    var notebookData: app.notebooks.Notebook = notebook.getNotebookData()
    expect(notebookData.worksheets.length).toBe(1);
    var worksheet = notebookData.worksheets[0];
    expect(worksheet.cells.length).toBe(0);
  });

  // action = notebook.clearOutputs
  describe('after notebook.clearOutputs action', () => {
    var notebookData: app.notebooks.Notebook;

    beforeEach(() => {
      var output: app.notebooks.CellOutput = {
        type: 'stdout',
        mimetypeBundle: {'text/plain': 'some stdout here'}
      };

      notebookData = notebook.getNotebookData();

      // Add a second worksheet
      notebookData.worksheets.push({
        id: 'worksheet-2',
        name: 'Worksheet2',
        metadata: {},
        cells: []
      });

      // Add some cells with outputs to each worksheet
      notebookData.worksheets.forEach((worksheet) => {
        worksheet.cells.push({
          id: worksheetId + '-cell-1',
          type: 'code',
          source: '',
          metadata: {},
          outputs: [output, output]
        });
        worksheet.cells.push({
          id: worksheetId + '-cell-2',
          type: 'code',
          source: '',
          metadata: {},
          outputs: [output, output]
        });
      });
    });

    afterEach(() => {
      notebookData = undefined;
    });

    it('should remove all of the outputs from every cell, in every worksheet', () => {
      // Validate there are two worksheets, each with two cells, each with two outputs
      expect(Object.keys(notebookData.worksheets).length).toBe(2);
      notebookData.worksheets.forEach((worksheet) => {
        var cells = worksheet.cells;
        expect(cells.length).toBe(2);
        cells.forEach((cell: app.notebooks.Cell) => {
          expect(cell.outputs.length).toBe(2);
        });
      });

      var action = {name: actions.notebook.clearOutputs, requestId: ''};
      var update = <app.notebooks.updates.Composite>notebook.apply(action);

      // Now each worksheet should still have two cells, each with zero outputs
      notebookData.worksheets.forEach((worksheet) => {
        var cells = worksheet.cells;
        expect(cells.length).toBe(2);
        cells.forEach((cell: app.notebooks.Cell) => {
          expect(cell.outputs.length).toBe(0);
        });
      });
    });
  });

  // action = cell.update
  describe('after cell.update action', () => {
    var cellUpdateAction: app.notebooks.actions.UpdateCell;
    var cellUpdate: app.notebooks.updates.CellUpdate;
    var cellIdToUpdate = 'cell-id-to-update';
    var cell: app.notebooks.Cell;

    beforeEach(() => {
      cellUpdateAction = {
        name: actions.cell.update,
        worksheetId: worksheetId,
        cellId: cellIdToUpdate,
        requestId: null
      };
      // Create a cell to be updated
      cell = {
        id: cellIdToUpdate,
        type: 'code',
        metadata: {meta: 'data'},
        source: 'initial source',
        outputs: [{
          type: 'stdout',
          mimetypeBundle: {'text/plain': 'first output'}
        }]
      }
      // Attach it to the worksheet
      var worksheet = getFirstWorksheet(notebook);
      worksheet.cells.push(cell);
    });

    afterEach(() => {
      cellUpdateAction = undefined;
      cellUpdate = undefined;
      cell = undefined;
    });

    it('should have the new source string value', () => {
      cellUpdateAction.source = 'updated source';
      var cellUpdate = <app.notebooks.updates.CellUpdate>notebook.apply(cellUpdateAction);
      expect(cellUpdate.source).toBe('updated source');
      expect(cell.source).toBe('updated source');
    });

    it('should have an additional output', () => {
      cellUpdateAction.outputs = [{
        type: 'stderr',
        mimetypeBundle: {'text/plain': 'second output'}
      }];
      var cellUpdate = <app.notebooks.updates.CellUpdate>notebook.apply(cellUpdateAction);
      // Validate that the update message is as expected
      expect(cellUpdate.outputs.length).toBe(1);
      expect(cellUpdate.outputs[0].mimetypeBundle['text/plain']).toBe('second output');
      expect(cellUpdate.replaceOutputs).toBeFalsy();
      // Validate that the notebook cell was updated accordingly
      expect(cell.outputs.length).toBe(2);
      expect(cell.outputs[0].mimetypeBundle['text/plain']).toBe('first output');
      expect(cell.outputs[1].mimetypeBundle['text/plain']).toBe('second output');
    });

    it('should have only the new output value', () => {
      cellUpdateAction.outputs = [{
        type: 'stderr',
        mimetypeBundle: {'text/plain': 'second output'}
      }];
      cellUpdateAction.replaceOutputs = true;
      var cellUpdate = <app.notebooks.updates.CellUpdate>notebook.apply(cellUpdateAction);
      // Validate that the update message is as expected
      expect(cellUpdate.outputs.length).toBe(1);
      expect(cellUpdate.outputs[0].mimetypeBundle['text/plain']).toBe('second output');
      expect(cellUpdate.replaceOutputs).toBe(true);
      // Validate that the notebook cell was updated accordingly
      expect(cell.outputs.length).toBe(1);
      expect(cell.outputs[0].mimetypeBundle['text/plain']).toBe('second output');
    });

    it('should also have the new metadata field', () => {
      cellUpdateAction.metadata = {more: 'meta'};
      var cellUpdate = <app.notebooks.updates.CellUpdate>notebook.apply(cellUpdateAction);
      // Validate that the update message is as expected
      // The update message will only carry the updated metadata fields
      expect(Object.keys(cellUpdate.metadata).length).toBe(1);
      expect(cellUpdate.metadata['meta']).not.toBeDefined();
      expect(cellUpdate.metadata['more']).toBe('meta');
      expect(cellUpdate.replaceMetadata).toBeFalsy();
      // Validate that the notebook cell was updated accordingly
      expect(Object.keys(cell.metadata).length).toBe(2);
      expect(cell.metadata['meta']).toBe('data');
      expect(cell.metadata['more']).toBe('meta');
    });

    it('should have only the new metadata field', () => {
      cellUpdateAction.metadata = {more: 'meta'};
      cellUpdateAction.replaceMetadata = true;
      var cellUpdate = <app.notebooks.updates.CellUpdate>notebook.apply(cellUpdateAction);
      // Validate that the update message is as expected
      expect(Object.keys(cellUpdate.metadata).length).toBe(1);
      expect(cellUpdate.metadata['meta']).not.toBeDefined();
      expect(cellUpdate.metadata['more']).toBe('meta');
      expect(cellUpdate.replaceMetadata).toBe(true);
      // Validate that the notebook cell was updated accordingly
      expect(Object.keys(cell.metadata).length).toBe(1);
      expect(cell.metadata['meta']).not.toBeDefined();
      expect(cell.metadata['more']).toBe('meta');
    });

    it('should have no metadata fields', () => {
      cellUpdateAction.metadata = {/* empty metadata dict */};
      cellUpdateAction.replaceMetadata = true;
      var cellUpdate = <app.notebooks.updates.CellUpdate>notebook.apply(cellUpdateAction);
      // Validate that the update message is as expected
      expect(Object.keys(cellUpdate.metadata).length).toBe(0);
      expect(cellUpdate.replaceMetadata).toBe(true);
      // Validate that the notebook cell was updated accordingly
      expect(Object.keys(cell.metadata).length).toBe(0);
    });
  });

  // action = cell.clearOutput
  describe('after cell.clearOutput action', () => {
    var clearOutputAction: app.notebooks.actions.ClearOutput;
    var cellUpdate: app.notebooks.updates.CellUpdate;
    var cellIdToClear = 'cell-id-to-clear';

    beforeEach(() => {
      clearOutputAction = {
        name: actions.cell.clearOutput,
        worksheetId: worksheetId,
        cellId: cellIdToClear,
        requestId: null
      };

      // Create a cell with a non-zero number of outputs to be cleared
      var worksheet = getFirstWorksheet(notebook);
      worksheet.cells.push({
        id: cellIdToClear,
        type: 'code',
        source: '',
        metadata: {},
        outputs: [{
          type: 'stdout',
          mimetypeBundle: {'text/plain': 'some stdout here'}
        }]
      });
    });

    afterEach(() => {
      clearOutputAction = undefined;
      cellUpdate = undefined;
    });

    it('should remove specified cell output', () => {
      // Validate that there is a single cell with non-zero number of outputs before clearing
      var worksheet = getFirstWorksheet(notebook);
      expect(worksheet.cells.length).toBe(1);
      var cell = worksheet.cells[0];
      expect(cell.id).toBe(cellIdToClear);
      expect(cell.outputs.length).toBeGreaterThan(0);

      // Apply the clear output action
      var cellUpdate = <app.notebooks.updates.CellUpdate>notebook.apply(clearOutputAction);

      // Validate the outputs of the cell were cleared within the notebook model
      expect(cell.outputs.length).toBe(0);

      // Validate that the update message will clear outputs on all clients
      expect(cellUpdate.cellId).toBe(cellIdToClear);
      expect(cellUpdate.outputs.length).toBe(0);
      expect(cellUpdate.replaceOutputs).toBe(true);
    });
  });

  describe('after worksheet.moveCell action', () => {

  });

  describe('after worksheet.deleteCell action', () => {
    var deleteCellAction: app.notebooks.actions.DeleteCell;
    var update: app.notebooks.updates.DeleteCell;
    var worksheet: app.notebooks.Worksheet;
    var notebookData: app.notebooks.Notebook;

    beforeEach(() => {
      worksheet = getFirstWorksheet(notebook);
      deleteCellAction = {
        name: actions.worksheet.deleteCell,
        worksheetId: worksheet.id,
        cellId: null,
        requestId: null
      };

      // Create three cells to validate deleting in various positions
      ['first', 'middle', 'last'].forEach((cellId) => {
        worksheet.cells.push({
          id: cellId,
          type: 'code',
          source: 'cell source content',
          metadata: {},
        });
      });
    });

    afterEach(() => {
      deleteCellAction = undefined;
      worksheet = undefined;
    });

    it('should delete the first cell', () => {
      deleteCellAction.cellId = 'first';
      update = <app.notebooks.updates.DeleteCell>notebook.apply(deleteCellAction);
      // Validate the update message
      expect(update.worksheetId).toBe(worksheet.id);
      expect(update.cellId).toBe('first');
      // Validate that the specified cell was removed from the notebook model
      expect(worksheet.cells.length).toBe(2);
      expect(worksheet.cells.map((cell) => {return cell.id})).toEqual(['middle', 'last']);
    });

    it('should delete the middle cell', () => {
      deleteCellAction.cellId = 'middle';
      update = <app.notebooks.updates.DeleteCell>notebook.apply(deleteCellAction);
      // Validate the update message
      expect(update.worksheetId).toBe(worksheet.id);
      expect(update.cellId).toBe('middle');
      // Validate that the specified cell was removed from the notebook model
      expect(worksheet.cells.length).toBe(2);
      expect(worksheet.cells.map((cell) => {return cell.id})).toEqual(['first', 'last']);
    });

    it('should delete the last cell', () => {
      deleteCellAction.cellId = 'last';
      update = <app.notebooks.updates.DeleteCell>notebook.apply(deleteCellAction);
      // Validate the update message
      expect(update.worksheetId).toBe(worksheet.id);
      expect(update.cellId).toBe('last');
      // Validate that the specified cell was removed from the notebook model
      expect(worksheet.cells.length).toBe(2);
      expect(worksheet.cells.map((cell) => {return cell.id})).toEqual(['first', 'middle']);
    });

    it('should delete all cells', () => {
      // Apply a delete operation for every cell in the notebook
      deleteCellAction.cellId = 'first';
      notebook.apply(deleteCellAction);
      deleteCellAction.cellId = 'middle';
      notebook.apply(deleteCellAction);
      deleteCellAction.cellId = 'last';
      notebook.apply(deleteCellAction);
      // Validate that the worksheet now contains zero cells
      expect(worksheet.cells.length).toBe(0);
    });
  });

  describe('after worksheet.moveCell action', () => {
    var moveCellAction: app.notebooks.actions.MoveCell;
    var worksheet: app.notebooks.Worksheet;
    beforeEach(() => {
      worksheet = getFirstWorksheet(notebook);
      moveCellAction = {
        name: actions.worksheet.moveCell,
        sourceWorksheetId: worksheet.id,
        destinationWorksheetId: worksheet.id,
        cellId: null,
        insertAfter: null,
        requestId: null
      };
      // Add 3 cells to the worksheet
      worksheet.cells.push({
        id: 'A',
        type: 'code',
        metadata: {},
        source: 'some code',
        outputs: []
      });
      worksheet.cells.push({
        id: 'B',
        type: 'code',
        metadata: {},
        source: 'some other code',
        outputs: []
      });
      worksheet.cells.push({
        id: 'C',
        type: 'code',
        metadata: {},
        source: 'yet another code',
        outputs: []
      });
    });

    afterEach(() => {
      moveCellAction = undefined;
      worksheet = undefined;
    });

    it('should move the last cell to be first', () => {
      moveCellAction.cellId = 'C';
      moveCellAction.insertAfter = null;
      var update = <app.notebooks.updates.MoveCell>notebook.apply(moveCellAction);
      expect(worksheet.cells.map((cell) => {return cell.id;})).toEqual(['C', 'A', 'B']);
    });

    it('should leave the cell order unchanged', () => {
      moveCellAction.cellId = 'A';
      moveCellAction.insertAfter = null;
      var update = <app.notebooks.updates.MoveCell>notebook.apply(moveCellAction);
      expect(worksheet.cells.map((cell) => {return cell.id;})).toEqual(['A', 'B', 'C']);
    });

    it('should move the first cell to the middle', () => {
      moveCellAction.cellId = 'A';
      moveCellAction.insertAfter = 'B';
      var update = <app.notebooks.updates.MoveCell>notebook.apply(moveCellAction);
      expect(worksheet.cells.map((cell) => {return cell.id;})).toEqual(['B', 'A', 'C']);
    });

    it('should move the first cell to the end', () => {
      moveCellAction.cellId = 'A';
      moveCellAction.insertAfter = 'C';
      var update = <app.notebooks.updates.MoveCell>notebook.apply(moveCellAction);
      expect(worksheet.cells.map((cell) => {return cell.id;})).toEqual(['B', 'C', 'A']);
    });
  });

  describe('after worksheet.addCell action', () => {
    var addCellAction: app.notebooks.actions.AddCell;
    var addCellUpdate: app.notebooks.updates.AddCell;

    beforeEach(() => {
      addCellAction = {
        name: actions.worksheet.addCell,
        worksheetId: worksheetId,
        cellId: 'NEW',
        type: 'code',
        source: 'some code here',
        requestId: null
      };
      var worksheet = getFirstWorksheet(notebook);
      worksheet.cells.push({
        id: 'A',
        type: 'code',
        source: 'source code here',
        metadata: {}
      });
      worksheet.cells.push({
        id: 'B',
        type: 'code',
        source: 'source code here',
        metadata: {}
      });
    });

    afterEach(() => {
      addCellAction = undefined;
      addCellUpdate = undefined;
    });

    it('should add a cell to the beginning of the worksheet', () => {
      addCellAction.insertAfter = null;
      var addCellUpdate = <app.notebooks.updates.AddCell>notebook.apply(addCellAction);

      // Validate the update message content
      expect(addCellUpdate.name).toBe(updates.worksheet.addCell);
      expect(addCellUpdate.worksheetId).toBe(worksheetId);
      expect(addCellUpdate.cell).toBeDefined();
      // Validate the new cell in the update has the expected structure
      expect(addCellUpdate.cell.id).toBe('NEW');
      expect(addCellUpdate.cell.type).toBe('code');
      expect(addCellUpdate.cell.source).toBe('some code here');
      // Validate that the notebook model was also updated to have the new cell
      var worksheet = getFirstWorksheet(notebook);
      expect(worksheet.cells.length).toBe(3);
      expect(worksheet.cells.map((cell) => {return cell.id})).toEqual(['NEW', 'A', 'B'])
    });

    it('should insert a cell after cell "B" in the worksheet', () => {
      addCellAction.insertAfter = 'B';
      notebook.apply(addCellAction);
      // Validate that the notebook model has the added cell where expectedd
      var worksheet = getFirstWorksheet(notebook);
      expect(worksheet.cells.length).toBe(3);
      expect(worksheet.cells.map((cell) => {return cell.id})).toEqual(['A', 'B', 'NEW'])
    });

    // Note: skipped currently as insertAfter is not yet implemented
    it('should throw an error due to bad insertAfter cell id', () => {
      addCellAction.insertAfter = 'does-not-exist';
      expect(() => {
        notebook.apply(addCellAction);
      }).toThrow();
    });

  });

});

function getFirstWorksheet (notebook: app.INotebookSession) {
  return notebook.getNotebookData().worksheets[0];
}
