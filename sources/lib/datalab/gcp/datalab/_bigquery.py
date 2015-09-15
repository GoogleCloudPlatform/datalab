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

"""Google Cloud Platform library - BigQuery IPython Functionality."""

import json
import imp
import re
import sys
import IPython
import IPython.core.display
import IPython.core.magic
import gcp.bigquery
import gcp.data
import gcp._util
import _commands
import _html
import _utils


def _create_sample_subparser(parser):
  sample_parser = parser.subcommand('sample',
      'execute a BigQuery SQL statement and display results or create a named query object')
  sample_parser.add_argument('-q', '--sql', help='the name for this query object')
  sample_parser.add_argument('-c', '--count', type=int, default=10,
                             help='number of rows to limit to if sampling')
  sample_parser.add_argument('-m', '--method', help='the type of sampling to use',
                             choices=['limit', 'random', 'hashed', 'sorted'], default='limit')
  sample_parser.add_argument('-p', '--percent', type=int, default=1,
                             help='For random or hashed sampling, what percentage to sample from')
  sample_parser.add_argument('-f', '--field',
                             help='field to use for sorted or hashed sampling')
  sample_parser.add_argument('-o', '--order', choices=['ascending', 'descending'],
                             default='ascending', help='sort order to use for sorted sampling')
  return sample_parser


def _create_udf_subparser(parser):
  udf_parser = parser.subcommand('udf', 'create a named Javascript UDF module')
  udf_parser.add_argument('-m', '--module', help='the name for this UDF module', required=True)
  return udf_parser


def _create_dry_run_subparser(parser):
  dry_run_parser = parser.subcommand('dryrun',
      'Send a query to BQ in dry run mode to receive approximate usage statistics')
  dry_run_parser.add_argument('-q', '--sql',
                             help='the name of the query to be dry run', required=True)
  return dry_run_parser


def _create_execute_subparser(parser, command):
  execute_parser = parser.subcommand(command,
      'execute a BigQuery SQL statement sending results to a named table')
  execute_parser.add_argument('-nc', '--nocache', help='don\'t used previously cached results',
                              action='store_true')
  execute_parser.add_argument('-m', '--mode', help='table creation mode', default='create',
                              choices=['create', 'append', 'overwrite'])
  execute_parser.add_argument('-l', '--large', help='allow large results',
                              action='store_true')
  execute_parser.add_argument('-q', '--sql', help='name of query to run, if not in cell body',
                              nargs='?')
  execute_parser.add_argument('-d', '--destination', help='target table name',
                              nargs='?')
  return execute_parser


def _create_table_subparser(parser):
  table_parser = parser.subcommand('table', 'view a BigQuery table')
  table_parser.add_argument('-r', '--rows', type=int, default=25,
                            help='rows to display per page')
  table_parser.add_argument('-c', '--cols',
                            help='comma-separated list of column names to restrict to')
  return table_parser


def _create_schema_subparser(parser):
  schema_parser = parser.subcommand('schema', 'view a BigQuery table or view schema')
  schema_parser.add_argument('item', help='the name of, or a reference to, the table or view')
  return schema_parser


def _create_datasets_subparser(parser):
  datasets_parser = parser.subcommand('datasets', 'list the datasets in a BigQuery project')
  datasets_parser.add_argument('-p', '--project',
                               help='the project whose datasets should be listed')
  return datasets_parser


def _create_tables_subparser(parser):
  tables_parser = parser.subcommand('tables', 'list the tables in a BigQuery project or dataset')
  tables_parser.add_argument('-p', '--project',
                             help='the project whose tables should be listed')
  tables_parser.add_argument('-d', '--dataset',
                             help='the dataset to restrict to')
  return tables_parser


def _create_extract_subparser(parser):
  extract_parser = parser.subcommand('extract', 'Extract BigQuery query results or table to GCS')
  extract_parser.add_argument('source', help='the query or table to extract')
  extract_parser.add_argument('-f', '--format', choices=['csv', 'json'], default='csv',
                              help='format to use for the export')
  extract_parser.add_argument('-c', '--compress', action='store_true', help='compress the data')
  extract_parser.add_argument('-H', '--header', action='store_true', help='include a header line')
  extract_parser.add_argument('-d', '--delimiter', default=',', help='field delimiter')
  extract_parser.add_argument('destination', help='the URL of the destination')
  return extract_parser


def _create_load_subparser(parser):
  load_parser = parser.subcommand('load', 'load data into a BigQuery table')
  load_parser.add_argument('-a', '--append', help='append to existing file',
                           action='store_true')
  load_parser.add_argument('-o', '--overwrite', help='overwrite existing file',
                           action='store_true')
  load_parser.add_argument('-f', '--format', help='source format', choices=['json', 'csv'],
                           default='csv')
  load_parser.add_argument('-n', '--skip', help='number of initial lines to skip',
                           type=int, default=0)
  load_parser.add_argument('-s', '--strict', help='reject bad values and jagged lines',
                           action='store_true')
  load_parser.add_argument('-d', '--delimiter', default=',',
                           help='the inter-field delimiter (default ,)')
  load_parser.add_argument('-q', '--quote', default='"',
                           help='the quoted field delimiter (default ")')
  load_parser.add_argument('-i', '--infer', help='attempt to infer schema from source',
                           action='store_true')
  load_parser.add_argument('source', help='URL of the GCS source(s)')
  load_parser.add_argument('table', help='the destination table')
  return load_parser


def _create_bigquery_parser():
  """ Create the parser for the %bigquery magics.

  Note that because we use the func default handler dispatch mechanism of argparse,
  our handlers can take only one argument which is the parsed args. So we must create closures
  for the handlers that bind the cell contents and thus must recreate this parser for each
  cell upon execution.
  """
  parser = _commands.CommandParser.create('bigquery')

  # This is a bit kludgy because we want to handle some line magics and some cell magics
  # with the bigquery command.

  # %%bigquery sample
  sample_parser = _create_sample_subparser(parser)
  sample_parser.set_defaults(
      func=lambda args, cell: _dispatch_handler(args, cell, sample_parser, _sample_cell))

  # %%bigquery dryrun
  dryrun_parser = _create_dry_run_subparser(parser)
  dryrun_parser.set_defaults(
      func=lambda args, cell: _dispatch_handler(args, cell, dryrun_parser,
                                                _dryrun_line, cell_prohibited=True))

  # %%bigquery udf
  udf_parser = _create_udf_subparser(parser)
  udf_parser.set_defaults(
      func=lambda args, cell: _dispatch_handler(args, cell, udf_parser,
                                                _udf_cell, cell_required=True))

  # %%bigquery execute
  execute_parser = _create_execute_subparser(parser, 'execute')
  execute_parser.set_defaults(
      func=lambda args, cell: _dispatch_handler(args, cell,
                                                execute_parser, _execute_cell))

  # %%bigquery pipeline
  pipeline_parser = _create_execute_subparser(parser, 'pipeline')
  pipeline_parser.add_argument('-n', '--name', help='pipeline name')
  pipeline_parser.set_defaults(
    func=lambda args, cell: _dispatch_handler(args, cell,
                                              pipeline_parser, _pipeline_cell))

  # %bigquery table
  table_parser = _create_table_subparser(parser)
  table_parser.set_defaults(
      func=lambda args, cell: _dispatch_handler(args, cell, table_parser,
                                                _table_line, cell_prohibited=True))

  # %bigquery schema
  schema_parser = _create_schema_subparser(parser)
  schema_parser.set_defaults(
      func=lambda args, cell: _dispatch_handler(args, cell,
                                                schema_parser, _schema_line, cell_prohibited=True))

  # %bigquery datasets
  datasets_parser = _create_datasets_subparser(parser)
  datasets_parser.set_defaults(
      func=lambda args, cell: _dispatch_handler(args, cell, datasets_parser,
                                                _datasets_line, cell_prohibited=True))

  # %bigquery tables
  tables_parser = _create_tables_subparser(parser)
  tables_parser.set_defaults(
      func=lambda args, cell: _dispatch_handler(args, cell, tables_parser,
                                                _tables_line, cell_prohibited=True))

  # % bigquery extract
  extract_parser = _create_extract_subparser(parser)
  extract_parser.set_defaults(
      func=lambda args, cell: _dispatch_handler(args, cell, extract_parser,
                                                _extract_line, cell_prohibited=True))

  # %bigquery load
  # TODO(gram): need some additional help, esp. around the option of specifying schema in
  # cell body and how schema infer may fail.
  load_parser = _create_load_subparser(parser)
  load_parser.set_defaults(
      func=lambda args, cell: _dispatch_handler(args, cell, load_parser, _load_cell))
  return parser


_bigquery_parser = _create_bigquery_parser()


@IPython.core.magic.register_line_cell_magic
def bigquery(line, cell=None):
  """Implements the bigquery cell magic for ipython notebooks.

  The supported syntax is:

    %%bigquery <command> [<args>]
    <cell>

  or:

    %bigquery <command> [<args>]

  Use %bigquery --help for a list of commands, or %bigquery <command> --help for help
  on a specific command.
  """
  namespace = {}
  if line.find('$') >= 0:
    # We likely have variables to expand; get the appropriate context.
    namespace = _notebook_environment()

  return _utils.handle_magic_line(line, cell, _bigquery_parser, namespace=namespace)


def _dispatch_handler(args, cell, parser, handler,
                      cell_required=False, cell_prohibited=False):
  """ Makes sure cell magics include cell and line magics don't, before dispatching to handler.

  Args:
    args: the parsed arguments from the magic line.
    cell: the contents of the cell, if any.
    parser: the argument parser for <cmd>; used for error message.
    handler: the handler to call if the cell present/absent check passes.
    cell_required: True for cell magics, False for line magics that can't be cell magics.
    cell_prohibited: True for line magics, False for cell magics that can't be line magics.
  Returns:
    The result of calling the handler.
  Raises:
    Exception if the invocation is not valid.
  """
  if cell_prohibited:
    if cell and len(cell.strip()):
      parser.print_help()
      raise Exception('Additional data is not supported with the %s command.' % parser.prog)
    return handler(args)

  if cell_required and not cell:
    parser.print_help()
    raise Exception('The %s command requires additional data' % parser.prog)

  return handler(args, cell)


def _get_query_argument(args, code=None, env=None):
  sql_arg = args['sql']
  item = _get_notebook_item(sql_arg)
  if isinstance(item, gcp.bigquery._query.Query):
    return item

  # For most magics we want to use the notebook environment; the only exception is the
  # %bigquery pipeline where we want to avoid it to test hermeticity.
  if env is None:
    env = _notebook_environment()
  item, env = gcp.data.SqlModule.get_sql_statement_with_environment(item, env)
  if code:
    exec code in env
  return gcp.bigquery.query(item, args=env)


def _sample_cell(args, code):
  """Implements the bigquery sample cell magic for ipython notebooks.

  Args:
    args: the optional arguments following '%%bigquery sample'.
    code: optional contents of the cell interpreted as Python.
  Returns:
    The results of executing the query converted to a dataframe if no variable
    was specified. None otherwise.
  """

  query = _get_query_argument(args, code)
  count = args['count']
  method = args['method']
  if method == 'random':
    sampling = gcp.bigquery._sampling.Sampling.random(percent=args['percent'], count=count)
  elif method == 'hashed':
    sampling = gcp.bigquery._sampling.Sampling.hashed(field_name=args['field'],
                                                      percent=args['percent'],
                                                      count=count)
  elif method == 'sorted':
    ascending = args['order'] == 'ascending'
    sampling = gcp.bigquery._sampling.Sampling.sorted(args['field'],
                                                      ascending=ascending,
                                                      count=count)
  elif method == 'limit':
    sampling = gcp.bigquery._sampling.Sampling.default(count=count)
  else:
    sampling = gcp.bigquery._sampling.Sampling.default(count=count)

  return query.sample(sampling=sampling)


def _dryrun_line(args):
  """Implements the BigQuery cell magic used to dry run BQ queries.

   The supported syntax is:
   %bigquery dryrun -q|--sql <query identifier>

  Args:
    args: the argument following '%bigquery dryrun'.
  Returns:
    The response wrapped in a DryRunStats object
  """
  query = _get_query_argument(args)

  result = query.execute_dry_run()
  return gcp.bigquery._query_stats.QueryStats(total_bytes=result['totalBytesProcessed'],
                                              is_cached=result['cacheHit'])


def _udf_cell(args, js):
  """Implements the bigquery_udf cell magic for ipython notebooks.

  The supported syntax is:
  %%bigquery udf --module <name>
  <js function>

  Args:
    args: the optional arguments following '%%bigquery udf'.
    declaration: the variable to initialize with the resulting UDF object.
    js: the UDF declaration (inputs and outputs) and implementation in javascript.
  Returns:
    The results of executing the UDF converted to a dataframe if no variable
    was specified. None otherwise.
  """
  module_name = args['module']
  if not module_name:
    raise Exception("Declaration must be of the form %%bigquery udf --module <name>")

  spec_pattern = r'\{\{([^}]+)\}\}'
  spec_part_pattern = r'[a-z_][a-z0-9_]*'
  fn_name_pattern = r'\n([A-Za-z_]\w*)\s*\('
  module = imp.new_module(module_name)

  # Split the cell into chunks that start with '/**' in the first column position.
  # parse the input and output specification, and extract the function name and
  # replace it with 'function'. For now we only allow UDF functions, not support
  # functions, so if there is no input/output specification we raise an exception.
  chunks = ['/**%s' % f for f in ('\n%s' % js).split('\n/**') if len(f.strip())]
  for chunk in chunks:
    m = re.search(fn_name_pattern, chunk)
    if m:
      fn_name = m.group(1)
      if fn_name == 'function':
        raise Exception('UDF functions must be named and cannot be anonymous')
    else:
      raise Exception('Couldn\'t find function')  # TODO(gram): make more actionable

    chunk = chunk.replace('\n%s' % fn_name, '\nfunction')

    header = chunk.split('*/')[0]
    specs = re.findall(spec_pattern, header)
    if len(specs) < 2:
      raise Exception('Each UDF must declare the input row and output emitter parameters '
                      'using valid jsdoc format comments.\n'
                      'The input row param declaration must be typed as {{field:type, field2:type}} '
                      'and the output emitter param declaration must be typed as '
                      'function({{field:type, field2:type}}.')

    inputs = []
    input_spec_parts = re.findall(spec_part_pattern, specs[0], flags=re.IGNORECASE)
    if len(input_spec_parts) % 2 != 0:
      raise Exception('Invalid input row param declaration. The jsdoc type expression must '
                      'define an object with field and type pairs.')
    for n, t in zip(input_spec_parts[0::2], input_spec_parts[1::2]):
      inputs.append((n, t))

    outputs = []
    output_spec_parts = re.findall(spec_part_pattern, specs[1], flags=re.IGNORECASE)
    if len(output_spec_parts) % 2 != 0:
      raise Exception('Invalid output emitter param declaration. The jsdoc type expression must '
                      'define a function accepting an an object with field and type pairs.')
    for n, t in zip(output_spec_parts[0::2], output_spec_parts[1::2]):
      outputs.append((n, t))

    # Finally build the UDF object
    module.__dict__[fn_name] = gcp.bigquery.udf(inputs, outputs, fn_name, chunk)

  sys.modules[module_name] = module
  exec 'import %s' % module_name in _notebook_environment()


def _execute_cell(args, code):
  query = _get_query_argument(args, code)
  return query.execute(args['destination'], table_mode=args['mode'], use_cache=not args['nocache'],
                       allow_large_results=args['large']).results


def _pipeline_cell(args, code):
  query = _get_query_argument(args, code, {})
  print(query.sql)
  result = query.execute_dry_run()
  return gcp.bigquery._query_stats.QueryStats(total_bytes=result['totalBytesProcessed'],
                                              is_cached=result['cacheHit'])


def _table_line(args):
  name = args['table']
  table = _get_table(name)
  if table and table.exists():
    fields = args['cols'].split(',') if args['cols'] else None
    html = _table_viewer(table, rows_per_page=args['rows'], fields=fields)
    return IPython.core.display.HTML(html)
  else:
    return "%s does not exist" % name


def _notebook_environment():
  ipy = IPython.get_ipython()
  return ipy.user_ns


def _get_notebook_item(name):
  """ Get an item from the IPython environment. """
  env = _notebook_environment()
  return gcp._util.get_item(env, name)


def _get_schema(name):
  """ Given a variable or table name, get the Schema if it exists. """
  item = _get_notebook_item(name)
  if not item:
    item = _get_table(name)

  if isinstance(item, gcp.bigquery._schema.Schema):
    return item
  if hasattr(item, 'schema') and isinstance(item.schema, gcp.bigquery._schema.Schema):
    return item.schema
  return None


# An LRU cache for Tables. This is mostly useful so that when we cross page boundaries
# when paging through a table we don't have to re-fetch the schema.
_table_cache = gcp._util.LRUCache(10)


def _get_table(name):
  """ Given a variable or table name, get a Table if it exists.

  Args:
    name: the name of the Table or a variable referencing the Table.
  Returns:
    The Table, if found.
  """
  # If name is a variable referencing a table, use that.
  item = _get_notebook_item(name)
  if isinstance(item, gcp.bigquery._table.Table):
    return item
  # Else treat this as a BQ table name and return the (cached) table if it exists.
  try:
    return _table_cache[name]
  except KeyError:
    table = gcp.bigquery.table(name)
    if table.exists():
      _table_cache[name] = table
      return table
  return None


def _schema_line(args):
  name = args['item']
  schema = _get_schema(name)
  if schema:
    html = _repr_html_table_schema(schema)
    return IPython.core.display.HTML(html)
  else:
    return "%s does not exist" % name


def _render_table(data, fields=None):
  """ Helper to render a list of dictionaries as an HTML display object. """
  return IPython.core.display.HTML(_html.HtmlBuilder.render_table(data, fields))


def _datasets_line(args):
  return _render_table([{'Name': str(dataset)}
                        for dataset in gcp.bigquery.datasets(args['project'])])


def _tables_line(args):
  if args['dataset']:
    datasets = [gcp.bigquery.dataset((args['project'], args['dataset']))]
  else:
    datasets = gcp.bigquery.datasets(args['project'])

  tables = []
  for dataset in datasets:
    tables.extend([{'Name': str(table)} for table in dataset])

  return _render_table(tables)


def _extract_line(args):
  name = args['source']
  source = _get_notebook_item(name)
  if not source:
    source = _get_table(name)

  if not source:
    return 'No such source: %s' % name
  elif isinstance(source, gcp.bigquery._table.Table) and not source.exists():
    return 'Source %s does not exist' % name
  else:

    job = source.extract(args['destination'],
                         format='CSV' if args['format'] == 'csv' else 'NEWLINE_DELIMITED_JSON',
                         compress=args['compress'],
                         field_delimiter=args['delimiter'],
                         print_header=args['header'])
    if job.failed:
      return 'Extract failed: %s' % str(job.fatal_error)
    elif job.errors:
      return 'Extract completed with errors: %s' % str(job.errors)


def _load_cell(args, schema):
  name = args['table']
  table = _get_table(name)
  if not table:
    table = gcp.bigquery.table(name)

  if table.exists():
    if not (args['append'] or args['overwrite']):
      return "%s already exists; use --append or --overwrite" % name
  elif schema:
    table.create(json.loads(schema))
  elif not args['infer']:
    return 'Table does not exist, no schema specified in cell and no --infer flag; cannot load'

  # TODO(gram): we should probably try do the schema infer ourselves as BQ doesn't really seem
  # to be able to do it. Alternatively we can drop the --infer argument and force the user
  # to use a pre-existing table or supply a JSON schema.
  job = table.load(args['source'],
                   append=args['append'],
                   overwrite=args['overwrite'],
                   create=not table.exists(),
                   source_format=('CSV' if args['format'] == 'csv' else 'NEWLINE_DELIMITED_JSON'),
                   skip_leading_rows=args['skip'],
                   allow_jagged_rows=not args['strict'],
                   ignore_unknown_values=not args['strict'],
                   field_delimiter=args['delimiter'],
                   quote=args['quote'])
  if job.failed:
    return 'Load failed: %s' % str(job.fatal_error)
  elif job.errors:
    return 'Load completed with errors: %s' % str(job.errors)


def _table_viewer(table, rows_per_page=25, fields=None):
  """  Return a table viewer.

  Args:
    table: the table to view.
    rows_per_page: how many rows to display at one time.
    fields: an array of field names to display; default is None which uses the full schema.
  Returns:
    A string containing the HTML for the table viewer.
  """
  if not table.exists():
    return "%s does not exist" % str(table)

  _HTML_TEMPLATE = """
    <div class="bqtv" id="%s"></div>
    <div><br />%s %s<br />%s</div>
    <script>
      require(['extensions/charting', 'element!%s'%s],
        function(charts, dom) {
          charts.render(dom,
            {
              chartStyle:"%s",
              dataName:"%s",
              fields:"%s",
              totalRows:%d,
              rowsPerPage:%d,
            }, {}, %s);
        }
      );
    </script>
  """

  if fields is None:
    fields = _utils.get_field_list(fields, table.schema)
  div_id = _html.Html.next_id()
  meta_count = ("rows: %d" % table.length) if table.length >= 0 else ''
  meta_name = str(table) if table.job is None else table.job.id
  meta_data = ''
  if table.job:
    if table.job.cache_hit:
      data_cost = 'cached'
    else:
      bytes = gcp.bigquery._query_stats.QueryStats._size_formatter(table.job.bytes_processed)
      data_cost = '%s processed' % bytes
    meta_data = '(%.1fs, %s)' % (table.job.total_time, data_cost)
  data, total_count = _utils.get_data(table, fields, 0, rows_per_page)

  if total_count < 0:
    # The table doesn't have a length metadata property but may still be small if we fetched less
    # rows than we asked for.
    fetched_count = len(data['rows'])
    if fetched_count < rows_per_page:
      total_count = fetched_count

  chart = 'table' if 0 <= total_count <= rows_per_page else 'paged_table'

  return _HTML_TEMPLATE %\
      (div_id, meta_name, meta_data, meta_count, div_id, _html.Html.get_style_arg('charting.css'),
       chart, str(table), ','.join(fields), total_count, rows_per_page,
       json.dumps(data, cls=gcp._util.JSONEncoder))


def _repr_html_query(query):
  # TODO(nikhilko): Pretty print the SQL
  return _html.HtmlBuilder.render_text(query.sql, preformatted=True)


def _repr_html_query_results_table(results):
  return _table_viewer(results)


def _repr_html_table(results):
  return _table_viewer(results)


def _repr_html_table_schema(schema):
  _HTML_TEMPLATE = """
    <div class="bqsv" id="%s"></div>
    <script>
      require(['extensions/bigquery', 'element!%s'%s],
          function(bq, dom) {
              bq.renderSchema(dom, %s);
          }
      );
    </script>
    """
  id = _html.Html.next_id()
  return _HTML_TEMPLATE % (id, id, _html.Html.get_style_arg('bigquery.css'),
                           json.dumps(schema._bq_schema))


def _repr_html_function_evaluation(evaluation):
  _HTML_TEMPLATE = """
    <div class="bqtv" id="%s"></div>
    <script>
      require(['extensions/bigquery', 'element!%s'],
          function(bq, dom) {
              bq.evaluateUDF(dom, %s, %s);
          }
      );
    </script>
    """
  id = _html.Html.next_id()
  return _HTML_TEMPLATE % (id, id, evaluation.implementation, json.dumps(evaluation.data))


def _register_html_formatters():
  try:
    ipy = IPython.get_ipython()
    html_formatter = ipy.display_formatter.formatters['text/html']

    html_formatter.for_type_by_name('gcp.bigquery._query', 'Query', _repr_html_query)
    html_formatter.for_type_by_name('gcp.bigquery._query_results_table', 'QueryResultsTable',
                                    _repr_html_query_results_table)
    html_formatter.for_type_by_name('gcp.bigquery._table', 'Table', _repr_html_table)
    html_formatter.for_type_by_name('gcp.bigquery._schema', 'Schema', _repr_html_table_schema)
    html_formatter.for_type_by_name('gcp.bigquery._udf', 'FunctionEvaluation',
                                    _repr_html_function_evaluation)
  except TypeError:
    # For when running unit tests
    pass

_register_html_formatters()
