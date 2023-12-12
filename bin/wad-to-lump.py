#!/usr/bin/env python3

# SPDX-License-Identifier: GPL-2.0-only
#
# wad-to-lump - Convert  WAD files and directories to and from each other
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
import shutil
import struct
import sys
import tempfile

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

    # The non-built lumps in a standard plain vanilla Doom PWAD. This is the
    # preferred order. These are sufficient for GZDoom.
    "_base_"    : ("_name_", "THINGS", "LINEDEFS", "SIDEDEFS", "VERTEXES",
                   "SECTORS"),

    # The built (node builder) lumps in a standard plain vanilla Doom PWAD.
    # This is the preferred order. There are other kinds of built nodes, but
    # not in the original Doom.
    "_built_"    : ("SEGS", "SSECTORS", "NODES", "REJECT", "BLOCKMAP"),

    # The 11 standard lumps in a standard plain vanilla Doom PWAD. This is the
    # preferred order. See https://zdoom.org/wiki/WAD . Note that BEHAVIOR and
    # SCRIPTS are not included because they are not in the original Doom.
    "_standard_": ("_name_", "THINGS", "LINEDEFS", "SIDEDEFS", "VERTEXES",
                   "SEGS", "SSECTORS", "NODES", "SECTORS", "REJECT",
                   "BLOCKMAP")}

# Match map names.
name_patt = re.compile("E\dM\d|MAP\d\d")

# Region names that are not lumps. "header" is not included since checking
# that the nubmer is 0 is sufficient and allows for actual lumps named "header".
non_lumps = {"waddir", "notindir"}

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

# The name of this script.
this_name= os.path.basename(sys.argv[0]).replace(".py", "")

# The type of the WAD. Default to PWAD.
wad_type  = "PWAD"

# Possible WAD types.
wad_types = {"IWAD", "PWAD"}

# Functions

# Apply user specified changes.
def apply_changes():
    global regions

    # For statistics displayed at the end.
    adds = 0
    modifies = 0
    deletes = 0

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
            if len(change) and change[0] == "+":
                fatal("Can not add bare lump \"" + change +
                      "\ - what would the value be?")
            # Delete or add (if -i).
            if change == "waddir":
                fatal("\"waddir\" may not be deleted explicitly.")
            if not len(change):
                continue
            cmap[re.compile(change, re.IGNORECASE)] = None
        else:
            # Add or modify
            name = change[:i].strip()
            cmd = change[i + 1:].strip()
            if len(cmd) and cmd[0] == ":":
                # Read from file.
                fhand = open(cmd[1:], "rb")
                value = fhand.read()
                fhand.close()
            elif len(cmd) and cmd[0] == "@":
                # Self (the value it currently has). Useful for "-1".
                value = self
            else:
                value = cmd
            if isinstance(value, str):
                value = value.encode("UTF-8")
            if len(name) and name[0] == "+":
                # For add the pattern is just the string given.
                amap[name[1:]] = value
            else:
                if name == "waddir":
                    fatal("\"waddir\" may not be changed explicitly.")
                # Ignore case for changes.
                if not len(name):
                    continue
                cmap[re.compile(name, re.IGNORECASE)] = value

    if "waddir" in amap.keys():
        fatal("\"waddir\" may not be added explicitly.")

    # Apply changes to the regions using cmap.
    max_offset = 0
    max_number = 0
    max_size   = 0
    # Start at index 1 to avoid changing the header.
    for region in regions[1:]:
        name = region[r_name]

        # The following may add items after the current directory, which is ok.
        # When the actual directory is written it will be at the end.
        if region[r_number] > max_number:
            max_offset = region[r_offset]
            max_number = region[r_number]
            max_size   = region[r_size]

        if name == "waddir":
            # Can't be changed.
            continue

        matched = False
        for patt, value in cmap.items():
            if patt.fullmatch(name):
                matched = True
                if value is None:
                    if not args.invert:
                        deletes += 1
                        regions.remove(region)
                else:
                    if value != self:
                        modifies += 1
                        region[r_size] = len(value)
                        region[r_contents] = value
                    if args.once:
                        # Delete the next region that matches the same pattern.
                        cmap[patt] = None
                # Only use the first matching pattern.
                break
        if (not matched) and args.invert:
            deletes += 1
            regions.remove(region)

    # Add new regions using amap.
    region_number = max_number + 1
    region_offset = max_offset + max_size
    for patt, value in amap.items():
        adds += 1
        bisect.insort(regions, new_region(region_offset, region_number,
                        len(value), "", patt, None, value, True))
        region_number += 1
        region_offset += len(value)

    summarize("changed", "%3d adds, %3d modifies, %3d deletes" % (
        adds, modifies, deletes), adds + modifies + deletes, None, None, None)

# Write a fatal error message to stderr and exit.
def fatal(msg):
    warn(msg)
    sys.exit(1)

# Like a recursive os.listdir where the keys are the base names of the files,
# and the values are paths relative to "waddir".
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

# Create a new region and return it.
def new_region(offset,  number, size, namespace, name, file_name, contents,
               is_lump):
    return [offset, number, size, namespace, name, file_name, contents, is_lump]

# Parse the command line arguments and store the result in 'args'.
def parse_args():
    global args

    parser = argparse.ArgumentParser(
        description="Doom WAD files and directories to and from lump files.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    # The following is sorted by long argument.
    parser.add_argument("-c", "--case", action="store_true",
        help="Maintain the case of regions.")
    parser.add_argument("-x", "--dir-names", action="store_true",
        help="Output (eXamine) the lump names in the directory in directory " +
        "order separated by spaces. Only applicable if a directory is read.")
    parser.add_argument("-f", "--force", action="store_true",
        help="Force. Overwrite existing output.")
    parser.add_argument("-i", "--invert", action="store_true",
        help="Invert. Invert the meaning of bare (no \"=\") lumps.")
    parser.add_argument("-l", "--lumps", action="store_true",
        help="Lumps. Only output actual lumps for -s, --show and " +
             "-d, --output-dir.")
    parser.add_argument("-n", "--namespace", action="store_true",
        help="Namespace support. Organize output by namespace.")
    parser.add_argument("-r", "--offset-order", action="store_true",
        help="If true then order the output directory based on the offset " +
        "of the lumps. By default the output directory will have the same " +
        "order as the input directory.")
    parser.add_argument("-1", "--once", action="store_true",
        help="Each changed region should only occur once by name.")
    parser.add_argument("-o", "--output",
        help="Output filename. A new WAD will created at this location.")
    parser.add_argument("-p", "--in-place", action="store_true",
        help="In place. The input WAD and output WAD are the same.")
    parser.add_argument("-d", "--output-dir",
        help="Output directory. Region files will be created at this " +
        "location.")
    parser.add_argument("-q", "--quiet", action="store_true",
        help="Quiet (minimum output).")
    parser.add_argument("-s", "--show", action="store_true",
        help="Show everything found.")
    parser.add_argument("-v", "--verbose", action="store_true",
        help="Verbose. Additional statistical information (recommended).")
    parser.add_argument("path", metavar="path",
        help="Path to WAD file or regions created by this tool.")
    parser.add_argument("changes", metavar="change", nargs="*",
        help="Changes to apply.")

    args = parser.parse_args()

    # Option consistency checks.
    if args.in_place and (args.output or args.output_dir):
        fatal("For in place (-p, --in-place option) output location can not " +
              "be specified.")

    return args

# Read just the names from a directory, or directory file. "file_ref" is
# assumed to be a file name if a string, or a file handle otherwise. "offset"
# is the offset in the file, and "count" is the number of directory entries.
def read_directory(file_ref, offset, count=None):
    # Map file_ref to a file handle.
    if isinstance(file_ref, str):
        # file_ref is a string.
        fhand =  open(file_ref, "rb")
    else:
        # file_ref is a file handle.
        fhand = file_ref

    # Build a list of directory names if requested.
    if args.dir_names:
        dir_names = ""

    # Seek to the directory.
    fhand.seek(offset)

    directory = []
    index = 0
    while True:
        if count and (index >= count):
            # Done.
            break
        dent_bytes = fhand.read(16)
        if len(dent_bytes) < 16:
            break # short read
        offset, region_size, region_name = unpack_str("<II8s", dent_bytes)
        entry = (offset, region_size, region_name.partition("\x00")[0])
        if len(entry) != 3:
            fatal("Entry \"" + str(entry) + "\" does not have expected " +
                  "length 3.")
        if args.dir_names:
            dir_names += " " + entry[2] if dir_names else entry[2]
        directory.append(entry)
        index += 1

    # Close it if it was opened.
    if isinstance(file_ref, str):
        fhand.close()

    if args.dir_names:
        print("Directory names: " + dir_names)

    return directory

# Read the regions, both lump and non-lump, into global "regions" in sorted
# order.
def read_regions():
    global in_is_dir
    global offset_to_namespace
    global region_fmt
    global regions
    global wad_type

    # Current namespace as determined by *_START and *_END lumps.
    current_ns = ""

    # Actual lumps read (regions that are in the directory).
    lumps_read = 0

    # Format to use for output.
    region_fmt = region_fmt_template.replace("_NS_", "%5s "
                                             if args.namespace else "%.0s")

    in_header = False # True if input header seen.
    waddir_count = 0
    num = 0
    last_num = None
    first = True # first iteration
    args_plen = len(args.path)
    in_is_dir = os.path.isdir(args.path)
    if in_is_dir:
        # Input is a directory.
        if not os.access(args.path, os.R_OK):
            fatal("Input directory \"" + args.path
                  + "\" does not have read permission.")
        fmap = file_map(args.path)
        digits = None
        first = True
        for fl in sorted(fmap.keys()):
            path = fmap[fl]
            if not os.path.isfile(path):
                # This shouldn't happen.
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
            last_num = num
            if first:
                if num == 0:
                    # Number 0 is reserved for the header.
                    in_header = True
                    if region_name != "header":
                        fatal("Number 0 must be named \"header\".")
                    fhand =  open(path, "rb")
                    wad_type, = unpack_str("4s", fhand.read(4))
                    if wad_type not in wad_types:
                        fatal(("Header path \"%s\" is type \"%s\" which is not a known " +
                          "WAD type. Allowed WAD types: %s") % (
                            path, wad_type, str(wad_types)))
                    fhand.close()
            elif region_name == "waddir":
                waddir_count += 1
            # The namespace is just the leading portion of the path.
            current_ns = path[args_plen + 1:len(path) - len(fl) - 1]
            is_lump = (region_name not in non_lumps) and (num != 0)
            if is_lump:
                lumps_read += 1
            bisect.insort(regions, new_region(0, num, os.path.getsize(path),
                        current_ns, region_name, path, None, is_lump))
            first = False
        waddir_count_expected = 1 if in_header else 0
        if waddir_count_expected != waddir_count:
            fatal("There must be one \"waddir\" file if there is a \"header\" " +
                  "file, and zero otherwise.")

        if not in_header:
            # If there is no input header then add a stub one now.
            bisect.insort(regions, new_region(0, 0, 12, "", "header", "",
                struct.pack("<4sII", wad_type.encode("UTF-8"), lumps_read, 0),
                False))

            # It's been verified that there is no "waddir", so create a stub
            # for that as well.
            bisect.insort(regions, new_region(0, num + 1, 0, "", "waddir", "",
                struct.pack(""), False))

        if waddir_count and not args.offset_order:
            # Build a map of the directory with an additional element at the end
            # indicating the index into the directory.
            index = 0
            dmap = {}
            directory = read_directory(path, 0)
            for dent in directory:
                low_name = dent[2].lower()
                if low_name in dmap:
                    warn("Directory entry \"" + low_name +
                         "\" found twice. Output may be inaccurate.")
                dmap[low_name] = dent + (index,)
                index += 1

            # Build a list of the region numbers for regions that are lumps
            # (lump_nums_orig), and at the same time build an index correlated list
            # of indexes into the directory (dir_idxs).
            lump_nums_orig = []
            dir_idxs = []
            for region in regions:
                if region[r_is_lump]:
                    lump_nums_orig.append(region[r_number])
                    low_name = region[r_name].lower()
                    if not low_name in dmap:
                        warn("Unable to find region \"" + str(region) +
                              "\" in external \"waddir\" file. Maintaining " +
                              "location of lump. Try deleting the " +
                              "\"waddir\" file if this is not correct.")
                        dir_idxs.append(len(dir_idxs))
                    else:
                        dir_idxs.append(dmap[low_name][3])

            # Build a new list of region numbers (lump_nums_new)
            lump_nums_new = [-1] * len(lump_nums_orig)
            for i in range(len(lump_nums_orig)):
                lump_nums_new[dir_idxs[i]] = lump_nums_orig[i]

            # Apply the new lump numbers to the list of regions.
            unordered_regions = []
            for i in range(len(lump_nums_orig)):
                # Update based on the new sort order.
                region = regions[lump_nums_new[i]]
                region[r_number] = lump_nums_orig[i]

                # Changing a key previously used by "insort" does not
                # automatically cause it to go to the right place. Note it so
                # it can be removed and re-added.
                unordered_regions.append(region)

            # Remove the unordered regions.
            for region in unordered_regions:
                regions.remove(region)

            # Add the unordered regions back.
            for region in unordered_regions:
                bisect.insort(regions, region)
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
        bisect.insort(regions, new_region(0, 0, 12, "", "header", None, None,
                                          False))
        in_header = True

        # Add the directory to the list of regions. The count is the max signed
        # 32 bit integer so that the directory is last.
        bisect.insort(regions, new_region(directory_offset, (1 << 31) - 1,
                        directory_entries * 16, "", "waddir", None, None,
                        False))

        # Seek to the regions and start reading regions.
        current_offset = 0
        region_number = 0
        fhand.seek(directory_offset)

        dir_ents = read_directory(fhand, directory_offset, directory_entries)
        for dir_ent in dir_ents:
            region_number += 1
            offset, region_size, region_name = dir_ent
            if region_name.lower() in non_lumps:
                fatal("Lump name \"" + region_name + "\" is not permitted.")
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

            region = new_region(offset, region_number, region_size, region_ns,
                        region_name, None, None, True)
            if not region_name:
                if offset or region_size:
                    warn("Region (" + (region_fmt % tuple(region)) + ") has no "
                         + "name, but has an offset or size.")
                continue
            if not offset:
                offset = current_offset
                region[r_offset] = offset
            lumps_read += 1
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
                region_number += 1
                ns_index = bisect.bisect(offsets, current_offset) - 1
                region_ns = offset_to_namespace[offsets[ns_index]]
                bisect.insort(regions, new_region(current_offset, region_number,
                             region[r_offset] - current_offset, region_ns,
                             "notindir", None, None, False))
            current_offset = region[r_offset] + region[r_size]
            last_size = region[r_size]

        # Extra space at the end of the WAD?
        if wad_size > current_offset:
            bisect.insort(regions, new_region(current_offset, 0,
                          wad_size - current_offset, current_ns, "notindir",
                          None, None, False))

    # Offset the number of regions.
    extra_reg = 0 if in_header else -2
    summarize("read", None, len(regions) + extra_reg, lumps_read,
              "directory" if in_is_dir else "WAD", args.path)

# Log a summary message if verbose.
def summarize(action, custom, region_count, lump_count, path_type, path):
    if not args.verbose:
        return
    if custom:
        stats = custom
    else:
        stats = "%3d lumps, %3d non-lumps" % (lump_count,
            region_count - lump_count)
    msg = "%3d regions %-11s (%s)" % (region_count, action, stats)
    if path_type is not None:
        direction = "from" if "read" in action else "to"
        msg += " %4s %-9s \"%s\"." % (direction, path_type, path)
    else:
        msg += "."
    verbose(msg)

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

# Log a message to stdout if verbose.
def verbose(msg):
    if args.verbose:
        message(msg)

# Print a warning to stderr. It's flushed.
def warn(msg):
    print(msg, file=sys.stderr)
    sys.stderr.flush()

# Process the regions.
def write_regions():
    global regions

    # Regions written. This can be less than len(regions) if -l, --lumps.
    regions_written = 0

    # Actual lumps written (regions that are in the directory).
    lumps_written = 0

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
    if args.in_place:
        # TODO: This may not be the best way of working with temporary files,
        # but it's good enough.
        out_wad = tempfile.NamedTemporaryFile(prefix=this_name + "-").name
    else:
        out_wad = args.output
    if out_wad:
        count = 0
        offset = 12
        directory = []
        try:
            out_fhand = open(out_wad, "wb")
        except IOError as e:
            fatal("Unable to create output WAD \"" + out_wad + "\": "
                  + str(e))

        out_fhand.write(struct.pack("<4sII", wad_type.encode("UTF-8"), 0, 0))
    if args.output_dir:
        # If -l, --lumps then start at 1 because 0 is only for "header".
        index = 1 if args.lumps else 0
    if args.show:
        print(region_fmt % index_names)
        print(region_fmt % tuple(["-" * len(x) for x in index_names]))
    for region in regions:
        if args.lumps and not region[r_is_lump]:
            # It's not a region and user only wants lumps.
            continue
        regions_written += 1
        if region[r_is_lump]:
            lumps_written += 1
        if args.show:
            print(region_fmt % tuple(region))
        if out_wad or args.output_dir:
            if region[r_contents]:
                region_contents = region[r_contents]
            else:
                if in_is_dir:
                    if not region[r_file_name]:
                        # No file even though directory input - waddir?
                        continue
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
        if args.lumps and not region[r_is_lump]:
            continue
        # For output WAD don't process the header entry, which is number 0, or
        # the directory - we'll deal with that later.
        if out_wad and region[r_number] and (region[r_name] != "waddir"):
            out_fhand.write(region_contents)
            region_name_wad  = region[r_name] if args.case else region[r_name].upper()
            if region[r_is_lump]:
                bisect.insort(directory, (region[r_number], offset, region[r_size],
                                          region_name_wad))
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
    if not in_is_dir:
        in_fhand.close()
    if out_wad:
        # Write the new directory.
        for dent in directory:
            out_fhand.write(struct.pack("<II8s", *(dent[1:3] + (
                dent[3].encode("UTF-8"),))))
        # Go back to the header to write the directory information.
        out_fhand.seek(4)
        out_fhand.write(struct.pack("<II", count, offset))

        if args.in_place:
            out_fhand.flush()
            try:
                shutil.copyfile(out_wad, args.path)
            except IOError as e:
                fatal("Unable to overwrite original WAD \"" + args.path +
                      "\" for in place: " + str(e))

        out_fhand.close()

    rw = regions_written
    lw = lumps_written
    nlw = rw - lw # non lump written
    extra_nl = 2 if args.lumps else 0
    if args.show:
        summarize("shown", None, rw, lw, None, None)
    if args.output or args.in_place:
        out_path = args.path if args.in_place else out_wad
        summarize("written", None, rw + extra_nl, lw, "WAD", out_path)
    if args.output_dir:
        summarize("written", None, rw, lw, "directory", args.output_dir)
    if not (args.show or args.output or args.output_dir or args.in_place):
        summarize("not written", None, rw, lw, None, None)

# Main

parse_args()
read_regions()
apply_changes()
write_regions()
