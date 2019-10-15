#!/bin/bash

# Tests for the wad-tweak project.
# Copyright (C)2019 Steven Elliott
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA
# 02110-1301, USA.

# Semi-strict mode.

set -eo pipefail
# For bash 4.3 and earlier empty arrays fail with "set -u".
if [[ $(( 10*BASH_VERSINFO[0] + BASH_VERSINFO[1] )) -ge 44 ]]
then
    set -u
fi

# Globals

bname="${0##*/}"                    # Basename of this script.
dname="${0%/*}"                     # Directory that this script is in.
root=$(realpath "$dname/../..")     # Project root.
test_data="$root/test/data"         # Test data files.
tmp_dir="/tmp/wad-tweak-$bname.$$"  # Temp directory
doom2_wad_dirs=("/usr/local/doom"   # Places here *doom2.wad can be found.
    "/usr/share/doom" "$HOME/doom")
doom2_wad_names=("doom2.wad"        # *doom2.wad names.
    "freedoom2.wad")

# For a common error message for Python 2 and 3.
out_fix="sed \"s|^\(^[a-z0-9-]*\.py: error:\).*$|\1 too few arguments|g\""

# Scripts to test.
l="$root/bin/wad-to-lump.py"
s="$root/bin/wad-shuffle-dir.py"

# wad-to-lump.py tests.

wtl_tests=(
    # Test WAD to both output directory and output WAD.
    w-in-wad                t
    "$l -svfo \$actual_dir/out.wad -d \$actual_dir/out-dir \$source_dir/in.wad"

    # Test directory to both output directory and output WAD.
    w-in-dir                t
    "$l -svfo \$actual_dir/out.wad -d \$actual_dir/out-dir \$source_dir/in-dir"

    # Same as test w-in-dir, but lumps only (-l).
    w-in-dir-lumps          t
    "$l -lsvfo \$actual_dir/out.wad -d \$actual_dir/out-dir \$source_dir/in-dir"

    # Same as test w-in-dir, but with changes.
    w-in-dir-changes        t
    "$l -svfo \$actual_dir/out.wad -d \$actual_dir/out-dir \$source_dir/in-dir \
        __eureka=\"the-eureka\" gl_map01=@ gl_pvs gl_ssect=:\$source_dir/gl_ssect \
        notindir=\"the-notindir\" "

    # Same as test w-in-dir-changes, but once (-1).
    w-in-dir-changes-once   t
    "$l -1svfo \$actual_dir/out.wad -d \$actual_dir/out-dir \$source_dir/in-dir \
        __eureka=\"the-eureka\" gl_map01=@ gl_pvs gl_ssect=:\$source_dir/gl_ssect \
        notindir=\"the-notindir\" "

    # Same as test w-in-dir-changes, but invert (-i).
    w-in-dir-changes-inv    t
    "$l -isvfo \$actual_dir/out.wad -d \$actual_dir/out-dir \$source_dir/in-dir \
        __eureka=\"the-eureka\" gl_map01=@ gl_pvs gl_ssect=:\$source_dir/gl_ssect \
        notindir=\"the-notindir\" "

    # Same as test w-in-dir, but with groups, regexes and an add. Also -i.
    w-in-dir-groups         t
    "$l -isvfo \$actual_dir/out.wad -d \$actual_dir/out-dir \$source_dir/in-dir \
        _standard_ \"GL_S.*\" +added=\"the-added\" \
        notindir=\"the-notindir\" "

    # Similar to w-in-wad, but with namespace support (-n).
    w-in-wad-ns             t
    "$l -nsvfo \$actual_dir/out.wad -d \$actual_dir/out-dir \$source_dir/in.wad"

    # Similar to w-in-dir, but with namespace support (-n).
    w-in-dir-ns             t
    "$l -nsvfo \$actual_dir/out.wad -d \$actual_dir/out-dir \$source_dir/in-dir"

    # A command line option that not supported.
    w-bad-option            f
    "$l -v --bad-option" )

# wad-shuffle-dir.py tests

wsd_tests=(
    # A command line option that not supported.
    s-bad-option            f
    "$s -v --bad-option" )

# All of the above tests in a flat array. The three values for each test
# (offset to relative to start):
#   0 - test name
#   1 - if success is expected
#   2 - the test

all_tests=( "${wtl_tests[@]}" "${wsd_tests[@]}" )

# Functions

function cleanup()
{
    if [[ -d $tmp_dir ]]
    then
        rm -rf "$tmp_dir"
    fi
}

### Main ###

# Create the temporary directory.
if ! mkdir "$tmp_dir"
then
    echo "Could not make temporary directory \"$tmp_dir\"." 1>&2
    exit 1
fi
echo "Test output is in \"$tmp_dir\"."
echo

# Find the path to *doom2.wad.
for doom2_wad_dir in "${doom2_wad_dirs[@]}"
do
    for doom2_wad_name in "${doom2_wad_names[@]}"
    do
        doom2_wad_path="$doom2_wad_dir/$doom2_wad_name"
        if [[ -f $doom2_wad_path ]]
        then
            break 2
        else
            doom2_wad_path=""
        fi
    done
done

if [[ -z $doom2_wad_path ]]
then
    echo "Can't find doom2.wad. Some wad-shuffle-dir.py tests will fail."
    doom2_wad_path="/cant/find/doom2.wad"
fi

if ! type -P deutex &> /dev/null
then
    echo "Can't find deutex. Some wad-shuffle-dir.py tests will fail."
fi

# Run the tests
test_count=$(( ${#all_tests[@]} / 3 ))
successes=0
failures=0
for (( test_index=0 ; test_index < ${#all_tests[@]}; test_index += 3 ))
do
    # Read the the values in for each test.
    test_name="${all_tests[$test_index]}"
    success_expected="${all_tests[$test_index+1]/f/}"
    test="${all_tests[$test_index+2]}"

    # Move repeated spaces in "test" for aesthetic reasons.
    last_test=""
    while [[ "$test" != "$last_test" ]]
    do
        last_test="$test"
        test="${test//  / }"
    done

    # Directories which will be compared.
    # shellcheck disable=SC2034
    source_dir="$test_data/source/$test_name"
    expected_dir="$test_data/expected/$test_name"
    actual_dir="$tmp_dir/$test_name"
    mkdir -p "$actual_dir"

    echo "Test $test_name:"
    echo "$test"

    # A list of errors encountered. Successful if empty.
    errors=()

    # This is where the test is actually run.
    if eval "$test" 2\>\&1 \| "$out_fix" > "$actual_dir/out.txt"
    then
        if [[ -z $success_expected ]]
        then
            errors+=("Exit code unexpectedly zero")
        fi
    else
        if [[ -n $success_expected ]]
        then
            errors+=("Exit code unexpectedly non-zero")
        fi
    fi

    # Compare the output created to the expected directory.

    # Test by recursively diffing.
    if ! diff -ru "$expected_dir" "$actual_dir"
    then
        errors+=("Output and expected did not match")
    fi

    if [[ ${#errors[@]} -gt 0 ]]
    then
        vars=(source_dir expected_dir actual_dir)
        for var in "${vars[@]}"
        do
            echo -e "$var:\t${!var}"
        done
        # Comma separated with a space (", "). Error messages should not
        # contain "%" or "*".
        # shellcheck disable=SC2086
        errors_comma_sep=$(IFS=%; j=${errors[*]}; echo ${j//%/, })
        echo -e "Errors:\t\t$errors_comma_sep"
        let ++failures
    else
        # Pre-increment used for counters to avoid non-zero exit with value 0.
        let ++successes
    fi
    echo
done

if [[ $failures -eq 0 ]]
then
    echo "All $test_count tests passed." 1>&2
else
    echo "$failures of $test_count tests failed." 1>&2
    exit 1
fi

# Cleanup here instead of always with a "trap" since temporary files are
# helpful when the test fails.
cleanup
