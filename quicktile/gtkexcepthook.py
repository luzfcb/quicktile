"""Graphical exception handler for PyGTK applications

(c) 2003 Gustavo J A M Carneiro gjc at inescporto.pt
(c) 2004-2005 Filip Van Raemdonck
(c) 2009, 2011, 2017 Stephan Sokolow

http://www.daa.com.au/pipermail/pygtk/2003-August/005775.html
Message-ID: <1062087716.1196.5.camel@emperor.homelinux.net>
"The license is whatever you want."

Instructions: import gtkexcepthook; gtkexcepthook.enable()

Changes from Van Raemdonck version:
 - Switched from auto-enable to gtkexcepthook.enable() to silence PyFlakes
   false positives. (Borrowed naming convention from cgitb)
 - Split out traceback import to silence PyFlakes warning.
 - Started to resolve PyLint complaints

@todo: Polish this up to meet my code formatting and clarity standards.
@todo: Clean up the SMTP support. It's a mess.
@todo: Confirm there isn't any other generally-applicable information that
       could be included in the debugging dump.
@todo: Consider the pros and cons of offering a function which allows
       app-specific debugging information to be registered for inclusion.
"""

__author__ = "Filip Van Daemdonck"
__license__ = "whatever you want"

import inspect, linecache, pydoc, sys
# import traceback
from cStringIO import StringIO
from gettext import gettext as _
from pprint import pformat
from smtplib import SMTP

import pygtk
pygtk.require('2.0')
import gtk, pango

# TODO: Decide what to do with this
# def analyse(exctyp, value, tback):
#     trace = StringIO()
#     traceback.print_exception(exctyp, value, tback, None, trace)
#     return trace

def lookup(name, frame, lcls):
    # TODO: MyPy type signature
    '''Find the value for a given name in the given frame'''
    if name in lcls:
        return 'local', lcls[name]
    elif name in frame.f_globals:
        return 'global', frame.f_globals[name]
    elif '__builtins__' in frame.f_globals:
        builtins = frame.f_globals['__builtins__']
        if isinstance(builtins, dict):
            if name in builtins:
                return 'builtin', builtins[name]
        else:
            if hasattr(builtins, name):
                return 'builtin', getattr(builtins, name)
    return None, []

def analyse(exctyp, value, tback):
    # TODO: MyPy type signature
    import tokenize, keyword

    trace = StringIO()
    nlines = 3
    frecs = inspect.getinnerframes(tback, nlines)
    trace.write('Traceback (most recent call last):\n')
    # pylint: disable=unused-variable
    for frame, fname, lineno, funcname, context, cindex in frecs:
        trace.write('  File "%s", line %d, ' % (fname, lineno))
        args, varargs, varkw, lcls = inspect.getargvalues(frame)

        def readline(lno=[lineno], *args):
            if args:
                print args
            try:
                return linecache.getline(fname, lno[0])
            finally:
                lno[0] += 1
        _all, prev, name, scope = {}, None, '', None
        for ttype, tstr, stup, etup, lin in tokenize.generate_tokens(readline):
            if ttype == tokenize.NAME and tstr not in keyword.kwlist:
                if name:
                    if name[-1] == '.':
                        try:
                            val = getattr(prev, tstr)
                        except AttributeError:
                            # XXX skip the rest of this identifier only
                            break
                        name += tstr
                else:
                    assert not name and not scope
                    scope, val = lookup(tstr, frame, lcls)
                    name = tstr
                try:
                    if val:
                        prev = val
                except:
                    pass
                # TODO
                # print('  found', scope, 'name', name, 'val', val, 'in',
                #       prev, 'for token', tstr)
            elif tstr == '.':
                if prev:
                    name += '.'
            else:
                if name:
                    _all[name] = (scope, prev)
                prev, name, scope = None, '', None
                if ttype == tokenize.NEWLINE:
                    break

        trace.write(funcname +
          inspect.formatargvalues(args, varargs, varkw, lcls,
            formatvalue=lambda v: '=' + pydoc.text.repr(v)) + '\n')
        trace.write(''.join(['    ' + x.replace('\t', '  ')
                             for x in context if x.strip()]))
        if len(_all):
            trace.write('  variables: %s\n' % pformat(_all, indent=3))

    trace.write('%s: %s' % (exctyp.__name__, value))
    return trace

def _info(exctyp, value, tback):
    # TODO: MyPy type signature
    # pylint: disable=no-member
    trace = None
    dialog = gtk.MessageDialog(parent=None, flags=0, type=gtk.MESSAGE_WARNING,
                               buttons=gtk.BUTTONS_NONE)
    dialog.set_title(_("Bug Detected"))
    if gtk.check_version(2, 4, 0) is not None:
        dialog.set_has_separator(False)

    primary = _("<big><b>A programming error has been detected during the "
                "execution of this program.</b></big>")
    secondary = _("It probably isn't fatal, but should be reported to the "
                  "developers nonetheless.")

    try:
        # TODO: Refactor to not use a try/except
        email = feedback  # pylint: disable=undefined-variable
        dialog.add_button(_("Report..."), 3)
    except NameError:
        secondary += _("\n\nPlease remember to include the contents of the "
                       "Details dialog.")
        # could ask for an email address instead...

    try:
        setsec = dialog.format_secondary_text
    except AttributeError:
        raise
        # TODO
        # dialog.vbox.get_children()[0].get_children()[1].set_markup(
        #    '%s\n\n%s' % (primary, secondary))
        # lbl.set_property("use-markup", True)
    else:
        del setsec
        dialog.set_markup(primary)
        dialog.format_secondary_text(secondary)

    dialog.add_button(_("Details..."), 2)
    dialog.add_button(gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE)
    dialog.add_button(gtk.STOCK_QUIT, 1)

    while True:
        resp = dialog.run()
        if resp == 3:
            if trace is None:
                trace = analyse(exctyp, value, tback)

            # TODO: prettyprint, deal with problems in sending feedback, &tc
            # TODO: Refactor to not use a try/except
            try:
                server = smtphost  # pylint: disable=undefined-variable
            except NameError:
                server = 'localhost'

            message = ('From: buggy_application"\nTo: bad_programmer\n'
                'Subject: Exception feedback\n\n%s' % trace.getvalue())

            smtp = SMTP()
            smtp.connect(server)
            smtp.sendmail(email, (email,), message)
            smtp.quit()
            break

        elif resp == 2:
            if trace is None:
                trace = analyse(exctyp, value, tback)

            # Show details...
            details = gtk.Dialog(_("Bug Details"), dialog,
              gtk.DIALOG_MODAL | gtk.DIALOG_DESTROY_WITH_PARENT,
              (gtk.STOCK_CLOSE, gtk.RESPONSE_CLOSE, ))
            details.set_property("has-separator", False)

            textview = gtk.TextView()
            textview.show()
            textview.set_editable(False)
            textview.modify_font(pango.FontDescription("Monospace"))

            swin = gtk.ScrolledWindow()
            swin.show()
            swin.set_policy(gtk.POLICY_AUTOMATIC, gtk.POLICY_AUTOMATIC)
            swin.add(textview)
            details.vbox.add(swin)
            textbuffer = textview.get_buffer()
            textbuffer.set_text(trace.getvalue())

            monitor = gtk.gdk.screen_get_default().get_monitor_at_window(
                dialog.window)
            area = gtk.gdk.screen_get_default().get_monitor_geometry(monitor)
            try:
                w = area.width // 1.6
                h = area.height // 1.6
            except SyntaxError:
                # python < 2.2
                w = area.width / 1.6
                h = area.height / 1.6
            details.set_default_size(int(w), int(h))

            details.run()
            details.destroy()

        elif resp == 1 and gtk.main_level() > 0:
            gtk.main_quit()
            break
        else:
            break

    dialog.destroy()

def enable():  # type: () -> None
    """Call this to set gtkexcepthook as the default exception handler"""
    sys.excepthook = _info


if __name__ == '__main__':
    class TestFodder(object):  # pylint: disable=too-few-public-methods
        """Just something interesting to show in the augmented traceback"""
        y = 'Test'

        def __init__(self): # type: () -> None
            self.z = self  # pylint: disable=invalid-name
    x = TestFodder()
    w = ' e'

    # TODO: Refactor this
    # feedback = 'developer@bigcorp.comp'
    # smtphost = 'mx.bigcorp.comp'
    # 1, x.z.y, f, w

    enable()
    raise Exception(x.z.y + w)

# vim: set sw=4 sts=4 :
