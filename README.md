# wad-tweak

Open source command line tools for tweaking (examining and modifying) Doom WAD files.

See the "doc" directory for license and version information.

### Installation

For all command line tools [Python](https://www.python.org/) 3 is required. For wad-shuffle-dir.py [DeuTex](https://doomwiki.org/wiki/DeuTex) is required in addition to Python.

wad-tweak can be downloaded from GitHub:
* [latest stable version](https://github.com/selliott512/wad-tweak/archive/0.9.5.zip) (recommended)
* [latest version](https://github.com/selliott512/wad-tweak/archive/master.zip)

wad-tweak can be installed by unzipping it to the desired location. Once installed commands can be run directly:
```shell
unzip wad-tweak-0.9.5.zip
wad-tweak-0.9.5/bin/endoom-tool.py ...
wad-tweak-0.9.5/bin/wad-shuffle-dir.py ...
wad-tweak-0.9.5/bin/wad-to-lump.py ...
```
Optionally the path can be set so that the commands can be run from anywhere without specifying the full path. For example:
```shell
unzip -d /opt wad-tweak-0.9.5.zip # Requires root.
PATH="$PATH:/opt/wad-tweak-0.9.5/bin"
endoom-tool.py ...
wad-shuffle-dir.py ...
wad-to-lump.py ...
```

There's small test suite, but you probably don't care about it:
```text
test/bin/test.sh
```

The rest of this document describes each command in detail. They are listed in alphabetical order.

## endoom-tool.py

endoom-tool.py can be used to display, split, cleanup and join ENDOOM lumps.

#### endoom-tool.py Usage

The usage can be seen by passing "-h" to wad-shuffle-dir.py:

```txt
usage: endoom-tool.py (-d | -h | -j JOIN-DIRECTORY | -s SPLIT-DIRECTORY) [-c] [-p] [-q] [-r] [-t] ENDOOM [ENDOOM ...]

Process the specified ENDOOM lumps.

positional arguments:
  ENDOOM                ENDOOM lump to process.

Commands:
  Specify exactly one command option

  -d, --display         Display command. Display the ENDOOM lump. (default: False)
  -h, --help            Help. Show this help message and exit.
  -j JOIN-DIRECTORY, --join JOIN-DIRECTORY
                        Join command. Join the directory previously created by --split to form an ENDOOM lump. (default: None)
  -s SPLIT-DIRECTORY, --split SPLIT-DIRECTORY
                        Split command. Split the ENDOOM lump into foreground, background and text in the specified directory. (default: None)

Options:
  Options that modify command behavior

  -c, --clean           Clean. Make foreground equal to background for spaces, and convert to space when foreground and background is the same color. Recommended when the exact ENDOOM does not need to be maintained. This option has no
                        effect with -j, --join. (default: False)
  -p, --plain           Plain. Disable all ANSI color effects. For -j, --join this means to use white and black instead of what's in the foreground and background files before any other color processing. (default: False)
  -q, --quiet           Quiet. Disable some warnings and noise. (default: False)
  -r, --random-colors   Random colors. Make the colors a hash of two bytes associated with each character in order to make it easier to see inconsistencies that are otherwise hidden. (default: False)
  -t, --tolerant        Tolerate missing data. Missing files and data are considered to be black spaces. (default: False)
```

#### endoom-tool.py Examples

See the comment in `endoom-tool.py` for multiple examples.

Display the ENDOOM lump in file `lumps/endoom.lmp`:
```shell
endoom-tool.py -d lumps/endoom.lmp
```

## wad-shuffle-dir.py

wad-shuffle-dir.py shuffles the lumps for specified lump types and writes the result to a directory. For example, if the sprites lump type was specified via "-sprites" and there were sprite lumps "A", "B" and "C". The result might be "C", "A", "B'. Although the result is strange, flickering, and is visually dissonant it can make for a interesting challenge. The output is a directory that can be passed to ZDoom and its descendants via the "-file" option:
```shell
gzdoom -file output-directory
```
where "output-directory" is created by wad-shuffle-dir.py. "output-directory" can be zipped up to produce a PK3 file.

#### wad-shuffle-dir.py Usage

The usage can be seen by passing "-h" to wad-shuffle-dir.py:

```txt
usage: wad-shuffle-dir.py [-h] [-d DEUTEX_PATH] [-f] [-i] [-k] [-s SEED] [-v]
                          IWAD OUT-DIR [LUMP [LUMP ...]]

Shuffle lumps in Doom IWADs and write to a directory.

positional arguments:
  IWAD                  IWAD file.
  OUT-DIR               Output directory.
  LUMP                  Lump types to select. (default: ['sprites'])

optional arguments:
  -h, --help            show this help message and exit
  -d DEUTEX_PATH, --deutex-path DEUTEX_PATH
                        Path to "deutex". (default: deutex)
  -f, --force           Force. Write to OUT-DIR even if it exists. (default:
                        False)
  -i, --invert          Invert the lump types specified. (default: False)
  -k, --keep            Keep the temporary directory. (default: False)
  -s SEED, --seed SEED  Seed for the random number generator. (default: None)
  -v, --verbose         Verbose output. (default: False)
```

#### wad-shuffle-dir.py Examples

##### Simple

Shuffle the sprites in "doom2.wad" in order to create a shuffled output directory at "/tmp/shuffled-sprites":
```shell
wad-shuffle-dir.py doom2.wad /tmp/shuffled-sprites
```

##### Complicated

Shuffle the flats, sounds and sprites lumps in "doom2.wad" in order to create a shuffled output directory "/tmp/shuffled". Keep temporary files (-k), run verbosely (-v) and forcefully overwrite the output directory (-f) at "/tmp/shuffled":
```shell
wad-shuffle-dir.py -kvf doom2.wad /tmp/shuffled flats sprites sounds
```

## wad-to-lump.py

wad-to-lump.py can be used to examine and modify WAD files. WAD files are made up of lumps as well as other portions of the WAD file that are not lumps which wad-to-lump.py collectively refers to as "regions". wad-to-lump.py can:
* Show the regions in a WAD file or input directory (-s, --show option).
* Create a new WAD file (-o, --output option).
* Create an output directory containing one file per region (-d, --output-dir option).
* Apply changes to the regions.

There are other tools that have similar functionality such as [DeuTex](https://doomwiki.org/wiki/DeuTex), [WadZip](https://www.doomworld.com/forum/topic/44058-wadzip/) and [XWE](https://www.doomworld.com/xwe/), but wad-to-lump.py has the advantage of being simple, recent and Python based.

When showing (-s, --show option) the regions in a WAD file a table is displayed showing the offset of each region, its size, name and whether it's a lump. A region is considered to be a lump if and only if it appears in the WAD directory ("dir" at the end of the table):
```txt
wad-to-lump.py -s comcon.wad
    Offset       Size     Name IsLump
    ------       ----     ---- ------
         0         12   header  False
        12       4000   ENDOOM   True
      4012      29808    DEMO1   True
     33820          0     E1M4   True
     33820       2740   THINGS   True
     36560      24010 LINEDEFS   True
     60570      75990 SIDEDEFS   True
    136560       5748 VERTEXES   True
    142308      32124     SEGS   True
    174432       4000 SSECTORS   True
    178432      27972    NODES   True
    206404      11648  SECTORS   True
    218052      25088   REJECT   True
    243140      15590 BLOCKMAP   True
    258730       2284   D_E1M4   True
    261014      66888   CREDIT   True
    327902        256      dir  False
```

When output is to a WAD file (-o, --output option) the output will match the input exactly other than changes that are requested explicitly, if any, and the fact that the WAD directory will be in ascending order, which it was likely to have been anyway. Also, null entries in the directory will be removed.

When output is to a directory the files will be named sequentially so that it's possible to recreate the original input WAD file by simply concatenating the files in lexicographical order. For example:
```txt
wad-to-lump.py -d /tmp/comcon comcon.wad

ls -l /tmp/comcon
total 348
-rw-rw-r--. 1 sle sle    12 Jul 27 17:01 00-header
-rw-rw-r--. 1 sle sle  4000 Jul 27 17:01 01-endoom
-rw-rw-r--. 1 sle sle 29808 Jul 27 17:01 02-demo1
-rw-rw-r--. 1 sle sle     0 Jul 27 17:01 03-e1m4
-rw-rw-r--. 1 sle sle  2740 Jul 27 17:01 04-things
-rw-rw-r--. 1 sle sle 24010 Jul 27 17:01 05-linedefs
-rw-rw-r--. 1 sle sle 75990 Jul 27 17:01 06-sidedefs
-rw-rw-r--. 1 sle sle  5748 Jul 27 17:01 07-vertexes
-rw-rw-r--. 1 sle sle 32124 Jul 27 17:01 08-segs
-rw-rw-r--. 1 sle sle  4000 Jul 27 17:01 09-ssectors
-rw-rw-r--. 1 sle sle 27972 Jul 27 17:01 10-nodes
-rw-rw-r--. 1 sle sle 11648 Jul 27 17:01 11-sectors
-rw-rw-r--. 1 sle sle 25088 Jul 27 17:01 12-reject
-rw-rw-r--. 1 sle sle 15590 Jul 27 17:01 13-blockmap
-rw-rw-r--. 1 sle sle  2284 Jul 27 17:01 14-d_e1m4
-rw-rw-r--. 1 sle sle 66888 Jul 27 17:01 15-credit
-rw-rw-r--. 1 sle sle   256 Jul 27 17:01 16-dir

cat /tmp/comcon/* > /tmp/comcon-recreated.wad
```

One or more changes can optionally be given at the end of the command line. Changes take the following form:
* *region=string* regions named "region" will have their contents changed to string "string"
* *region=:file* regions named "region" will have their contents changed to the contents of file "file"
* *region*=@ regions named "region" will have their contents changed to their current contents (a no-op except when option -1, --once is given)
* *region* regions named "region" will be deleted

If the change is preceeded by "+" then a lump is added instead of changing the existing lumps.

#### wad-to-lump.py Usage

The usage can be seen by passing "-h" to wad-to-lump.py:

```txt
usage: wad-to-lump.py [-h] [-c] [-x] [-f] [-i] [-l] [-n] [-r] [-1] [-o OUTPUT]
                      [-p] [-d OUTPUT_DIR] [-q] [-s] [-v]
                      path [change [change ...]]

Doom WAD files and directories to and from lump files.

positional arguments:
  path                  Path to WAD file or regions created by this tool.
  change                Changes to apply. (default: None)

optional arguments:
  -h, --help            show this help message and exit
  -c, --case            Maintain the case of regions. (default: False)
  -x, --dir-names       Output (eXamine) the lump names in the directory in
                        directory order separated by spaces. Only applicable
                        if a directory is read. (default: False)
  -f, --force           Force. Overwrite existing output. (default: False)
  -i, --invert          Invert. Invert the meaning of bare (no "=") lumps.
                        (default: False)
  -l, --lumps           Lumps. Only output actual lumps for -s, --show and -d,
                        --output-dir. (default: False)
  -n, --namespace       Namespace support. Organize output by namespace.
                        (default: False)
  -r, --offset-order    If true then order the output directory based on the
                        offset of the lumps. By default the output directory
                        will have the same order as the input directory.
                        (default: False)
  -1, --once            Each changed region should only occur once by name.
                        (default: False)
  -o OUTPUT, --output OUTPUT
                        Output filename. A new WAD will created at this
                        location. (default: None)
  -p, --in-place        In place. The input WAD and output WAD are the same.
                        (default: False)
  -d OUTPUT_DIR, --output-dir OUTPUT_DIR
                        Output directory. Region files will be created at this
                        location. (default: None)
  -q, --quiet           Quiet (minimum output). (default: False)
  -s, --show            Show everything found. (default: False)
  -v, --verbose         Verbose. Additional statistical information
                        (recommended). (default: False)
```

#### wad-to-lump.py Examples

##### Simple

Show (-s) the regions in "comcon.wad":
```shell
wad-to-lump.py -s comcon.wad
```

##### Standard

Sometimes level editors will add extraneous lumps and space that is not in the WAD directory (shown as "notindir" by wad-to-lump.py). To remove such regions of the WAD file so that only the minimal, or standard, lumps remain the following can be run:
```shell
wad-to-lump.py -vip comcon.wad _standard_
```
A helpful mnemonic is that only the VIP (important) lumps should remain, which are the following 11 lumps:
```shell
Offset       Size      Name IsLump
------       ----      ---- ------
     0         12    header  False
    12          0      E1M4   True
    12       2740    THINGS   True
  2752      24010  LINEDEFS   True
 26762      75990  SIDEDEFS   True
102752       5748  VERTEXES   True
108500      32124      SEGS   True
140624       4000  SSECTORS   True
144624      27972     NODES   True
172596      11648   SECTORS   True
184244      25088    REJECT   True
209332      15590  BLOCKMAP   True
224922        176    waddir  False
```
Notice that the non-standard "CREDIT" lump was removed. The options are verbose (-v), invert (-i) and in-place (-p). Verbose (-v) gives helpful information about the number of lumps. Invert (-i) inverts the way changes work so that so that only specified lumps (ones in the "_standard_" group in this case) are included. In-place (-p) means to edit the input file rather than creating a new file.

##### Namespace

Doom WADs sometimes have namespaces marked by empty lumps with pattern "namespace_START" and "namespace_END". When the namespace option (-n) is passed the namespace will be indicated for show (-s), and subdirectories will be created for the namespace when writing to a directory (-d). For example, to see only the namespace markers ("_ns_" group) in "freedoom2.wad" as well as the implied namespace (-n):
```shell
wad-to-lump.py -lvins freedoom2.wad _ns_
```
Which shows (-s) the following:
```shell
    Offset       Size    NS      Name IsLump
    ------       ----    --      ---- ------
  13516048          0     S   S_START   True
  17919264          0     S     S_END   True
  17919264          0     P   P_START   True
  17919264          0  P/P1  P1_START   True
  27736780          0  P/P1    P1_END   True
  27736780          0  P/P2  P2_START   True
  27736780          0  P/P2    P2_END   True
  27736780          0  P/P3  P3_START   True
  27736780          0  P/P3    P3_END   True
  27736780          0     P     P_END   True
  27736780          0     F   F_START   True
  27736780          0  F/F1  F1_START   True
  28691148          0  F/F1    F1_END   True
  28691148          0  F/F2  F2_START   True
  28691148          0  F/F2    F2_END   True
  28691148          0  F/F3  F3_START   True
  28691148          0  F/F3    F3_END   True
  28691148          0     F     F_END   True
```
Only lumps are included in the above output due to the lumps (-l) option. When writing to a directory (-d) lumps between "F3_START" and "F3_END" would end up in subdirectory "f/f3" relative to the output directory (-d). Notice the "NS" column.

##### Adding

It's possible to change the lumps in various ways as shown in the previous examples. If the change is preceded by "+" then a new lump is added instead of changing the existing lumps. For example, to add the contents of "mybehavior.o", which was compiled by the ACC compiler, as the "BEHAVIOR" lump to "comcon.wad":
```shell
wad-to-lump.py -vp comcon.wad +behavior=:mybehavior.o
```

##### Directory Names

To see the lump names in the directory in directory order (-x, --dir-names option):
```shell
wad-to-lump.py -vx comcon.wad
Directory names: ENDOOM DEMO1 E1M4 THINGS LINEDEFS SIDEDEFS VERTEXES SEGS SSECTORS NODES SECTORS REJECT BLOCKMAP D_E1M4 CREDIT
 17 regions read        ( 15 lumps,   2 non-lumps) from WAD       "comcon.wad".
 17 regions not written ( 15 lumps,   2 non-lumps).
```

##### Lump Groups

In the above examples "\_standard\_" makes an appearance as a lump group - a token that can be passed as a change that represents a group of lumps. Lump groups are defined relative to the original plain vanilla Doom. See https://zdoom.org/wiki/WAD for an explanation of each lump. An alphabetical list of change groups along with their definitions:

* **_base_**: The 6 non-built lumps in a standard plain vanilla Doom PWAD. These lumps are sufficient for GZDoom. Lumps: `_name_, THINGS, LINEDEFS, SIDEDEFS, VERTEXES, SECTORS`
* **_built_**: The 5 built (node builder) lumps in a standard plain vanilla Doom PWAD. There are other kinds of built nodes, but not in the original Doom. Lumps: `SEGS, SSECTORS, NODES, REJECT, BLOCKMAP`
* **_name_**: The name lump. This should be the first lump. Lumps: `E\dM\d|MAP\d\d`
* **_ns_**: Empty lumps that mark the begin and end of each namespace. Lumps; `.*_(START|END)`
* **_standard_**: The 11 standard lumps in a standard plain vanilla Doom PWAD. Lumps: `_name_, THINGS, LINEDEFS, SIDEDEFS, VERTEXES, SEGS, SSECTORS, NODES, SECTORS, REJECT, BLOCKMAP`

##### Complicated

An example to demonstrate many options at once. Verbosely (-v) show (-s) the regions, but only if they are lumps (-l) in the previously created "comcon" directory. Write output to output directory (-d) "comcon2" and to output WAD file (-o) "comcon2.wad". Replace region "THINGS" with the contents of file "things-file". Replace the contents of region "DEMO01" with string "This is a demo". Delete region "SECTORS". Use the original region name case for the files created (-c). If the output directory already exists then overwrite it (-f). If a changed region occurs more than once then only keep the first occurrence (-1):
```shell
wad-to-lump.py -vslfc1 -d comcon2 -o comcon2.wad comcon things=:things-file demo1="This is a demo" sectors
```
