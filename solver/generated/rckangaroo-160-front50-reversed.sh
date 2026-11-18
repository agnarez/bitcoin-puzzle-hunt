# RCKangaroo — puzzle #160, FRONT-50% window, REVERSED
# Mirrored pubkey Q_rev = (a+b)*G - Q for the front-50% interval.
# If this run finds k_rev, the real key is k = a + b - k_rev
#   where a = 8000000000000000000000000000000000000000, b = bfffffffffffffffffffffffffffffffffffffff.
# NEVER write a found key into this file or any public file.
RCKangaroo -dp 16 -range 158 -start 8000000000000000000000000000000000000000 -pubkey 03becfa4cf6f2a9fe893619a361c2a393880ad2fa33c58dc79ba749c975882f313
