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

"""Google Cloud Platform library - Chart cell magic."""

import argparse
import json as _json
import pandas as pd
import time as _time

try:
  import IPython as _ipython
  import IPython.core.magic as _magic
except ImportError:
  raise Exception('This module can only be loaded in ipython.')

import gcp.bigquery as _bq
from gcp._util import JSONEncoder as _JSONEncoder


@_magic.register_line_cell_magic
def chart(line, cell=None):
  parser = argparse.ArgumentParser(prog='chart')
  subparsers = parser.add_subparsers(help='chart sub-commands')
  for chart_type in ['annotation', 'area', 'bars', 'bubbles', 'calendar', 'candlestick', 'columns',
                     'combo', 'gauge', 'geo', 'histogram', 'line', 'map', 'orgchart', 'paged_table',
                     'pie', 'sankey', 'scatter', 'stepped_area', 'table', 'timeline', 'treemap']:
    subparser = subparsers.add_parser(chart_type, help='generate a %s chart' % chart_type)
    subparser.add_argument('-f', '--field',
                           help='the field(s) to include in the chart', nargs='*')
    subparser.add_argument('data',
                           help='the name of the variable referencing the Table or Query to chart')
    subparser.set_defaults(chart=chart_type)

  parser.format_usage = parser.format_help  # Show full help always
  args = filter(None, line.split())
  try:
    parsed_args = parser.parse_args(args)
    return _chart_cell(vars(parsed_args), cell)
  except Exception as e:
    if e.message:
      print e.message


def _chart_cell(args, cell):
  chart_options = cell if cell and len(cell.strip()) else '{}'
  fields = ','.join(args['field']) if args['field'] else ''

  _HTML_TEMPLATE = """
    <div class="bqgc" id="bqgc_%s">
    </div>
    <script>
          require(['extensions/charting', 'element!bqgc_%s'],
              function(charts, dom) {
                  charts.render("%s", dom, "%s", "%s", %s);
              }
          );
    </script>
  """
  div_id = str(int(round(_time.time())))
  return _ipython.core.display.HTML(
    _HTML_TEMPLATE % (div_id, div_id, args['chart'], args['data'], fields, chart_options))


@_magic.register_line_magic
def _get_chart_data(line):
  try:
    args = line.strip().split()
    name = args[0]
    fields = args[1]
    first_row = int(args[2]) if len(args) > 2 else 0
    count = int(args[3]) if len(args) > 3 else -1

    ipy = _ipython.get_ipython()
    item = ipy.user_ns[name] if name in ipy.user_ns else name
    table = None

    list_list = None
    dict_list = None
    data_frame = None

    if isinstance(item, list):
      if len(item) == 0:
        raise Exception("Cannot chart empty list")

      if isinstance(item[0], dict):
        dict_list = item
      elif isinstance(item[0], list):
        if fields != '*':
          raise Exception("Fields argument not currently supported with lists of lists.")
        list_list = item
      else:
        raise Exception("To chart a list it must contain dictionaries or lists.")
    elif isinstance(item, pd.DataFrame):
      data_frame = item
    elif isinstance(item, basestring):
      table = _bq.table(item)
    else:
      # We don't have direct access to the Query type so we try the below to distinguish between
      # table and query
      try:
        table = item.results()
      except AttributeError:
        table = item

    # Get the schema, either from the table or through inference. This is a secondary check
    # too that if we fell through to assuming a Table, we really have one.
    if table:
      try:
        schema = table.schema()
      except AttributeError:
        raise Exception("Cannot chart %s; unsupported object type" % name)
    else:
      schema = _bq.schema(item)

    # If the fields weren't supplied get them from the schema.
    if fields == '*':
      fields = [f.name for f in schema]
    else:
      fields = fields.split(',')

    # Get the row data. This is type-specific, and we also use different paths depending on
    # whether a count was specified, to make the alternate case more efficient.
    rows = []
    if table:
      gen = table.range(first_row, count) if count >= 0 else table
      rows = [{'c': [{'v': row[c]} for c in fields]} for row in gen]
    elif dict_list:
      gen = dict_list[first_row:first_row + count] if count >= 0 else dict_list
      rows = [{'c': [{'v': row[c]} for c in fields]} for row in gen]
    elif list_list:
      gen = list_list[first_row:first_row + count] if count >= 0 else list_list
      rows = [{'c': [{'v': row[i]} for i in range(0, len(fields))]} for row in gen]
    elif type(data_frame) is not type(None):  # Pandas doesn't like "if dataframe" etc.

      dfslice = data_frame.reset_index(drop=True)[first_row:first_row + count]
      for index, data_frame_row in dfslice.iterrows():
        row = data_frame_row.to_dict()
        for key in row.keys():
          val = row[key]
          if isinstance(val, pd.Timestamp):
            row[key] = val.to_pydatetime()

        rows.append({'c': [{'v': row[c]} for c in fields]})

    else:  # shouldn't happen
      raise Exception("Nothing to chart")

    # Get the column metadata by converting the BQ schema.
    typemap = {
      'STRING': 'string',
      'INTEGER': 'number',
      'FLOAT': 'number',
      'BOOLEAN': 'boolean',
      'TIMESTAMP': 'datetime'
    }
    cols = []
    for col in fields:
      f = schema[col]
      cols.append({'id': f.name, 'label': f.name, 'type': typemap[f.data_type]})

    data = {'cols': cols, 'rows': rows}

  except Exception, e:
    import traceback
    traceback.print_exc()
    print str(e)
    data = {}

  model = {
    'data': data
  }
  return _ipython.core.display.JSON(_json.dumps(model, cls=_JSONEncoder))

