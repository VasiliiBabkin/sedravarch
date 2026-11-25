/* Linux-only fault injector for isolated P03.1 test fixtures.
 * Never preload into production processes. Only affects staging files under
 * SDA_FAULT_ROOT, and only when a test-selected fault mode is active. */
#define _GNU_SOURCE
#include <dlfcn.h>
#include <errno.h>
#include <limits.h>
#include <signal.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/syscall.h>
#include <unistd.h>

static size_t written;
static int selected(int fd) {
    const char *root=getenv("SDA_FAULT_ROOT");
    if (!root || !*root) return 0;
    char link[64], path[PATH_MAX];
    snprintf(link,sizeof(link),"/proc/self/fd/%d",fd);
    ssize_t n=readlink(link,path,sizeof(path)-1);
    if(n<0) return 0;
    path[n]=0;
    size_t r=strlen(root);
    return strncmp(path,root,r)==0 && path[r]=='/' &&
           (strstr(path+r,"/.sedravarch-tmp-") || strstr(path+r,"/.sedravarch-tree-"));
}
static void mark(const char *s) {
    syscall(SYS_write,STDERR_FILENO,s,strlen(s));
}
ssize_t write(int fd,const void *buf,size_t count) {
    ssize_t (*real)(int,const void*,size_t)=dlsym(RTLD_NEXT,"write");
    const char *mode=getenv("SDA_FAULT_MODE");
    if(!mode || !selected(fd) || (strcmp(mode,"write") && strcmp(mode,"block")))
        return real(fd,buf,count);
    if(written>=256) {
        if(!strcmp(mode,"block")) {
            mark("P031 BLOCK REACHED\n");
            for(;;) pause();
        }
        mark("P031 ENOSPC WRITE\n");
        errno=ENOSPC;return -1;
    }
    if(count>256-written) count=256-written;
    ssize_t n=real(fd,buf,count);
    if(n>0) written+=(size_t)n;
    return n;
}
int fsync(int fd) {
    int (*real)(int)=dlsym(RTLD_NEXT,"fsync");
    const char *mode=getenv("SDA_FAULT_MODE");
    if(mode && !strcmp(mode,"sync") && selected(fd)) {
        mark("P031 ENOSPC SYNC\n");
        errno=ENOSPC;return -1;
    }
    return real(fd);
}
