import os

# Mojibake sequences - these are UTF-8 characters misread as latin-1
# We detect them by looking for the byte patterns that result from this misencoding.
# Pattern: bytes that look like windows-1252/latin-1 but are actually UTF-8 emoji bytes.

def has_mojibake(text):
    """Check if text contains common mojibake sequences from UTF-8/Latin-1 confusion."""
    # These hex sequences are common garbled multi-byte chars
    indicators = [
        '\xc3\xb0\xc5\xb8',   # ðŸ prefix (U+00F0 U+0178 in latin-1 misread UTF-8)
        '\xe2\x80',             # â€ prefix 
        '\xc3\xa2\xe2\x82\xac', # â€˜ left quote
        '\xc3\x83\xc2\xa9',    # Ã© e accent
        '\xc3\x82\xc2\xa0',    # Â non-breaking space
        '\xe2\x9c\x94',         # check mark
        '\xc3\xaf\xc2\xb8',    # ï¸ variation selector
    ]
    return False  # placeholder

# Instead, detect by looking for the visible garbled characters in the file
# We read as bytes and look for specific UTF-8 byte sequences
# that when decoded as latin-1 produce the garbled characters we see

MOJIBAKE_BYTES = [
    b'\xc3\xb0\xc5\xb8',   # start of "ðŸ" garbled emoji prefix
    b'\xe2\x80\x99',         # â€™ right single quote garbled
    b'\xe2\x80\x93',         # â€" em dash garbled  
    b'\xe2\x80\x98',         # â€˜ left single quote garbled
    b'\xe2\x80\xa6',         # … ellipsis garbled
    b'\xe2\x80\x9c',         # â€œ left double quote garbled
    b'\xe2\x80\x9d',         # â€ right double quote garbled
    b'\xc3\xa9',             # Ã© e with accent garbled
    b'\xc3\x82\xc2\xa0',    # Â non-breaking space garbled
]

# Actually let's just search for the visible mojibake strings as they appear
# by reading with latin-1 encoding and looking for the mojibake patterns
LATIN1_MOJIBAKE = [
    # These are what you SEE in the file when UTF-8 is misread as latin-1
    b'\xc3\xb0\xc5\xb8',   # ðŸ emoji prefix garbled
    b'\xe2\x80\x99',
    b'\xe2\x80\x93',
    b'\xe2\x80\x9c',
    b'\xe2\x80\x9d',
    b'\xc3\xa9',
]

matches = []
for root, dirs, files in os.walk('.'):
    dirs[:] = [d for d in dirs if d not in ['__pycache__', '.git', 'node_modules', 'venv', 'migrations']]
    for fname in files:
        if any(fname.endswith(ext) for ext in ['.py', '.html', '.js', '.css']):
            fpath = os.path.join(root, fname)
            try:
                raw = open(fpath, 'rb').read()
                # Check if any mojibake byte sequences exist
                found_seqs = []
                for seq in LATIN1_MOJIBAKE:
                    if seq in raw:
                        found_seqs.append(seq.hex())
                if found_seqs:
                    matches.append((fpath, found_seqs))
            except Exception as e:
                pass

print(f'Found {len(matches)} files with potential mojibake byte sequences:')
for fpath, seqs in matches:
    print(f'  {fpath}: {seqs}')
