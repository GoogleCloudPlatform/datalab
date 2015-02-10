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

"""Implements Table, and related Table BigQuery APIs."""

import collections
from datetime import datetime
import json
import pandas as pd
import re
import time
import uuid

from gcp._util import Iterator as _Iterator
from ._job import Job as _Job
from ._parser import Parser as _Parser
from ._sampling import Sampling as _Sampling
import _query


class TableSchema(list):
  """Represents the schema of a BigQuery table.
  """

  class _Field(object):

    def __init__(self, name, data_type, mode, description):
      self.name = name
      self.data_type = data_type
      self.mode = mode
      self.description = description

    def _repr_sql_(self):
      """Returns a representation of the field for embedding into a SQL statement.

      Returns:
        A formatted field name for use within SQL statements.
      """
      return self.name

    def __eq__(self, other):
      return self.name == other.name and self.data_type == other.data_type \
          and self.mode == other.mode

    def __str__(self):
      # Stringize in the form of a dictionary
      return "{ 'name': '%s', 'type': '%s', 'mode':'%s', 'description': '%s' }" %\
             (self.name, self.data_type, self.mode, self.description)

    def __repr__(self):
      return str(self)


  @staticmethod
  def _from_dataframe(dataframe, default_type='STRING'):
    """
      Infer a BigQuery table schema from a Pandas dataframe. Note that if you don't explicitly set
      the types of the columns in the dataframe, they may be of a type that forces coercion to
      STRING, so even though the fields in the dataframe themselves may be numeric, the type in the
      derived schema may not be. Hence it is prudent to make sure the Pandas dataframe is typed
      correctly.

    Args:
      dataframe: DataFrame
      default_type : The default big query type in case the type of the column does not exist in
          the schema.
    Returns:
      A list of dictionaries containing field 'name' and 'type' entries, suitable for use in a
          BigQuery Tables resource schema.
    """

    type_mapping = {
      'i': 'INTEGER',
      'b': 'BOOLEAN',
      'f': 'FLOAT',
      'O': 'STRING',
      'S': 'STRING',
      'U': 'STRING',
      'M': 'TIMESTAMP'
    }

    fields = []
    for column_name, dtype in dataframe.dtypes.iteritems():
      fields.append({'name': column_name,
                     'type': type_mapping.get(dtype.kind, default_type)})

    return fields

  def __init__(self, data):
    """Initializes a TableSchema from its raw JSON representation or a Pandas Dataframe.
    """
    list.__init__(self)
    self._map = {}
    if isinstance(data, pd.DataFrame):
      data = TableSchema._from_dataframe(data)
    self._populate_fields(data)

  def __getitem__(self, key):
    """Provides ability to lookup a schema field by position or by name.
    """
    if isinstance(key, basestring):
      return self._map.get(key, None)
    return list.__getitem__(self, key)

  def _populate_fields(self, data, prefix=''):
    self._bq_schema = data
    for field_data in data:
      name = prefix + field_data['name']
      data_type = field_data['type']

      field = TableSchema._Field(name, data_type,
                                 field_data.get('mode', 'NULLABLE'),
                                 field_data.get('description', ''))
      self.append(field)
      self._map[name] = field

      if data_type == 'RECORD':
        # Recurse into the nested fields, using this field's name as a prefix.
        self._populate_fields(field_data.get('fields'), name + '.')

  def __iter__(self):
    return self._map.itervalues()

  def __str__(self):
    return str(self._bq_schema)


class DataSet(object):
  """Represents a list of BigQuery tables in a dataset."""

  def __init__(self, api, dataset_id):
    """Initializes an instance of a DataSet.

    Args:
      api: the BigQuery API object to use to issue requests. The project ID will be inferred from
          this.
      dataset_id: the BigQuery dataset ID corresponding to this list.
    """
    self._api = api
    self._dataset_id = dataset_id

  def exists(self):
    """ Checks if the dataset exists.

    Args:
      None
    Returns:
      True if the dataset exists; False otherwise.
    """
    try:
      _ = self._api.datasets_get(self._dataset_id)
    except Exception as e:
      if (len(e.args[0]) > 1) and (e.args[0][1] == 404):
        return False
      raise e
    return True

  def delete(self, delete_contents=False):
    """Issues a request to delete the dataset.

    Args:
      delete_contents: if True, any tables in the dataset will be deleted. If False and the
          dataset is non-empty an exception will be raised.
    Returns:
      None on success (including if the dataset didn't exist).
    Raises:
      Exception if the delete fails.
    """
    if self.exists():
      self._api.datasets_delete(self._dataset_id, delete_contents=delete_contents)
    return None

  def create(self, friendly_name=None, description=None):
    """Creates the Dataset with the specified friendly name and description.

    Args:
      friendly_name: (optional) the friendly name for the dataset if it is being created.
      description: (optional) a description for the dataset if it is being created.
    Returns:
      The DataSet.
    Raises:
      Exception if the DataSet could not be created.
    """
    if not self.exists():
      response = self._api.datasets_insert(self._dataset_id,
                                           friendly_name=friendly_name,
                                           description=description)
      if 'selfLink' not in response:
        raise Exception("Could not create dataset %s.%s" % self.full_name)
    return self

  def _retrieve_tables(self, page_token):
    list_info = self._api.tables_list(page_token=page_token)

    tables = list_info.get('tables', [])
    if len(tables):
      try:
        project_id = self._api.project_id
        tables = [Table(self._api, (project_id, self._dataset_id,
                                    info['tableReference']['tableId'])) for info in tables]
      except KeyError:
        raise Exception('Unexpected item list response.')

    page_token = list_info.get('nextPageToken', None)
    return tables, page_token

  def __iter__(self):
    return iter(_Iterator(self._retrieve_tables))

  def __repr__(self):
    """Returns an empty representation for the dataset for showing in the notebook.
    """
    return ''


class TableMetadata(object):
  """Represents metadata about a BigQuery table."""

  def __init__(self, name, info):
    """Initializes an instance of a TableMetadata.

    Args:
      name: the name of the table.
      info: The BigQuery information about this table.
    """
    self._name = name
    self._info = info

  @property
  def created_on(self):
    """The creation timestamp."""
    timestamp = self._info.get('creationTime')
    return _Parser.parse_timestamp(timestamp)

  @property
  def description(self):
    """The description of the table if it exists."""
    return self._info.get('description', '')

  @property
  def expires_on(self):
    """The timestamp for when the table will expire."""
    timestamp = self._info.get('expirationTime', None)
    if timestamp is None:
      return None
    return _Parser.parse_timestamp(timestamp)

  @property
  def friendly_name(self):
    """The friendly name of the table if it exists."""
    return self._info.get('friendlyName', '')

  @property
  def full_name(self):
    """The full name of the table."""
    return self._name

  @property
  def modified_on(self):
    """The timestamp for when the table was last modified."""
    timestamp = self._info.get('lastModifiedTime')
    return _Parser.parse_timestamp(timestamp)

  @property
  def rows(self):
    """The number of rows within the table."""
    return self._info['numRows']

  @property
  def size(self):
    """The size of the table in bytes."""
    return self._info['numBytes']


TableName = collections.namedtuple('TableName', ['project_id', 'dataset_id', 'table_id'])


class Table(object):
  """Represents a Table object referencing a BigQuery table.

  This object can be used to inspect tables and create SQL queries.
  """

  # Absolute project-qualified name pattern: <project>:<dataset>.<table>
  _ABS_NAME_PATTERN = r'^([a-z0-9\-_\.:]+)\:([a-zA-Z0-9_]+)\.([a-zA-Z0-9_]+)$'

  # Relative name pattern: <dataset>.<table>
  _REL_NAME_PATTERN = r'^([a-zA-Z0-9_]+)\.([a-zA-Z0-9_]+)$'

  # Table-only name pattern: <table>
  _TABLE_NAME_PATTERN = r'^([a-zA-Z0-9_]+)$'

  # Allowed characters in a BigQuery table column name
  _VALID_COLUMN_NAME_CHARACTERS = '_abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789'

  @staticmethod
  def parse_name(name, project_id=None, dataset_id=None):
    """Parses a table name into its individual parts.

    Args:
      name: the name to parse, or a triple containing the parts.
      project_id: the expected project ID. If the name does not contain a project ID,
          this will be used; if the name does contain a project ID and it does not match
          this, an exception will be thrown.
      dataset_id: the expected dataset ID. If the name does not contain a dataset ID,
          this will be used; if the name does contain a dataset ID and it does not match
          this, an exception will be thrown.
    Returns:
      A tuple consisting of the full name and individual name parts.
    Raises:
      Exception: raised if the name doesn't match the expected formats.
    """
    if isinstance(name, basestring):
      # Try to parse as absolute name first.
      m = re.match(Table._ABS_NAME_PATTERN, name, re.IGNORECASE)
      if m is not None:
        _project_id, _dataset_id, _table_id = m.groups()
      else:
        # Next try to match as a relative name implicitly scoped within current project.
        m = re.match(Table._REL_NAME_PATTERN, name)
        if m is not None:
          groups = m.groups()
          _project_id, _dataset_id, _table_id = project_id, groups[0], groups[1]
        else:
          # Finally try to match as a table name only.
          m = re.match(Table._TABLE_NAME_PATTERN, name)
          if m is not None:
            groups = m.groups()
            _project_id, _dataset_id, _table_id = project_id, dataset_id, groups[0]
          else:
            raise Exception('Invalid table name: ' + name)
    else:
      # Treat as a triple.
      _project_id, _dataset_id, _table_id = name

    if dataset_id and _dataset_id != dataset_id:
      raise Exception('Invalid dataset ID %s in name %s; expected %s' %
                      (_dataset_id, name, dataset_id))

    return TableName(_project_id, _dataset_id, _table_id)

  def __init__(self, api, name, is_temporary=False):
    """Initializes an instance of a Table object.

    Args:
      api: the BigQuery API object to use to issue requests.
      name: the name of the table either as a string or a 3-part tuple (projectid, datasetid, name).
      is_temporary: if True, this is a short-lived table for intermediate results (default False).
    """
    self._api = api
    self._name_parts = Table.parse_name(name, api.project_id)
    self._full_name = '%s:%s.%s' % self._name_parts
    self._info = None
    self._is_temporary = is_temporary

  @property
  def full_name(self):
    """The full name for the table."""
    return self._full_name

  @property
  def name(self):
    """The TableName for the table."""
    return self._name_parts

  @property
  def istemporary(self):
    """ Whether this is a short-lived table or not. """
    return self._is_temporary

  def _load_info(self):
    """Loads metadata about this table."""
    if self._info is None:
      self._info = self._api.tables_get(self._name_parts)

  def metadata(self):
    """Retrieves metadata about the table.

    Returns:
      A TableMetadata object.
    Raises
      Exception if the request could not be executed or the response was malformed.
    """
    self._load_info()
    return TableMetadata(self._full_name, self._info)

  def exists(self):
    """Checks if the table exists.

    Returns:
      True if the table exists; False otherwise.
    Raises:
      Exception if there was an error requesting information about the table.
    """
    try:
      _ = self._api.tables_get(self._name_parts)
    except Exception as e:
      if (len(e.args[0]) > 1) and (e.args[0][1] == 404):
        return False
      raise e
    return True

  def delete(self):
    """ Delete the table.

    Returns:
      Nothing
    """
    try:
      self._api.table_delete(self._name_parts)
    except Exception as e:
      # TODO(gram): May want to check the error reasons here and if it is not
      # because the file didn't exist, return an error.
      pass

  def create(self, schema, truncate=False):
    """ Create the table with the specified schema.

    Args:
      schema: the schema to use to create the table. Should be a list of dictionaries, each
          containing at least a pair of entries, 'name' and 'type'.
          See https://cloud.google.com/bigquery/docs/reference/v2/tables#resource
      truncate: if True, delete the table first if it exists. If False and the Table exists,
          creation will fail and raise an Exception.
    Returns:
      The Table instance.
    Raises:
      Exception if the table couldn't be created or already exists and truncate was False.
    """
    if truncate and self.exists():
      self.delete()
    if isinstance(schema, TableSchema):
      schema = schema._bq_schema
    response = self._api.tables_insert(self._name_parts, schema)
    if 'selfLink' in response:
      return self
    raise Exception("Table %s could not be created as it already exists" % self.full_name)

  def sample(self, fields=None, count=5, sampling=None, timeout=0, use_cache=True):
    """Retrieves a sampling of data from the table.

    Args:
      fields: an optional list of field names to retrieve.
      count: an optional count of rows to retrieve which is used if a specific
          sampling is not specified.
      sampling: an optional sampling strategy to apply to the table.
      timeout: duration (in milliseconds) to wait for the query to complete.
      use_cache: whether to use cached results or not.
    Returns:
      A query results object containing the resulting data.
    Raises:
      Exception if the sample query could not be executed or query response was malformed.
    """
    if sampling is None:
      sampling = _Sampling.default(fields=fields, count=count)
    sql = sampling(self._repr_sql_())
    q = _query.Query(self._api, sql)

    return q.results(timeout=timeout, use_cache=use_cache)

  @staticmethod
  def _encode_dict_as_row(record, column_name_map):
    """ Encode a dictionary representing a table row in a form suitable for streaming to BQ.
        This means encoding timestamps as ISO-compatible strings and removing invalid
        characters from column names.

    Args:
      record: a Python dictionary representing the table row.
      column_name_map: a dictionary mapping dictionary keys to column names. This is initially
        empty and built up by this method when it first encounters each column, then used as a
        cache subsequently.
    Returns:
      The sanitized dictionary.
    """
    for k in record.keys():
      v = record[k]
      # If the column is a date, convert to ISO string.
      if isinstance(v, pd.Timestamp) or isinstance(v, datetime):
        v = record[k] = record[k].isoformat()

      # If k has invalid characters clean it up
      if k not in column_name_map:
        column_name_map[k] = ''.join(c for c in k if c in Table._VALID_COLUMN_NAME_CHARACTERS)
      new_k = column_name_map[k]
      if k != new_k:
        record[new_k] = v
        del record[k]
    return record

  def insertAll(self, dataframe, include_index=False):
    """ Insert the contents of a Pandas dataframe into the table. Note that at present, any
        timeunit values will be truncated to integral seconds. Support for microsecond resolution
        will come later.

    Args:
      dataframe: the dataframe to insert.
      include_index: whether to include the DataFrame index as a column in the BQ table.
    Returns:
      The table.
    Raises:
      Exception if the table doesn't exists, the schema differs from the dataframe's, or the insert
          failed.
    """
    # TODO(gram): create a version which can take a list of Python objects.

    # There are BigQuery limits on the streaming API:
    #
    # max_rows_per_post = 500
    # max_bytes_per_row = 20000
    # max_rows_per_second = 10000
    # max_bytes_per_post = 1000000
    # max_bytes_per_second = 10000000
    #
    # It is non-trivial to enforce these here, but as an approximation we enforce the 500 row limit
    # with a 0.1 sec POST interval.
    max_rows_per_post = 500
    post_interval = 0.1

    # TODO(gram): add different exception types for each failure case.
    if not self.exists():
      raise Exception('Table %s does not exist.' % self._full_name)

    data_schema = TableSchema(dataframe)
    table_schema = self.schema()

    # Do some validation of the two schema to make sure they are compatible.
    for data_field in data_schema:
      name = data_field.name
      table_field = table_schema[name]
      if table_field is None:
        raise Exception('Table does not contain field %s' % name)
      data_type = data_field.data_type
      table_type = table_field.data_type
      if table_type != data_type:
        raise Exception('Field %s in data has type %s but in table has type %s' %
                        (name, data_type, table_type))

    total_rows = len(dataframe)
    total_pushed = 0

    job_id = uuid.uuid4().hex
    rows = []
    column_name_map = {}

    # reset_index creates a new dataframe so we don't affect the original. reset_index(drop=True)
    # drops the original index and uses an integer range.
    for index, dataframe_row in dataframe.reset_index(drop=not include_index).iterrows():

      rows.append({
        'json': self._encode_dict_as_row(dataframe_row.to_dict(), column_name_map),
        'insertId': job_id + str(index)
      })

      total_pushed += 1

      if (total_pushed == total_rows) or (len(rows) == max_rows_per_post):
        response = self._api.tabledata_insertAll(self._name_parts, rows)
        if 'insertErrors' in response:
          raise Exception('insertAll failed: %s' % response['insertErrors'])

        time.sleep(post_interval)  # Streaming API is rate-limited
        rows = []
    return self

  def extract(self, destination, format='CSV', compress=False,
              field_delimiter=',', print_header=True):
    """Exports the table to GCS.

    Args:
      destination: the destination URI(s). Can be a single URI or a list.
      format: the format to use for the exported data; one of CSV, NEWLINE_DELIMITED_JSON or AVRO.
          Defaults to CSV.
      compress whether to compress the data on export. Compression is not supported for
          AVRO format. Defaults to False.
      field_delimiter: for CSV exports, the field delimiter to use. Defaults to ','
      print_header: for CSV exports, whether to include an initial header line. Default true.
    Returns:
      A Job object for the export Job if it was started successfully; else None.
    """
    response = self._api.table_extract(self._name_parts, destination, format, compress,
                                      field_delimiter, print_header)
    return _Job(self._api, response['jobReference']['jobId']) \
        if response and 'jobReference' in response else None

  def load(self, source, append=False, overwrite=False, source_format='CSV'):
    """ Load the table from GCS.

    Args:
      source: the URL of the source bucket(s). Can include wildcards.
      append: if True append onto existing table contents.
      overwrite: if True overwrite existing table contents.
      source_format: the format of the data; default 'CSV'. Other options are DATASTORE_BACKUP
          or NEWLINE_DELIMITED_JSON.
    Returns:
      A Job object for the load Job if it was started successfully; else None.
    """
    response = self._api.jobs_insert_load(source, self._name_parts,
                                          append=append, overwrite=overwrite,
                                          source_format=source_format)
    return _Job(self._api, response['jobReference']['jobId']) \
        if response and 'jobReference' in response else None

  def to_dataframe(self, start_row=0, max_rows=None):
    """ Exports the table to a Pandas dataframe.

    Args:
      start_row: the row of the table at which to start the export (default 0)
      max_rows: an upper limit on the number of rows to export (default None)
    Returns:
      A dataframe containing the table data.
    """
    page_token = None
    rows = []
    schema = self.schema()
    while True:
      response = self._api.tabledata_list(self._name_parts, start_index=start_row,
                                          max_results=max_rows, page_token=page_token)
      page_rows = response['rows']
      page_token = response['pageToken'] if 'pageToken' in response else None
      total_rows = response['totalRows'] if 'totalRows' in response else len(rows)

      if not max_rows or max_rows > total_rows:
        max_rows = total_rows
      for row_dict in page_rows:
        row = row_dict['f']
        record = {}
        column_index = 0
        for col in row:
          value = col['v']
          if schema[column_index].data_type == 'TIMESTAMP':
            value = datetime.utcfromtimestamp(float(value))
          record[schema[column_index].name] = value
          column_index += 1

        rows.append(record)

      start_row += len(page_rows)
      max_rows -= len(page_rows)
      if max_rows <= 0:
        break

    return pd.DataFrame(rows)

  def schema(self):
    """Retrieves the schema of the table.

    Returns:
      A TableSchema object containing a list of schema fields and associated metadata.
    Raises
      Exception if the request could not be executed or the response was malformed.
    """
    try:
      self._load_info()
      return TableSchema(self._info['schema']['fields'])
    except KeyError:
      raise Exception('Unexpected table response.')

  def _repr_sql_(self):
    """Returns a representation of the table for embedding into a SQL statement.

    Returns:
      A formatted table name for use within SQL statements.
    """
    return '[' + self._full_name + ']'

  def __repr__(self):
    """Returns an empty representation for the table for showing in the notebook.
    """
    return ''

  def __str__(self):
    """Returns a string representation of the table using its specified name.

    Returns:
      The string representation of this object.
    """
    return self._name

