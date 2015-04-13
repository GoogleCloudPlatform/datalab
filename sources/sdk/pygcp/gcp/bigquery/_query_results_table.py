# Copyright 2014 Google Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#  http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Implements BigQuery query job results table functionality."""

from ._table import Table as _Table


class QueryResultsTable(_Table):

  def __init__(self, api, name, job, is_temporary=False):
    """Initializes an instance of a Table object.

    Args:
      api: the BigQuery API object to use to issue requests.
      name: the name of the table either as a string or a 3-part tuple (projectid, datasetid, name).
      is_temporary: if True, this is a short-lived table for intermediate results (default False).
    """
    super(QueryResultsTable, self).__init__(api, name)
    self._job = job
    self._is_temporary = is_temporary

  @property
  def job_id(self):
    return self._job.id

  @property
  def sql(self):
    return self._job.sql

  @property
  def is_temporary(self):
    """ Whether this is a short-lived table or not. """
    return self._is_temporary

