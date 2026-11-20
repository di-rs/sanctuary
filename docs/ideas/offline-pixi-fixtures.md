# Ship Biggie with a mapping team's offline tools

A mapping team's importer reads 999,999 survey records from a file that
should contain a million. A developer reproduces the missing row on a
Mac. How can a field engineer vary the test on a disconnected Linux
worker? Sanctuary could distribute Biggie, its test data generator, in
the Pixi environment the team already delivers with GDAL. The engineer
could then change a station ID or row count on site and rerun the import.

GDAL documents how to install its mapping tools in a Pixi project.
A robotics engineer evaluating Pixi described delivering updated Debian
packages to disconnected Linux computers on USB drives. For a mapping
crew that works this way, a request for a second test file can mean
another trip.
[GDAL's Pixi guide](https://gdal.org/en/stable/download.html#pixi)
and [the field deployment account](https://github.com/prefix-dev/pixi/discussions/6411)

## Reproduce the missing record

With a CSV-enabled Biggie and GDAL 3.13.3's `ogrinfo` on your path, run
this in an empty directory. The two invented stations alternate throughout
the file. Biggie quotes the station names and writes the first row as data.
[Build and run Biggie](../../packages/biggie/README.md#try-it)

```sh
biggie fields --format csv --delimiter , --fields 2 --lines 1000000 \
  --field-value S07 --field-value 'Pier, East' \
  --field-value S12 --field-value 'Quay "B"' stations.csv
ogrinfo -ro -so stations.csv stations
ogrinfo -ro -so -oo HEADERS=NO stations.csv stations
```

An Apple silicon Mac and an offline Debian 12 x86-64 container on Docker
Desktop generated identical 17,000,000-byte files. By default GDAL used
`S07` and `Pier, East` as column headings. Changing just `S07` in the
generator command on the worker showed when the first record disappeared.
Both inspections exited zero in every case.
[GDAL's CSV header rules](https://gdal.org/en/stable/drivers/vector/csv.html#open-options)

| First station ID | Default feature count | With `HEADERS=NO` |
| --- | ---: | ---: |
| `S07` | 999,999 | 1,000,000 |
| `7` | 1,000,000 | 1,000,000 |
| `007` | 999,999 | 1,000,000 |

## Deliver the generator with GDAL

In the prototype, Rattler-Build packaged both binaries in a local conda
channel, a directory of indexed packages. The trial package was called
`sanctuary-biggie`. With only the version pinned, a fresh Mac installation
picked a higher-numbered build with CSV disabled. It printed
`biggie 0.1.0`, then rejected the example with exit code 2. These
entries in the project's Pixi manifest selected the CSV build alongside
GDAL from conda-forge.
[Rattler-Build filesystem channels](https://rattler-build.prefix.dev/latest/publish/#channel-initialization)
and [Pixi lock files](https://pixi.prefix.dev/latest/workspace/lock_file/)

```toml
[dependencies]
sanctuary-biggie = { version = "==0.1.0", build = "csv_0" }
libgdal-core = "==3.13.3"
```

From the locked project on the Mac,
`pixi-pack --platform linux-64 -o stations-linux.tar pixi.toml` collected
the Linux packages. Transfer that archive and the Linux `pixi-unpack`
executable. With the unpacker on your path and the archive in a fresh
directory on the worker, run `pixi-unpack stations-linux.tar`, then
`. ./activate.sh` to use the packaged tools.
[Packing and unpacking for another platform](https://github.com/Quantco/pixi-pack/blob/v0.7.12/README.md#cross-platform-packs)

On the bare Debian slim image, `pixi-unpack` 0.7.12 stopped because it
could not load any system CA certificates, even though the archive
contained them. Providing Debian's certificate bundle on the worker let
the same archive unpack with networking disabled.

## When is a package worth maintaining?

For a single reproduction, send the compressed file. On the Mac,
`gzip -n -9 -c stations.csv` reduced this repetitive CSV to 49,547 bytes.
Adding Biggie to the Linux GDAL archive grew it from 70.18 to 70.94 MiB,
an extra 801,792 bytes.

Ask two mapping teams that already deliver Pixi environments to try
Biggie and their usual handoff, including any local generation script.
Give each team a new row count and station ID after its worker goes
offline. Swap the cases and the order between teams. Check each generated
file against the developer's expected bytes and record both GDAL counts,
operator time and additional transfers. Maintain the package if both
teams reproduce their changed case in one transfer and the operator time
saved over a release cycle covers preparing and testing both builds.
