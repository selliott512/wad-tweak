#!/usr/bin/env python
# SPDX-License-Identifier: BSD-3-Clause
#
# wad2lump - Convert  WAD files and directories to and from each other
#
# This utility can take a WAD file as input and produce a directory that
# contains one file for each region in the WAD file. The directory will be
# referred to as a "WAD directory". WAD directories can also act as input.
# It is also possible to produce a WAD file as output. Changes can optionally
# be applied in order to change the contents or existence of particular regions.

from __future__ import print_function

# Imports

import argparse
import bisect
import os
import re
import struct
import sys

# Globals

# Command line arguments as a hash map.
args      = {} # Command line arguments.

# Pattern used region files.
file_patt = re.compile("^(\d+)-(\S+)$")

# The names of the indexes for "regions".
index_names = ("Offset", "Count", "Size", "Name", "File", "Contents", "IsLump")

# True if the input argument is a directory.
in_is_dir = False

# Region names that are not lumps.
non_lumps = {"header", "dir", "notindir"}

# Format used for output (-s option).
region_fmt  = "%10s %.0s%10s %8s %.0s%.0s%6s"

# A list of regions for the WAD file. Each regions tuple has the following
# layout by index:
#   0 offset
#   1 number
#   2 size
#   3 name
#   4 file_name
#   5 contents
#   6 is_lump
regions   = []

# The type of the WAD.
wad_type  = ""

# Possible WAD types.
wad_types = {"IWAD", "PWAD"}

# Functions

# Apply user specified changes.
def apply_changes():
    global regions

    cmap = {}
    self = {}
    for change in args.changes:
        i = change.find("=")
        if i == -1:
            # Delete
            cmap[change.lower()] = None
        else:
            # Add or modify
            name = change[:i].strip().lower()
            cmd = change[i + 1:].strip()
            if cmd[0] == ":":
                # Read from file.
                fhand = open(cmd[1:], "rb")
                value = fhand.read()
                fhand.close()
            elif cmd[0] == "@":
                # Self (the value it currently has).
                value = self
            else:
                value = cmd
            if isinstance(value, str):
                value = value.encode("UTF-8")
            cmap[name] = value

    for region in regions[:]:
        name = region[3].lower()
        if name in cmap:
            value = cmap[name]
            if value is None:
                regions.remove(region)
            else:
                if value != self:
                    region[2] = len(value)
                    region[5] = value
                if args.once:
                    # Delete the next region by the same name.
                    cmap[name] = None

# Write a fatal error message to stderr and exit.
def fatal(msg):
    warn(msg)
    sys.exit(1)

# Print a message to stdout. It's flushed.
def message(msg):
    print(msg)
    sys.stdout.flush()

# Parse the command line arguments and store the result in 'args'.
def parse_args():
    global args

    parser = argparse.ArgumentParser(
        description="Doom WAD files and directories to and from lump files.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    # The following is sorted by long argument.
    parser.add_argument("-1", "--once", action="store_true",
        help="Each changed region should only occur once by name.")
    parser.add_argument("-c", "--case", action="store_true",
        help="Maintain the case of regions.")
    parser.add_argument("-d", "--output-dir",
        help="Output directory. Region files will be created at this " +
        "location.")
    parser.add_argument("-o", "--output",
        help="Output filename. A new WAD will created at this location.")
    parser.add_argument("-f", "--force", action="store_true",
        help="Force. Overwrite existing output.")
    parser.add_argument("-l", "--lumps", action="store_true",
        help="Lumps. Only output actual lumps for -s, --show and " +
             "-d, --output-dir.")
    parser.add_argument("-q", "--quiet", action="store_true",
        help="Quiet (minimum output).")
    parser.add_argument("-s", "--show", action="store_true",
        help="Show everything found.")
    parser.add_argument("-v", "--verbose", action="store_true",
        help="Verbose. Additional debugging information.")
    parser.add_argument("path", metavar="path",
        help="Path to WAD file or regions created by this tool.")
    parser.add_argument("changes", metavar="change", nargs="*",
        help="Changes to apply.")

    args = parser.parse_args()

    return args

# Read the regions, both lump and non-lump, into global "regions" in sorted
# order.
def read_regions():
    global in_is_dir
    global regions
    global wad_type

    in_is_dir = os.path.isdir(args.path)
    if in_is_dir:
        if not os.access(args.path, os.R_OK):
            fatal("Input directory \"" + args.path
                  + "\" does not have read permission.")
        files = os.listdir(args.path)
        files.sort()
        digits = None
        last_num = None
        for fl in files:
            path = os.path.join(args.path, fl)
            if not os.path.isfile(path):
                warn("Ignoring non-file \"" + path + "\".")
                continue
            num_str, region_name = file_patt.match(fl).groups()
            if not digits:
                digits = len(num_str)
            elif len(num_str) != digits:
                warn("Ignoring path \"" + fl + "\" because it's prefixed " +
                     "with \"" + len(num_str) + "\" digits instead of \"" +
                     str(digits))
                continue
            num = int(num_str)
            if num == last_num:
                warn("Ignoring path \"" + fl + "\" because number \"" + num +
                     "\" has already been used.")
                continue
            if region_name == "header":
                if wad_type:
                    warn("Ignoring duplicate header \"" + path + "\".")
                    continue
                fhand =  open(path, "rb")
                wad_type, = unpack_str("4s", fhand.read(4))
                if wad_type not in wad_types:
                    fatal(("Header path \"%s\" is type \"%s\" which is not a known " +
                      "WAD type. Allowed WAD types: %s") % (
                        path, wad_type, str(wad_types)))
                fhand.close()
            bisect.insort(regions, [0, num, os.path.getsize(path), region_name, path,
                                    None, region_name not in non_lumps])
    else:
        try:
            fhand =  open(args.path, "rb")
        except IOError as e:
            fatal("Unable to open \"" + args.path + "\" for read: " + str(e))
        header = fhand.read(12)
        wad_type, directory_entries, directory_offset = unpack_str(
            "<4sII", header)
        if not wad_type in wad_types:
            fatal(("WAD file \"%s\" is type \"%s\" which is not a known " +
                  "WAD type. Allowed WAD types: %s") % (
                      args.path, wad_type, str(wad_types)))

        # Add the header to the list of regions.
        bisect.insort(regions, [0, 0, 12, "header", None, None, False])

        # Add the regions to the list of regions.
        bisect.insort(regions, [directory_offset, 0, directory_entries * 16,
                                "dir", None, None, False])

        # Seek to the regions and start reading regions.
        current_offset = 0
        region_number = 0
        fhand.seek(directory_offset)
        for _ in range(directory_entries):
            dent_bytes = fhand.read(16)
            region_number += 1
            if len(dent_bytes) < 16:
                break # short read
            offset, region_size, region_name = unpack_str(
                "<II8s", dent_bytes)
            region_name = region_name.partition("\x00")[0]
            region = [offset, region_number, region_size, region_name, None, None, True]
            if not region_name:
                if offset or region_size:
                    warn("Region (" + (region_fmt % tuple(region)) + ") has no "
                         + "name, but has an offset or size.")
                continue
            if not offset:
                offset = current_offset
                region[0] = offset
            bisect.insort(regions, region)
            current_offset = offset + region_size
        fhand.close()

        # Add unreferenced regions ("notindir").
        wad_size = os.path.getsize(args.path)
        current_offset = 0
        for region in regions:
            if region[0] > current_offset:
                bisect.insort(regions, [current_offset, 0,
                             region[0] - current_offset, "notindir", None, None, False])
            current_offset = region[0] + region[2]
        # Extra space at the end of the WAD?
        if wad_size > current_offset:
            bisect.insort(regions, [current_offset, 0,
                          wad_size - current_offset, "notindir", None, None, False])

    verbose(str(len(regions)) + " regions read.")

# Similar to unpack, but each bytes value is decoded to a string via UTF-8.
# This helps with Python 2 & 3 support.
def unpack_str(fmt, buff):
    if "s" in fmt:
        # There may be strings to covert.
        return tuple([v.decode("UTF-8") if isinstance(v, bytes) else v
                      for v in struct.unpack(fmt, buff)])
    else:
        # There can be no strings to convert.
        return struct.unpack(fmt, buff)

# Print a warning to stderr. It's flushed.
def warn(msg):
    print(msg, file=sys.stderr)
    sys.stderr.flush()

# Process the regions.
def write_regions():
    global regions

    if not in_is_dir:
        try:
            in_fhand = open(args.path, "rb")
        except IOError:
            # Probably the WAD file couldn't be open for read (test) or read
            # and write (default).
            fatal("Unable to open input file path \"" + args.path + "\".")

    # Prepare the output regions.
    if args.output_dir:
        if os.path.exists(args.output_dir):
            if not args.force:
                fatal("Output directory \"" + args.output_dir +
                      "\" exists, but -f, --force was not specified.")
            if not os.path.isdir(args.output_dir):
                fatal("Output directory \"" + args.output_dir +
                      "\" exists, but is not a directory.")
            if not os.access(args.output_dir, os.W_OK):
                fatal("Output directory \"" + args.output_dir
                      + "\" does not have write permission.")
        else:
            try:
                os.makedirs(args.output_dir)
            except OSError as e:
                fatal("Unable to create output directory \""
                      + args.output_dir + "\": " + str(e))

    # Zero based due to the header.
    digits = len(str(len(regions) - 1))
    file_fmt = "%%0%dd-%%s" % digits
    if args.output:
        count = 0
        offset = 12
        directory = []
        try:
            out_fhand = open(args.output, "wb")
        except IOError as e:
            fatal("Unable to create output WAD \"" + args.output + "\": "
                  + str(e))

        out_fhand.write(struct.pack("<4sII", wad_type.encode("UTF-8"), 0, 0))
    if args.output_dir:
        index = 0
    if args.show:
        print(region_fmt % index_names)
        print(region_fmt % tuple(["-" * len(x) for x in index_names]))
    for region in regions:
        if args.lumps and not region[6]:
            # It's not a region and user only wants lumps.
            continue
        if args.show:
            print(region_fmt % tuple(region))
        if args.output or args.output_dir:
            if region[5]:
                region_contents = region[5]
            else:
                if in_is_dir:
                    try:
                        fhand = open(region[4], "rb")
                    except IOError:
                        # Permission issue with region file?
                        fatal("Unable to open region file path \"" + region[4] + "\"")
                    region_contents = fhand.read()
                    fhand.close()
                else:
                    in_fhand.seek(region[0])
                    region_contents = in_fhand.read(region[2])
        if args.output and region[6]:
            out_fhand.write(region_contents)
            region_name_wad  = region[3] if args.case else region[3].upper()
            directory.append((offset, region[2], region_name_wad))
            count += 1
            offset += region[2]
        if args.output_dir:
            region_name_file = region[3] if args.case else region[3].lower()
            region_file = file_fmt % (index, region_name_file)
            with open(args.output_dir + "/" + region_file, "wb") as out_hand:
                out_hand.write(region_contents)
            index += 1
    if args.output:
        # Write the new directory.
        for dent in directory:
            out_fhand.write(struct.pack("<II8s", *(dent[0:2] + (
                dent[2].encode("UTF-8"),))))
        # Go back to the header to write the directory information.
        out_fhand.seek(4)
        out_fhand.write(struct.pack("<II", count, offset))
        out_fhand.close()

# Log a message to stdout if verbose.
def verbose(msg):
    if args.verbose:
        message(msg)

# Main

parse_args()
read_regions()
apply_changes()
write_regions()
