# JeanLucPons Kangaroo — puzzle #155, FRONT-50% window
# HARD LIMIT: interval width <= 125 bits. Front-50% width is 153 bits, so it splits into 268435456 chunks of 2^125 keys each.
# Two example chunk files are generated (centre + first).
# Generate ALL chunk files with: python3 -c "..." (see generated/README.md)
# Or use the Kangaroo-256 fork (ZenulAbidin/Kangaroo-256), which
# lifts the cap to 256 bits and takes the same 3-line format:
#   ./Kangaroo -gpu jlp-kangaroo-155-front50-full.txt
# Example chunk run:
./Kangaroo -gpu jlp-kangaroo-155-front50-centre-chunk134217728.txt
