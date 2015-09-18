/*
 * Copyright 2015 Google Inc. All rights reserved.
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
// Provides function, which, given a string, will return the highlighting mode required,
//  if none matched fallback string is returned.

/// <amd-dependency path="modes/bqsql.js" />
/// <amd-dependency path="modes/overlay.js" />

import CodeMirror = require('codeMirror');

interface magicTypeMap {
  [index : string] : RegExp[];
}

// Map between CodeMirror mode name and list of regular expressions.
var magicMap:magicTypeMap = {
  "text/x-bqsql": [/^\%\%bigquery sql\s/, /^\%\%bigquery dryrun\s/],
  "text/javascript": [/^%%javascript\s/, /^%%bigquery udf\s/]
};

/**
 * Map text content to a CodeMirror mode.
 * @param content, string of text, which is used to determine the correct mode.
 * @param fallback, The string name of the mode to be used of no regex matches the passed string,
 *        pass undefined if no highlighting required.
 * @returns {string}, name of the mode, or the fallback value if there is no match.
 */
export var magicDetector = function(content:string, fallback?:string):string {
  // TODO: Util function to loop through the keys of an object and apply a
  //       function to the iteration.

  // Loop through MIME types.
  for (var mmapKey in magicMap) {
    if (magicMap.hasOwnProperty(mmapKey)) {
      // Loop through Regexes associated to those types.
      for (var index = 0; index < magicMap[mmapKey].length; index++) {
        var matches = content.match(magicMap[mmapKey][index]);
        if (matches) {
          return mmapKey;
        }
      }
    }
  }

  // Return fallback if no pattern matched.
  return fallback;
};


// Define overlay mode.
CodeMirror.defineMode("magic_overlay", function(config: any, parserConfig: any) {
  var magicOverlay = {
    startState: function() {return {firstMatched : false}},
    token: function(stream: any, state: any) {
      if(!state.firstMatched) {
        var ch : any;
        stream.eatSpace(); // consume all spaces, can span over several lines

        if (!stream.eol()) {
          state.firstMatched = true;
          if (stream.match("%%")) {
            stream.skipToEnd();
            return "comment"
          }
        }
      } else {
        // ignore line, as this line is not part of the magic line anymore.
        stream.skipToEnd();
      }

      return null;
    }
  };
  return CodeMirror.overlayMode(CodeMirror.getMode(config, parserConfig.backdrop || "python"), magicOverlay);
});


