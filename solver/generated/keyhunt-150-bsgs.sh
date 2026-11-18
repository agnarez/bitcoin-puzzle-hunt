# KeyHunt BSGS — puzzle #150
# WARNING: BSGS memory is ~sqrt(width) points. Full/front-50% #140
# needs ~2^69 table entries — impossible. Use only on small
# subranges (see solver/bsgs.py, which refuses large intervals).
# Forward:
./keyhunt -m bsgs -f keyhunt-150.txt -b 150 -R
# Reversed (both directions):
./keyhunt -m bsgs -f keyhunt-150.txt -b 150 -B both -R
