## -*- coding: utf-8 -*-
##
## formatters.py
##
## Author:   Toke Høiland-Jørgensen (toke@toke.dk)
## Date:     16 oktober 2012
## Copyright (c) 2012, Toke Høiland-Jørgensen
##
## This program is free software: you can redistribute it and/or modify
## it under the terms of the GNU General Public License as published by
## the Free Software Foundation, either version 3 of the License, or
## (at your option) any later version.
##
## This program is distributed in the hope that it will be useful,
## but WITHOUT ANY WARRANTY; without even the implied warranty of
## MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
## GNU General Public License for more details.
##
## You should have received a copy of the GNU General Public License
## along with this program.  If not, see <http://www.gnu.org/licenses/>.

import pprint, sys, csv, math

from .settings import settings
from .util import cum_prob, frange
from functools import reduce

PLOT_KWARGS = (
    'alpha',
    'antialiased',
    'color',
    'dash_capstyle',
    'dash_joinstyle',
    'drawstyle',
    'fillstyle',
    'label',
    'linestyle',
    'linewidth',
    'lod',
    'marker',
    'markeredgecolor',
    'markeredgewidth',
    'markerfacecolor',
    'markerfacecoloralt',
    'markersize',
    'markevery',
    'pickradius',
    'solid_capstyle',
    'solid_joinstyle',
    'visible',
    'zorder'
    )

class Formatter(object):

    def __init__(self, output):
        if isinstance(output, str):
            if output == "-":
                self.output = sys.stdout
            else:
                self.output = open(output, "w")
        else:
            self.output = output

    def format(self, results):
        sys.stderr.write("No output formatter selected.\nTest data is in %s (use with -i to format).\n" % results.dump_file)

DefaultFormatter = Formatter


class OrgTableFormatter(Formatter):
    """Format the output for an Org mode table. The formatter is pretty crude
    and does not align the table properly, but it should be sufficient to create
    something that Org mode can correctly realign."""

    def format(self, results):
        name = results.meta("NAME")

        if not results:
            self.output.write(str(name) + " -- empty\n")
        keys = list(settings.DATA_SETS.keys())
        header_row = [name] + keys
        self.output.write("| " + " | ".join(header_row) + " |\n")
        self.output.write("|-" + "-+-".join(["-"*len(i) for i in header_row]) + "-|\n")

        def format_item(item):
            if isinstance(item, float):
                return "%.2f" % item
            return str(item)

        for row in results.zipped(keys):
            self.output.write("| ")
            self.output.write(" | ".join(map(format_item, row)))
            self.output.write(" |\n")



class CsvFormatter(Formatter):
    """Format the output as csv."""

    def format(self, results):
        name = results.meta("NAME")

        if not results:
            return

        writer = csv.writer(self.output)
        keys = list(settings.DATA_SETS.keys())
        header_row = [name] + keys
        writer.writerow(header_row)

        def format_item(item):
            if item is None:
                return ""
            return str(item)

        for row in results.zipped(keys):
            writer.writerow(list(map(format_item, row)))

class PlotFormatter(Formatter):

    def __init__(self, output):
        self.output = output
        try:
            import matplotlib, numpy
            # If saving to file, try our best to set a proper backend for
            # matplotlib according to the output file name. This helps with
            # running matplotlib without an X server.
            if output != "-":
                if output.endswith('.svg') or output.endswith('.svgz'):
                    matplotlib.use('svg')
                elif output.endswith('.ps') or output.endswith('.eps'):
                    matplotlib.use('ps')
                elif output.endswith('.pdf'):
                    matplotlib.use('pdf')
                elif output.endswith('.png'):
                    matplotlib.use('agg')
                else:
                    raise RuntimeError("Unrecognised file format for output '%s'" % output)
            import matplotlib.pyplot as plt
            self.plt = plt
            self.np = numpy
            self._init_plots()
        except ImportError:
            raise RuntimeError("Unable to plot -- matplotlib is missing! Please install it if you want plots.")


    def _load_plotconfig(self, plot):
        if not plot in settings.PLOTS:
            raise RuntimeError("Unable to find plot configuration '%s'" % plot)
        config = settings.PLOTS[plot]
        if 'parent' in config:
            parent_config = settings.PLOTS[config['parent']]
            parent_config.update(config)
            return parent_config
        return config

    def _init_plots(self):
        self.config = self._load_plotconfig(settings.PLOT)
        getattr(self, '_init_%s_plot' % self.config['type'])()

    def _init_timeseries_plot(self, config=None, axis=None):
        if axis is None:
            axis = self.plt.gca()
        if config is None:
            config = self.config

        if 'dual_axes' in config and config['dual_axes']:
            second_axis = self.plt.axes(axis.get_position(), sharex=axis, frameon=False)
            second_axis.yaxis.tick_right()
            second_axis.yaxis.set_label_position('right')
            second_axis.yaxis.set_offset_position('right')
            second_axis.xaxis.set_visible(False)
            config['axes'] = [axis,second_axis]
        else:
            config['axes'] = [axis]


        unit = [None]*len(config['axes'])
        for s in config['series']:
            if 'axis' in s and s['axis'] == 2:
                a = 1
            else:
                a = 0
            s_unit = settings.DATA_SETS[s['data']]['units']
            if unit[a] is not None and s_unit != unit[a]:
                raise RuntimeError("Plot axis unit mismatch: %s/%s" % (unit[a], s_unit))
            unit[a] = s_unit

        axis.set_xlabel('Time')
        for i,u in enumerate(unit):
            config['axes'][i].set_ylabel(unit[i])

    def _init_cdf_plot(self, config=None, axis=None):
        if axis is None:
            axis = self.plt.gca()
        if config is None:
            config = self.config

        unit = None
        for s in config['series']:
            s_unit = settings.DATA_SETS[s['data']]['units']
            if unit is not None and s_unit != unit:
                raise RuntimeError("Plot axis unit mismatch: %s/%s" % (unit, s_unit))
            unit = s_unit

        axis.set_xlabel(unit)
        axis.set_ylabel('Cumulative probability')
        axis.set_ylim(0,1)
        config['axes'] = [axis]


    def _init_meta_plot(self):
        self.configs = []
        for i,subplot in enumerate(self.config['subplots']):
            axis = self.plt.subplot(len(self.config['subplots']),1,i+1, sharex=self.plt.gca())
            config = self._load_plotconfig(subplot)
            self.configs.append(config)
            getattr(self, '_init_%s_plot' % config['type'])(config=config, axis=axis)
            if i < len(self.config['subplots'])-1:
                axis.set_xlabel("")


    def _do_timeseries_plot(self, results, config=None, axis=None):
        if axis is None:
            axis = self.plt.gca()
        if config is None:
            config = self.config

        axis.set_xlim(0, settings.TOTAL_LENGTH)
        data = []
        for i in range(len(config['axes'])):
            data.append([])

        for s in config['series']:
            if 'smoothing' in s:
                smooth=s['smoothing']
            else:
                smooth = False
            kwargs = {}
            for k in PLOT_KWARGS:
                if k in s:
                    kwargs[k] = s[k]

            y_values = results.series(s['data'], smooth)
            if 'axis' in s and s['axis'] == 2:
                a = 1
            else:
                a = 0
            data[a] += y_values
            for r in settings.SCALE_DATA:
                data[a] += r.series(s['data'], smooth)
            config['axes'][a].plot(results.x_values,
                   y_values,
                   **kwargs)

        if 'scaling' in config:
            btm,top = config['scaling']
        else:
            btm,top = 0,100

        for a in range(len(config['axes'])):
            self._do_scaling(config['axes'][a], data[a], btm, top)

        self._do_legend(config)

    def _do_cdf_plot(self, results, config=None, axis=None):
        if axis is None:
            axis = self.plt.gca()
        if config is None:
            config = self.config

        data = []
        max_value = 0.0
        for s in config['series']:
            s_data = results.series(s['data'])
            if 'cutoff' in config:
                # cut off values from the beginning and end before doing the
                # plot; for e.g. pings that run long than the streams, we don't
                # want the unloaded ping values
                start,end = config['cutoff']
                s_data = s_data[int(start/settings.STEP_SIZE):-int(end/settings.STEP_SIZE)]
            d = sorted([x for x in s_data if x is not None])
            max_value = max([max_value]+d)
            data.append(d)

            for r in settings.SCALE_DATA:
                d_s = [x for x in r.series(s['data']) if x is not None]
                if d_s:
                    max_value = max([max_value]+d_s)


        x_values = list(frange(0, max_value, 0.1))

        for i,s in enumerate(config['series']):
            if not data[i]:
                continue
            kwargs = {}
            for k in PLOT_KWARGS:
                if k in s:
                    kwargs[k] = s[k]
            axis.plot(x_values,
                      [cum_prob(data[i], point) for point in x_values],
                      **kwargs)
        self._do_legend(config)


    def _do_meta_plot(self, results):
        for i,config in enumerate(self.configs):
            getattr(self, '_do_%s_plot' % config['type'])(results, config=config)

    def format(self, results):
        if not results:
            return

        getattr(self, '_do_%s_plot' % self.config['type'])(results)

        self._annotate_plot()

        # Since outputting image data to stdout does not make sense, we launch
        # the interactive matplotlib viewer if stdout is set for output.
        # Otherwise, the filename is passed to matplotlib, which selects an
        # appropriate output format based on the file name.
        if self.output == "-":
            self.plt.show()
        else:
            self.plt.savefig(self.output)


    def _annotate_plot(self):
        plot_title = settings.DESCRIPTION
        if 'description' in self.config:
            plot_title += "\n" + self.config['description']
        if settings.TITLE:
            plot_title += "\n" + settings.TITLE
        self.plt.suptitle(plot_title, fontsize=14)

        annotation_string = "Local/remote: %s/%s - Time: %s - Length/step: %ds/%.2fs" % (
            settings.LOCAL_HOST, settings.HOST,
            settings.TIME,
            settings.LENGTH, settings.STEP_SIZE)
        self.plt.suptitle(annotation_string,
                          x=0.5,
                          y=0.005,
                          horizontalalignment='center',
                          verticalalignment='bottom',
                          fontsize=8)

    def _do_legend(self, config):
        axes = config['axes']

        # Each axis has a set of handles/labels for the legend; combine them
        # into one list of handles/labels for displaying one legend that holds
        # all plot lines
        handles, labels = reduce(lambda x,y:(x[0]+y[0], x[1]+y[1]),
                                 [a.get_legend_handles_labels() for a in axes])

        # Shrink the current subplot by 20% in the horizontal direction, and
        # place the legend on the right of the plot.
        for a in axes:
            box = a.get_position()
            a.set_position([box.x0, box.y0, box.width * 0.8, box.height])


            kwargs = {}
            if 'legend_title' in config:
                kwargs['title'] = config['legend_title']

            a.legend(handles, labels,
                     bbox_to_anchor=(1.05, 1.0),
                     loc='upper left', borderaxespad=0.,
                     prop={'size':'small'},
                     **kwargs)

    def _do_scaling(self, axis, data, btm, top):
        """Scale the axis to the selected bottom/top percentile"""
        data = [x for x in data if x is not None]
        top_percentile = self.np.percentile(data, top)*1.05
        btm_percentile = self.np.percentile(data, btm)*0.95
        axis.set_ylim(ymin=btm_percentile, ymax=top_percentile)