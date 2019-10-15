#!/usr/bin/env python3
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
import collections
import os
import re
import struct
import sys

# Globals

# Command line arguments as a hash map.
args      = {} # Command line arguments.

# Matches the directory leading up to the final path element.
dir_patt = re.compile("^.*/")

# Match region files.
file_patt = re.compile("^(\d+)-(\S+)$")

# The names of the indexes for "regions".
index_names = ("Offset", "Count", "Size", "NS", "Name", "File", "Contents", "IsLump")

# True if the input argument is a directory.
in_is_dir = False

# Groups (sets) of lumps that can be used to apply_changes. Each group name is
# prefixed and suffixed with "_". Since regexes are a type of group in the sense
# that they may match more one lump regexes are a possible value for each key.
lump_groups = {
    # The name lump. This should be the first lump.
    "_name_"    : "E\dM\d|MAP\d\d",

    # Empty lumps that mark the begin and end of each namespace.
    "_ns_"      : ".*_(START|END)",

    # The ten standard lumps that should be in all WADs in this order preceded
    # by the empty name lump.
    "_standard_": ("_name_", "THINGS", "LINEDEFS", "SIDEDEFS", "VERTEXES",
                   "SEGS", "SSECTORS", "NODES", "SECTORS", "REJECT",
                   "BLOCKMAP")}

# Match map names.
name_patt = re.compile("E\dM\d|MAP\d\d")

# Region names that are not lumps.
non_lumps = {"header", "dir", "notindir"}

# From offset to the start of a namespace. Initial default namespace is "".
offset_to_namespace = {0:""}

# Template used for "region_fmt".
region_fmt_template  = "%10s %.0s%10s _NS_%9s %.0s%.0s%6s"

# Format used for output (-s option).
region_fmt = None

# Indexes into each region tuple.
r_offset    = 0
r_number    = 1
r_size      = 2
r_namespace = 3
r_name      = 4
r_file_name = 5
r_contents  = 6
r_is_lump   = 7

# A list of regions tuples. See above for the layout.
regions   = []

# The type of the WAD. Default to PWAD.
wad_type  = "PWAD"

# Possible WAD types.
wad_types = {"IWAD", "PWAD"}

# Functions

# Apply user specified changes.
def apply_changes():
    global regions

    if not len(args.changes):
        return
    amap = collections.OrderedDict()
    cmap = collections.OrderedDict()
    self = {}
    changes = args.changes
    while True:
        new_changes = []
        # True if a substitution happened, which requires another pass.
        subst = False
        for change in changes:
            if change in lump_groups:
                subst = True
                lump_group = lump_groups[change]
                if isinstance(lump_group, str):
                    new_changes.append(lump_group)
                else:
                    new_changes += lump_group
            else:
                new_changes.append(change)
        if not subst:
            # No more substitutions - done.
            break
        changes = new_changes
    for change in changes:
        i = change.find("=")
        if i == -1:
            if change[0] == "+":
                fatal("Can not add bare lump \"" + change +
                      "\ - what would the value be?")
            # Delete or add (if -i).
            cmap[re.compile(change, re.IGNORECASE)] = None
        else:
            # Add or modify
            name = change[:i].strip()
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
            if name[0] == "+":
                # For add the pattern is just the string given.
                amap[name[1:]] = value
            else:
                # Ignore case for changes.
                cmap[re.compile(name, re.IGNORECASE)] = value

    # Apply changes to the regions using cmap.
    max_offset = 0
    max_number = 0
    max_size   = 0
    for region in regions[:]:
        name = region[r_name]
        if (name != "dir") and (region[r_number] > max_number):
            max_offset = region[r_offset]
            max_number = region[r_number]
            max_size   = region[r_size]
        matched = False
        for patt, value in cmap.items():
            if patt.fullmatch(name):
                matched = True
                if value is None:
                    if not args.invert:
                        regions.remove(region)
                else:
                    if value != self:
                        region[r_size] = len(value)
                        region[r_contents] = value
                    if args.once:
                        # Delete the next region that matches the same pattern.
                        cmap[patt] = None
                # Only use the first matching pattern.
                break
        if (not matched) and args.invert:
            regions.remove(region)

    # Add new regions using amap.
    region_number = max_number + 1
    region_offset = max_offset + max_size
    for patt, value in amap.items():
        bisect.insort(regions, [region_offset, region_number, len(value), "",
                                patt, None, value, True])
        region_number += 1
        region_offset += len(value)

# Write a fatal error message to stderr and exit.
def fatal(msg):
    warn(msg)
    sys.exit(1)

# Like a recursive os.listdir where the keys are the base names of the files,
# and the values are paths relative to "dir".
def file_map(dir):
    fmap = {}
    for file in os.listdir(dir):
        path = dir + "/" + file
        if os.path.isdir(path):
            # A directory. Recursively call this method and append.
            fmap.update(file_map(path))
        else:
            # A file. Just add it.
            fmap[file] = path
    return fmap

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
    parser.add_argument("-n", "--namespace", action="store_true",
        help="Namespace support. Organize output by by namespace.")
    parser.add_argument("-f", "--force", action="store_true",
        help="Force. Overwrite existing output.")
    parser.add_argument("-i", "--invert", action="store_true",
        help="Invert. Invert the meaning of bare (no \"=\") lumps.")
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
    global offset_to_namespace
    global region_fmt
    global regions
    global wad_type

    # True if a header has been processed.
    header_seen = False

    # Current namespace as determined by *_START and *_END lumps.
    current_ns = ""

    # Format to use for output.
    region_fmt = region_fmt_template.replace("_NS_", "%5s "
                                             if args.namespace else "%.0s")

    args_plen = len(args.path)
    in_is_dir = os.path.isdir(args.path)
    if in_is_dir:
        # Input is a directory.
        if not os.access(args.path, os.R_OK):
            fatal("Input directory \"" + args.path
                  + "\" does not have read permission.")
        fmap = file_map(args.path)
        digits = None
        last_num = None
        for fl in sorted(fmap.keys()):
            path = fmap[fl]
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
                if header_seen:
                    warn("Ignoring duplicate header \"" + path + "\".")
                    continue
                header_seen = True
                fhand =  open(path, "rb")
                wad_type, = unpack_str("4s", fhand.read(4))
                if wad_type not in wad_types:
                    fatal(("Header path \"%s\" is type \"%s\" which is not a known " +
                      "WAD type. Allowed WAD types: %s") % (
                        path, wad_type, str(wad_types)))
                fhand.close()
            elif region_name.endswith("_START"):
                ns = region_name[0:len(region_name) - len("_START")]
            # The namespace is just the leading portion of the path.
            current_ns = path[args_plen + 1:len(path) - len(fl) - 1]
            bisect.insort(regions, [0, num, os.path.getsize(path), current_ns,
                                    region_name, path, None,
                                    region_name not in non_lumps])
    else:
        # Input is a file.
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
        bisect.insort(regions, [0, 0, 12, "", "header", None, None, False])

        # Add the directory to the list of regions. The count is the max signed
        # 32 bit integer so that the directory is last.
        bisect.insort(regions, [directory_offset, (1 << 31) - 1,
                                directory_entries * 16, "", "dir", None, None,
                                False])

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
            region_ns = current_ns
            if region_name.endswith("_START"):
                prefix = region_name[0:len(region_name) - len("_START")]
                if current_ns:
                    current_ns = current_ns + "/" + prefix
                else:
                    current_ns = prefix
                region_ns = current_ns
                offset_to_namespace[offset] = current_ns
            elif region_name.endswith("_END"):
                prefix = region_name[0:len(region_name) - len("_END")]
                if current_ns:
                    final_ns = dir_patt.sub("", current_ns)
                    if prefix == final_ns:
                        current_ns = current_ns[0: len(current_ns) -
                                                 len("/" + final_ns)]
                        if not current_ns:
                            current_ns = ""
                    else:
                        # This shouldn't happen.
                        warn("Ignoring END \"" + region_name +
                             "\" because the last NS is \"" + final_ns + ".")
                offset_to_namespace[offset] = current_ns

            region = [offset, region_number, region_size, region_ns,
                      region_name, None, None, True]
            if not region_name:
                if offset or region_size:
                    warn("Region (" + (region_fmt % tuple(region)) + ") has no "
                         + "name, but has an offset or size.")
                continue
            if not offset:
                offset = current_offset
                region[r_offset] = offset
            bisect.insort(regions, region)
            current_offset = offset + region_size
        fhand.close()

        # Add unreferenced regions ("notindir").
        wad_size = os.path.getsize(args.path)
        current_offset = 0
        region_ns = current_ns
        offsets = sorted(offset_to_namespace.keys())
        for region in regions:
            if not region[r_size]:
                # Only consider regions that have size.
                continue
            if region[r_offset] > current_offset:
                ns_index = bisect.bisect(offsets, current_offset) - 1
                region_ns = offset_to_namespace[offsets[ns_index]]
                bisect.insort(regions, [current_offset, 0,
                             region[r_offset] - current_offset, region_ns,
                                    "notindir", None, None, False])
            current_offset = region[r_offset] + region[r_size]
            last_size = region[r_size]

        # Extra space at the end of the WAD?
        if wad_size > current_offset:
            bisect.insort(regions, [current_offset, 0,
                          wad_size - current_offset, current_ns, "notindir",
                          None, None, False])

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
    file_fmt = "%%s%%0%dd-%%s" % digits
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
        if args.lumps and not region[r_is_lump]:
            # It's not a region and user only wants lumps.
            continue
        if args.show:
            print(region_fmt % tuple(region))
        if args.output or args.output_dir:
            if region[r_contents]:
                region_contents = region[r_contents]
            else:
                if in_is_dir:
                    try:
                        fhand = open(region[r_file_name], "rb")
                    except IOError:
                        # Permission issue with region file?
                        fatal("Unable to open region file path \"" +
                              region[r_file_name] + "\"")
                    region_contents = fhand.read()
                    fhand.close()
                else:
                    in_fhand.seek(region[r_offset])
                    region_contents = in_fhand.read(region[r_size])
        if args.output and region[r_is_lump]:
            out_fhand.write(region_contents)
            region_name_wad  = region[r_name] if args.case else region[r_name].upper()
            directory.append((offset, region[r_size], region_name_wad))
            count += 1
            offset += region[r_size]
        if args.output_dir:
            region_name_file = region[r_name] if args.case else region[r_name].lower()
            region_prefix = region[r_namespace] if args.case else region[r_namespace].lower() \
                if args.namespace else ""
            if region_prefix:
                region_dir = args.output_dir + "/" + region_prefix
                if not os.path.exists(region_dir):
                    os.makedirs(region_dir)
                region_prefix += "/"
            else:
                region_dir = args.output_dir
            region_file = file_fmt % (region_prefix, index, region_name_file)
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
