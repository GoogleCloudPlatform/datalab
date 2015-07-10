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

# Utility functions that don't need class wrappers and don't merit their own files.
"""Utility functions."""

import json
import pandas as pd
import gcp.bigquery as _bq


try:
  import IPython as _ipython
except ImportError:
  raise Exception('This module can only be loaded in ipython.')


def _get_field_list(fields, schema):
  """ Convert a field list spec into a real list of field names.

      For tables, we return only the top-level non-RECORD fields as Google charts
      can't handle nested data.
  """
  # If the fields weren't supplied get them from the schema.
  if isinstance(fields, list):
    return fields
  if isinstance(fields, basestring) and fields != '*':
    return fields.split(',')
  if not schema:
    return []
  return [f['name'] for f in schema._bq_schema if f['type'] != 'RECORD']


def _get_cols(fields, schema):
  """ Get column metadata for Google Charts based on field list and schema. """
  typemap = {
    'STRING': 'string',
    'INTEGER': 'number',
    'FLOAT': 'number',
    'BOOLEAN': 'boolean',
    'TIMESTAMP': 'datetime'
  }
  cols = []
  for col in fields:
    if schema:
      f = schema[col]
      cols.append({'id': f.name, 'label': f.name, 'type': typemap[f.data_type]})
    else:
      # This will only happen if we had no rows to infer a schema from, so the type
      # is not really important
      cols.append({'id': col, 'label': col, 'type': 'string'})
  return cols


def _get_data_from_empty_list(source, fields, first_row, count):
  """ Helper function for _get_data that handles empty lists. """
  fields = _get_field_list(fields, None)
  return {'cols': _get_cols(fields, None), 'rows': []}, 0


def _get_data_from_list_of_dicts(source, fields, first_row, count):
  """ Helper function for _get_data that handles lists of dicts. """
  schema = _bq.schema(source)
  fields = _get_field_list(fields, schema)
  gen = source[first_row:first_row + count] if count >= 0 else source
  rows = [{'c': [{'v': row[c]} for c in fields]} for row in gen]
  return {'cols': _get_cols(fields, schema), 'rows': rows}, len(source)


def _get_data_from_list_of_lists(source, fields, first_row, count):
  """ Helper function for _get_data that handles lists of lists. """
  schema = _bq.schema(source)
  fields = _get_field_list(fields, schema)
  gen = source[first_row:first_row + count] if count >= 0 else source
  rows = [{'c': [{'v': row[i]} for i in range(0, len(fields))]} for row in gen]
  return {'cols': _get_cols(fields, schema), 'rows': rows}, len(source)


def _get_data_from_dataframe(source, fields, first_row, count):
  """ Helper function for _get_data that handles Pandas DataFrames. """
  schema = _bq.schema(source)
  fields = _get_field_list(fields, schema)
  rows = []
  df_slice = source.reset_index(drop=True)[first_row:first_row + count]
  for index, data_frame_row in df_slice.iterrows():
    row = data_frame_row.to_dict()
    for key in row.keys():
      val = row[key]
      if isinstance(val, pd.Timestamp):
        row[key] = val.to_pydatetime()

    rows.append({'c': [{'v': row[c]} for c in fields]})
  cols = _get_cols(fields, schema)
  return {'cols': cols, 'rows': rows}, len(source)


def _get_data_from_table(source, fields, first_row, count):
  """ Helper function for _get_data that handles BQ Tables. """
  if not source.exists():
    return _get_data_from_empty_list(source, fields, first_row, count)
  schema = source.schema
  fields = _get_field_list(fields, schema)
  gen = source.range(first_row, count) if count >= 0 else source
  rows = [{'c': [{'v': row[c]} for c in fields]} for row in gen]
  return {'cols': _get_cols(fields, schema), 'rows': rows}, source.length


def _get_data(source, fields, first_row, count):
  """ A utility function to get a subset of data from a Table, Query, Pandas dataframe or List.

  Args:
    source: the source of the data. Can be a Table, Pandas DataFrame, List of dictionaries or
        lists, or a string, in which case it is expected to be the name of a table in BQ.
    fields: a list of fields that we want to return as a list of strings, comma-separated string,
        or '*' for all.
    first_row: the index of the first row to return.
    count: the number or rows to return.

  Returns:
    A dictionary with two entries: 'cols' which is a list of column metadata entries for
    Google Charts, and 'rows' which is a list of lists of values.

  Raises:
    Exception if the request could not be fulfilled.
  """

  if isinstance(source, basestring):
    ipy = _ipython.get_ipython()
    source = ipy.user_ns.get(source, source)
    if isinstance(source, basestring):
      source = _bq.table(source)

  if isinstance(source, list):
    if len(source) == 0:
      return _get_data_from_empty_list(source, fields, first_row, count)
    elif isinstance(source[0], dict):
      return _get_data_from_list_of_dicts(source, fields, first_row, count)
    elif isinstance(source[0], list):
      return _get_data_from_list_of_lists(source, fields, first_row, count)
    else:
      raise Exception("To get tabular data from a list it must contain dictionaries or lists.")
  elif isinstance(source, pd.DataFrame):
    return _get_data_from_dataframe(source, fields, first_row, count)
  elif isinstance(source, _bq._Query):
    return _get_data_from_table(source.results(), fields, first_row, count)
  elif isinstance(source, _bq._Table):
    return _get_data_from_table(source, fields, first_row, count)
  else:
    raise Exception("Cannot chart %s; unsupported object type" % source)

def _handle_magic_line(line, cell, parser):
  """ Helper function for handling magic command lines given a parser with handlers set. """
  ipy = _ipython.get_ipython()
  args = parser.parse(line, ipy.user_ns)
  if args:
    try:
      return args.func(vars(args), cell)
    except Exception as e:
      return e.message
  return None


def _extract_storage_api_response_error(message):
  """ A helper function to extract user-friendly error messages from service exceptions.

  Args:
    message: An error message from an exception. If this is from our HTTP client code, it
        will actually be a tuple.

  Returns:
    A modified version of the message that is less cryptic.
  """
  try:
    if len(message) == 3:
      # Try treat the last part as JSON
      data = json.loads(message[2])
      return data['error']['errors'][0]['message']
  except Exception:
    pass
  return message

