"""Docked screens, text controls and screen helpers in $B000..$BDFF.

Evidence summary: instruction semantics; the decoded token/message tables
(tools/text_codec.py); 48K runtime traces (docked market/equipment/data/chart
screens, chart-cursor, ecm-bomb-pod, docked-system-data); and SkoolKit
simulator runs of the original handlers with controlled RAM (R6 analysis
tests): every text control handler, the economy line, commodity units and the
attribute-strip routine were executed on the reference image with the 48K
ROM.  Pass-2 simulator checks (p6-*) in tools/check_routines.py cover the
chart selection, input routines, nova cargo screens and equipment purchase.
Text names (TEXTNAMES) render control codes in decoded text comments.
The trading/equipment routines are transactional: SaveTradeState and
RestoreTradeState bracket every attempt.  Money is kept as two words in
tenths of a credit: high = count of 10000 tenths, low = 0..9999 tenths.
"""

SECTIONS = {
    0xB026: ('Docked-screen helpers: prompt lines, text input and chart cursor',
             'Prompt rows 21/22, string input, frame waits, commodity units and the\n'
             'chart cross-hair key handlers reached through the jump table at $A7F5.'),
    0xB27B: ('Market and equipment screens, money and decimal output',
             'Buy/sell cargo, equip ship and laser mounting; the nova-mission offer and\n'
             'completion; base-10000 money arithmetic and the decimal printer.'),
    0xB8AC: ('Text control-code handlers and the system data screen',
             'Handlers reached through TokenControlTable (L_6FA3) and\n'
             'MessageControlTable (L_6FBF), then the "DATA ON" screen.'),
    0xBBC6: ('Attribute strips, screen clear/frame and justified text',
             'Attribute fills, full-width rules, the clear-screen frame and the\n'
             'word-wrapping, fully justified output used by planet descriptions.'),
}

LABELS = {
    # ---------------------------------------------------------------- prompt / input
    0xB026: ('EraseInputCharacter', 'verified', """
Backspace on the prompt rows: if TextColumn is nonzero, decrement it and clear
the 8 pixel bytes of that character cell on text row 21 (TextRow = 21) or
otherwise row 22.  The cell address is patched into the LD HL at L_B03E.
Input: TextRow, TextColumn.  Clobbers: A, B, HL.
Evidence: callers InputString (delete key) and InputQuantity (L_B32B)."""),
    0xB03E: (None, 'verified', """
Self-modified: the low byte of LD HL,$5000 is written at $B03B with
$A1/$C1 + new column, giving the screen cell of the erased character."""),
    0xB049: ('PrintTokenInCapitals', 'verified', """
Print token A between control codes 6 (capitals on) and 8 (title case):
PrintToken(6), PrintToken(A), PrintToken(8).  Clobbers: A, BC, DE, HL.
Evidence: instruction semantics; TokenControlTable entries 6 and 8."""),
    0xB057: ('PrintScreenTitle', 'verified', """
Print token A in capitals (PrintTokenInCapitals), call L_A4BD, then print
token $77 ({cr}{cr}{cr}).  Input: A = title token.
Evidence: callers print "DATA ON", " CARGO" (after "SELL"), "INVENTORY" and
"<system> MARKET PRICES" titles."""),
    0xB06F: ('PrintCommodityUnit', 'verified', """
Print the unit of commodity L_AF30 in lower case (clears L_A892 first):
0..12 and 16 "t", 13..14 "kg", 15 "g", 17 or more "km" (used for the
planet radius).  Evidence: simulator run of all indexes 0..17 (a simulator
check in tools/check_routines.py)."""),
    0xB09D: ('TestCommodityTonnes', 'verified', """
Carry set when commodity L_AF30 is measured in tonnes (indexes 0..12 and 16),
clear for 13..15 (kg/g).  Only tonne goods change the free cargo space
L_A83E.  Evidence: simulator run of indexes 0..17; callers L_B3A1/L_B501."""),
    0xB0AB: ('Wait20Frames', 'verified', """
Wait for 20 interrupts (HALT loop, about 0.4 s).  Clobbers: B."""),
    0xB0AF: ('Wait36Frames', 'verified', """
Wait for 36 interrupts (HALT loop, about 0.7 s).  Clobbers: B."""),
    0xB0B1: ('WaitFrames', 'verified', """
Wait for B interrupts with HALT.  Clobbers: B."""),
    0xB0B5: ('SaveTextCursor', 'verified', """
Copy the TextColumn/TextRow word to L_AF37.  Clobbers: HL."""),
    0xB0BC: ('ClearPromptLines', 'verified', """
Set TextRow 21 and column 0, then clear text rows 21 and 22, columns 1..30
(pixel bytes only).  Clobbers: A, BC, HL.
Evidence: simulator (480 bytes from $50A1 cleared); message control 21."""),
    0xB0CB: ('FillPromptRow22', 'verified', """
Fill text row 22, columns 1..30, all 8 pixel lines with A.  Falls into
FillCharacterRow30.  Evidence: instruction semantics."""),
    0xB0CE: ('FillCharacterRow30', 'verified', """
Fill 30 bytes on each of the 8 pixel lines of the character row at HL
(INC H per line) with A.  Clobbers: B, HL."""),
    0xB0DE: ('RestoreTextCursor', 'verified', """
Restore TextColumn/TextRow from L_AF37 (see SaveTextCursor).  Clobbers: HL."""),
    0xB0E5: ('InputLength', 'verified', """
InputString: number of characters entered so far (0..limit)."""),
    0xB0E6: ('InputWritePointer', 'verified', """
InputString: address where the next character is stored."""),
    0xB0E8: ('InputKey', 'verified', """
InputString: last key code returned by L_AF48."""),
    0xB0E9: ('PromptFindSystem', 'verified', """
Chart key handler (JP from $A807): prompt with message 14 "PLANET NAME?",
read up to 8 characters into L_AC25 with InputString, and search with
L_AC77.  Empty input clears the prompt; carry from L_AC77 prints the name
and " NOT FOUND" and beeps; otherwise PrintSelectedSystemSummary.
Evidence: decoded messages/tokens; jump-table entry next to the docked screens."""),
    0xB113: (None, 'verified', """
PromptFindSystem, name found (L_AC77 returned carry clear and has selected the
system): back to title case, then PrintSelectedSystemSummary shows its name,
the distance line and beeps."""),
    0xB11A: ('InputPromptMessage', 'verified', """
InputString: message number printed as the prompt."""),
    0xB11B: ('InputBufferStart', 'verified', """
InputString: start address of the destination buffer."""),
    0xB11D: ('InputString', 'verified', """
Read a string on the prompt rows.  Input: A = prompt message, B = maximum
length (patched into L_B163), HL = buffer.  Accepts '0'..'9' and '@'..'Z';
key $FE deletes (then pauses 8 frames), Enter ($0D) ends.  A character typed
while the buffer already holds the maximum also ends the input, like Enter, and
is not stored.  The buffer is zero-terminated; on exit InputLength holds the
length.  Waits for Enter to be released, then clears the key state (L_AF56).
Evidence: instruction semantics; callers $B0E9, $D429; a simulator check in
tools/check_routines.py (full buffer, rejected keys, delete)."""),
    0xB163: ('InputLimitCompare', 'verified', """
Self-modified CP n: the operand is the maximum input length, written at $B121
by InputString from B on entry ($0A in the image)."""),
    0xB1AC: ('SelectSystemAtCursor', 'verified', """
Chart key handler (JP from $A804): select the system nearest to the chart
cursor with L_ACB3 (the cursor moves onto it; on the chart screens 7 and 8 the
cross-hair is erased and redrawn), then fall into PrintSelectedSystemSummary:
its name in capitals on prompt row 21, the distance line and a beep.
Evidence: executed in the chart-cursor trace; a simulator check in
tools/check_routines.py (cursor (3, 92) selects TIBEDIED at (2, 90), cursor
(21, 171) selects LAVE at (20, 173), both names printed)."""),
    0xB1AF: ('PrintSelectedSystemSummary', 'verified', """
Clear the prompt rows, print the selected system name in capitals (token
control 3 through PrintTokenInCapitals), a new line and the distance line
(L_AE5A), then beep (L_AF39)."""),
    0xB1C0: ('DrawChartCursor', 'verified', """
Draw the chart cross-hair for cursor L_A87D (x) / L_A87E (y) via L_D886.
With L_D883 = $0A (the value the galactic chart L_AB4E leaves) the screen
position is (x, y/2+$18); otherwise it is relative to the current system
L_A85B/L_A859: ($61 + 4*dx, $60 + 2*dy).  Returns without drawing when the
position overflows or y is outside $19..$A6.  Output: L_A813/L_A814.
Called before and after each cursor move, so the drawing toggles (XOR).
Evidence: chart-cursor and chart traces; instruction semantics."""),
    0xB224: ('MoveChartCursorUp', 'verified', """
Chart key handler (JP from $A7FE): erase cursor, L_A87E -= 2 (clamped to 0),
redraw.  Evidence: executed in the chart-cursor trace."""),
    0xB236: ('MoveChartCursorDown', 'verified', """
Chart key handler (JP from $A7FB): erase cursor, L_A87E += 2 (clamped to
255), redraw.  Evidence: executed in the chart-cursor trace."""),
    0xB249: ('MoveChartCursorLeft', 'verified', """
Chart key handler (JP from $A7F5): erase cursor, L_A87D -= 1 (minimum 1),
redraw.  Evidence: executed in the chart-cursor trace."""),
    0xB256: (None, 'verified', """
Common tail of the cursor handlers: redraw the cursor (JP DrawChartCursor)."""),
    0xB259: ('MoveChartCursorRight', 'verified', """
Chart key handler (JP from $A7F8): erase cursor, L_A87D += 1 (maximum 254),
redraw.  Evidence: executed in the chart-cursor trace."""),
    0xB26A: ('ResetChartCursor', 'verified', """
Chart key handler (JP from $A801): erase cursor, move it to the current
system (L_A85B -> L_A87D, L_A859 -> L_A87E), redraw.
Evidence: executed in the chart-cursor trace."""),
    # ---------------------------------------------------------------- market
    0xB27B: ('BuyCargoScreen', 'verified', """
Docked "buy cargo" key handler (JP from $A7DA).
- bit 5 of L_A872 set: wait and show the inventory (L_D279);
- L_A843 nonzero: show message 91 "THE SUN IS GOING NOVA* WILL YOU SAVE US
  (Y/N)?" with a drawing by L_8461; on 'Y' set L_A846, clear the cargo hold
  (17 bytes at L_A82D), set free space L_A83E = 0 and bit 5 of L_A872;
  any other key declines without changes; both answers end at the inventory;
- otherwise run the buy list (BuyCargoList).
Bit 5 of L_A872 is the refugee flag: ShowInventory prints message 12
"REFUGEES" while it is set, and it blocks buying until SellCargoScreen (or the
escape pod) clears it.  Evidence: decoded messages 91/12; a simulator check in
tools/check_routines.py (accept, decline, blocked).
L_A843 is NovaMissionActive (missions/p5-nova-offer-and-reward)."""),
    0xB2C5: ('BuyScreenAttributeStrips', 'verified', """
ColourAttributeStrips data for the buy list: 30 cells with $05 on text rows 1
and 2 ($F1 = 30 cells then one row down, $F0 = 30 cells and end).
Evidence: simulator run of ColourAttributeStrips with this table."""),
    0xB2C7: ('BuyCargoList', 'verified', """
Clear the screen and print token $FF (column headings), colour the title and
prompt rows, then for each of the 17 commodities: print its market line
(L_AF63; carry skips it), prompt for a quantity and run InputQuantity with
BuyCommodity.  Result 1 retries, 2 skips; any other key leaves to L_D279.
Evidence: docked-market trace; decoded tokens."""),
    0xB31B: (None, 'inferred', """
Dormant routine, never referenced: fill the 768 attribute bytes from $5800
with A (LD HL,$5800, two CALLs to the 256-byte loop at L_B324, then the loop
itself).  Decoded as code because both internal CALL operands point exactly
at the loop; no CALL/JP/pointer in the image targets $B31B.
fuelfix=yes replaces these 16 bytes with FuelPriceUpdate."""),
    0xB32B: (None, 'verified', """
InputQuantity: delete after the first digit - erase it, undo the attempt
(RestoreTradeState) and restart the number."""),
    0xB333: ('InputQuantity', 'verified', """
Read a quantity of one or two digits on the prompt row and try it with the
handler HL (saved in QuantityHandler, called through CallHL).  The first
digit must be 1..9; after every digit the previous attempt is undone and
the handler is called with EnteredNumber.  Result:
  NC          accepted (Enter after the digits, or a second digit);
  C, A = 2    Enter before any digit (skip);
  C, A = 1    the handler reported an error (retry);
  C, other A  a non-digit key (leave the screen); after a first digit that
              attempt is not undone, so its trade stays applied.
Codes below '1' (first digit) or '0' (second) are ignored; delete before a
digit is ignored, after it undoes the attempt and restarts (L_B32B).
Evidence: instruction semantics; docked-market, trade-complete traces; a
simulator check in tools/check_routines.py (scripted key sequences)."""),
    0xB391: (None, 'verified', """
Enter before any digit: return A = 2 with carry set."""),
    0xB395: ('ShowCashAfterTrade', 'verified', """
Column 3, token control 7 (the "Cash: ... Cr" line), then BeepAndWait."""),
    0xB3A0: ('CallHL', 'verified', """
JP (HL): called by InputQuantity to run the transaction handler."""),
    0xB3A1: ('BuyCommodity', 'verified', """
InputQuantity handler for buying EnteredNumber units of commodity L_AF30:
take them from the station stock (L_AF35 pointer), pay the price word
(L_AF33 pointer) once per unit with SubtractCash, reduce the free space
L_A83E for tonne goods, add them to the hold (L_AF31 pointer) and report
the purchase to L_A8D4.  Errors: "QUANTITY?", "CASH?" or " CARGO?"."""),
    0xB3DE: ('ReportQuantityError', 'verified', """
Print "QUANTITY?" (token $B0) through PrintTradeError."""),
    0xB3E2: ('ReportCashError', 'verified', """
Print "CASH?" (token $C5) through PrintTradeError."""),
    0xB3E6: ('ReportCargoError', 'verified', """
Print " CARGO?" (token $CE) through PrintTradeError."""),
    0xB3E8: ('PrintTradeError', 'verified', """
At column 3 print token A and '?', undo the attempt (RestoreTradeState),
then BeepAndWait (returns A = 1, carry set)."""),
    0xB3F8: ('BeepAndWait', 'verified', """
Beep if sound is enabled (L_AF39), wait 36 frames, return A = 1 with carry
set (the "retry" result of InputQuantity handlers)."""),
    0xB402: ('SaveTradeState', 'verified', """
Save the cash words (L_A828, L_A82A), the station stock byte at (L_AF35),
the hold byte at (L_AF31) and the free cargo space L_A83E in L_B46A..L_B470.
Clobbers: A, HL."""),
    0xB423: ('RestoreTradeState', 'verified', """
Restore everything saved by SaveTradeState (undo a trade attempt)."""),
    0xB444: ('PromptCommodityQuantity', 'verified', """
Clear the prompt rows and print "QUANTITY OF <commodity>/<unit> ?" for
commodity L_AF30 with a capital first letter, then a new line."""),
    0xB46A: ('SavedCashLow', 'verified', """
SaveTradeState copy of the low cash word L_A82A."""),
    0xB46C: ('SavedCashHigh', 'verified', """
SaveTradeState copy of the high cash word L_A828."""),
    0xB46E: ('SavedHoldAmount', 'verified', """
SaveTradeState copy of the hold byte at (L_AF31)."""),
    0xB46F: ('SavedStockAmount', 'verified', """
SaveTradeState copy of the station stock byte at (L_AF35)."""),
    0xB470: ('SavedCargoSpace', 'verified', """
SaveTradeState copy of the free cargo space L_A83E."""),
    0xB471: ('EnteredNumber', 'verified', """
Number typed into InputQuantity (1..99); also the selected equipment item."""),
    0xB472: ('QuantityHandler', 'verified', """
Address of the transaction handler called by InputQuantity."""),
    0xB474: ('SellCargoScreen', 'verified', """
Docked "sell cargo" key handler (JP from $A7DD).  When L_A843 is zero and
bit 5 of L_A872 (refugees aboard) is set: clear the bit, add 1 to the combat
score high byte L_A824, set the GEM-STONES hold byte L_A83C (commodity 15,
token $DF, unit g) to 100 and the free space L_A83E to 35, show message 15
"YOU HAVE SAVED OUR LIVES*..." and the inventory.  Otherwise run the sell
list (SellCargoList).  Evidence: decoded tokens/messages; a simulator check in
tools/check_routines.py (reward values; L_A843 nonzero reaches SellCargoList).
This is the completion of the nova mission: L_A843 (NovaMissionActive) is cleared by
the galactic jump the mission forces (missions/p5-nova-offer-and-reward)."""),
    0xB49E: ('TradeScreenAttributeStrip', 'verified', """
ColourAttributeStrips data: 30 cells with $05 on text row 1, then end."""),
    0xB49F: ('BeginTradeScreen', 'verified', """
BeginTitledScreen, colour text row 1 (TradeScreenAttributeStrip) and the
prompt row (ColourPromptRow)."""),
    0xB4AB: ('BeginTitledScreen', 'verified', """
Print message 150: clear screen and frame, title rule, capitals, column 4
with a capital (codes 9, 11, 1, 8)."""),
    0xB4B0: ('SellCargoList', 'verified', """
Title "SELL CARGO", then for each commodity: print the hold line (L_AFB9;
carry skips it), prompt and run InputQuantity with SellCommodity.  Result 1
retries, 2 skips, other keys leave; finally wait 40 frames and show the
inventory (L_D279).  Evidence: trade-complete trace; decoded tokens."""),
    0xB501: ('SellCommodity', 'verified', """
InputQuantity handler for selling EnteredNumber units of commodity L_AF30:
remove them from the hold ("QUANTITY?" if too few), give back free space
for tonne goods and add the price word (L_AF33 pointer) once per unit with
AddCash.  The station stock is not changed, and unlike BuyCommodity it does
not call L_A8D4, so selling never changes the legal score."""),
    0xB52E: ('ResetCommodityPointers', 'verified', """
Set L_AF31 to the byte before the hold array, L_AF33 to two bytes before
the price words (both are pre-incremented per commodity) and L_AF30 = 0."""),
    # ---------------------------------------------------------------- equipment
    0xB53F: ('EquipShipScreen', 'verified', """
Docked "equip ship" key handler (JP from $A7E0): title "EQUIP SHIP", then
list EquipmentItemCount items (tech level L_A85E + 3, or all 14 from 9 up)
with number, name (token $69+n) and price from the table at L_9236.
Fuel (item 1) is not listed while L_A843 is nonzero.  Its price is L_9237 as the last
jump or purchase left it (see there).
Evidence: docked-equipment, buy-* and equip-tech10 traces.
fuelfix=yes calls FuelPriceUpdate instead of BeginTradeScreen: it recomputes L_9237
and continues in BeginTradeScreen."""),
    0xB5B4: ('BuyEquipmentItem', 'verified', """
Prompt "ITEM? ", read the number (InputQuantity with AcceptQuantity) and buy
it: pay the price (SubtractCashHigh, SubtractCash; "CASH?" on failure),
then fuel refills to 70 (L_D86D), missiles up to 4, large cargo bay adds 15
to L_A83E, lasers go to ChooseLaserView, other items set their byte to $FF;
items already present print "... PRESENT".  Non-digit keys or an item out
of range go to the status screen (L_D0B9).
Quirk: item 1 (fuel) typed while L_A843 is nonzero (the list hides it then) is
paid for but refused: the code returns to the item prompt without undoing the
payment, so the current fuel price is lost.
Evidence: instruction semantics; a simulator check in tools/check_routines.py
(fuel with and without L_A843, missiles at 4)."""),
    0xB616: (None, 'verified', """
BuyEquipmentItem, items 2..14 after payment: 2 adds a missile (at most 4,
otherwise "ALL PRESENT"), 3 fits the large cargo bay (+15 free space, byte $FF), 4 and
7..12 set their commander byte (L_A843 + item) to $FF unless it is already
nonzero ("... PRESENT"), 5, 6, 13 and 14 are lasers (L_B65A).  Every refusal
undoes the payment (RestoreTradeState in L_B729)."""),
    0xB65A: (None, 'verified', """
Laser items: B = laser type 1 (item 5, pulse), 2 (item 6, beam),
3 (item 13, military) or 4 (item 14, mining)."""),
    0xB66B: ('ChooseLaserView', 'verified', """
Store the laser type B in NewLaserType, clear the screen, print the laser
name and the four views (0 FRONT .. 3 RIGHT), prompt " VIEW ?" and read a
key.  '0'..'3' fits the laser to L_A83F+view and refunds the laser that was
there (item number from the table at L_FB99+type, price from L_9236);
any other key undoes the purchase (L_B6FD)."""),
    0xB6FD: (None, 'verified', """
Cancel a laser purchase: RestoreTradeState, then the status screen."""),
    0xB702: ('ReportEquipmentCashError', 'verified', """
"CASH?" (ReportCashError) and back to the item prompt."""),
    0xB708: ('AcceptQuantity', 'verified', """
InputQuantity handler that accepts any number: AND A (clear carry), RET."""),
    0xB70A: ('GetEquipmentPriceEntry', 'verified', """
HL = L_9236 + 3*(A-1): the 3-byte price entry of equipment item A
(byte = high cash units of 10000 tenths, word = low tenths)."""),
    0xB713: ('GetEquipmentStatePointer', 'verified', """
HL = L_A843 + EnteredNumber: the commander byte of the selected item
(item 1 = fuel L_A844, 2 = missiles L_A845, ...)."""),
    0xB719: ('AddAToHL', 'verified', """
HL = HL + A (D = 0, E = A).  Clobbers: DE."""),
    0xB71E: ('ReportAllMissilesPresent', 'verified', """
Print "ALL PRESENT" (four missiles already fitted)."""),
    0xB722: ('ReportEquipmentPresent', 'verified', """
Print "<item name> PRESENT" for item EnteredNumber (token $68+n)."""),
    0xB729: (None, 'verified', """
Print token A, " PRESENT", BeepAndWait, undo the purchase
(RestoreTradeState) and show the status screen (L_D0B9)."""),
    0xB739: ('EquipmentItemCount', 'verified', """
Number of equipment items offered (3 + tech level, 14 when that is 12+)."""),
    0xB73A: ('EquipmentListIndex', 'verified', """
Loop index of the equipment list (also used by ChooseLaserView)."""),
    0xB73B: ('EquipmentPricePointer', 'verified', """
Pointer into the equipment price table while listing (3 bytes per item)."""),
    0xB73D: ('NewLaserType', 'verified', """
Laser type 1..4 being fitted by ChooseLaserView."""),
    0xB73E: ('PrintBannerTitle', 'verified', """
Column 6, PrintScreenTitle(A), then ColourBannerRows with attribute $17.
Evidence: callers in the short-range (L_A9D0) and galactic (L_AB4E) charts."""),
    0xB749: ('ColourBannerRows', 'verified', """
Fill attribute rows 0..2 with A and draw a full-width line at pixel row 23
($4740).  Clobbers: A, B, HL."""),
    # ---------------------------------------------------------------- decimal / money
    0xB757: ('DecimalRemainder', 'verified', """
PrintDecimalHL: value still to be printed (remainder after each digit)."""),
    0xB794: (None, 'verified', """
Decimal point before the last digit."""),
    0xB7A8: ('PrintCash', 'verified', """
Print the commander's cash: HL = high word L_A828, DE = low word L_A82A,
then PrintMoney.  Evidence: token 7 "Cash:   100.0 Cr" in the simulator."""),
    0xB7AF: ('PrintMoney', 'verified', """
Print HL*10000+DE tenths of a credit with one decimal place: if HL is
nonzero print it (width 3) and DE zero-padded (4 digits), else DE in a
7-character field.  Clobbers: AF, BC, DE, HL."""),
    0xB7D2: ('PrintDecimalDigit', 'verified', """
Divide DecimalRemainder by DE (repeated subtraction), keep the remainder
and print the digit; a zero digit is skipped while L_A88D is set."""),
    0xB7EB: ('PrintDigitA', 'verified', """
Print digit A (0..9) as a character."""),
    0xB7F7: ('PadDecimalField', 'verified', """
Count the digits of HL (a value below 10 counts 2 when carry requests a
decimal point) and print spaces (L_A88D set) or zeros up to the field width
in L_A88E."""),
    0xB848: ('CompareHLDE', 'verified', """
Carry set when HL < DE (SBC with the incoming carry); HL is preserved."""),
    0xB84D: ('AddCash', 'verified', """
Add DE tenths to the low cash word; at 10000 or more subtract 10000 and add
1 to the high word (falls into AddCashHigh with DE = 1)."""),
    0xB861: ('AddCashHigh', 'verified', """
Add DE to the high cash word L_A828."""),
    0xB869: ('SubtractCashHigh', 'verified', """
Subtract DE from the high cash word (SBC; carry must be clear on entry).
Carry set and no change if it would go negative."""),
    0xB877: ('SubtractCash', 'verified', """
Subtract DE tenths from the cash, borrowing 10000 from the high word when
needed.  Carry set (unchanged cash) when the cash is insufficient."""),
    # ---------------------------------------------------------------- control handlers
    0xB8AC: ('PrintEmptyMessageAndWait', 'verified', """
Message control 25: print message 216 (an empty message) and wait 36 frames.
Not used by any message in the tables."""),
    0xB8B4: ('PrintCashLine', 'verified', """
Token control 7: "Cash:" + PrintCash + " Cr" and a new line.
Evidence: simulator prints "Cash:   100.0 Cr" for JAMESON."""),
    0xB8C0: ('PrintCommanderName', 'verified', """
Token control 4 / message control 4: print the commander name (the
zero-terminated token string at ActiveCommanderRecord).
Evidence: simulator prints "Jameson"."""),
    0xB8C5: ('SetTitleCase', 'verified', """
Token control 8 / message control 2: L_A891 = 0 (title case: capital after
any non-letter).  Evidence: simulator."""),
    0xB8C9: ('PrintFuelLine', 'verified', """
Token control 5: "Fuel: " + L_A844 in tenths + " Light Years", new line.
Evidence: simulator prints "Fuel: 7.0 Light Years"."""),
    0xB8DD: ('PrintGalaxyNumber', 'verified', """
Token control 1: print CurrentGalaxy+1 in a 2-character field.
Evidence: simulator prints " 1" and " 3" for galaxies 0 and 2."""),
    0xB8E9: ('PrintGalaxyFirstSystemName', 'verified', """
Token control 11 / message control 16: copy the 6 galaxy seed bytes L_A852
to L_AC15, generate the system name (L_AD6F into L_AC2E) and print it.
The galaxy seeds are where L_AE79 starts the galaxy's system list, so this
is the name of the first system.  Used by the Thargoid invasion texts: token
$0F "MAYDAY* ... INVADED*" and messages 10 and 224.
Evidence: simulator prints "Tibedied"; decoded tokens/messages."""),
    0xB8FC: ('PrintPresentSystemName', 'verified', """
Token control 2: capitalise the next letter and print the name at L_AC37.
Evidence: token "{present-system} MARKET PRICES"; L_AC37 is rewritten at
$D6CB during hyperspace arrival."""),
    0xB904: ('PrintSelectedSystemName', 'verified', """
Token control 3 / message control 3: capitalise the next letter and print the
name at L_AC40.  Evidence: "DATA ON ..." and "HYPERSPACE -- ..." tokens."""),
    0xB90D: ('SetColumn4Capital', 'verified', """
Message control 8: TextColumn = 4, then CapitaliseNextLetter."""),
    0xB911: ('CapitaliseNextLetter', 'verified', """
Message control 19: L_A893 = 1, so PrintCharacter capitalises one letter."""),
    0xB916: ('IgnoreTextControl', 'verified', """
RET: unused control codes (token 0, 12, 13; message 0, 20, 26..28, 30, 31)."""),
    0xB917: ('PrintRandomName', 'verified', """
Message control 18: capitalise the next letter, then print 1..4 letter
pairs chosen by NextDescriptionRandom from the pair table at L_FBAB
(L_FBA9 + 2); a '?' second letter is not printed.
Evidence: simulator prints words such as "Atainso", "Noreet"."""),
    0xB93B: ('SetLowerCase', 'verified', """
Message control 13: L_A891 = 2 (letters in lower case)."""),
    0xB93F: (None, 'verified', """
Unreachable byte $C9 (a RET opcode) between SetLowerCase and SetCapitals: no
word anywhere in the image (control tables, CALL/JP operands, data) and no
JR/DJNZ target points at it, and the instruction before it is the
unconditional JR of SetLowerCase, so nothing falls through.  Kept as a byte.
Evidence: a simulator check in tools/check_routines.py scans the image; never
executed in the runtime traces."""),
    0xB940: ('SetCapitals', 'verified', """
Token control 6 / message control 1: L_A891 = 1 (capitals)."""),
    0xB942: ('SetLetterCase', 'verified', """
Store A in the letter-case mode L_A891."""),
    0xB946: ('PrintSelectedSystemAdjective', 'verified', """
Message control 17: print the selected system name (L_AC40) and "IAN";
when its last letter is a vowel (VowelTable) that letter is first removed
from the justified-line buffer.  Only correct inside justified text.
Evidence: simulator in justified mode: Lave -> "Lavian", Diso -> "Disian"."""),
    0xB96E: ('AdjectiveSuffix', 'verified', """
Zero-terminated token string "IAN" printed by PrintSelectedSystemAdjective."""),
    0xB972: ('VowelTable', 'verified', """
The five vowels "AEIOU" searched by PrintSelectedSystemAdjective (B = 5)."""),
    0xB977: ('SelectMessageMode', 'verified', """
Token control 10 / message control 5: L_BA98 = 1 (message interpretation)."""),
    0xB97B: ('SelectTokenMode', 'verified', """
Message control 6: L_BA98 = 0 (message bytes go to PrintToken)."""),
    0xB97D: ('SetMessageMode', 'verified', """
Store A in the message interpretation mode L_BA98."""),
    0xB981: ('SetTextRow6', 'verified', """
Message control 29: SetTextRow(6)."""),
    0xB985: ('SetTextRow10', 'verified', """
Message control 23: SetTextRow(10)."""),
    0xB98A: ('PrintPairCharacter', 'verified', """
Print the character at (HL) unless it is '?'."""),
    # ---------------------------------------------------------------- data screen
    0xB991: ('DisplaySystemData', 'verified', """
Docked "data on system" key handler (JP from $A7E9): select the system
(L_ACB3), title "DATA ON <selected system>", then distance, economy,
government (token $B1+L_AC4C), tech level (L_AC4D+1), population (L_AC4E
tenths + " BILLION"), species, gross productivity (L_AC4F) and average
radius (L_D056), followed by the Thargoid invasion message 222 (when L_A871
is nonzero and the selected system is the galaxy's first one, i.e. L_D06C
finds L_AC0F equal to the galaxy seeds; rows 19/20 coloured $03) or the planet
description (PrintPlanetDescription).  Evidence: docked-system-data trace."""),
    0xBA49: ('PrintPlanetDescription', 'verified', """
Seed NextDescriptionRandom from the selected system seeds (L_AC11 -> L_AC21,
L_AC13 -> L_AC23) and print message 5, the justified planet description."""),
    0xBA5A: ('PrintTokenBlankLine', 'verified', """
PrintTokenNewLine(A), then one more NewLine."""),
    0xBA5F: ('PrintBlankLine', 'verified', """
Two NewLines (end the current line and leave a blank one)."""),
    0xBA65: ('PrintEconomy', 'verified', """
Print "Economy:", an adjective and "Industrial"/"Agricultural" (token
$A8 + L_AC4B/4), then a new line and a blank line.  Economy 4 prints
"Mainly"; every other value prints "Rich": the adjective comes from the inline
token $AA, which replaces A, so the SUB 5 result is discarded.
Evidence: simulator for economies 0..7.
INFERRED: the intended code selected RICH/AVERAGE/POOR/MAINLY by A+$AA."""),
    0xBA79: (None, 'verified', """
PrintEconomy, second word: token $A8 INDUSTRIAL for economies 0..3 or $A9
AGRICULTURAL for 4..7, then a new line and a blank line (PrintTokenBlankLine)."""),
    0xBA8A: ('PrintSpecies', 'verified', """
Print the species: "Human Colonial" (token $BC) when the low byte of the
seed word L_AC13 is below $80, otherwise L_D00F builds an alien species."""),
    # ---------------------------------------------------------------- character output
    0xBB58: ('PutCharacter', 'verified', """
Advance TextColumn (32 wraps to column 1 of the next row) and draw
character A at the new cursor cell (falls into GetCharacterBitmap).
Used directly by the justified-line printer to bypass case conversion."""),
    0xBB7F: ('LoadCharacterScreenBase', 'verified', """
Self-modified LD HL,$4000: bit 7 of the high operand byte (L_BB81) is set by
$7260/$7272/$D468 and cleared by $727A/$D483, so text is drawn into the
view bitmap buffer at $C000 instead of the screen."""),
    # ---------------------------------------------------------------- attributes / lines
    0xBBC6: ('ColourPromptRow', 'verified', """
Set attributes of text row 21, columns 1..30, to $05; HL ends at $5AC1.
Evidence: simulator (30 cells $5AA1..$5ABE)."""),
    0xBBCB: ('FillAttributeRow30', 'verified', """
Fill 30 bytes at HL with A, then HL += 2 (column 1 of the next row)."""),
    0xBBD3: ('DrawTitleUnderline', 'verified', """
Message control 11: full-width line at pixel row 19 ($4340), under the title
row.  Evidence: simulator (32 bytes $FF at $4340)."""),
    0xBBD6: ('DrawFullWidthLine', 'verified', """
Write 32 bytes of $FF from HL (one full-width pixel line)."""),
    0xBBDA: ('FillBytes', 'verified', """
Write A to B bytes from HL; HL ends after the last byte."""),
    0xBBDF: ('ColourAttributeStrips', 'verified', """
Colour attribute strips from the list at DE, starting at $5821 (row 1,
column 1).  Each byte: bits 7..3 = number of cells set to $05 from the strip
start, bits 2..0 = rows to move down for the next strip; 0 rows ends the
list.  Finally cells $5822 and $5823 are set to $07.
Evidence: simulator with BuyScreenAttributeStrips and TradeScreenAttributeStrip."""),
    0xBC6C: ('DoubleSignMagnitude', 'verified', """
C = (A AND $80) OR ((A << 1) AND $7E) OR carry-in: a sign-magnitude byte with
its magnitude doubled.  Also A bit 0 := A bit 6, carry out = old bit 0.
Evidence: simulator for all 256 values and both carry inputs (a simulator
check in tools/check_routines.py)."""),
    0xBC76: ('RandomMessageTable', 'verified', """
Base message numbers for the random message codes $5B..$80 (38 bytes);
PrintRandomMessage adds 0..4 to the selected entry."""),
    0xBC9C: ('ClearScreenSavedSP', 'verified', """
Stack pointer saved while ClearScreenAndFrame fills the screen by PUSH."""),
    0xBC9E: ('ClearScreenAndFrame', 'verified', """
Message control 9: with interrupts off and SP at $5B00, PUSH $0707 into all
768 attribute bytes and $0000 into the 6144 bitmap bytes, then fall into
DrawScreenFrame.  Evidence: simulator (attributes 7, frame only)."""),
    0xBCC7: ('DrawScreenFrame', 'verified', """
Draw a one-pixel frame around the whole screen (left and right pixel
columns, top and bottom lines) and set TextColumn = 0, TextRow = 1."""),
    # ---------------------------------------------------------------- justified text
    0xBCF6: ('JustifyWritePointer', 'verified', """
Justified text: address of the last character stored in the line buffer
(L_7004..L_7021); also used as the scan position for inserting spaces."""),
    0xBCF8: ('JustifyCarryLength', 'verified', """
Justified text: length of the partial word moved to the next line."""),
    0xBCF9: ('JustifyLineLength', 'verified', """
Justified text: characters in the current line (a line holds 30)."""),
    0xBCFA: ('JustifyNextWritePointer', 'verified', """
Justified text: write pointer for the next line (L_7003 + carried length)."""),
    0xBCFC: ('BufferJustifiedCharacter', 'verified', """
PrintCharacter output while L_A894 = 1 (character on the stack): store it
in the line buffer.  A '.' prints the line at once.  When the 31st
character arrives, a space ends the line; otherwise the partial word is
moved to the carry buffer L_7023, the line is padded by inserting spaces at
earlier gaps (L_D000) and printed.  Quirk: a character other than a space that
arrives as the 31st character is stored after the 30 printed ones and lost, so a
line-ending '.' can disappear (text/justified-full-stop-loss).
Evidence: docked-system-data trace; tools/check_routines.py text checks."""),
    0xBD5D: ('PrintJustifiedLine', 'verified', """
Print the 30 buffered characters at L_7004 with PutCharacter, a new line,
clear L_A892, then StartNextJustifiedLine."""),
    0xBD75: ('StartNextJustifiedLine', 'verified', """
Move the carried word (L_7023..) to the line buffer (L_7004..), refill the
carry buffer with spaces and reset the pointers and lengths."""),
    0xBD9D: ('StartJustifiedText', 'verified', """
Message control 14: L_A894 = 1 (characters go to BufferJustifiedCharacter),
fill 31 bytes from L_7023 with spaces and start an empty line.
NOTE: the 31st byte is $7041 (CurrentScreenId), written by $BDA9 at runtime."""),
    0xBDB9: ('EndJustifiedText', 'verified', """
Message control 15: L_A894 = 0 and print any partly filled line."""),
    0xBDC6: ('FindPreviousSpace', 'verified', """
Move JustifyWritePointer back to the previous space; B = distance.  Below
L_7004 the scan restarts from the line end (L_7022), so repeated calls visit
the gaps of the line from right to left in a cycle.  A line without any space
would make it scan for ever, so B is 1..30 whenever it returns."""),
    0xBDE4: ('ActivatePlayerEcm', 'verified', """
Tail of the ECM update (JP from $ED9E when EcmTimer is zero): if an ECM is
fitted (C = L_A847) and key bit 4 of L_FC11 was set (B), store C OR $80
in L_A847 and set EcmTimer = 10.  Evidence: ecm-bomb-pod trace ('E' key)."""),
    0xBDF5: (None, 'inferred', """
Eleven zero bytes up to the page-aligned SquareLookupTables; no reference.
Probably alignment padding."""),
}

COMMENTS = {
    0xB006: 'SetTextRow wraps rows 24+ back to row 1',
    0xB014: '32 columns per text row',
    0xB017: 'column 32 or more: start a new line instead',
    0xB01C: '24 text rows',
    0xB01F: 'past the bottom: wrap to row 1',
    0xB024: 'and column 0',
    0xB029: 'B = low byte of the row-21 cell base + 1 ($50A1)',
    0xB02B: 'prompt row 21?',
    0xB02F: 'row 22: $50C1',
    0xB035: 'column 0: nothing to erase',
    0xB037: 'cursor back one cell',
    0xB03A: 'row base + 1 + new column = cell of the last character',
    0xB03B: 'patch the low byte of LD HL at L_B03E',
    0xB03E: 'self-modified low byte: erased character cell',
    0xB042: '8 pixel lines per character cell',
    0xB045: 'next pixel line of the cell (+$100)',
    0xB05A: 'update the alert colour (row-1 tiles off the cockpit views)',
    0xB063: 'zero terminator?',
    0xB065: 'end of string: carry set, A = 0',
    0xB068: 'PrintToken does not preserve HL',
    0xB071: 'no capital for the unit letters',
    0xB077: 'indexes 0..12: tonnes',
    0xB07B: '13, 14: kilograms',
    0xB07F: '15: grams',
    0xB081: '16 (alien items): tonnes; 17 or more: km',
    0xB087: "'T', printed as 't' (L_A892 cleared)",
    0xB08B: '\'K\' of "kg"',
    0xB090: "'G', printed as 'g'",
    0xB094: 'index 17+: "km" (only the planet radius uses it)',
    0xB0A0: '0..12: carry set (tonnes)',
    0xB0A3: '16 is also measured in tonnes',
    0xB0A9: '13..15 and 17+: carry clear',
    0xB0AB: '20 frames',
    0xB0AF: '36 frames',
    0xB0B1: 'wait for the next interrupt',
    0xB0B5: 'TextColumn and TextRow (adjacent bytes) as one word',
    0xB0BC: 'prompt row 21',
    0xB0C4: 'fill byte 0: blank pixels',
    0xB0C5: 'screen: text row 21, column 1, pixel line 0',
    0xB0CB: 'screen: text row 22, column 1, pixel line 0',
    0xB0CE: '8 pixel lines',
    0xB0D1: '30 cells (columns 1..30)',
    0xB0D9: 'next pixel line of the row (+$100)',
    0xB0E1: 'column and row restored together',
    0xB0E9: 'message 14: "{prompt}PLANET NAME? {nop}"',
    0xB0EB: 'at most 8 characters',
    0xB0ED: 'typed name buffer',
    0xB0F3: 'anything typed?',
    0xB0F7: 'empty input: just clear the prompt rows',
    0xB0FA: 'carry: no system of this galaxy has that name',
    0xB0FF: 'echo the typed name',
    0xB10D: 'beep (only with sound enabled)',
    0xB110: 'clear the key state and return',
    0xB117: 'found: name, distance line and beep',
    0xB120: 'maximum length',
    0xB121: 'patch the maximum length into InputLimitCompare',
    0xB127: 'write pointer starts at the buffer',
    0xB12E: 'no characters yet',
    0xB131: 'clear rows 21/22, cursor to row 21 column 0',
    0xB134: 'prompt and echo in capitals',
    0xB13B: 'print the prompt message',
    0xB13E: 'next key code',
    0xB144: 'Enter ends the input',
    0xB148: '$FE = delete key',
    0xB14F: "below '0': ignored",
    0xB153: "beyond 'Z': ignored",
    0xB157: "'0'..'9': accepted",
    0xB15B: "':'..'?' ignored; '@'..'Z' accepted",
    0xB15F: 'keep the character',
    0xB163: 'self-modified: maximum length (from B)',
    0xB165: 'buffer full: a further character ends the input like Enter',
    0xB16F: 'store the character',
    0xB174: 'echo it on the prompt row',
    0xB17D: 'delete with nothing typed: ignored',
    0xB186: 'step the write pointer back',
    0xB18A: 'erase the last character cell',
    0xB18D: 'pause 8 frames before the next key',
    0xB192: 'clear the key state',
    0xB19A: 'zero-terminate the string',
    0xB19F: 'pause 20 frames',
    0xB1A2: 'wait until Enter is released',
    0xB1A9: 'clear the key state and return',
    0xB1AC: 'select the system nearest the cursor (moves the cursor onto it)',
    0xB1AF: 'clear rows 21/22',
    0xB1BA: 'DISTANCE line (only when nonzero)',
    0xB1BD: 'beep (only with sound enabled)',
    0xB1C3: '$0A: galactic chart cross-hair size',
    0xB1C7: 'short-range chart: relative to the current system',
    0xB1CE: 'dx = cursor x - current x',
    0xB1CF: 'cursor left of the current system',
    0xB1D1: '2*dx; carry: off the chart',
    0xB1D3: '4*dx: 4 pixels per x unit',
    0xB1D6: 'short-range chart x centre',
    0xB1D9: 'beyond the right edge: not drawn',
    0xB1DC: '|dx|',
    0xB1E3: 'x centre again',
    0xB1E5: 'x = $61 - 4*|dx|',
    0xB1E6: 'beyond the left edge: not drawn',
    0xB1E7: 'cross-hair centre x',
    0xB1F1: 'dy = cursor y - current y',
    0xB1F4: '2*dy: 2 pixels per y unit',
    0xB1F7: 'short-range chart y centre',
    0xB1F9: 'y = $60 + 2*dy',
    0xB1FD: '|dy|',
    0xB202: 'y centre again',
    0xB204: 'y = $60 - 2*|dy|',
    0xB206: 'above pixel row 25: not drawn',
    0xB209: 'pixel row 167 or below: not drawn',
    0xB20C: 'cross-hair centre y',
    0xB211: 'galactic chart: x = cursor x (1 pixel per unit)',
    0xB21A: 'half height: y/2',
    0xB21C: 'galactic chart: y/2 + 24',
    0xB221: 'XOR the cross-hair (a second call erases it)',
    0xB224: 'erase the cross-hair at the old position',
    0xB22A: 'two units up',
    0xB22C: '$FE/$FF: moved past 0',
    0xB230: 'clamp at 0',
    0xB236: 'erase the cross-hair at the old position',
    0xB23C: 'two units down',
    0xB23E: '0/1: moved past 255',
    0xB242: 'clamp at 255',
    0xB249: 'erase the cross-hair at the old position',
    0xB24F: 'one unit left',
    0xB252: 'x 0 is not allowed: back to 1',
    0xB256: 'draw the cross-hair at the new position',
    0xB259: 'erase the cross-hair at the old position',
    0xB25F: 'one unit right',
    0xB260: '255 is not allowed',
    0xB264: 'back to 254',
    0xB26A: 'erase the cross-hair at the old position',
    0xB26D: 'cursor := current system coordinates',
    0xB27E: 'bit 5: refugees aboard (ShowInventory lists REFUGEES)',
    0xB280: 'refugees aboard: no market, pause and show the inventory',
    0xB282: 'NovaMissionActive nonzero: nova refugee offer instead of the buy list',
    0xB286: 'zero: normal buy list',
    0xB288: 'D = message 91 (nova offer), E = attribute $17',
    0xB28B: 'text column 1, row 2',
    0xB28E: 'blank screen, all attributes $17, message 91',
    0xB291: 'circle centre x',
    0xB296: 'circle centre y',
    0xB29B: 'circle radius',
    0xB2A0: 'draw the circle straight on the screen',
    0xB2A3: 'read the answer',
    0xB2A6: "'Y' accepts",
    0xB2A8: 'any other key declines',
    0xB2AA: "accept: large cargo bay byte := 'Y' (nonzero)",
    0xB2AE: 'no free cargo space',
    0xB2B1: 'empty all 17 hold bytes',
    0xB2B4: '17 commodities',
    0xB2BD: 'refugees aboard',
    0xB2BF: 'pause, then the inventory',
    0xB2C7: 'blank framed screen, cursor at row 1',
    0xB2D6: 'colour text rows 1 and 2',
    0xB2D9: 'colour the prompt row 21',
    0xB2DC: 'commodity 0; hold and price pointers',
    0xB2DF: 'station stock, pre-incremented per commodity',
    0xB2E2: 'PrintMarketLine advances it per commodity',
    0xB2E8: 'hold byte of this commodity',
    0xB2EC: 'name, unit, price and stock; carry: nothing in stock',
    0xB2EF: 'out of stock: next commodity',
    0xB2F1: 'cursor is at the start of the next market line',
    0xB2F4: '"QUANTITY OF ..." on the prompt row',
    0xB2FD: 'bought: show the new cash',
    0xB301: 'A = 1: error, ask again',
    0xB305: 'A = 2: Enter, skip this commodity',
    0xB307: 'any other key: leave to the inventory',
    0xB30C: 'continue with the next market line',
    0xB314: '17 commodities',
    0xB324: '256 bytes per call',
    0xB32E: 'undo the first-digit attempt',
    0xB337: 'no number yet',
    0xB33D: 'Enter before any digit',
    0xB341: "first digit must be '1'..'9'",
    0xB343: "'0' and lower codes ignored",
    0xB347: 'delete before any digit: ignored',
    0xB349: 'any other key leaves the screen',
    0xB34E: 'digit value',
    0xB354: 'echo the digit',
    0xB35A: 'try the one-digit quantity',
    0xB35D: 'refused: carry, A from the handler',
    0xB364: 'Enter: keep the one-digit result (carry clear)',
    0xB367: "below '0': ignored",
    0xB36B: 'delete: undo and start again',
    0xB36F: 'other key: leave; the one-digit attempt stays applied',
    0xB375: 'EnteredNumber = EnteredNumber*10 + digit',
    0xB381: 'echo the second digit',
    0xB384: 'undo the one-digit attempt',
    0xB38A: 'try the two-digit quantity',
    0xB38F: 'accepted: carry clear',
    0xB3A1: 'checkpoint for RestoreTradeState',
    0xB3A8: 'station stock of this commodity',
    0xB3AD: 'not enough in stock',
    0xB3AF: 'stock reduced',
    0xB3B3: 'unit price in tenths of a credit',
    0xB3B9: 'not enough cash',
    0xB3BB: 'pay once per unit (B = quantity)',
    0xB3BD: 'carry: measured in tonnes',
    0xB3C4: 'kg/g goods use no cargo space',
    0xB3CB: 'not enough free cargo space',
    0xB3CD: 'free space reduced',
    0xB3CE: 'hold byte of this commodity',
    0xB3D3: 'hold byte overflow',
    0xB3D9: 'report the purchase (legal score for some goods)',
    0xB3DC: 'success: carry clear',
    0xB3F5: 'undo the failed attempt',
    0xB3FE: 'A = 1 with carry: the "retry" result',
    0xB447: 'capitalise the first letter',
    0xB450: 'commodity names are tokens $D0..$E0',
    0xB45E: 'unit in lower case',
    0xB478: 'nonzero: normal sell list',
    0xB47E: 'refugees aboard?',
    0xB480: 'no: normal sell list',
    0xB482: 'refugees delivered',
    0xB487: 'combat score high byte + 1',
    0xB488: 'reward: 100 g of gem-stones (commodity 15)',
    0xB48D: 'free space 35: the empty large cargo bay',
    0xB492: 'D = message 15, E = attribute $0F',
    0xB495: 'text column 0, row 7',
    0xB498: 'message 15 and a key wait',
    0xB4BC: 'colour the prompt row 21',
    0xB4C2: 'price word of this commodity',
    0xB4CA: 'carry: none of it in the hold',
    0xB4CD: 'not held: next commodity',
    0xB4D8: 'SellCommodity runs after every digit',
    0xB4DB: 'refused, skipped or left',
    0xB4DD: 'sold: show the new cash',
    0xB4EB: '17 commodities',
    0xB4F0: '40 frames in total',
    0xB4F8: 'A = 1: error, ask again',
    0xB4FB: 'A = 2: Enter, skip this commodity',
    0xB4FE: 'other keys come straight here',
    0xB501: 'checkpoint for RestoreTradeState',
    0xB50D: 'more than held',
    0xB510: 'hold reduced',
    0xB516: 'kg/g goods free no cargo space',
    0xB51B: 'free space += quantity',
    0xB526: 'paid once per unit',
    0xB52C: 'success: carry clear (no legal-score change when selling)',
    0xB52E: 'hold array starts at record +$17 (pointer pre-incremented)',
    0xB534: 'price words start two bytes later (pre-incremented by 2)',
    0xB542: 'title in capitals',
    0xB553: 'end the title line and leave a blank line',
    0xB556: 'first price entry (item 1)',
    0xB55C: 'tech level',
    0xB561: 'tech level 9 or more offers all 14 items',
    0xB565: 'counts 12 and 13 become 14: items 12..14 appear together',
    0xB56F: 'index 0 = item 1 (fuel)?',
    0xB571: 'nonzero: fuel is not offered',
    0xB575: 'fuel not listed',
    0xB579: 'item number in a 3-character field',
    0xB57F: 'items are numbered from 1',
    0xB587: 'token $69+index: item name',
    0xB594: 'price entry: high byte, then low word',
    0xB5A0: 'HL = high part (units of 10000 tenths)',
    0xB5A3: 'price with one decimal place',
    0xB5B1: 'all offered items listed?',
    0xB5B4: 'clear rows 21/22',
    0xB5C0: 'snapshot: InputQuantity may call RestoreTradeState',
    0xB5C9: 'non-digit key: status screen',
    0xB5D2: 'item 0 (cannot be typed): status screen',
    0xB5D9: 'item beyond the offered list?',
    0xB5DA: 'non-digit key or item not offered: status screen',
    0xB5DD: 'checkpoint before paying',
    0xB5E8: 'high part of the price',
    0xB5EA: 'carry is clear here (ADD HL,DE in AddAToHL)',
    0xB5F1: 'low part of the price (tenths)',
    0xB5F7: 'not enough cash: "CASH?", undo, ask again',
    0xB5FD: 'item 1: fuel',
    0xB605: 'L_A843 set: refused, the fuel price is not refunded',
    0xB608: 'fuel price low byte := 0 (its high byte is always 0)',
    0xB60E: 'fill the tank: 70 = 7.0 light years',
    0xB613: 'list the items again',
    0xB616: 'item 2: missile',
    0xB61E: 'four missiles at most',
    0xB624: 'one more missile',
    0xB627: 'item 3: large cargo bay',
    0xB62B: 'large cargo bay already fitted?',
    0xB636: 'free cargo space +15',
    0xB63B: 'item 4: E.C.M. system',
    0xB63F: 'items 5 and 6: lasers',
    0xB643: 'items 13 and 14: lasers; 7..12 fall through',
    0xB647: 'commander byte of the item',
    0xB64C: 'already fitted',
    0xB652: '$FF: item fitted',
    0xB654: 'new cash, then the next item',
    0xB670: 'new screen for the view choice',
    0xB677: 'column 4 + laser type',
    0xB67D: 'row 14',
    0xB685: 'token $68+item: laser name',
    0xB68B: 'views listed from row 16',
    0xB69B: "view number '0'..'3'",
    0xB6A3: 'token $60+view: FRONT, REAR, LEFT, RIGHT',
    0xB6AC: 'four views',
    0xB6B0: 'clear rows 21/22',
    0xB6BB: 'view key',
    0xB6C0: "below '0': cancel the purchase",
    0xB6C5: "above '3': cancel the purchase",
    0xB6C9: 'echo the key',
    0xB6CF: 'laser type per view (4 bytes)',
    0xB6D5: 'laser type previously in this view',
    0xB6D9: 'fit the new laser',
    0xB6DC: 'view was empty: nothing to refund',
    0xB6DE: 'table of item numbers for laser types 1..4 (index 1-based)',
    0xB6E4: 'item number of the old laser',
    0xB6EA: 'refund the high part of its price',
    0xB6F4: 'refund the low part',
    0xB6F7: 'new cash, then the equipment list',
    0xB70A: 'items are numbered from 1',
    0xB70D: 'A = 3*(item-1)',
    0xB713: 'item n uses the byte at L_A843 + n',
    0xB71E: 'token $7C: "ALL"',
    0xB722: 'item names are tokens $69..$76',
    0xB733: 'undo the purchase (cash)',
    0xB747: 'banner attribute $17',
    0xB749: 'attribute row 0, column 0',
    0xB74C: '96 cells: attribute rows 0..2',
    0xB751: 'pixel row 23',
    0xB762: 'leading spaces or zeros up to the field width',
    0xB766: 'skip leading zero digits from here on',
    0xB76B: 'value still to be printed',
    0xB76E: '10000',
    0xB774: '1000',
    0xB77A: '100',
    0xB780: '10',
    0xB787: 'no decimal point requested',
    0xB78D: 'a digit was printed already',
    0xB790: 'value below 10: "0" before the point',
    0xB798: 'units digit (the tenth when a point was printed)',
    0xB7A0: 'reset the field width',
    0xB7A4: 'LeadingZeroFlag = 1 again',
    0xB7A8: 'high part: units of 10000 tenths',
    0xB7B2: 'below 1000 Cr: a single field',
    0xB7B4: 'high part in 3 characters',
    0xB7B9: 'no decimal point',
    0xB7BE: 'low part padded with zeros',
    0xB7C1: '4 digits including the tenth',
    0xB7C8: '7 digits including the tenth, space-padded',
    0xB7CE: 'with one decimal place',
    0xB7D5: 'digit 0, carry clear',
    0xB7D7: 'subtract the divisor until it goes negative',
    0xB7DE: 'undo the last subtraction: remainder',
    0xB7E3: 'zero digit',
    0xB7E7: 'nonzero digit: stop skipping zeros',
    0xB7EB: "digit to '0'..'9'",
    0xB7F4: 'zero digit printed unless still leading',
    0xB7F7: 'at least one digit',
    0xB7F9: 'no decimal point',
    0xB803: 'below 10 with a point: 2 digits ("0.n")',
    0xB80C: 'below 10: 1 digit',
    0xB814: 'below 100: 2 digits',
    0xB81C: 'below 1000: 3 digits',
    0xB824: 'below 10000: 4 digits, otherwise 5',
    0xB82E: 'field not wider than the number: no padding',
    0xB830: 'number of padding characters',
    0xB837: 'flag clear: pad with zeros',
    0xB83A: 'flag set: pad with spaces',
    0xB850: 'add to the low word',
    0xB855: 'cash low word wraps at 10000 tenths',
    0xB858: '10000 or more?',
    0xB85B: 'keep the excess',
    0xB85E: 'carry 1 into the high word',
    0xB86C: 'carry: not enough',
    0xB873: 'success: carry clear',
    0xB875: 'not enough: carry set, cash unchanged',
    0xB87D: 'the low word suffices',
    0xB885: 'high word 0 too: not enough (carry set)',
    0xB886: 'borrow one high unit',
    0xB88A: 'borrow 10000 tenths from the high word',
    0xB894: 'low = low + 10000 - price',
    0xB898: 'success: carry clear',
    0xB8A4: 'two bytes per handler address',
    0xB8AB: 'jump to the handler',
    0xB8B9: 'cash with one decimal place',
    0xB8BC: 'token $E2: " CR"',
    0xB8BE: 'shared tail: token, then a new line',
    0xB8C0: 'the name is the first field of the record',
    0xB8C3: 'print it as a token string',
    0xB8C5: 'mode 0: title case',
    0xB8D2: 'tenths of a light year',
    0xB8DF: 'field width 2',
    0xB8E2: 'galaxies 0..7 shown as 1..8',
    0xB8EF: 'six galaxy seed bytes',
    0xB8F4: 'name of the system with the galaxy seeds',
    0xB8FF: 'name of the system the ship is in',
    0xB907: 'name of the selected (target) system',
    0xB90A: 'print the name',
    0xB913: 'capitalise the next letter once',
    0xB91A: 'random byte',
    0xB91D: '1..4 letter pairs',
    0xB923: 'even offset: pair 1..32',
    0xB92D: 'first letter of the pair',
    0xB932: "second letter ('?' is skipped)",
    0xB937: 'last pair printed',
    0xB93B: 'mode 2: lower case',
    0xB940: 'mode 1: capitals',
    0xB94C: 'print the name; HL ends at its terminator',
    0xB94F: 'last letter of the name',
    0xB951: 'five vowels',
    0xB956: 'is it a vowel?',
    0xB95C: 'then "IAN"',
    0xB961: 'drop the vowel from the justified line buffer',
    0xB964: 'one character fewer in the line',
    0xB969: 'the next character overwrites the vowel',
    0xB977: 'mode 1: decode message bytes',
    0xB97B: 'mode 0: message bytes are tokens',
    0xB98B: "'?': one-letter pair",
    0xB991: 'select the system nearest the cursor',
    0xB994: 'blank framed screen, title rule',
    0xB997: 'attribute bars of this screen',
    0xB9A2: 'first data line at row 3',
    0xB9A7: 'DISTANCE line (only when nonzero)',
    0xB9AD: 'Economy line and a blank line',
    0xB9B5: 'token $B1+government',
    0xB9BC: 'government name and a blank line',
    0xB9C6: 'field width 3',
    0xB9CC: 'tech level shown from 1',
    0xB9DB: 'population in tenths of a billion',
    0xB9DE: 'token $C6: " BILLION"',
    0xB9E7: 'species, printed as "(...S)"',
    0xB9F8: 'gross productivity',
    0xB9FD: 'field width 5',
    0xBA00: 'no decimal point',
    0xBA0C: 'token $E2: " CR", in capitals',
    0xBA19: 'average radius, 5 characters',
    0xBA20: 'unit index 17 prints "km"',
    0xBA25: 'unit "km"',
    0xBA2E: 'L_A871 zero: planet description',
    0xBA34: "carry clear: it is the galaxy's first system",
    0xBA37: 'another system: planet description',
    0xBA39: 'attribute $03 for text rows 19 and 20',
    0xBA3B: 'attribute row 19, column 1',
    0xBA4C: 'description generator seeded per system',
    0xBA6A: 'economy 0..7',
    0xBA6F: '4: "MAINLY"',
    0xBA71: '0..3: the same "RICH" path',
    0xBA73: '5..7: result unused (A is replaced)',
    0xBA75: 'always "RICH ": the inline token replaces A',
    0xBA7C: 'economy / 4: 0..3 industrial, 4..7 agricultural',
    0xBA80: '$A8 INDUSTRIAL, $A9 AGRICULTURAL',
    0xBA82: 'type, new line and blank line',
    0xBA88: 'then the economy type',
    0xBA8E: 'low seed byte $80 or more: alien species',
    0xBA93: 'token $BC: "HUMAN COLONIAL"',
    0xBA9F: 'codes 0..13: control handlers',
    0xBAA4: '14..31: dictionary tokens $80..$91',
    0xBAA9: '32..95: characters',
    0xBAAE: '96..127: dictionary tokens 96..127',
    0xBAB2: '128..159: two-letter tokens',
    0xBAB5: '160..255: dictionary tokens 0..95',
    0xBAC1: 'reached token A',
    0xBAC8: 'skip one zero-terminated token',
    0xBACE: 'zero: end of the token',
    0xBACF: 'tokens nest: HL is saved',
    0xBADC: 'reached message A',
    0xBAE2: 'skip one zero-terminated message',
    0xBAEE: 'mode 0: pass the byte to PrintToken',
    0xBAF2: 'codes 0..31: control handlers',
    0xBAF7: '$20..$5A: characters',
    0xBAFB: '$5B..$80: random choice of five messages',
    0xBB00: '$81..$D6: nested message',
    0xBB02: '$D7..$FF: two-letter token',
    0xBB05: 'print the message bytes up to the zero',
    0xBB09: 'messages nest: HL is saved',
    0xBB12: "below 'A': not a letter",
    0xBB16: "above 'Z': not a letter",
    0xBB1E: 'mode 1: letters unchanged (capitals)',
    0xBB24: 'no one-shot capital pending',
    0xBB27: 'one-shot capital used up',
    0xBB2A: 'and the title-case request too',
    0xBB34: 'no capital requested: lower case',
    0xBB37: 'title-case capital used up',
    0xBB3F: 'mode 2: lower case even after a non-letter',
    0xBB44: 'to lower case',
    0xBB4C: 'a non-letter requests a capital next',
    0xBB54: 'redirected into the justified-line buffer',
    0xBB5C: 'the cursor advances before drawing',
    0xBB5E: 'past column 31?',
    0xBB62: 'wrap to column 1',
    0xBB65: 'of the next row',
    0xBB71: 'BC = 8 * glyph index',
    0xBB7F: 'self-modified high byte: $40 screen or $C0 view buffer',
    0xBB85: 'rows 16..23: bottom third',
    0xBB8A: 'rows 8..15: middle third',
    0xBB96: 'bottom third starts $1000 later',
    0xBBA0: 'middle third starts $0800 later',
    0xBBA6: 'BC = 32 * row within the third',
    0xBBB9: '+ column',
    0xBBC1: 'next pixel line of the cell (+$100)',
    0xBBC6: 'text row 21, column 1',
    0xBBC9: 'attribute $05',
    0xBBD0: 'skip columns 31 and 0: next row, column 1',
    0xBBD3: 'pixel row 19',
    0xBBD6: '$FF: all 8 pixels set',
    0xBBD8: '32 bytes: the full width',
    0xBBDF: 'text row 1, column 1',
    0xBBE2: 'next strip byte',
    0xBBE7: 'cell count = bits 7..3',
    0xBBEC: 'strip attribute $05',
    0xBBF3: 'bits 2..0: rows down to the next strip',
    0xBBF5: '0: end of the list',
    0xBBF8: 'down one attribute row (32 bytes)',
    0xBC03: 'two cells at row 1, columns 2..3',
    0xBC08: 'cells 2 and 3 of row 1 set to $07',
    0xBC0C: 'pair index',
    0xBC18: 'two bytes per pair',
    0xBC25: "'?': one-letter pair",
    0xBC2D: 'index into RandomMessageTable',
    0xBC3B: 'random below $33: choice 0',
    0xBC40: 'below $66: choice 1',
    0xBC45: 'below $99: choice 2',
    0xBC4A: 'below $CC: choice 3, otherwise 4',
    0xBC54: 'base message + choice',
    0xBC5B: 'shift the low byte of w1 (carry out)',
    0xBC61: 'w2 + w1 + carry',
    0xBC63: 'result: its high byte',
    0xBC68: 'w2 := old w1 (shifted)',
    0xBC9E: 'no interrupts while SP points into the screen',
    0xBC9F: 'save SP: the screen is filled by PUSH',
    0xBCA3: 'SP = end of the attribute area',
    0xBCA6: 'attribute $07 (white ink, black paper)',
    0xBCA9: '24 x 16 pushes = 768 attribute bytes',
    0xBCB4: 'bitmap: all pixels off',
    0xBCB7: '192 x 16 pushes = 6144 bitmap bytes',
    0xBCC2: 'restore the stack pointer',
    0xBCC7: '192 pixel lines',
    0xBCCC: 'left byte column, from the top line',
    0xBCD0: 'leftmost pixel',
    0xBCD3: '+32 bytes: column 0 of all 192 lines, in memory order',
    0xBCD8: 'right-hand byte column',
    0xBCDC: 'rightmost pixel',
    0xBCE2: 'top pixel line',
    0xBCE8: 'bottom pixel line',
    0xBCF2: 'TextColumn = 0, TextRow = 1',
    0xBCFC: 'advance to the next free position',
    0xBD03: 'character left on the stack by PrintCharacter',
    0xBD05: "'.' prints the line at once",
    0xBD0B: 'one more character in the line',
    0xBD12: 'line holds 30 characters',
    0xBD14: 'line not full yet',
    0xBD15: 'the 31st character: a space just ends the line',
    0xBD1B: 'B = length of the word cut by the line end',
    0xBD2C: 'carry buffer for the partial word',
    0xBD2F: 'move the cut word to the carry buffer',
    0xBD3B: 'the next line continues after it',
    0xBD41: 'never taken: FindPreviousSpace returns B <= 30',
    0xBD4A: 'zero the cut word and its space: free cells',
    0xBD52: 'one extra space per freed cell',
    0xBD53: 'next gap to the left (wraps at the line start)',
    0xBD56: 'widen that gap by one space',
    0xBD60: '30 characters per line',
    0xBD65: 'no case conversion: already applied when buffered',
    0xBD72: 'no capital at the start of the next line',
    0xBD78: 'the line continues after the carried word',
    0xBD84: 'its length so far',
    0xBD8D: 'refill value: space',
    0xBD96: 'carried word to the line start',
    0xBD97: 'carry buffer back to spaces',
    0xBDA2: '31 bytes: $7023..$7041 (overwrites CurrentScreenId)',
    0xBDAD: 'no carried word yet',
    0xBDC2: 'flush a partly filled line (not justified)',
    0xBDCB: 'scan backwards',
    0xBDD0: 'until a space',
    0xBDDB: 'still inside the line',
    0xBDDC: 'passed the start: continue from the line end',
    0xBDE6: 'no ECM fitted',
    0xBDE7: 'key bit 4 from L_FC11',
    0xBDE9: 'ECM key not pressed',
    0xBDEA: 'bit 7: ECM active',
    0xBDEF: 'EcmTimer = 10',
}

DATA = {
    0xB0E5: (0xB0E6, 'bytes', 1),
    0xB0E6: (0xB0E8, 'words', 1),
    0xB0E8: (0xB0E9, 'bytes', 1),
    0xB11A: (0xB11B, 'bytes', 1),
    0xB11B: (0xB11D, 'words', 1),
    0xB2C5: (0xB2C7, 'bytes', 2),
    0xB46A: (0xB46C, 'words', 1),
    0xB46C: (0xB46E, 'words', 1),
    0xB46E: (0xB46F, 'bytes', 1),
    0xB46F: (0xB470, 'bytes', 1),
    0xB470: (0xB471, 'bytes', 1),
    0xB471: (0xB472, 'bytes', 1),
    0xB472: (0xB474, 'words', 1),
    0xB49E: (0xB49F, 'bytes', 1),
    0xB739: (0xB73A, 'bytes', 1),
    0xB73A: (0xB73B, 'bytes', 1),
    0xB73B: (0xB73D, 'words', 1),
    0xB73D: (0xB73E, 'bytes', 1),
    0xB757: (0xB759, 'words', 1),
    0xB93F: (0xB940, 'bytes', 1),
    0xB96E: (0xB972, 'text', 4),
    0xB972: (0xB977, 'text', 5),
    0xBA98: (0xBA99, 'bytes', 1),
    0xBC76: (0xBC9C, 'bytes', 8),
    0xBC9C: (0xBC9E, 'words', 1),
    0xBCF6: (0xBCF8, 'words', 1),
    0xBCF8: (0xBCF9, 'bytes', 1),
    0xBCF9: (0xBCFA, 'bytes', 1),
    0xBCFA: (0xBCFC, 'words', 1),
    0xBDF5: (0xBE00, 'zeros', 11),
}

SEEDS = {
    0xB1AC: 'JP $B1AC at $A804 (chart key jump table); executed in the chart-cursor trace',
    0xB224: 'JP $B224 at $A7FE (chart key jump table); executed in the chart-cursor trace',
    0xB236: 'JP $B236 at $A7FB (chart key jump table); executed in the chart-cursor trace',
    0xB249: 'JP $B249 at $A7F5 (chart key jump table); executed in the chart-cursor trace',
    0xB259: 'JP $B259 at $A7F8 (chart key jump table); executed in the chart-cursor trace',
    0xB26A: 'JP $B26A at $A801 (chart key jump table); executed in the chart-cursor trace',
    0xB31B: 'dormant routine: its two CALL operands ($B31F/$B322) target its own loop $B324',
}

OPERANDS = {
    # Pointer bases that are pre-incremented before each use.
    0xB2DF: 'MarketStock-1',   # station stock array at record +$4A
    0xB52E: 'CargoHold-1',   # hold (cargo) array at record +$17
}

TEXTCALLS = {
    0xB049: 'token',
    0xB057: 'token',
    0xB11D: 'message',
    0xB73E: 'token',
    0xBA5A: 'token',
}

TEXTNAMES = {
    ('token', 0): 'nop',
    ('token', 1): 'galaxy',
    ('token', 2): 'present-system',
    ('token', 3): 'selected-system',
    ('token', 4): 'commander',
    ('token', 5): 'fuel',
    ('token', 6): 'caps',
    ('token', 7): 'cash',
    ('token', 8): 'title-case',
    ('token', 9): 'cr',
    ('token', 10): 'msg-mode',
    ('token', 11): 'first-system',
    ('token', 12): 'nop',
    ('token', 13): 'nop',
    ('message', 0): 'nop',
    ('message', 1): 'caps',
    ('message', 2): 'title-case',
    ('message', 3): 'selected-system',
    ('message', 4): 'commander',
    ('message', 5): 'msg-mode',
    ('message', 6): 'token-mode',
    ('message', 7): 'beep',
    ('message', 8): 'col4-cap',
    ('message', 9): 'cls',
    ('message', 10): 'next-row',
    ('message', 11): 'rule',
    ('message', 12): 'cr',
    ('message', 13): 'lower',
    ('message', 14): 'justify',
    ('message', 15): 'end-justify',
    ('message', 16): 'first-system',
    ('message', 17): 'adjective',
    ('message', 18): 'random-name',
    ('message', 19): 'cap-next',
    ('message', 20): 'nop',
    ('message', 21): 'prompt',
    ('message', 22): 'wait20',
    ('message', 23): 'row10',
    ('message', 24): 'wait36',
    ('message', 25): 'empty-wait36',
    ('message', 26): 'nop',
    ('message', 27): 'nop',
    ('message', 28): 'nop',
    ('message', 29): 'row6',
    ('message', 30): 'nop',
    ('message', 31): 'nop',
}
