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


/**
 * Directive for creating a single heading cell.
 */
/// <reference path="../../../../../../../../externs/ts/angularjs/angular.d.ts" />
/// <amd-dependency path="app/components/editorcell/EditorCellDirective" />
/// <amd-dependency path="app/components/headingviewer/HeadingViewerDirective" />
import logging = require('app/common/Logging');
import constants = require('app/common/Constants');
import doccell = require('app/components/documentcell/DocumentCell');
import _app = require('app/App');


var log = logging.getLogger(constants.scopes.headingCell);

/**
 * Creates a heading cell directive definition.
 *
 * @return A directive definition.
 */
function headingCellDirective (): ng.IDirective {

  return {
    restrict: 'E',
    scope: {
      cell: '=',
      worksheetId: '='
    },
    templateUrl: constants.scriptPaths.app + '/components/headingcell/headingcell.html',
    replace: true,
    controller: doccell.DocumentCellController
  }
}

_app.registrar.directive(constants.headingCell.directiveName, headingCellDirective);
log.debug('Registered heading cell directive');
