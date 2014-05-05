#!/usr/bin/env python
# -*- coding: utf-8 -*-

from __future__ import unicode_literals

import os
import json
import re
import traceback
import argparse

import logging

import edi

from config import db, export_as_cmd, UnknownFooException, ParseException

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("actor-service")

def handle_command(chan, thing_name, args):
    assert db.has_key(thing_name)
    thing = db[thing_name]

    def do():
        dst = db[thing_name].exchange

        payloads = thing.payload(args)
        rkeys = thing.rkey(args)

        print "---> [CONFIG]", "payloads:", payloads, "rkeys:", rkeys

        assert len(payloads) == len(rkeys)

        for p, r in zip(payloads, rkeys):
            success = edi.emit.emit(chan, dst, r, p)
            if success:
                print "---> [?] success=%s" % (success)

        return success

    if hasattr(thing, "expansions"):
        print "~~~~ [EXPAND] orig:", thing_name, args

        for thing_name, args in [ ex.split(None, 1) for ex in thing.expansions(args) if ex]:
            print "~~~~ [EXPAND] *", thing_name, args
            handle_command(chan, thing_name, args)
    else:
        do()

class ArgumentParserError(Exception):
    pass

class ThrowingArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise ArgumentParserError(message)

def parse_args(args):
    """Argparse the top level arguments. Throw exceptions instead of sys.exit"""
    parser = ThrowingArgumentParser(description="Actor Service", add_help=False)

    choices = ["act"] + [x.name for x in db.values()]

    parser.add_argument("--help",
                        default=False,
                        nargs="?",
                        choices=choices,
                        help="Help message")

    parser.add_argument("actor", choices=choices, nargs="?", help="Actor")
    parser.add_argument("args", nargs=argparse.REMAINDER, help="Actor Arguments")

    result = parser.parse_args(args)
    result.help_message = parser.format_help()

    return result

def cmd_args(c, a):
    """Handle all cases in which the arguments may be fucked up"""

    if c == "act":
        s = a.split(None, 1)
        if len(s) == 2:
            c = s[0]
            a = a.split()
        elif len(s) == 1:
            c = s[0]
            a = ("--help", s[0])
        else:
            c = ""
            a = ("--help",)
        return c,a
    else:
        return cmd_args("act", " ".join((c, a)))

def main():
    with edi.Manager() as e:
        def reply(args, msg):
            print args, msg
            if args.has_key("user"):
                edi.emit.msg_reply(e.chan,
                                   src=args["src"],
                                   user=args["user"],
                                   msg=msg)

        @edi.edi_cmd(e, "list")
        def list(**args):
            reply(args, "act " + " ".join(export_as_cmd))

        @edi.edi_cmd(e, "act")
        def act(**args):
            try:
                c, a = cmd_args(args["cmd"], args["args"])
                a = parse_args(a)

                if a.help in db.keys():
                    reply(args, db[a.help].help())
                elif a.help == None:
                    reply(args, a.help_message)
                elif a.actor in db.keys():
                    handle_command(e.chan, c, " ".join(a.args))

            except ArgumentParserError, ex:
                reply(args, ex)

            except UnknownFooException:
                reply(args, "Unknown Foo")

            except ParseException:
                reply(args, "Couldn't parse that")

            except Exception, ex:
                print "~~~~ EXCEPTION in callback: ", ex
                traceback.print_exc()

        for cmd in export_as_cmd:
            e.register_command(act, cmd)

        e.run()

main()
