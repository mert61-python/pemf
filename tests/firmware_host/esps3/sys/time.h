/* tests/firmware_host/esps3 — <sys/time.h> taklidi (1-G · D1.102): `gettimeofday` aparatın sanal saatinden. */
#ifndef PEMF_HOST_S3_SYS_TIME_H
#define PEMF_HOST_S3_SYS_TIME_H

struct timeval {
  long tv_sec;
  long tv_usec;
};
int gettimeofday(struct timeval *tv, void *tz);

#endif /* PEMF_HOST_S3_SYS_TIME_H */
