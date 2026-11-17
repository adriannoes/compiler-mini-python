#include <stdint.h>

/* A separate translation unit keeps this call visible without LTO. */
int64_t next(int64_t value);

int64_t sum_next(int64_t limit) {
  int64_t index = 0;
  int64_t total = 0;
  while (index < limit) {
    total = total + next(index);
    index = index + 1;
  }
  return total;
}
