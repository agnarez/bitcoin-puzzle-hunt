# KeyHunt BSGS — puzzle #145
# WARNING: BSGS memory is ~sqrt(width) points. Full/front-50% #140
# needs ~2^69 table entries — impossible. Use only on small
# subranges (see solver/bsgs.py, which refuses large intervals).
# Forward:
./keyhunt -m bsgs -f keyhunt-145.txt -b 145 -R
# Reversed (both directions):
./keyhunt -m bsgs -f keyhunt-145.txt -b 145 -B both -R
