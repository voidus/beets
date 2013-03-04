# This file is part of beets.
# Copyright 2013, Jakob Schnitzer.
#
# Permission is hereby granted, free of charge, to any person obtaining
# a copy of this software and associated documentation files (the
# "Software"), to deal in the Software without restriction, including
# without limitation the rights to use, copy, modify, merge, publish,
# distribute, sublicense, and/or sell copies of the Software, and to
# permit persons to whom the Software is furnished to do so, subject to
# the following conditions:
#
# The above copyright notice and this permission notice shall be
# included in all copies or substantial portions of the Software.

"""Update library's tags using MusicBrainz.
"""
import logging

from beets.plugins import BeetsPlugin
from beets import autotag, library, ui, util

log = logging.getLogger('beets')


def _print_and_apply_changes(lib, item, move, pretend, write):
    changes = {}
    for key in library.ITEM_KEYS_META:
        if item.dirty[key]:
            changes[key] = item.old_data[key], getattr(item, key)
    if not changes:
        return

    # Something changed.
    ui.print_obj(item, lib)
    for key, (oldval, newval) in changes.iteritems():
        ui.commands._showdiff(key, oldval, newval)

    # If we're just pretending, then don't move or save.
    if not pretend:
        # Move the item if it's in the library.
        if move and lib.directory in util.ancestry(item.path):
            lib.move(item)

        if write:
            item.write()
        lib.store(item)


def mbsync_singletons(lib, query, move, pretend, write):
    """Synchronize matching singleton items.
    """
    singletons_query = library.get_query(query, False)
    singletons_query.subqueries.append(library.SingletonQuery(True))
    for s in lib.items(singletons_query):
        if not s.mb_trackid:
            log.info(u'Skipping singleton {0}: has no mb_trackid'
                        .format(s.title))
            continue

        s.old_data = dict(s.record)
        candidates, _ = autotag.match.tag_item(s, search_id=s.mb_trackid)
        match = candidates[0]
        with lib.transaction():
            autotag.apply_item_metadata(s, match.info)
            _print_and_apply_changes(lib, s, move, pretend, write)


def mbsync_albums(lib, query, move, pretend, write):
    """Synchronize matching albums.
    """
    # Process matching albums.
    for a in lib.albums(query):
        if not a.mb_albumid:
            log.info(u'Skipping album {0}: has no mb_albumid'.format(a.id))
            continue

        items = list(a.items())
        for item in items:
            item.old_data = dict(item.record)

        _, _, candidates, _ = \
            autotag.match.tag_album(items, search_id=a.mb_albumid)
        match = candidates[0]     # There should only be one match!

        with lib.transaction():
            autotag.apply_metadata(match.info, match.mapping)
            for item in items:
                _print_and_apply_changes(lib, item, move, pretend, write)

            if not pretend:
                # Update album structure to reflect an item in it.
                for key in library.ALBUM_KEYS_ITEM:
                    setattr(a, key, getattr(items[0], key))

                # Move album art (and any inconsistent items).
                if move and lib.directory in util.ancestry(items[0].path):
                    log.debug(u'moving album {0}'.format(a.id))
                    a.move()


def mbsync_func(lib, opts, args):
    """Command handler for the mbsync function.
    """
    move = opts.move
    pretend = opts.pretend
    write = opts.write
    query = ui.decargs(args)

    mbsync_singletons(lib, query, move, pretend, write)
    mbsync_albums(lib, query, move, pretend, write)


class MBSyncPlugin(BeetsPlugin):
    def __init__(self):
        super(MBSyncPlugin, self).__init__()

    def commands(self):
        cmd = ui.Subcommand('mbsync',
                            help='update metadata from musicbrainz')
        cmd.parser.add_option('-p', '--pretend', action='store_true',
                              help='show all changes but do nothing')
        cmd.parser.add_option('-M', '--nomove', action='store_false',
                              default=True, dest='move',
                              help="don't move files in library")
        cmd.parser.add_option('-W', '--nowrite', action='store_false',
                              default=True, dest='write',
                              help="don't write updated metadata to files")
        cmd.func = mbsync_func
        return [cmd]