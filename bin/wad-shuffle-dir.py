#!/usr/bin/env python

# SPDX-License-Identifier: GPL-2.0-only
#
# wad-shuffle-dir - Shuffle lumps in WAD files
#
# Shuffle lumps of a given type in order to produce a randomized WAD. This
# more of a novelty than a useful tool.

from __future__ import print_function

# Imports

import argparse
import atexit
import os
import random
import shutil
import subprocess
import sys
import tempfile

# Globals

args          = {}  # Command line arguments.
allowed_lumps = (   # Allowed lump types.
    "flats",
    "graphics",
    "musics",
    "patches",
    "sounds",
    "sprites")
iwad_dir      = ""  # Directory that the IWAD is in.
name          = ""  # Basename of this script without the ".py".
temp_dir      = ""  # Temporary directory to extract to.

# Functions

# Cleanup temporary files.
def cleanup():
    common = "temporary directory \"" + temp_dir + "\"."
    if args.keep:
        verbose("Keeping " + common)
        return
    else:
        verbose("Removing " + common)
        shutil.rmtree(temp_dir)

# Write a fatal error message to stderr and exit.
def fatal(msg):
    print(msg, file=sys.stderr)
    sys.stderr.flush()
    sys.exit(1)

# Initialize variables.
def init():
    global iwad_dir
    global name
    global temp_dir

    # Make sure the IWAD exits.
    if not os.path.isfile(args.iwad):
        fatal("IWAD \"" + args.iwad + "\" does not exist.")
    iwad_dir = os.path.dirname(args.iwad)
    verbose("IWAD file           : " + args.iwad)
    verbose("IWAD directory      : " + iwad_dir)

    # Make sure that the output directory can be created.
    if os.path.isdir(args.out_dir):
        if not args.force:
            fatal("Output directory \"" + args.out_dir + "\" already exists, but "
                  + "-f, --force was not specified.")
    else:
        os.makedirs(args.out_dir)
    verbose("Output directory    : " + args.out_dir)

    # Create a temporary directory.
    name = os.path.basename(sys.argv[0]).replace(".py", "")
    temp_dir = tempfile.mkdtemp(prefix=name + "-")
    if not "win" in sys.platform.lower():
        # For case sensitive operating systems (not Windows) convert to a
        # lower case temp_dir to avoid a bug in duetex.
        temp_dir_lower = temp_dir.lower()
        if temp_dir != temp_dir_lower:
            os.mkdir(temp_dir_lower, 0o700)
            os.rmdir(temp_dir)
            temp_dir = temp_dir_lower
    verbose("Temporary directory : " + temp_dir)

    if args.seed:
        random.seed(args.seed)

    # Make sure to clean up the above directories.
    atexit.register(cleanup)

    # Special value "all" means all allowed lumps.
    if len(args.lumps) == 1 and args.lumps[0] == "all":
        args.lumps = allowed_lumps

    # args.lumps should now be a subset of allowed_lumps.
    for lump in args.lumps:
        if lump not in allowed_lumps:
            fatal("Lump \"" + lump + "\" is not allowed. Allowed lump types: "
                  + str(allowed_lumps))

    if args.invert:
        lumps_new = ()
        for lump in allowed_lumps:
            if lump not in args.lumps:
                lumps_new += (lump,)
        args.lumps = lumps_new

# Parse the command line arguments.
def parse_args():
    global args

    parser = argparse.ArgumentParser(
        description="Shuffle lumps in Doom IWADs and write to a directory.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)

    # The following is sorted by long argument.
    parser.add_argument("-d", "--deutex-path", type=str, default="deutex",
        help="Path to \"deutex\".")
    parser.add_argument("-f", "--force", action="store_true",
        help="Force. Write to OUT-DIR even if it exists.")
    parser.add_argument("-i", "--invert", action="store_true",
        help="Invert the lump types specified.")
    parser.add_argument("-k", "--keep", action="store_true",
        help="Keep the temporary directory.")
    parser.add_argument("-s", "--seed", type=str,
        help="Seed for the random number generator.")
    parser.add_argument("-v", "--verbose", action="store_true",
        help="Verbose output.")
    parser.add_argument("iwad", metavar="IWAD",
        help="IWAD file.")
    parser.add_argument("out_dir", metavar="OUT-DIR",
        help="Output directory.")
    parser.add_argument("lumps", metavar="LUMP", nargs="*", default=["sprites"],
        help="Lump types to select.")

    args = parser.parse_args()

# Run "deutex" to extract the lumps.
def run_deutex():
    iwad_arg = "-doom2" if args.iwad.lower().endswith("2.wad") else "-doom"
    dargs = [args.deutex_path, iwad_arg, iwad_dir, "-dir", temp_dir]
    dargs += ["-" + l for l in args.lumps]
    dargs += ["-x", args.iwad]
    verbose("Running: " + " ".join(dargs))

    # Suppress stdout unless verbose.
    rc  = subprocess.call(dargs, stdout=(
        None if args.verbose else open(os.devnull, "w")))
    if rc:
        fatal("Unable to run deutex.")

# Process a lump by copying randomly to the output directory.
def process_lump(lump):
    verbose("Processing lump \"" + lump + "\".")
    sdir = temp_dir + "/" + lump
    if not os.path.isdir(sdir):
        fatal("Source directory \"" + sdir + "\" is missing.")
    ddir = args.out_dir + "/" + lump
    if not os.path.exists(ddir):
        os.mkdir(ddir)

    orig = os.listdir(sdir)
    rnd = orig[:]
    random.shuffle(rnd)
    for i in range(len(orig)):
        shutil.move(sdir + "/" + orig[i], ddir + "/" + rnd[i])

# Process all of the lump types.
def process_lumps():
    for lump in args.lumps:
        process_lump(lump)

# Log a message to stdout if verbose.
def verbose(msg):
    if args.verbose:
        print(msg)

# Main

parse_args()
init()
run_deutex()
process_lumps()
