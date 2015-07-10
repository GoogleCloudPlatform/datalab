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

/// <reference path="../shared/interfaces.d.ts" />
/**
 * Internal message types for capturing the relevant details of the IPython messaging protocol
 *
 * Imminent changes to the messaging spec from protocol 4.1 to 5.x
 * https://github.com/ipython/ipython/wiki/IPEP-13:-Updating-the-Message-Spec
 */


declare module app {

  interface ExecuteReply extends KernelMessage {
    success: boolean;
    // When execute has not been aborted, we get back an execution count
    executionCounter?: string;
    // When an error has occurred, the following are populated
    errorName?: string;
    errorMessage?: string;
    traceback?: string[];
  }

  interface ExecuteRequest extends KernelMessage {
    code: string;
  }

  /**
   * Common fields for kernel messages.
   */
  interface KernelMessage {
    requestContext: RequestContext;
  }

  interface KernelStatus extends KernelMessage {
    status: string;
  }

  interface OutputData extends KernelMessage {
    type: string; // 'stdout' | 'stderr' | 'result' | 'error'
    mimetypeBundle: any;
  }

  interface RequestContext {
    requestId: string;
    cellId?: string;
    worksheetId?: string;
    connectionId?: string;
  }

  interface SessionStatus {
    kernelStatus: string;
    // additional session metadata fields go here eventually (e.g., connected users)
  }

  module ipy {

    interface Header {
      msg_id: string;
      msg_type: string;
      msg_context: any;
    }

    interface Message {
      identities: string[];
      header: Header;
      parentHeader: Header;
      metadata: Map<any>;
      content: any;
    }

    interface ExecuteRequestContent {
      code: string;
      silent: boolean;
      store_history: boolean;
      allow_stdin: boolean;
    }

  }

}
