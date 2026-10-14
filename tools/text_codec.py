"""Decode Elite's two text encodings for source comments.

The reference code defines both formats; this module reads its table
addresses from the immutable reference instructions, so it never relies on
the current build's layout.  Two interpreters exist in the game:

* PrintToken ($BA9D in the reference): a byte selects a control handler,
  a character, a dictionary token or a two-letter token.
* PrintMessage ($BAD7): message N is the N-th zero-terminated entry of the
  message table, interpreted by PrintMessageByte ($BAE7).  While the mode
  byte at $BA98 is zero, message bytes are handed to PrintToken instead.

The renderer is for documentation.  Control and random choices are shown
symbolically, e.g. {cr} or {A|B|C|D|E}; case conversion is not applied.
"""

BASE = 0x6048

# Reference instruction operands that locate the tables (opcode, address).
OPERANDS = dict(
    dictionary=(0x21, 0xBABB),        # LD HL,TextTokenDictionary
    messages=(0x21, 0xBAD7),          # LD HL,MessageTable
    pairs=(0x21, 0xBC15),             # LD HL,two-letter tokens $80..$9F
    message_pairs=(0x21, 0xBC0E),     # LD HL,two-letter tokens $D7..$FF
    random=(0x21, 0xBC30),            # LD HL,random message choices
    token_controls=(0x21, 0xB89F),    # LD HL,PrintToken control handlers
    message_controls=(0x21, 0xB89A),  # LD HL,PrintMessage control handlers
)
RANDOM_CHOICES = 5


class TextCodec:
    def __init__(self, image, names=None):
        self.image = bytes(image)
        self.names = names or {}
        self.table = {key: self.operand(*spec) for key, spec in OPERANDS.items()}

    def byte(self, address):
        return self.image[address - BASE]

    def operand(self, opcode, address):
        if self.byte(address) != opcode:
            raise ValueError(f'Text table operand changed at ${address:04X}')
        return self.byte(address + 1) | self.byte(address + 2) << 8

    def entry(self, table, number):
        """Address of the number-th zero-terminated string of a table."""
        address = table
        for _ in range(number):
            while self.byte(address):
                address += 1
            address += 1
        return address

    def string(self, address):
        values = []
        while self.byte(address):
            values.append(self.byte(address))
            address += 1
        return values

    def pair(self, table, index):
        a, b = self.byte(table + 2 * index), self.byte(table + 2 * index + 1)
        return chr(a) + ('' if b == 0x3F else chr(b))

    def control(self, kind, code):
        handlers = self.table['token_controls' if kind == 'token' else 'message_controls']
        address = handlers + 2 * code
        target = self.byte(address) | self.byte(address + 1) << 8
        name = self.names.get((kind, code)) or self.names.get(target)
        return '{' + (name or f'{kind[0]}{code}') + '}'

    def token(self, code, depth=0):
        """Render one byte as interpreted by PrintToken."""
        if depth > 8:
            return '{...}'
        if code < 0x0E:
            return self.control('token', code)
        if code < 0x20:
            return self.dictionary(code + 0x72, depth)
        if code < 0x60:
            return chr(code)
        if code < 0x80:
            return self.dictionary(code, depth)
        if code < 0xA0:
            return self.pair(self.table['pairs'], code - 0x80)
        return self.dictionary(code - 0xA0, depth)

    def dictionary(self, number, depth=0):
        address = self.entry(self.table['dictionary'], number)
        return ''.join(self.token(value, depth + 1) for value in self.string(address))

    def message(self, number, depth=0, mode=None):
        """Render message N (1-based) as interpreted by PrintMessage."""
        if depth > 6:
            return '{...}'
        address = self.entry(self.table['messages'], number - 1)
        return self.message_bytes(self.string(address), depth, mode)

    def message_bytes(self, values, depth=0, mode=None):
        state = dict(extended=True if mode is None else mode)
        return ''.join(self.message_byte(value, depth, state) for value in values)

    def message_byte(self, code, depth, state):
        if not state['extended']:
            text = self.token(code, depth)
            # PrintToken control 10 selects message mode again (sets $BA98).
            if code == 10:
                state['extended'] = True
            return text
        if code < 0x20:
            if code == 6:      # Message control 6 clears $BA98.
                state['extended'] = False
            elif code == 5:
                state['extended'] = True
            return self.control('message', code)
        if code < 0x5B:
            return chr(code)
        if code < 0x81:
            first = self.byte(self.table['random'] + code - 0x5B)
            choices = [self.message(first + n, depth + 1) for n in range(RANDOM_CHOICES)]
            return '{' + '|'.join(choices) + '}'
        if code < 0xD7:
            return self.message(code, depth + 1)
        return self.pair(self.table['message_pairs'], code - 0xD7)

    def message_count(self, end):
        number, address = 0, self.table['messages']
        while address < end:
            while self.byte(address):
                address += 1
            address += 1
            number += 1
        return number


def clip(text, limit=100):
    text = text.replace('\n', ' ')
    return text if len(text) <= limit else text[:limit - 3] + '...'


if __name__ == '__main__':
    from tape import reference
    codec = TextCodec(reference()[1][5].payload)
    for number in range(1, 40):
        print(f'message {number:3}: {clip(codec.message(number), 150)}')
    for number in range(0, 0x92):
        print(f'token {number:3}: {codec.dictionary(number)}')
