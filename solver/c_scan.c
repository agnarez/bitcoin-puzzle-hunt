/* c_scan.c — fast C sequential scanner using OpenSSL EC.
 *
 * Scans [start, end] (hex, inclusive) key-by-key, checking each
 * candidate's compressed public key against the target. Uses incremental
 * EC_POINT addition (P_{k+1} = P_k + G), one point-add per key.
 *
 * Usage:
 *   ./c_scan --pubkey <hex> --start <hex> --end <hex>
 *            [--mode forward|reversed] [--max-keys N]
 *            [--private-out <path>] [--checkpoint-every N]
 *
 * HARD RULE: on a find this program prints ONLY "FOUND" to stdout and
 * writes the key ONLY to --private-out (default
 * ../private/FOUND-PRIVATE.txt, relative to the hunt root when run from
 * solver/). It never prints or logs the key. Progress lines contain
 * counts only.
 *
 * Honest note: even in C, this VM does ~10^5 keys/s. #140's front-50%
 * window is 2^138 keys. This is a small-range / verification engine,
 * not a realistic #140 engine — see README.md.
 */
#define _POSIX_C_SOURCE 200809L
#include <openssl/ec.h>
#include <openssl/obj_mac.h>
#include <openssl/bn.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

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

    unsigned char target_raw[33];
    if (hex_to_bytes(pubkey_hex, target_raw, 33) != 0) {
        fprintf(stderr, "bad --pubkey (need 33-byte compressed hex)\n"); return 2;
    }
    EC_POINT *target = EC_POINT_new(group);
    if (!EC_POINT_oct2point(group, target, target_raw, 33, ctx)) {
        fprintf(stderr, "target pubkey not on curve\n"); return 2;
    }

    BIGNUM *start = NULL, *end = NULL, *one = BN_new();
    BN_hex2bn(&start, start_hex);
    BN_hex2bn(&end, end_hex);
    BN_one(one);

    BIGNUM *k = BN_dup(reversed ? end : start);
    EC_POINT *pt = EC_POINT_new(group);
    /* pt = k*G for the first key (one scalar mult; the rest is incremental). */
    if (!EC_POINT_mul(group, pt, k, NULL, NULL, ctx)) {
        fprintf(stderr, "initial scalar mult failed\n"); return 1;
    }
    const EC_POINT *gen = EC_GROUP_get0_generator(group);
    EC_POINT *neg_gen = EC_POINT_dup(gen, group);
    EC_POINT_invert(group, neg_gen, ctx);

    long checked = 0;
    time_t t0 = time(NULL);
    int found = 0;
    while (checked < max_keys) {
        if (EC_POINT_cmp(group, pt, target, ctx) == 0) { found = 1; break; }
        /* Advance one key. */
        if (reversed) {
            if (BN_cmp(k, start) <= 0) { checked++; break; }
            EC_POINT_add(group, pt, pt, neg_gen, ctx);
            BN_sub(k, k, one);
        } else {
            if (BN_cmp(k, end) >= 0) { checked++; break; }
            EC_POINT_add(group, pt, pt, gen, ctx);
            BN_add(k, k, one);
        }
        checked++;
        if (checkpoint_every > 0 && checked % checkpoint_every == 0) {
            double el = difftime(time(NULL), t0);
            fprintf(stderr, "checked=%ld elapsed=%.0fs rate=%.0f keys/s\n",
                    checked, el, el > 0 ? checked / el : 0);
        }
    }
    double el = difftime(time(NULL), t0);
    if (found) {
        /* HARD RULE: write the key ONLY to the private file; stdout gets
         * only "FOUND". */
        FILE *f = fopen(private_out, "w");
        if (!f) { fprintf(stderr, "cannot open private file %s\n", private_out); return 1; }
        char *khex = BN_bn2hex(k);
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
