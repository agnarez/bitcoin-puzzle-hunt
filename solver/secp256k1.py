"""Pure-Python secp256k1 (Bitcoin curve) — Jacobian coordinates.

No external dependencies. Correct, not fast: ~1-3k scalar multiplications/s
in CPython on this VM. Sequential scanning below uses incremental point
addition (one EC add per key) instead of a fresh scalar mult per key.

HARD RULE: this module never logs or stores a private key. Callers must
handle a found key per README.md / run_hunt.py (private file only).
"""
import hashlib

P = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEFFFFFC2F
N = 0xFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFFEBAAEDCE6AF48A03BBFD25E8CD0364141
Gx = 0x79BE667EF9DCBBAC55A06295CE870B07029BFCDB2DCE28D959F2815B16F81798
Gy = 0x483ADA7726A3C4655DA4FBFC0E1108A8FD17B448A68554199C47D08FFB10D4B8
G = (Gx, Gy)

# Jacobian point: (X, Y, Z), affine (x, y) == (X/Z^2, Y/Z^3). Infinity = (0, 1, 0).
INF_J = (0, 1, 0)


def _to_jacobian(pt):
    if pt is None:
        return INF_J
    x, y = pt
    return (x, y, 1)


def _to_affine(pt_j):
    X, Y, Z = pt_j
    if Z == 0:
        return None
    zinv = pow(Z, P - 2, P)
    zinv2 = zinv * zinv % P
    zinv3 = zinv2 * zinv % P
    return (X * zinv2 % P, Y * zinv3 % P)


def _batch_to_affine(pts_j):
    """Convert a list of Jacobian points to affine with ONE inversion.

    Montgomery's trick: a single pow() for the whole batch instead of one
    per point. The values returned are mathematically identical to
    calling _to_affine() on each point — this changes cost, never
    results, so a walk that uses batched conversions follows exactly
    the same points, jumps and collisions as before.
    """
    n = len(pts_j)
    out = [None] * n
    idx = [i for i, p in enumerate(pts_j) if p[2] != 0]
    if not idx:
        return out
    prefix = []
    acc = 1
    for i in idx:
        acc = acc * pts_j[i][2] % P
        prefix.append(acc)
    inv_all = pow(acc, P - 2, P)
    for j in range(len(idx) - 1, -1, -1):
        i = idx[j]
        zinv = inv_all * (prefix[j - 1] if j > 0 else 1) % P
        zinv2 = zinv * zinv % P
        zinv3 = zinv2 * zinv % P
        X, Y, Z = pts_j[i]
        out[i] = (X * zinv2 % P, Y * zinv3 % P)
        inv_all = inv_all * Z % P
    return out


def _jacobian_double(pt_j):
    X, Y, Z = pt_j
    if Z == 0 or Y == 0:
        return INF_J
    Y2 = Y * Y % P
    S = 4 * X * Y2 % P
    M = 3 * X * X % P  # a = 0 for secp256k1
    X3 = (M * M - 2 * S) % P
    Y3 = (M * (S - X3) - 8 * Y2 * Y2) % P
    Z3 = 2 * Y * Z % P
    return (X3, Y3, Z3)


def _jacobian_add(pt1_j, pt2_j):
    if pt1_j[2] == 0:
        return pt2_j
    if pt2_j[2] == 0:
        return pt1_j
    X1, Y1, Z1 = pt1_j
    X2, Y2, Z2 = pt2_j
    Z1Z1 = Z1 * Z1 % P
    Z2Z2 = Z2 * Z2 % P
    U1 = X1 * Z2Z2 % P
    U2 = X2 * Z1Z1 % P
    S1 = Y1 * Z2 % P * Z2Z2 % P
    S2 = Y2 * Z1 % P * Z1Z1 % P
    if U1 == U2:
        if S1 != S2:
            return INF_J
        return _jacobian_double(pt1_j)
    H = (U2 - U1) % P
    r = (S2 - S1) % P
    H2 = H * H % P
    H3 = H * H2 % P
    U1H2 = U1 * H2 % P
    X3 = (r * r - H3 - 2 * U1H2) % P
    Y3 = (r * (U1H2 - X3) - S1 * H3) % P
    Z3 = H * Z1 % P * Z2 % P
    return (X3, Y3, Z3)


def scalar_mult(k, point=G):
    """Return k*point as an affine (x, y) tuple, or None for k==0."""
    k = k % N
    if k == 0:
        return None
    result = INF_J
    addend = _to_jacobian(point)
    while k:
        if k & 1:
            result = _jacobian_add(result, addend)
        addend = _jacobian_double(addend)
        k >>= 1
    return _to_affine(result)


def point_add_affine(p1, p2):
    """Affine add (slow, for clarity). Sequential scanners use _jacobian_add."""
    if p1 is None:
        return p2
    if p2 is None:
        return p1
    return _to_affine(_jacobian_add(_to_jacobian(p1), _to_jacobian(p2)))


def priv_to_pubkey_compressed(priv):
    """int private key -> 33-byte compressed public key hex (02/03 + 32-byte x)."""
    pt = scalar_mult(priv)
    if pt is None:
        raise ValueError("invalid private key 0")
    x, y = pt
    return ("03" if y & 1 else "02") + format(x, "064x")


def pubkey_hex_to_point(pubkey_hex):
    """Compressed pubkey hex -> affine (x, y). Verifies the point is on-curve."""
    b = bytes.fromhex(pubkey_hex)
    if len(b) != 33 or b[0] not in (2, 3):
        raise ValueError("expected 33-byte compressed public key")
    x = int.from_bytes(b[1:], "big")
    if x >= P:
        raise ValueError("pubkey x out of range")
    y_sq = (pow(x, 3, P) + 7) % P
    y = pow(y_sq, (P + 1) // 4, P)
    if y * y % P != y_sq:
        raise ValueError("pubkey point not on curve")
    if (y & 1) != (b[0] & 1):
        y = P - y
    return (x, y)


def verify_privkey(priv, pubkey_hex):
    """True iff priv (int) in [1, N) produces pubkey_hex. No key is logged."""
    try:
        return 1 <= priv < N and priv_to_pubkey_compressed(priv) == pubkey_hex.lower()
    except Exception:
        return False


def _hash160(data):
    sha = hashlib.sha256(data).digest()
    try:
        return hashlib.new("ripemd160", sha).digest()
    except Exception:
        # Fallback for OpenSSL builds without RIPEMD160 (not expected here).
        raise RuntimeError("RIPEMD160 unavailable in this Python/OpenSSL build")


_B58 = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"


def pubkey_to_address(pubkey_hex):
    """Compressed pubkey hex -> P2PKH Bitcoin address."""
    h160 = _hash160(bytes.fromhex(pubkey_hex))
    payload = b"\x00" + h160
    checksum = hashlib.sha256(hashlib.sha256(payload).digest()).digest()[:4]
    n = int.from_bytes(payload + checksum, "big")
    s = ""
    while n:
        n, r = divmod(n, 58)
        s = _B58[r] + s
    # Leading zero bytes become '1's.
    pad = 0
    for byte in payload + checksum:
        if byte == 0:
            pad += 1
        else:
            break
    return "1" * pad + s


def mirror_pubkey(pubkey_hex, a, b):
    """Reversed-scan mirror: Q_rev = (a + b) * G - Q, as compressed hex.

    If k in [a, b] is the key for Q, then k_rev = a + b - k is the key
    for Q_rev. Searching for k_rev (forward) is searching for k (reversed).
    """
    q = pubkey_hex_to_point(pubkey_hex)
    total = scalar_mult((a + b) % N)
    # (a+b)*G - Q
    neg_q = (q[0], (-q[1]) % P)
    rev = point_add_affine(total, neg_q)
    if rev is None:
        raise ValueError("mirrored point is infinity")
    x, y = rev
    return ("03" if y & 1 else "02") + format(x, "064x")


if __name__ == "__main__":
    # Self-check against the known generator and puzzle #140's pubkey/address.
    assert priv_to_pubkey_compressed(1) == (
        "0279be667ef9dcbbac55a06295ce870b07029bfcdb2dce28d959f2815b16f81798"
    )
    assert pubkey_to_address(
        "031f6a332d3c5c4f2de2378c012f429cd109ba07d69690c6c701b6bb87860d6640"
    ) == "1QKBaU6WAeycb3DbKbLBkX7vJiaS8r42Xo"
    print("secp256k1 self-check OK")
