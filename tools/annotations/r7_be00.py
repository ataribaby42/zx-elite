"""$BE00..$D3FF: view-buffer area remnants, docked information screens, mission
message screens and the commander tape access menu.

Evidence: instruction semantics; decoded tokens/messages (tools/text_codec.py);
runtime traces (docs/generated/runtime-xrefs.json: docked screens, market,
inventory, system data, access menu); the supplied 48K ROM (LD-BYTES/SA-BYTES
entry points); SkoolKit execution tests for InsertSpaceInTextBuffer,
CompareWithGalaxySeeds, the rating thresholds (all bands) and the security
number (3000 random records against a Python model).  The square tables
($BE00), font ($C000), cockpit attributes ($C700) and bitmap ($C800) are
verified include files owned elsewhere.
"""

SECTIONS = {
    0xC2D8: ('View-buffer area after the font: zero fill and a dormant loader',
             'Initial tape content only.  At runtime $C000..$CFFF is the view bitmap buffer;\n'
             'every byte of $C2D8..$C6FF is written and read there (view clear, line drawing,\n'
             'BlitViewBitmap).  No instruction of the game references $C2D8..$C6FF.'),
    0xD000: ('Docked information screens and text helpers',
             'System-data helpers (species, radius, seed compare), market prices,\n'
             'commander status, inventory, and the full-screen mission/boarding messages.'),
    0xD2DA: ('Access menu: commander tape load and save',
             'Message 1 "ACCESS MENU": 1 load, 2 save, 3 exit.  The 104-byte commander record\n'
             'at ActiveCommanderRecord is transferred by the ROM tape routines.'),
}

FIELDS = {
    'RomLdBytesAfterSetup': (0x0562, 'ROM LD-BYTES after its border set-up and SA/LD-RET push'),
    'RomSaBytesAfterSetup': (0x04C6, 'ROM SA-BYTES after its SA/LD-RET push'),
}

OPERANDS = {
    0xD32E: 'RomLdBytesAfterSetup',     # CALL $0562
    0xD376: 'RomSaBytesAfterSetup',     # CALL $04C6
    # Pointer bases one entry before an array: the per-item routines pre-increment.
    0xD09F: 'L_AF0E-2',                 # L_AF63 adds 2 before reading the price word
    0xD0A5: 'L_A860-1',                 # L_AF63 adds 1 before reading the station stock
    0xD2C4: 'L_A82D-1',                 # L_AFB9 adds 1 before reading the cargo count
}

CONSTANTS = {
    0xD219: 'D = message $DF, E = attribute $1F for L_D258; not an address',
    0xD238: 'D = message $E0, E = attribute $17 for L_D258; not an address',
}

TEXTCALLS = {
    0xD053: 'token',      # JP PrintToken
    0xD1D5: 'token',      # token A printed after ':' at column 21
    0xD1EC: 'message',    # PrintMessage A (boarders' name)
}

DATA = {
    0xC2D8: (0xC350, 'zeros', 120),
    0xC40C: (0xC40E, 'bytes', 2),
    0xC40E: (0xC600, 'zeros', 498),
    0xC640: (0xC700, 'zeros', 192),
    0xD0B8: (0xD0B9, 'bytes', 1),
    0xD1E2: (0xD1E8, 'bytes', 6),
    0xD1E8: (0xD1EC, 'bytes', 4),
    0xD2DA: (0xD2DC, 'zeros', 2),
    0xD2DC: (0xD2E1, 'bytes', 5),
    0xD2E1: (0xD2E2, 'bytes', 1),
    0xD2E2: (0xD2E4, 'words', 1),
}

LABELS = {
    # ---- $C2D8..$C6FF: mixed initial content of the view bitmap buffer ----
    0xC2D8: ('ViewBufferZerosAfterFont', 'verified', """
Zero fill in the reference image (120 bytes) between the font and the dormant loader.
Runtime: part of the view bitmap buffer: cleared with PUSH at L_7485, drawn into by the
pixel/line routines (stores at $86B8, $875E, $87BD, $A282, $F204, $F232, $F253, $F27F) and
CharacterBlendOpcode, copied to the screen by BlitViewBitmap (LDI at $73C5).  Traces show
every byte of this run written and read.  No static reference.
INFERRED: the initial zeros are never needed, because the buffer is redrawn before use."""),
    0xC350: ('DormantPortLoader', 'verified', """
Dormant self-relocating loader (188 bytes, $C350..$C40B), never referenced by the game
and never executed in any 48K trace.  Entered with BC = its own address (BASIC USR
convention), it patches the operands of its nine CALL DormantPortReceiveByte
instructions, sets up I/O ports $DF/$5D/$FE, then repeatedly: waits for a '-' sync
byte, receives destination (HL), length (BC) and execution address (pushed), receives
the block with an additive checksum starting at $FF and RETurns into the loaded code
when the check byte matches; otherwise it flashes the border until a key is pressed
and waits for a new header.
INFERRED: a development-system remnant (external parallel interface on ports
$1F/$9F) left in memory when the image was saved; not the game's tape code (see
RunAccessMenu)."""),
    0xC3EE: ('DormantPortReceiveByte', 'verified', """
Dormant byte receiver of DormantPortLoader: handshake through port $1F (bit 0),
E = byte from port $9F, then border stripes from C.  Returns E."""),
    0xC40C: ('ViewBufferResidueAfterLoader', 'verified', """
Two residue bytes $F3,$AF in the reference image (DI, XOR A if decoded) after the
receiver's RET.  Runtime: part of the view bitmap buffer like the surrounding zeros.
No static reference.  In all seven 48K access traces their first access is the
ClearViewBuffer write (PUSH HL at L_7485), so the stored values are never used.  Of
$C000..$CFFF only the FontBitmap, CockpitAttributes and CockpitBitmap source bytes
are read before a write.
Evidence: memory_read_before_write_map of tools/run_runtime_scenarios.py --accesses;
tools/check_routines.py dormant/unused-interrupt-routines (ClearViewBuffer zeroes them)."""),
    0xC40E: ('ViewBufferZerosAfterLoader', 'verified', """
Zero fill in the reference image (498 bytes) up to the optional Adder startup area.
Runtime: part of the view bitmap buffer like L_C2D8 (cleared by L_7485, drawn into,
copied by BlitViewBitmap).  No static reference."""),
    0xC600: (None, 'verified', """
64 zero bytes kept in place for the optional ship=adder startup (src/adder-startup.asm,
docs/BUILD-VARIANTS.md); the default build emits the original zeros.  Runtime: part of
the view bitmap buffer like the surrounding bytes."""),
    0xC640: ('ViewBufferZerosBeforeCockpit', 'verified', """
Zero fill in the reference image (192 bytes) up to CockpitAttributes.  Runtime: part of
the view bitmap buffer like L_C2D8 (cleared by L_7485, drawn into, copied by BlitViewBitmap)."""),

    # ---- $D000..$D06C: text and system-data helpers ----
    0xD000: ('InsertSpaceInTextBuffer', 'verified', """
Insert a space at the address held in the pointer word L_BCF6: each byte from there up
to and including the first zero moves up one position (the zero is overwritten by the
byte before it, so the buffer must continue with zeros).  L_BCF6 is unchanged.
Input: L_BCF6.  Clobbers: A, B, C, HL, flags.
Only caller: L_BD52 in the justified printer.  When a word wraps to the next line it calls
FindPreviousSpace and then this routine once for every column the shortened line in L_7004
lacks, so the word gaps widen from right to left until the line is 30 characters wide again.
Evidence: instruction semantics; tools/check_routines.py text/insert-space and
text/p7-justify-padding (calls = padding spaces, every full line exactly 30 characters)."""),
    0xD00F: ('PrintAlienSpecies', 'verified', """
Print the inhabitant species of a system whose seed byte L_AC13 is >= $80
(entered by JP from L_BA8A with H = high byte of word L_AC13):
  (H >> 2) AND 7 < 3  -> token $E3+n LARGE/FIERCE/SMALL and a space
  H >> 5 < 6          -> token $E6+n GREEN/RED/YELLOW/BLUE/BLACK/HARMLESS and a space
  (hi L_AC0F XOR hi L_AC11) AND 7 = m < 6 -> token $EC+m SLIMY..FURRY and a space
  ((m + (hi L_AC13 AND 3)) AND 7) -> token $F2.. RODENT/FROG/LIZARD/LOBSTER/BIRD/
                                     HUMANOID/FELINE/INSECT (tail jump to PrintToken)
An adjective whose value is outside its range is left out; the species noun is always printed.
Only path: DisplaySystemData -> PrintSpecies (a seed byte below $80 prints HUMAN COLONIAL
instead).  Clobbers: A, B, HL, flags.
Evidence: decoded tokens; the system-data screen L_B991 prints "(" species "S)"."""),
    0xD053: (None, 'verified', """
Shared tail JP PrintToken; L_BA8A enters here with A = $BC "HUMAN COLONIAL"."""),
    0xD056: ('PrintPlanetRadius', 'verified', """
Print HL = ((hi L_AC13 AND $0F) + $0B) * 256 + hi L_AC11 as a five-character decimal
number (L_A88E = 5, carry clear: no decimal point); the value range is 2816..6911.
Tail jump to PrintDecimalHL.
Evidence: the only caller (L_B991) prints token $FA "AVERAGE RADIUS:" first and " km"
(PrintCommodityUnit with unit 17) after it; runtime docked-system-data."""),
    0xD06C: ('CompareWithGalaxySeeds', 'verified', """
Compare the six bytes at HL with the galaxy seeds L_A852..L_A857.
Output: carry clear if all six are equal, carry set otherwise.  Clobbers: A, B, DE, HL.
The galaxy seeds are also the seeds of the galaxy's first system (system 0, the name that
message control 16 prints), so a match identifies that system: the special-mission target,
where L_D7E1 sets mission-3 state 4 and the data screen shows the Thargoid message $DE.
Evidence: tools/check_routines.py commander/galaxy-seed-compare; L_A852..L_A857 are rotated
one bit per byte by galactic hyperspace (L_D63A/L_D64F).  Callers pass L_AC0F (system shown
on the data screen, L_B991) and L_A858 (current system, L_D7E1)."""),

    # ---- $D07D..$D2D9: docked screens ----
    0xD07D: ('ShowMarketPrices', 'verified', """
Market prices screen (screen function 6, L_A7EC): BeginTitledScreen clears the screen and
draws the frame and title rule; title token $A7 "{t2} MARKET PRICES" on row 1, column header
token $FF at column 16, row 3 (two lines), attribute bars from L_FC0B.  Unless L_7061 is
nonzero (witchspace), list the 17 trade goods from row 6 through L_AF63 with item index
L_AF30 = 0..16, price pointer L_AF33 and station stock pointer L_AF35.
Evidence: decoded tokens; runtime docked-market (executed through $D0B7)."""),
    0xD0B8: ('StatusLaserMountIndex', 'verified', """
Laser mount index while the status screen lists lasers: set to $FF at $D17D and
incremented by PrintLaserMount before each mount (0 front, 1 rear, 2 left, 3 right)."""),
    0xD0B9: ('ShowCommanderStatus', 'verified', """
Commander status screen (CurrentScreenId = $0B): token $7E "COMMANDER {name}" with the
labels PRESENT SYSTEM and HYPERSPACE SYSTEM, their names (token controls 2 and 3) at
column 21, then FUEL (control 5), CASH (control 7), LEGAL STATUS, RATING and the
EQUIPMENT list, and finally the screen frame (L_BCC7).  Rows: name 1, systems 4..5, fuel 6,
cash 7, legal status 8, rating 9, EQUIPMENT 11, items from row 12 at column 5.
Callers: screen function 7 (L_A7EF), StartNewGame, the docked main loop after an access menu
that read nothing (L_72A2), BuyEquipmentItem (L_B5DA, L_B736) and the hyperspace key while
docked (L_D5D6).  L_A4BD adds the condition tiles at column 27, row 1 only in flight.
Evidence: decoded tokens/messages; runtime docked screens (executed to $D1DF);
tools/check_routines.py commander/p7-docked-screen-text (text and rows, three equipment sets)."""),
    # Steps of ShowCommanderStatus (fall-through blocks, no other entry except L_D161)
    0xD0D4: (None, 'verified', """
Status screen: the present and hyperspace system names after their labels on rows 4 and 5
(PrintColonTokenAtColumn21: ':' at column 21, token control 2 or 3, new line)."""),
    0xD0EC: (None, 'verified', """
Status screen: the CASH line (token control 7) on row 7, below the FUEL line of row 6."""),
    0xD0F0: (None, 'verified', """
Status screen: "LEGAL STATUS:" on row 8 (message $71 and ':'); PrintLegalStatus and
SelectLegalStatusToken follow with CLEAN, OFFENDER or FUGITIVE."""),
    0xD114: (None, 'verified', """
Status screen: rating.  A kill count (word L_A823) below 256 is looked up by its low byte in
RatingKillThresholdsLow starting with token $15, a larger one by its high byte in
RatingKillThresholdsHigh starting with token $1A.  B advances one token for every
threshold below the byte; the first threshold >= the byte (at the latest the $FF end
marker) selects token B.
Evidence: tools/check_routines.py commander/rating-thresholds."""),
    0xD138: (None, 'verified', """
Status screen: equipment list below "EQUIPMENT:" (row 11), one item per line at column 5
(NewLineAtColumn5).  Order: large cargo bay, fuel scoops, E.C.M. system or jammer, energy
bomb, energy unit, docking computers, galactic hyperspace, the laser mounts and the
cloaking device.  Each record byte is printed when nonzero (PrintInlineTokenIfSet)."""),
    0xD142: (None, 'verified', """
Equipment list: FUEL SCOOPS when FuelScoopsFitted is nonzero."""),
    0xD149: (None, 'verified', """
Equipment list: with CommanderFlags bit 7 (the jammer that OfferSpecialMission gives) print
message $CF "E.C.M.SYSTEM JAMMER" instead of the plain E.C.M. SYSTEM line, whether or not
EcmFitted is set; otherwise E.C.M. SYSTEM when EcmFitted is nonzero."""),
    0xD161: (None, 'verified', """
Equipment list: ENERGY BOMB when EnergyBombFitted is nonzero; both E.C.M. paths join here."""),
    0xD168: (None, 'verified', """
Equipment list: ENERGY UNIT when EnergyUnitFitted is nonzero."""),
    0xD16F: (None, 'verified', """
Equipment list: DOCKING COMPUTERS when DockingComputerFitted is nonzero."""),
    0xD176: (None, 'verified', """
Equipment list: GALACTIC HYPERSPACE when GalacticHyperdriveFitted is nonzero."""),
    0xD17D: (None, 'verified', """
Equipment list: one PrintLaserMount call for each byte of L_A83F..L_A842 (front, rear,
left, right; StatusLaserMountIndex starts at $FF), then CLOAKING DEVICE for CommanderFlags
bit 6 (last line, no new line) and the screen frame (tail jump to DrawScreenFrame)."""),
    0xD19C: ('PrintInlineTokenIfSet', 'verified', """
Read the inline token byte after the CALL; if A is nonzero print that token and fall
into NewLineAtColumn5, else return after the inline byte without printing.
Used for equipment items: A = the item's commander-record byte (any nonzero value prints).
Clobbers: B, HL, flags; when the item is printed also what PrintToken and NewLine change.
Evidence: tools/check_routines.py commander/p7-docked-screen-text."""),
    0xD1A6: ('NewLineAtColumn5', 'verified', """
NewLine, then text column 5 (the indentation of the equipment list)."""),
    0xD1AE: ('PrintLaserMount', 'verified', """
Advance StatusLaserMountIndex, read the laser type at HL (HL+1 on return).  Type 0: no
output.  Otherwise print token $60+index (FRONT/REAR/LEFT/RIGHT) and a space, then the
laser: type 1..2 -> token $66+type (PULSE LASER, BEAM LASER), type 3..4 -> token
$72+type (MILITARY LASER, MINING LASER), and NewLineAtColumn5.
Input: HL = the mount's byte in L_A83F..L_A842.  Output: HL + 1 (kept across the printing).
Evidence: decoded tokens; caller loops over L_A83F..L_A842; tools/check_routines.py
commander/p7-docked-screen-text (all four types on all four mounts)."""),
    0xD1D5: ('PrintColonTokenAtColumn21', 'verified', """
Set text column 21, print ':' and then token A followed by a new line.
Token A waits in the alternate AF (EX AF,AF') while the column and ':' are printed.
Callers: ShowCommanderStatus with A = 2 (present system) and A = 3 (hyperspace system)."""),
    0xD1E2: ('RatingKillThresholdsLow', 'verified', """
Rating thresholds for a kill count below 256 (compared with the low byte L_A823):
count <= 8 HARMLESS ($15), <= 16 MOSTLY HARMLESS, <= 32 POOR, <= 64 AVERAGE,
<= 128 ABOVE AVERAGE, otherwise COMPETENT ($1A).  The $FF entry ends the search.
Evidence: tools/check_routines.py commander/rating-thresholds checks all bands."""),
    0xD1E8: ('RatingKillThresholdsHigh', 'verified', """
Rating thresholds for a kill count of 256 or more (compared with the high byte L_A824):
high byte <= 2 COMPETENT ($1A), <= 10 DANGEROUS, <= 25 DEADLY, otherwise
"---- E L I T E ----" ($1D); i.e. counts 768, 2816 and 6656 start the higher ratings."""),
    0xD1EC: ('ShowShipBoardedScreen', 'verified', """
Full-screen message on white/red (attribute $17): "SHIP BOARDED BY" at column 3, row 7,
message A (the boarders: 13 "PIRATE" from L_7840 or $D4 "THARGON" from L_7832), "S",
then "THEY SHOW NO MERCY..." at column 4, row 11; wait for a key and continue at L_D20A.
Only caller: EndGameWithMessage at docking, when pirates boarded the station during the last
hyperspace arrival (CheckPirateGameOver) or when docking at the station the Thargons hold
(mission-3 state 4, L_782B).  The caller then restarts through L_718F."""),
    0xD20A: (None, 'verified', """
Shared end of the message screens: beep if enabled (L_AF39), wait for a key (L_AF48),
clear the screen (L_BC9E), call L_B0AF and continue at L_7BFF."""),
    0xD219: ('OfferSpecialMission', 'verified', """
Show message $DF "WANTED BY GALCOP: A BRAVE COMMANDER FOR A SPECIAL MISSION ...
ARE YOU INTERESTED (Y/N)?" on attribute $1F and wait for a key.  Not 'Y': L_A871 = 0 and
return.  'Y': set L_A872 bit 7, L_A871 = 3 and show the briefing message
$E0 ("THE THARGONS ARE USING THE SPACE STATION AT ... YOUR MISSION: TO DESTROY THE SPACE
STATION ...") on attribute $17, then wait for a key (L_D23E).
Reached at docking (L_782B) while the mission-3 state L_A871 is 1 or 2.  The states, from
the code that writes and tests L_A871: 1 set by the trigger at 254 jumps (L_D853, which also
sets CommanderFlags bit 2, so a declined offer never returns), 2 after the next arrival;
0 declined here; 3 accepted here; 4 on arrival in the galaxy's first system (L_D7E1),
3 again on leaving it; 5 on the arrival after a missile hit the station there
(UpdateMissileGuidance, L_D7AC).  Docking with 4 ends the game (Thargons board, message $D4),
docking with 5 calls AwardHighestHonour.  L_ED83 tests CommanderFlags bit 7 in state 4.
Evidence: decoded messages; the status screen prints "E.C.M.SYSTEM JAMMER" for bit 7;
instruction semantics of the writers named above; tools/check_routines.py
missions/hyperspace-arrival for the arrival transitions."""),
    0xD23E: ('ShowMessageScreenAndWait', 'verified', """
ShowColouredMessageScreen (D = message, E = attribute, L = column, H = row), then the
shared key wait at L_D20A.  Also called by L_B474 for message $0F "YOU HAVE SAVED OUR
LIVES".  Returns through L_7BFF."""),
    0xD243: ('AwardHighestHonour', 'verified', """
Add 256 to the kill count (INC L_A824), clear L_A871, set L_A872 bit 3
and show message $0A "IN APPRECIATION OF YOUR EXCEPTIONAL COURAGE THE INHABITANTS OF ...
AWARD YOU THEIR HIGHEST HONOUR." on attribute $0F (white on blue).  Entered from L_7832 at
docking with mission-3 state 5 (see OfferSpecialMission): the end of the special mission.
CommanderFlags bit 3 is also an input of the save security number (AccessMenuSave)."""),
    0xD258: ('ShowColouredMessageScreen', 'verified', """
Clear the screen (L_BC9E), print message $5C (control 19: capitalise the next letter), set
the text position from HL (L = column, H = row), fill all 768 attribute cells from $5800 with
E and print message D (tail jump to PrintMessage).
Callers: L_B27B (message $5B "THE SUN IS GOING NOVA"), ShowShipBoardedScreen,
OfferSpecialMission, ShowMessageScreenAndWait."""),
    0xD279: ('ShowInventory', 'verified', """
Inventory screen (CurrentScreenId = $0C): title token $A4 "INVENTORY", FUEL and CASH
(token controls 5 and 7), "LARGE CARGO BAY" with an attribute bar when L_A846 is set,
"REFUGEES" when L_A872 bit 5 is set, then each held cargo item (L_AFB9, items 0..16).
Rows: FUEL 3, CASH 4, LARGE CARGO BAY 6 (attributes $05, columns 1..30), REFUGEES 7, cargo
from row 8, or row 7 without refugees (row 6 stays empty without the cargo bay).
Callers: screen function 8 (L_A7F2) and the ends of the cargo screens (L_B2BF, L_B318,
SellCargoScreen, L_B4FE).
Evidence: decoded tokens/messages; runtime docked-inventory; tools/check_routines.py
commander/p7-docked-screen-text."""),

    # ---- $D2DA..$D3FF: access menu ----
    0xD2DA: (None, 'inferred', """
Two zero bytes with no static or runtime reference; unused padding."""),
    0xD2DC: ('AccessMenuAttributeBars', 'verified', """
Attribute bar list for L_BBDF (access menu): each byte = (cells << 3) + rows to move
down; L_BBDF colours that many cells with attribute 5 from column 1 and stops after an
entry with zero rows.  Bars: 1 cell (row 1), 2 cells (rows 5, 7 and 9), 16 cells (row 12,
behind the "SECURITY NUMBER:" label that AccessMenuSave prints at column 1, row 12).  Like
every list, ColourAttributeStrips then sets $5822/$5823 to $07 (already $07 after the clear)."""),
    0xD2E1: ('CommanderLoadedFlag', 'verified', """
Access menu result: cleared on entry, set to 1 whenever a record has been read from tape,
even one that LoadCommanderRecord then rejects for its name; returned in A (and as NZ) when
the menu exits.  Evidence: tools/check_routines.py commander/p7-tape-load-paths."""),
    0xD2E2: ('AccessMenuStackPointer', 'verified', """
Stack pointer saved on entry to the access menu (LD (nn),SP at $D2FD) and restored at
the top of every key loop iteration, so the tape paths can jump back to AccessMenuKeyLoop."""),
    0xD2E4: ('RunAccessMenu', 'verified', """
Access menu: clear the screen, colour bars, print message 1 ("ACCESS MENU ... 1 LOAD NEW
COMMANDER ... 2 SAVE COMMANDER ... 3 EXIT") and loop on keys '1' (load), '2' (save) and
'3' (exit).  Output: A = CommanderLoadedFlag, NZ if any record was read from tape.
Callers: the title prompt "LOAD NEW COMMANDER (Y/N)?" on 'Y' (L_71A2), continuing at L_71BE;
and the docked main loop's access-menu key (L_72A2), which restarts through L_71BE on NZ (the
next game starts from CommanderTemplateBuffer) and otherwise shows the status screen and stays
docked with ActiveCommanderRecord as it is.
Evidence: decoded message; runtime access-menu scenario (keys 1 and 3)."""),
    0xD301: ('AccessMenuKeyLoop', 'verified', """
Restore the menu stack (AccessMenuStackPointer) and wait for a key."""),
    0xD320: ('AccessMenuLoad', 'verified', """
Load: ask for the commander name into L_AC25 (L_D425, message 8 "COMMANDER'S NAME? ",
at most 10 characters), then load records until one matches."""),
    0xD326: ('LoadCommanderRecord', 'verified', """
Load one headerless 104-byte record (flag $FF) into ActiveCommanderRecord through the
ROM LD-BYTES loop.  The ROM prologue (INC D / EX AF,AF' / DEC D / DI) is repeated here and the
ROM is entered at $0562, skipping its white border and the SA/LD-RET exit (which would
restore the border from BORDCR and raise the BASIC "BREAK" error).
Success: CommanderLoadedFlag = 1, message $D6 "FOUND COMMANDER {name}", then compare the
typed name with the loaded one: an empty typed name or equal names (up to 11 bytes
including the zero terminator) accept the record (CopyCommanderToTemplate); otherwise the
next record is loaded over it.  Failure: TapeLoadFailed.
Evidence: ROM entry points; tools/check_routines.py commander/p7-tape-load-paths (LD-BYTES
stubbed: register set, name matching, flag, template copy)."""),
    0xD35A: ('AccessMenuSave', 'verified', """
Save: input the commander name straight into the record (L_D425), copy the nine bytes at
L_7065 into record bytes +$5D..+$65 (L_A873), print message 2 "START TAPE, THEN PRESS ANY
KEY", wait for a key and write the 104-byte record with ROM SA-BYTES entered at $04C6
(after its SA/LD-RET push).  Black border, EI.  BREAK: L_D407.  Success: message $97
"COMMANDER SAVED", then "SECURITY NUMBER: " and two decimal numbers (HL, then DE with
leading zeros) computed from the kill count, galaxy, L_A872 bits 3/6 and word L_A828,
and CopyCommanderToTemplate (a save also becomes the restart snapshot).
The two numbers appear as one digit string: HL is printed with the field width and leading
zero state that PrintDecimalHL leaves behind (0 and suppressed), DE as exactly five digits.
On BREAK the typed name and the nine sun bytes are already in the record; the template is
not updated.
Evidence: decoded messages, ROM entry points; tools/check_routines.py
commander/security-number (Python model of HL and DE) and commander/p7-security-number-print
(printed text)."""),
    0xD3E2: ('CopyCommanderToTemplate', 'verified', """
Copy the 102 persistent bytes of ActiveCommanderRecord to CommanderTemplateBuffer (the
restart snapshot) after a successful load or save, then return to AccessMenuKeyLoop.
This is the only writer of the template (static references and all runtime traces); a new
game (InitialiseCommander) starts from it and a tape loading error restores it."""),
    0xD3ED: (None, 'verified', """
Return to AccessMenuKeyLoop (target of the tape message paths at L_D407/L_D411)."""),
    0xD3F0: ('RotateParityIntoD', 'verified', """
Count the set bits of A in C (B = 8 RRA steps) and rotate the parity (bit 0 of C) into
bit 7 of D (RR C / RR D).  Clobbers: A, B, C, flags.  Used by the security number."""),
    0xD3FF: ('TapeLoadFailed', 'verified', """
LD-BYTES returned with carry clear: HALT for the next keyboard scan; if the key code
L_FC13 is ' ' (BREAK) print "BREAK" (L_D407), otherwise "TAPE LOADING ERROR" and restore
the active record from the snapshot via L_7C2D (L_D411); both return to the menu loop.
After BREAK the bytes LD-BYTES had already stored stay in ActiveCommanderRecord.  After an
error the record returns to CommanderTemplateBuffer, the state of the last load, save or
game start, so a docked commander loses the progress made since then.
Evidence: tools/check_routines.py commander/p7-tape-load-paths (stubbed LD-BYTES with a
partial record)."""),
}

COMMENTS = {
    # InsertSpaceInTextBuffer
    0xD000: 'B = the space to insert',
    0xD002: 'HL = insertion point',
    0xD007: 'store the carried byte, carry the old one',
    0xD00B: 'stop after moving the first zero byte',
    # PrintAlienSpecies
    0xD00F: 'H = high byte of word L_AC13 (from L_BA8A)',
    0xD017: 'size 0..2: LARGE, FIERCE, SMALL',
    0xD027: 'colour 0..5: GREEN .. HARMLESS',
    0xD030: 'high byte of word L_AC0F',
    0xD035: 'high byte of word L_AC11',
    0xD03D: 'skin 0..5: SLIMY .. FURRY',
    0xD046: 'high byte of word L_AC13, bits 0..1',
    0xD051: 'species token $F2..$F9',
    # PrintPlanetRadius
    0xD05C: 'radius high byte = (seed AND $0F) + $0B',
    0xD061: 'radius low byte = high byte of word L_AC11',
    0xD063: 'field width 5 (L_A88E)',
    0xD068: 'carry clear: no decimal point',
    # CompareWithGalaxySeeds
    0xD06F: 'six seed bytes',
    0xD079: 'equal: carry clear',
    0xD07B: 'different: carry set',
    # ShowMarketPrices
    0xD085: 'column 16, row 3',
    0xD090: 'attribute bar list for L_BBDF',
    0xD096: 'goods listed only while L_7061 is zero',
    0xD09B: 'item index L_AF30 = 0',
    0xD09F: 'price word pointer (L_AF63 adds 2 first)',
    0xD0A5: 'station stock pointer (L_AF63 adds 1 first)',
    0xD0AB: 'print one market line for item L_AF30',
    0xD0B3: '17 trade goods',
    # ShowCommanderStatus
    0xD0B9: 'screen id $0B: commander status',
    0xD0C6: 'attribute bar list for L_BBDF',
    0xD0D4: 'row 4',
    0xD0D9: 'token control 2: present system name',
    0xD0DE: 'token control 3: hyperspace system name',
    0xD0E3: 'row 6',
    0xD0EB: 'PrintInlineToken argument: token control 5, "FUEL: n.n LIGHT YEARS"',
    0xD0EF: 'PrintInlineToken argument: token control 7, "CASH: ... CR"',
    0xD114: 'kill count high byte (word L_A823)',
    0xD11B: 'below 256: compare the low byte',
    0xD11F: 'token $15 HARMLESS',
    0xD126: 'token $1A COMPETENT',
    0xD12A: 'threshold >= count: rating found',
    0xD131: 'print the rating token and a blank line (L_BA5A)',
    0xD13B: 'L_A846: large cargo bay',
    0xD142: 'L_A84A: fuel scoops',
    0xD149: 'L_A872 bit 7: E.C.M. jammer replaces the E.C.M. line',
    0xD15A: 'L_A847: E.C.M. system',
    0xD161: 'L_A84C: energy bomb',
    0xD168: 'L_A84D: energy unit',
    0xD16F: 'L_A84E: docking computers',
    0xD176: 'L_A84F: galactic hyperspace',
    0xD17D: 'mount index -1: first increment selects FRONT',
    0xD182: 'laser type per mount: front, rear, left, right',
    0xD18E: 'L_A872 bit 6: cloaking device',
    0xD199: 'draw the screen frame and return (L_BCC7)',
    # PrintInlineTokenIfSet / PrintLaserMount
    0xD19D: 'B = inline token code',
    0xD1A0: 'A = 0: item not fitted, skip it',
    0xD1A9: 'equipment indentation: column 5',
    0xD1B5: 'laser type of this mount; 0 = none',
    0xD1BE: 'tokens $60..$63: FRONT, REAR, LEFT, RIGHT',
    0xD1C8: 'types 3..4: MILITARY/MINING LASER ($75/$76)',
    0xD1CC: 'types 1..2: PULSE/BEAM LASER ($67/$68)',
    # PrintColonTokenAtColumn21
    0xD1D5: 'keep token A',
    # ShowShipBoardedScreen and other message screens
    0xD1ED: 'D = message $0B "SHIP BOARDED BY", E = attribute $17',
    0xD1F0: 'column 3, row 7',
    0xD1F7: 'message A: PIRATE or THARGON',
    0xD1FF: 'column 4, row 11',
    0xD20A: 'beep if sound is enabled',
    0xD20D: 'wait for a key',
    0xD210: 'clear the screen',
    0xD219: 'D = message $DF (mission offer), E = attribute $1F',
    0xD21C: 'column 5, row 4',
    0xD225: "'Y' accepts",
    0xD229: 'declined: L_A871 = 0',
    0xD231: 'L_A872 bit 7: E.C.M. jammer (status screen)',
    0xD233: 'accepted: L_A871 = 3',
    0xD238: 'D = message $E0 (mission briefing), E = attribute $17',
    0xD23B: 'column 0, row 2',
    0xD246: 'kill count high byte + 1: 256 kill points',
    0xD247: 'L_A871 = 0',
    0xD24E: 'L_A872 bit 3',
    0xD250: 'D = message $0A (highest honour), E = attribute $0F',
    0xD253: 'column 0, row 5',
    0xD264: 'L = column, H = row',
    0xD267: 'attribute area: 768 cells',
    0xD275: 'print message D',
    # ShowInventory
    0xD279: 'screen id $0C: inventory',
    0xD283: 'token $A4 "INVENTORY" as the title (L_B057)',
    0xD288: 'attribute bar list for L_BBDF',
    0xD296: 'PrintInlineToken argument: token control 5, FUEL line',
    0xD297: 'token control 7: CASH line',
    0xD29C: 'L_A846: large cargo bay',
    0xD2A2: 'attribute cell row 6, column 1',
    0xD2B1: 'L_A872 bit 5: refugees on board',
    0xD2C4: 'cargo count pointer (L_AFB9 adds 1 first)',
    0xD2CA: 'print item L_AF30 if held (carry clear)',
    0xD2D5: '17 cargo items',
    # RunAccessMenu
    0xD2E4: 'clear the screen',
    0xD2E7: 'access-menu attribute bars',
    0xD2ED: 'attribute bar on row 21',
    0xD2F0: 'attribute $0F for rows 0..2 (L_B749)',
    0xD2F5: 'no commander loaded yet',
    0xD2FA: 'message 1: ACCESS MENU',
    0xD2FD: 'remember the stack for the key loop',
    0xD301: 'tape paths jump back here with any stack depth',
    0xD305: 'wait for a key',
    0xD308: "'1': load",
    0xD30C: "'2': save",
    0xD310: "'3': exit; other keys are ignored",
    0xD313: 'beep and redraw (L_B3F8)',
    0xD316: 'clear the key state',
    0xD319: 'A = 1 and NZ if a commander was loaded',
    0xD31E: 'A = 0 and Z',
    0xD320: 'typed commander name buffer',
    0xD323: 'input the name (message 8, up to 10 characters)',
    0xD326: 'IX = ActiveCommanderRecord, DE = 104, A = $FF',
    0xD329: 'carry set: LOAD rather than VERIFY',
    0xD32A: 'ROM LD-BYTES prologue ($0556..$0559)',
    0xD32E: 'load 104 bytes; carry set on success',
    0xD332: 'tape error or BREAK',
    0xD335: 'CommanderLoadedFlag = 1',
    0xD33A: 'message $D6: "FOUND COMMANDER" and the loaded name',
    0xD33F: 'typed name',
    0xD342: 'loaded name (record +0)',
    0xD347: 'empty typed name: accept any record',
    0xD34A: 'at most 11 bytes including the terminator',
    0xD34E: 'names differ: load the next record',
    0xD350: 'equal bytes: zero means both names ended',
    0xD358: 'no terminator within 11 bytes: load the next record',
    0xD35A: 'name field of the active record',
    0xD35D: 'input the name into the record',
    0xD360: 'nine bytes at L_7065',
    0xD363: 'to record +$5D..+$65',
    0xD36B: 'message 2: START TAPE, THEN PRESS ANY KEY',
    0xD370: 'wait for a key',
    0xD373: 'IX = ActiveCommanderRecord, DE = 104, A = $FF',
    0xD376: 'save 104 bytes',
    0xD379: 'black border',
    0xD37E: 'BREAK: message "BREAK"',
    0xD381: 'message $97: COMMANDER SAVED',
    0xD386: 'column 1, row 12',
    0xD391: 'kill count word',
    0xD394: 'carry = bit 7 of the low byte',
    0xD397: 'E = kill count >> 7 (low eight bits)',
    0xD399: 'galaxy number',
    0xD39F: 'L_A872 bit 3 -> bit 3',
    0xD3A5: 'L_A872 bit 6 -> bit 4',
    0xD3AB: 'word L_A828',
    0xD3AE: 'D = (galaxy and flags) rotated left three times',
    0xD3B3: 'parity of E into D',
    0xD3B7: 'parity of H into D',
    0xD3BB: 'parity of L into D',
    0xD3C0: 'D = (L XOR D) + $3D',
    0xD3C4: 'E = (D XOR E) + $66',
    0xD3C8: 'H = (E XOR H) + $8F',
    0xD3CC: 'L = (H XOR L) + $C7',
    0xD3CF: 'second number',
    0xD3D1: 'first number: HL',
    0xD3D4: 'field width 5',
    0xD3D9: 'print leading zeros',
    0xD3DF: 'second number (the pushed DE)',
    0xD3E8: '102 persistent record bytes',
    0xD3F2: 'C = number of set bits',
    0xD3FA: 'carry = parity',
    0xD3FC: 'parity into bit 7 of D',
    0xD3FF: 'wait for the interrupt keyboard scan',
    # pass 2: system data helpers
    0xD01D: 'size adjective and a space',
    0xD02D: 'colour adjective and a space',
    0xD043: 'skin adjective and a space',
    0xD065: 'pad the radius to five characters',
    0xD069: 'tail jump: print HL and return to DisplaySystemData',
    # pass 2: market prices
    0xD07D: 'clear the screen, frame and title rule (message 150)',
    0xD082: 'title in capitals on row 1, then three new lines',
    0xD08D: 'header rows 3 and 4; the goods start on row 6',
    0xD0AE: 'next commodity',
    # pass 2: commander status
    0xD0C0: 'clear the screen, frame and title rule, capitals',
    0xD0C3: 'condition tiles at column 27, row 1 (in flight only)',
    0xD0D0: 'COMMANDER name on row 1, system labels on rows 4 and 5',
    0xD0DB: 'row 4, column 21',
    0xD0E0: 'row 5, column 21',
    0xD0E8: 'FUEL line on row 6',
    0xD0F2: '"LEGAL STATUS:" on row 8',
    0xD0F9: 'B = token $12 CLEAN; +1 OFFENDER, +2 FUGITIVE',
    0xD101: 'scores 1..49: OFFENDER, 50..255: FUGITIVE',
    0xD108: 'legal status token, then a new line',
    0xD10D: '"RATING:" on row 9',
    0xD12C: 'next rating token',
    0xD13E: 'printed only when A is nonzero',
    0xD155: 'next line at column 5',
    0xD188: 'one mount; HL advances to the next byte',
    0xD195: 'last line: no new line follows',
    # pass 2: equipment and laser helpers
    0xD1A3: 'print the item name',
    0xD1AB: 'tail jump: TextColumn = 5',
    0xD1C0: 'mount name and a space',
    0xD1CF: 'laser name',
    0xD1D2: 'HL = next mount byte',
    0xD1DF: 'tail jump: token A and a new line',
    # pass 2: rating thresholds (one byte per line)
    0xD1E2: 'kills 0..8: HARMLESS',
    0xD1E3: '9..16: MOSTLY HARMLESS',
    0xD1E4: '17..32: POOR',
    0xD1E5: '33..64: AVERAGE',
    0xD1E6: '65..128: ABOVE AVERAGE',
    0xD1E7: 'end marker: 129..255 COMPETENT',
    0xD1E8: 'high byte 1..2 (256..767): COMPETENT',
    0xD1E9: 'high byte 3..10 (768..2815): DANGEROUS',
    0xD1EA: 'high byte 11..25 (2816..6655): DEADLY',
    0xD1EB: 'end marker: 6656 and more ELITE',
    # pass 2: message screens
    0xD1F3: 'clear, colour every cell $17, print "SHIP BOARDED BY"',
    0xD1FA: 'plural "S", then two 36-frame pauses (message $5D)',
    0xD213: '36-frame pause',
    0xD216: 'tail jump: reset the flight inputs and key state',
    0xD222: 'A = key code',
    0xD25A: 'clear the screen (attributes $07) and draw the frame',
    0xD25D: 'message $5C: capitalise the next letter',
    0xD26D: 'B = 3 outer passes of 256 (C starts at 0)',
    0xD276: 'tail jump',
    # pass 2: inventory
    0xD280: 'clear the screen, frame and title rule, capitals',
    0xD28E: 'row 3',
    0xD299: 'CASH line on row 4, then a new line (row 6 next)',
    0xD2A7: 'columns 1..30 of row 6 in attribute $05',
    0xD2AA: 'LARGE CARGO BAY on row 6',
    0xD2AE: 'row 7 next, even without the cargo bay',
    0xD2BD: 'cargo starts on the next row',
    0xD2CD: 'held item: new line',
    0xD2D0: 'next commodity',
    # pass 2: access menu bars (one byte per line)
    0xD2DC: '$0C: 1 cell on row 1, then 4 rows down',
    0xD2DD: '$12: 2 cells on row 5, then 2 rows down',
    0xD2DE: '$12: 2 cells on row 7, then 2 rows down',
    0xD2DF: '$13: 2 cells on row 9, then 3 rows down',
    0xD2E0: '$80: 16 cells on row 12; 0 rows ends the list',
    # pass 2: access menu, load and save
    0xD2F2: 'plus a full-width line at pixel row 23',
    0xD337: 'set for any record read, even if rejected below',
    0xD33C: 'bottom status line (row 22), beep if enabled',
    0xD36D: 'bottom status line (row 22), beep if enabled',
    0xD383: 'bottom status line (row 22), beep if enabled',
    0xD38E: 'label on row 12 (coloured by AccessMenuAttributeBars)',
    0xD39C: 'mission flags',
    0xD3D6: 'second number: exactly five digits',
    0xD3E5: 'restart snapshot (InitialiseCommander starts from it)',
}
