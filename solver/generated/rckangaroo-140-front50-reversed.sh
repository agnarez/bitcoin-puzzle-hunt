# RCKangaroo — puzzle #140, FRONT-50% window, REVERSED
# Mirrored pubkey Q_rev = (a+b)*G - Q for the front-50% interval.
# If this run finds k_rev, the real key is k = a + b - k_rev
#   where a = 80000000000000000000000000000000000, b = bffffffffffffffffffffffffffffffffff.
# NEVER write a found key into this file or any public file.
RCKangaroo -dp 16 -range 138 -start 80000000000000000000000000000000000 -pubkey 0398b44d387f57a90a7355690669a47d5c1f1a25b68743bb8e61d85c65e440a3aa
