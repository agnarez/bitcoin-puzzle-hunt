CC = gcc
CFLAGS = -O3 -march=native -Wall -Wextra
LDFLAGS = -lcrypto

all: c_scan

c_scan: c_scan.c
	$(CC) $(CFLAGS) -o c_scan c_scan.c $(LDFLAGS)

clean:
	rm -f c_scan

.PHONY: all clean
