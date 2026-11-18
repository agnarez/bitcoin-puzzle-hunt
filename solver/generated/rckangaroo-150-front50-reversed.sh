# RCKangaroo — puzzle #150, FRONT-50% window, REVERSED
# Mirrored pubkey Q_rev = (a+b)*G - Q for the front-50% interval.
# If this run finds k_rev, the real key is k = a + b - k_rev
#   where a = 20000000000000000000000000000000000000, b = 2fffffffffffffffffffffffffffffffffffff.
# NEVER write a found key into this file or any public file.
RCKangaroo -dp 16 -range 148 -start 20000000000000000000000000000000000000 -pubkey 022169411f57af7f2b31bce02901ef8fab3a555f1148f6e2def26db7f952f503ec
