# RCKangaroo — puzzle #145, FRONT-50% window, REVERSED
# Mirrored pubkey Q_rev = (a+b)*G - Q for the front-50% interval.
# If this run finds k_rev, the real key is k = a + b - k_rev
#   where a = 1000000000000000000000000000000000000, b = 17fffffffffffffffffffffffffffffffffff.
# NEVER write a found key into this file or any public file.
RCKangaroo -dp 16 -range 143 -start 1000000000000000000000000000000000000 -pubkey 032feb49bf843e25fa8e4343ba71aae3cb28dbede1cc7fed9f47298cd11970a43a
