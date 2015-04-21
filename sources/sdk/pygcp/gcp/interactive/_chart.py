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
import time as _time

try:
  import IPython as _ipython
  import IPython.core.magic as _magic
except ImportError:
  raise Exception('This module can only be loaded in ipython.')

from gcp._util import JSONEncoder as _JSONEncoder
from gcp._util import print_exception_with_last_stack as _print_exception_with_stack
from ._utils import _get_data


@_magic.register_line_cell_magic
def chart(line, cell=None):
  parser = argparse.ArgumentParser(prog='chart')
  subparsers = parser.add_subparsers(help='chart sub-commands')
  for chart_type in ['annotation', 'area', 'bars', 'bubbles', 'calendar', 'candlestick', 'columns',
                     'combo', 'gauge', 'geo', 'histogram', 'line', 'map', 'org', 'paged_table',
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
  fields = ','.join(args['field']) if args['field'] else '*'

  _HTML_TEMPLATE = """
    <div class="bqgc" id="bqgc_%s">
    </div>
    <script>
          require(['extensions/charting', 'element!bqgc_%s'],
              function(charts, dom) {
                  charts.render(dom, {chartStyle:'%s', dataName:'%s', fields:'%s'}, %s, %s);
              }
          );
    </script>
  """
  div_id = str(int(round(_time.time())))
  source = args['data']
  chart_type = args['chart']
  count = 25 if chart_type == 'paged_table' else -1
  data = _get_data(source, fields, 0, count)
  return _ipython.core.display.HTML(
    _HTML_TEMPLATE % (div_id, div_id, chart_type, source, fields, chart_options,
                      _json.dumps(data, cls=_JSONEncoder)))


@_magic.register_line_magic
def _get_chart_data(line):
  try:
    args = line.strip().split()
    source = args[0]
    fields = args[1]
    first_row = int(args[2]) if len(args) > 2 else 0
    count = int(args[3]) if len(args) > 3 else -1
    data = _get_data(source, fields, first_row, count)
  except Exception, e:
    _print_exception_with_stack(e)
    data = {}

  return _ipython.core.display.JSON(_json.dumps({'data': data}, cls=_JSONEncoder))

