/* c_scan2.c — fast C sequential scanner, batch-inversion edition.
 *
 * NOT DEPLOYED (2026-11-18): measured 0.41-0.44x the speed of c_scan
 * (139k vs 312k keys/s best of 3 alternating runs) — OpenSSL BN call
 * overhead swamps the inversions saved. Correctness verified (all 12
 * synthetic FOUND tests pass, right keys at block boundaries), but it
 * is slower, so the live C-scan keeps using c_scan. Kept as reference.
 * Do not deploy without re-measuring.
 *
 * Same job as c_scan.c: scan [start, end] key-by-key, checking each
 * candidate's compressed public key against the target. Same CLI,
 * same stdout/stderr formats, same exit codes, same FOUND rule.
 *
 * Speedup: keys are processed in blocks of 64. For a block starting at
 * point P (key k), the 64 points P + i*G (i = 0..63) are all computed
 * with ONE modular inversion via Montgomery's trick, instead of one
 * inversion per key (OpenSSL's EC_POINT_add inverts every time).
 * The block advance P -> P + 64*G is folded in as a 65th lane of the
 * same batch, so a block costs exactly one inversion total.
 * Only the x-coordinate is compared per lane; the y-coordinate is
 * computed only when x matches (i.e. essentially never, unless found).
 * All values are mathematically identical to the per-key version —
 * same keys, same order, same FOUND behaviour.
 *
 * HARD RULE: on a find this program prints ONLY "FOUND" to stdout and
 * writes the key ONLY to --private-out. It never prints or logs a key.
 */
#define _POSIX_C_SOURCE 200809L
#include <openssl/ec.h>
#include <openssl/obj_mac.h>
#include <openssl/bn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#define BLK 64          /* lanes per block (plus lane 64 = block advance) */
#define LANES (BLK + 1) /* lanes needing an inversion: i = 1..64 */

static void usage(const char *prog) {
    fprintf(stderr,
        "Usage: %s --pubkey <hex> --start <hex> --end <hex>\n"
        "       [--mode forward|reversed] [--max-keys N]\n"
        "       [--private-out <path>] [--checkpoint-every N]\n", prog);
}

static int hex_to_bytes(const char *hex, unsigned char *out, size_t outlen) {
    size_t n = strlen(hex);
    if (n % 2 || n / 2 != outlen) return -1;
    for (size_t i = 0; i < outlen; i++) {
        unsigned int v;
        if (sscanf(hex + 2 * i, "%2x", &v) != 1) return -1;
        out[i] = (unsigned char)v;
    }
    return 0;
}

int main(int argc, char **argv) {
    const char *pubkey_hex = NULL, *start_hex = NULL, *end_hex = NULL;
    const char *mode = "forward";
    const char *private_out = "../private/FOUND-PRIVATE.txt";
    long max_keys = 1000000, checkpoint_every = 1000000;

    for (int i = 1; i < argc; i++) {
        if (!strcmp(argv[i], "--pubkey") && i + 1 < argc) pubkey_hex = argv[++i];
        else if (!strcmp(argv[i], "--start") && i + 1 < argc) start_hex = argv[++i];
        else if (!strcmp(argv[i], "--end") && i + 1 < argc) end_hex = argv[++i];
        else if (!strcmp(argv[i], "--mode") && i + 1 < argc) mode = argv[++i];
        else if (!strcmp(argv[i], "--private-out") && i + 1 < argc) private_out = argv[++i];
        else if (!strcmp(argv[i], "--max-keys") && i + 1 < argc) max_keys = atol(argv[++i]);
        else if (!strcmp(argv[i], "--checkpoint-every") && i + 1 < argc) checkpoint_every = atol(argv[++i]);
        else { usage(argv[0]); return 2; }
    }
    if (!pubkey_hex || !start_hex || !end_hex) { usage(argv[0]); return 2; }
    int reversed = !strcmp(mode, "reversed");
    if (!reversed && strcmp(mode, "forward") != 0) { usage(argv[0]); return 2; }

    EC_GROUP *group = EC_GROUP_new_by_curve_name(NID_secp256k1);
    BN_CTX *ctx = BN_CTX_new();
    if (!group || !ctx) { fprintf(stderr, "OpenSSL init failed\n"); return 1; }
    const BIGNUM *order_p = EC_GROUP_get0_field(group);

    unsigned char target_raw[33];
    if (hex_to_bytes(pubkey_hex, target_raw, 33) != 0) {
        fprintf(stderr, "bad --pubkey (need 33-byte compressed hex)\n"); return 2;
    }
    BIGNUM *tx = BN_bin2bn(target_raw + 1, 32, NULL);
    int target_odd = target_raw[0] & 1;

    BIGNUM *start = NULL, *end = NULL, *one = BN_new();
    BN_hex2bn(&start, start_hex);
    BN_hex2bn(&end, end_hex);
    BN_one(one);

    BIGNUM *k = BN_dup(reversed ? end : start);
    EC_POINT *pt = EC_POINT_new(group);
    if (!EC_POINT_mul(group, pt, k, NULL, NULL, ctx)) {
        fprintf(stderr, "initial scalar mult failed\n"); return 1;
    }

    /* Precompute T[i] = i*G affine, i = 0..64. T[0] is infinity. */
    BIGNUM *tabx[LANES + 1], *taby[LANES + 1];
    for (int i = 0; i <= LANES; i++) { tabx[i] = BN_new(); taby[i] = BN_new(); }
    {
        EC_POINT *tmp = EC_POINT_new(group);
        BIGNUM *bi = BN_new();
        for (int i = 1; i <= LANES; i++) {
            BN_set_word(bi, (unsigned)i);
            if (!EC_POINT_mul(group, tmp, bi, NULL, NULL, ctx)) {
                fprintf(stderr, "table build failed\n"); return 1;
            }
            if (!EC_POINT_get_affine_coordinates(group, tmp, tabx[i], taby[i], ctx)) {
                fprintf(stderr, "table affine failed\n"); return 1;
            }
        }
        EC_POINT_free(tmp);
        BN_free(bi);
    }

    /* Batch temporaries, allocated once. */
    BIGNUM *d[LANES], *invd[LANES], *lam[LANES], *x3[LANES], *pfx[LANES];
    BIGNUM *px = BN_new(), *py = BN_new(), *t1 = BN_new(), *t2 = BN_new();
    BIGNUM *acc = BN_new(), *inv_all = BN_new();
    for (int i = 0; i < LANES; i++) {
        d[i] = BN_new(); invd[i] = BN_new(); lam[i] = BN_new();
        x3[i] = BN_new(); pfx[i] = BN_new();
    }

    long checked = 0;
    time_t t0 = time(NULL);
    int found = 0;
    BIGNUM *k_found = NULL;

    while (checked < max_keys) {
        /* Keys left before the bound (inclusive). */
        BIGNUM *left = BN_new();
        if (reversed) BN_sub(left, k, start), BN_add(left, left, one);
        else BN_sub(left, end, k), BN_add(left, left, one);
        long n = BLK;
        if (n > max_keys - checked) n = max_keys - checked;
        /* left can be ~2^138: only trust its word value when it fits. */
        if (BN_num_bits(left) <= 7) {
            long ll = (long)BN_get_word(left);
            if (ll < n) n = ll;
        }
        BN_free(left);
        if (n <= 0) break;

        /* Current P affine. */
        if (!EC_POINT_get_affine_coordinates(group, pt, px, py, ctx)) {
            fprintf(stderr, "P not affine (infinity?)\n"); return 1;
        }
        /* Lane 0 is P itself. */
        if (BN_cmp(px, tx) == 0) {
            /* y parity check: P's y vs target. */
            if (BN_is_odd(py) == target_odd) { found = 1; k_found = BN_dup(k); break; }
        }
        /* Lanes 1..m need an inversion: for a full block, lanes 1..63
         * are this block's keys k+1..k+63 and lane 64 is the block
         * advance (P + 64*G); for a partial block, lanes 1..n-1 are
         * this block's keys and there is no advance lane. */
        int m = (n == BLK) ? BLK : (int)n - 1;
        if (m < 0) m = 0;
        int need_fallback = 0;
        for (int i = 1; i <= m; i++) {
            /* d_i = x_Ti - x_P (mod p). */
            if (!BN_mod_sub(d[i - 1], tabx[i], px, order_p, ctx)) return 1;
            if (BN_is_zero(d[i - 1])) { need_fallback = 1; break; }
        }
        if (need_fallback) {
            /* Degenerate lane (x_Ti == x_P): impossible in our ranges,
             * but fall back to the plain per-key loop for this block. */
            EC_POINT *gen = EC_POINT_dup(EC_GROUP_get0_generator(group), group);
            EC_POINT *ng = EC_POINT_dup(gen, group);
            EC_POINT_invert(group, ng, ctx);
            for (long j = 0; j < n; j++) {
                /* compare via affine (cheap here: fallback is rare) */
                BIGNUM *cx = BN_new(), *cy = BN_new();
                EC_POINT_get_affine_coordinates(group, pt, cx, cy, ctx);
                if (BN_cmp(cx, tx) == 0 && BN_is_odd(cy) == target_odd) {
                    found = 1; k_found = BN_dup(k); BN_free(cx); BN_free(cy); break;
                }
                BN_free(cx); BN_free(cy);
                if (reversed) EC_POINT_add(group, pt, pt, ng, ctx);
                else EC_POINT_add(group, pt, pt, gen, ctx);
                if (reversed) BN_sub(k, k, one); else BN_add(k, k, one);
                checked++;
                if (checkpoint_every > 0 && checked % checkpoint_every == 0) {
                    double el = difftime(time(NULL), t0);
                    fprintf(stderr, "checked=%ld elapsed=%.0fs rate=%.0f keys/s\n",
                            checked, el, el > 0 ? checked / el : 0);
                }
                if (found) break;
            }
            EC_POINT_free(gen); EC_POINT_free(ng);
            if (found) break;
            continue;
        }
        /* Montgomery batch inversion of d[0..m-1]. */
        if (!BN_one(acc)) return 1;
        for (int i = 0; i < m; i++) {
            if (!BN_mod_mul(pfx[i], acc, d[i], order_p, ctx)) return 1;
            BN_copy(acc, pfx[i]);
        }
        if (!BN_mod_inverse(inv_all, acc, order_p, ctx)) return 1;
        for (int i = m - 1; i >= 0; i--) {
            /* inv_d_i = inv_all * prefix[i-1] */
            if (i > 0) { if (!BN_mod_mul(invd[i], inv_all, pfx[i - 1], order_p, ctx)) return 1; }
            else BN_copy(invd[i], inv_all);
            if (!BN_mod_mul(inv_all, inv_all, d[i], order_p, ctx)) return 1;
        }
        /* Per lane: lam = (y_Ti' - y_P) * inv_d; x3 = lam^2 - x_P - x_Ti.
         * y_Ti' is taby[i] forward, -taby[i] reversed. */
        BIGNUM *y3 = BN_new();
        for (int i = 1; i <= m; i++) {
            /* t1 = y_Ti' - y_P (mod p) */
            if (reversed) {
                if (!BN_mod_add(t1, taby[i], py, order_p, ctx)) return 1;
                if (!BN_mod_sub(t1, order_p, t1, order_p, ctx)) return 1;
            } else {
                if (!BN_mod_sub(t1, taby[i], py, order_p, ctx)) return 1;
            }
            if (!BN_mod_mul(lam[i - 1], t1, invd[i - 1], order_p, ctx)) return 1;
            /* x3 = lam^2 - x_P - x_Ti */
            if (!BN_mod_sqr(t2, lam[i - 1], order_p, ctx)) return 1;
            if (!BN_mod_sub(t2, t2, px, order_p, ctx)) return 1;
            if (!BN_mod_sub(x3[i - 1], t2, tabx[i], order_p, ctx)) return 1;
            /* Lanes 1..n-1 hold this block's keys k+1..k+n-1 (lane 0 is
             * key k, lane n is the next block's start / advance lane). */
            if (i < n && BN_cmp(x3[i - 1], tx) == 0) {
                /* x matches: compute y3 and check parity. */
                if (!BN_mod_sub(t2, px, x3[i - 1], order_p, ctx)) return 1;
                if (!BN_mod_mul(t2, lam[i - 1], t2, order_p, ctx)) return 1;
                if (!BN_mod_sub(y3, t2, py, order_p, ctx)) return 1;
                if (BN_is_odd(y3) == target_odd) {
                    found = 1;
                    k_found = BN_dup(k);
                    if (reversed) BN_sub_word(k_found, (unsigned)i);
                    else BN_add_word(k_found, (unsigned)i);
                    break;
                }
            }
        }
        BN_free(y3);
        if (found) break;
        if (n == BLK) {
            /* Advance P by 64*G using lane 64's x3/lam (index BLK-1).
             * Its y3: y3 = lam_64 * (x_P - x3_64) - y_P. */
            BIGNUM *ny = BN_new();
            if (!BN_mod_sub(t2, px, x3[BLK - 1], order_p, ctx)) return 1;
            if (!BN_mod_mul(t2, lam[BLK - 1], t2, order_p, ctx)) return 1;
            if (!BN_mod_sub(ny, t2, py, order_p, ctx)) return 1;
            if (!EC_POINT_set_affine_coordinates(group, pt, x3[BLK - 1], ny, ctx)) return 1;
            BN_free(ny);
            if (reversed) BN_sub_word(k, BLK); else BN_add_word(k, BLK);
        } else {
            /* Partial last block: advance P by n steps the plain way. */
            EC_POINT *gen = EC_POINT_dup(EC_GROUP_get0_generator(group), group);
            EC_POINT *ng = EC_POINT_dup(gen, group);
            EC_POINT_invert(group, ng, ctx);
            for (long j = 0; j < n; j++) {
                if (reversed) EC_POINT_add(group, pt, pt, ng, ctx);
                else EC_POINT_add(group, pt, pt, gen, ctx);
            }
            EC_POINT_free(gen); EC_POINT_free(ng);
            if (reversed) BN_sub_word(k, (unsigned)n); else BN_add_word(k, (unsigned)n);
        }
        checked += n;
        if (checkpoint_every > 0 && checked % checkpoint_every == 0) {
            double el = difftime(time(NULL), t0);
            fprintf(stderr, "checked=%ld elapsed=%.0fs rate=%.0f keys/s\n",
                    checked, el, el > 0 ? checked / el : 0);
        }
    }

    double el = difftime(time(NULL), t0);
    if (found) {
        FILE *f = fopen(private_out, "w");
        if (!f) { fprintf(stderr, "cannot open private file %s\n", private_out); return 1; }
        char *khex = BN_bn2hex(k_found);
        fprintf(f, "PRIVATE - DO NOT SHARE, DO NOT PUBLISH, DO NOT PUT ON ANY WEBSITE\n");
        fprintf(f, "date_found: %ld\n", (long)time(NULL));
        fprintf(f, "private_key_hex: %s\n", khex);
        fclose(f);
        OPENSSL_free(khex);
        printf("FOUND\n");
        return 0;
    }
    printf("not found: checked=%ld elapsed=%.0fs rate=%.0f keys/s\n",
           checked, el, el > 0 ? checked / el : 0);
    return 1;
}
