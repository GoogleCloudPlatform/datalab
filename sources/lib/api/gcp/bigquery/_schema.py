# Copyright 2015 Google Inc. All rights reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License"); you may not use this file except
# in compliance with the License. You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software distributed under the License
# is distributed on an "AS IS" BASIS, WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express
# or implied. See the License for the specific language governing permissions and limitations under
# the License.

"""Implements Table and View Schema APIs."""

import datetime
import pandas


class Schema(list):
  """Represents the schema of a BigQuery table as a flattened list of objects representing fields.

   Each field object has name, data_type, mode and description properties. Nested fields
   get flattened with their full-qualified names. So a Schema that has an object A with nested
   field B will be represented as [(name: 'A', ...), (name: 'A.b', ...)].
  """

  class Field(object):
    """ Represents a single field in a Table schema.

    This has the properties:

    - name: the flattened, full-qualified name of the field.
    - data_type: the type of the field as a string ('INTEGER', 'BOOLEAN', 'FLOAT', 'STRING'
       or 'TIMESTAMP').
    - mode: the mode of the field; 'NULLABLE' by default.
    - description: a description of the field, if known; empty string by default.

     """

    # TODO(gram): consider renaming data_type member to type. Yes, it shadows top-level
    # name but that is what we are using in __str__ and __getitem__ and is what is used in BQ.
    # The shadowing is unlikely to cause problems.
    def __init__(self, name, data_type, mode='NULLABLE', description=''):
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
      """ Compare two schema field objects for equality (ignoring description). """
      return self.name == other.name and self.data_type == other.data_type\
          and self.mode == other.mode

    def __str__(self):
      """ Returns the schema field as a string form of a dictionary. """
      return "{ 'name': '%s', 'type': '%s', 'mode':'%s', 'description': '%s' }" % \
             (self.name, self.data_type, self.mode, self.description)

    def __repr__(self):
      """ Returns the schema field as a string form of a dictionary. """
      return str(self)

    def __getitem__(self, item):
      # TODO(gram): Currently we need this for a Schema object to work with the Parser object.
      # Eventually if we change Parser to only work with Schema (and not also with the
      # schema dictionaries in query results) we can remove this.

      if item == 'name':
        return self.name
      if item == 'type':
        return self.data_type
      if item == 'mode':
        return self.mode
      if item == 'description':
        return self.description

  @staticmethod
  def _from_dataframe(dataframe, default_type='STRING'):
    """
      Infer a BigQuery table schema from a Pandas dataframe. Note that if you don't explicitly set
      the types of the columns in the dataframe, they may be of a type that forces coercion to
      STRING, so even though the fields in the dataframe themselves may be numeric, the type in the
      derived schema may not be. Hence it is prudent to make sure the Pandas dataframe is typed
      correctly.

    Args:
      dataframe: The DataFrame.
      default_type : The default big query type in case the type of the column does not exist in
          the schema. Defaults to 'STRING'.
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

  @staticmethod
  def from_dataframe(dataframe, default_type='STRING'):
    """
      Infer a BigQuery table schema from a Pandas dataframe. Note that if you don't explicitly set
      the types of the columns in the dataframe, they may be of a type that forces coercion to
      STRING, so even though the fields in the dataframe themselves may be numeric, the type in the
      derived schema may not be. Hence it is prudent to make sure the Pandas dataframe is typed
      correctly.

    Args:
      dataframe: The DataFrame.
      default_type : The default big query type in case the type of the column does not exist in
          the schema. Defaults to 'STRING'.
    Returns:
      A Schema.
    """
    return Schema(Schema._from_dataframe(dataframe, default_type=default_type))

  @staticmethod
  def _from_list(data):
    """
    Infer a BigQuery table schema from a list. The list must be non-empty and be a list
    of dictionaries (in which case the first item is used), or a list of lists. In the latter
    case the type of the elements is used and the field names are simply 'Column1', 'Column2', etc.

    Args:
      data: The list of dictionaries or lists.
    Returns:
      A list of dictionaries containing field 'name' and 'type' entries, suitable for use in a
          BigQuery Tables resource schema.
    """
    if not data:
      return []

    def _get_type(value):
      if isinstance(value, datetime.datetime):
        return 'TIMESTAMP'
      elif isinstance(value, bool):
        return 'BOOLEAN'
      elif isinstance(value, float):
        return 'FLOAT'
      elif isinstance(value, int):
        return 'INTEGER'
      else:
        return 'STRING'

    datum = data[0]
    if isinstance(datum, dict):
      return [{'name': key, 'type': _get_type(datum[key])} for key in datum.keys()]
    else:
      return [{'name': 'Column%d' % (i + 1), 'type': _get_type(datum[i])}
              for i in range(0, len(datum))]

  @staticmethod
  def from_list(data):
    """
    Infer a BigQuery table schema from a list. The list must be non-empty and be a list
    of dictionaries (in which case the first item is used), or a list of lists. In the latter
    case the type of the elements is used and the field names are simply 'Column1', 'Column2', etc.

    Args:
      data: The list of dictionaries or lists.
    Returns:
      A Schema for the list.
    """
    return Schema(Schema._from_list(data))

  @staticmethod
  def from_data(source):
    """Creates a table/view schema from its JSON representation, a list of data, or a Pandas
       dataframe.

    Args:
      source: the Pandas Dataframe or list of data from which to infer the schema, or
          a definition of the schema as a list of dictionaries with 'name' and 'type' entries
          and possibly 'mode' and 'description' entries. Only used if no data argument was provided.
          'mode' can be 'NULLABLE', 'REQUIRED' or 'REPEATED'. For the allowed types, see:
          https://cloud.google.com/bigquery/preparing-data-for-bigquery#datatypes
    Returns:
      A Schema for the data.
    """
    if isinstance(source, pandas.DataFrame):
      return Schema.from_dataframe(source)
    elif isinstance(source, list):
      # Inspect the list - if each entry is a dictionary with name and type entries,
      # then use it directly; else infer from it.
      if all([isinstance(d, dict) and 'name' in d and 'type' in d for d in source]):
        return Schema(source)
      else:
        return Schema.from_list(source)
    else:
      raise Exception('Cannot create a schema from %s' % str(source))

  def __init__(self, definition=None):
    """Initializes a Schema from its raw JSON representation, a Pandas Dataframe, or a list.

    Args:
      definition: a definition of the schema as a list of dictionaries with 'name' and 'type'
          entries and possibly 'mode' and 'description' entries. Only used if no data argument was
          provided. 'mode' can be 'NULLABLE', 'REQUIRED' or 'REPEATED'. For the allowed types, see:
          https://cloud.google.com/bigquery/preparing-data-for-bigquery#datatypes
    """
    super(Schema, self).__init__()
    self._map = {}
    self._bq_schema = definition
    self._populate_fields(definition)

  def __getitem__(self, key):
    """Provides ability to lookup a schema field by position or by name.
    """
    if isinstance(key, basestring):
      return self._map.get(key, None)
    return list.__getitem__(self, key)

  def _add_field(self, name, data_type, mode='NULLABLE', description=''):
    field = Schema.Field(name, data_type, mode, description)
    self.append(field)
    self._map[name] = field

  def find(self, name):
    """ Get the index of a field in the flattened list given its (fully-qualified) name.

    Args:
      name: the fully-qualified name of the field.
    Returns:
      The index of the field, if found; else -1.
    """
    for i in range(0, len(self)):
      if self[i].name == name:
        return i
    return -1

  def _populate_fields(self, data, prefix=''):
    for field_data in data:
      name = prefix + field_data['name']
      data_type = field_data['type']
      self._add_field(name, data_type, field_data.get('mode', None),
                      field_data.get('description', None))

      if data_type == 'RECORD':
        # Recurse into the nested fields, using this field's name as a prefix.
        self._populate_fields(field_data.get('fields'), name + '.')

  def __str__(self):
    """ Returns a string representation of the non-flattened form of the schema. """
    # TODO(gram): We should probably return the flattened form. There was a reason why this is
    # not but I don't remember what it was. Figure that out and fix this.
    return str(self._bq_schema)

  def __eq__(self, other):
    """ Compares two schema for equality. """
    other_map = other._map
    if len(self._map) != len(other_map):
      return False
    for name in self._map.iterkeys():
      if name not in other_map:
        return False
      if not self._map[name] == other_map[name]:
        return False
    return True

  def __ne__(self, other):
    """ Compares two schema for inequality. """
    return not(self.__eq__(other))
