# Commander state, tape records and restart behaviour

This note records the verified relationship between the live commander state,
the tape record and the in-memory commander snapshot. It is based on the
current byte-identical disassembly and 48K runtime traces.

## Memory regions

| Address range | Size | Purpose |
|---|---:|---|
| `$A816..$A87D` | 104 bytes | Buffer passed directly to the Spectrum ROM tape load/save routines; 102 persistent commander bytes followed by two transient runtime bytes |
| `$A910..$A975` | 102 bytes | Initial JAMESON data and the snapshot used to restore the commander when starting again |

The two blocks are related, but they are not interchangeable. The active tape
buffer contains 104 bytes, while only its first 102 bytes carry persistent
commander information and are preserved in the restart snapshot.

The 104-byte length belongs to this compatibility-fixed release. The game
itself still uses the 48K Spectrum memory model, despite being distributed as
“Elite 128K”. According to the
[supplied save-format research](<info/ZX Spectrum Elite Save Format.txt>), the
earlier original 48K release stored 102 bytes on tape; the compatibility-fixed
release added two trailing bytes and therefore stores 104 bytes. The release
name, machine memory model and tape-record length must be kept as separate
concepts.

## Initial start and restart

The program image initially contains the default JAMESON commander at `$A910`.
After the title sequence, routine `$A976` calls `$7C2D`, which copies 102 bytes
from `$A910` to the active record at `$A816`.

The two extra tape bytes at offsets `$66` and `$67` do not carry necessary
persistent commander information. Their RAM locations are nevertheless reused
as transient variables while the game is running:

- `$A87C` is cleared by the startup path at `$7231`;
- `$A87D` is rebuilt at `$A97F` from the current-system coordinate already
  stored at `$A85B`.

Consequently, “unused” describes these bytes as serialized save fields. It
does not mean that the program never accesses their RAM addresses at runtime.

The byte at `$A87E`, immediately after the tape record, is also initialized by
the startup routine, but it is not part of the 104-byte ROM tape transfer.

## Successful tape load and save

The tape menu passes `$A816` and a length of 104 bytes to the Spectrum ROM:

- ROM load entry `$0562` is called at `$D32E`;
- ROM save entry `$04C6` is called at `$D376`.

After either a successful load or a successful save, the common path at
`$D3E2` copies the first 102 active bytes from `$A816` back to `$A910`. This
updates the restart snapshot. Normal gameplay changes such as trading and
hyperspace update the active record but do not continuously update this
snapshot.

## Death and continuation

The death sequence at `$7335..$7395` eventually returns to the title loop at
`$718F`. Starting again reaches `$A976`, so the 102 persistent bytes of the
active commander record are restored from the snapshot at `$A910`, and the
two trailing tape-buffer bytes are initialized as described above.

The practical result is that death discards commander-state changes made since
the last successful load or save. At initial boot, before either operation has
updated the snapshot, restarting restores the built-in JAMESON state.

## Evidence status

The copy directions, byte counts, ROM entry points and restart control flow are
verified directly from the reconstructed machine code. Runtime traces also
show the active record changing during ordinary gameplay while the snapshot
remains unchanged. A complete physical-tape save/load session has not yet been
used as a separate behavioural test.
