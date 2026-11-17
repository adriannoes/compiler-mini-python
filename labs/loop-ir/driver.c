#include <errno.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>

int64_t sum_next(int64_t limit);

int64_t next(int64_t value) {
  return value + 1;
}

int main(int argc, char **argv) {
  if (argc != 2) {
    fputs("Supply one integer limit from -2 through 8.\n", stderr);
    return 1;
  }
  char *end;
  errno = 0;
  long limit = strtol(argv[1], &end, 10);
  if (errno != 0 || end == argv[1] || *end != '\0' || limit < -2 || limit > 8) {
    fputs("The limit must be an integer from -2 through 8.\n", stderr);
    return 1;
  }
  printf("%" PRId64 "\n", sum_next((int64_t)limit));
  return 0;
}
