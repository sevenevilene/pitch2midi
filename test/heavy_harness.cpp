// Runs the Heavy-compiled patch over a 16-bit mono wav, prints noteout events.
#include "Heavy_p2m.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <ctime>
static double SR;
static void hook(HeavyContextInterface *c, const char *name, hv_uint32_t, const HvMessage *m) {
  if (strcmp(name, "__hv_noteout") == 0)
    printf("EV: %d %.0f %d\n", (int)hv_msg_getFloat(m, 0),
           hv_msg_getTimestamp(m) * 1000.0 / SR, (int)hv_msg_getFloat(m, 1));
}
int main(int argc, char **argv) {
  FILE *f = fopen(argv[1], "rb"); SR = atof(argv[2]);
  fseek(f, 0, SEEK_END); long sz = ftell(f); fseek(f, 44, SEEK_SET);
  long n = (sz - 44) / 2; short *pcm = (short *)malloc(n * 2); fread(pcm, 2, n, f);
  HeavyContextInterface *ctx = hv_p2m_new(SR);
  hv_setSendHook(ctx, hook);
  float in[64], out[64 * 2];
  clock_t t0 = clock();
  for (long i = 0; i + 64 <= n + 44100; i += 64) {
    for (int k = 0; k < 64; k++) in[k] = (i + k < n) ? pcm[i + k] / 32768.f : 0.f;
    hv_processInline(ctx, in, out, 64);
  }
  double cpu = double(clock() - t0) / CLOCKS_PER_SEC;
  fprintf(stderr, "processed %.1f s audio in %.3f s CPU (%.2f%% of one core)\n", n / SR, cpu, 100 * cpu / (n / SR));
  hv_delete(ctx);
}
