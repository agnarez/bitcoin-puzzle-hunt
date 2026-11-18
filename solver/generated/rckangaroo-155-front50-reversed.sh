# RCKangaroo — puzzle #155, FRONT-50% window, REVERSED
# Mirrored pubkey Q_rev = (a+b)*G - Q for the front-50% interval.
# If this run finds k_rev, the real key is k = a + b - k_rev
#   where a = 400000000000000000000000000000000000000, b = 5ffffffffffffffffffffffffffffffffffffff.
# NEVER write a found key into this file or any public file.
RCKangaroo -dp 16 -range 153 -start 400000000000000000000000000000000000000 -pubkey 03411b6375e408a1737d06f382add280ef679d5d1cae8b0ab69e89f2232b7dff27
