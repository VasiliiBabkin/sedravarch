/* Small measurement launcher: fork from a minimal process, not the Python benchmark. */
#define _POSIX_C_SOURCE 200809L
#define _DEFAULT_SOURCE
#include <sys/types.h>
#include <sys/wait.h>
#include <sys/resource.h>
#include <time.h>
#include <unistd.h>
#include <stdio.h>
#include <errno.h>
int main(int argc,char **argv){
    if(argc<3)return 2;
    struct timespec a,b;struct rusage u;int status;
    if(clock_gettime(CLOCK_MONOTONIC,&a)<0)return 2;
    pid_t p=fork();
    if(p<0)return 2;
    if(p==0){execvp(argv[2],argv+2);perror("exec");_exit(127);}
    while(wait4(p,&status,0,&u)<0){if(errno!=EINTR)return 2;}
    if(clock_gettime(CLOCK_MONOTONIC,&b)<0)return 2;
    FILE *f=fopen(argv[1],"w");if(!f)return 2;
    fprintf(f,"%.9f %.6f %.6f %ld\n",(b.tv_sec-a.tv_sec)+(b.tv_nsec-a.tv_nsec)/1e9,
      u.ru_utime.tv_sec+u.ru_utime.tv_usec/1e6,u.ru_stime.tv_sec+u.ru_stime.tv_usec/1e6,u.ru_maxrss);
    if(fclose(f))return 2;
    return WIFEXITED(status)?WEXITSTATUS(status):128+WTERMSIG(status);
}
