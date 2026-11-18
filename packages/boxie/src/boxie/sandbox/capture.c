/* PID 1 for a noninteractive Boxie job. Only this process owns Docker stdout.
 * A frame is type:u8, length:u32be, payload. The final record proves both
 * streams finished and binds their byte counts and exit code to this launch. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <poll.h>
#include <signal.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>
#include <sys/prctl.h>
#include <sys/random.h>
#include <sys/resource.h>
#include <sys/syscall.h>
#include <sys/wait.h>
#include <unistd.h>

enum { FAILURE = 125, CHUNK_SIZE = 32768, NONCE_SIZE = 16 };

static void write_all(int fd, const uint8_t *data, size_t size) {
    while (size) {
        ssize_t written = write(fd, data, size);
        if (written < 0 && errno == EINTR) continue;
        if (written <= 0) _exit(FAILURE);
        data += written;
        size -= (size_t)written;
    }
}

static void write_frame(uint8_t type, const uint8_t *data, uint32_t size) {
    uint8_t header[5] = {type, size >> 24, size >> 16, size >> 8, size};
    write_all(STDOUT_FILENO, header, sizeof(header));
    write_all(STDOUT_FILENO, data, size);
}

static void put_count(uint8_t *dest, uint64_t count) {
    for (int i = 7; i >= 0; --i) {
        dest[i] = (uint8_t)count;
        count >>= 8;
    }
}

static void close_inherited(void) {
#ifdef SYS_close_range
    if (syscall(SYS_close_range, 3U, UINT_MAX, 0) == 0) return;
#endif
    struct rlimit limit;
    if (getrlimit(RLIMIT_NOFILE, &limit) < 0 || limit.rlim_cur > INT_MAX) _exit(FAILURE);
    for (int fd = 3; fd < (int)limit.rlim_cur; ++fd) close(fd);
}

static void wake_parent(int sig) { (void)sig; }

static void copy_output(struct pollfd *fd, uint8_t type, uint64_t *total) {
    uint8_t buf[CHUNK_SIZE];
    ssize_t size = read(fd->fd, buf, sizeof(buf));
    if (size < 0 && errno == EINTR) return;
    if (size < 0) _exit(FAILURE);
    if (size == 0) {
        close(fd->fd);
        fd->fd = -1;
        return;
    }
    *total += (uint64_t)size;
    write_frame(type, buf, (uint32_t)size);
}

int main(int argc, char **argv) {
    if (getpid() != 1 || argc < 3 || strcmp(argv[1], "--") || argv[2][0] != '/') return FAILURE;
    /* Block the same-UID workload from reopening PID 1's Docker output via procfs. */
    if (prctl(PR_SET_DUMPABLE, 0, 0, 0, 0) < 0) return FAILURE;
    close_inherited();
    int output[2], error[2], exec_status[2];
    if (pipe2(output, O_CLOEXEC) || pipe2(error, O_CLOEXEC) || pipe2(exec_status, O_CLOEXEC))
        return FAILURE;
    sigset_t blocked, prior;
    sigemptyset(&blocked);
    sigaddset(&blocked, SIGCHLD);
    struct sigaction wake = {.sa_handler = wake_parent, .sa_flags = SA_NOCLDSTOP};
    sigemptyset(&wake.sa_mask);
    if (sigaction(SIGCHLD, &wake, NULL) || sigprocmask(SIG_BLOCK, &blocked, &prior)) return FAILURE;
    /* Publish the cookie before the workload can produce a byte. execv replaces
     * the child's address space; neither its argv nor its environment carries it. */
    uint8_t end[NONCE_SIZE + 8 + 8 + 1];
    if (getrandom(end, NONCE_SIZE, 0) != NONCE_SIZE) return FAILURE;
    write_all(STDOUT_FILENO, (const uint8_t *)"BXJ1", 4);
    write_all(STDOUT_FILENO, end, NONCE_SIZE);
    pid_t child = fork();
    if (child < 0) return FAILURE;
    if (child == 0) {
        if (dup2(output[1], STDOUT_FILENO) >= 0 && dup2(error[1], STDERR_FILENO) >= 0 &&
            sigprocmask(SIG_SETMASK, &prior, NULL) == 0) {
            execv(argv[2], argv + 2);
        }
        write_all(exec_status[1], (const uint8_t *)"!", 1);
        _exit(FAILURE);
    }
    close(output[1]);
    close(error[1]);
    close(exec_status[1]);
    uint8_t failure;
    ssize_t exec_result;
    do { exec_result = read(exec_status[0], &failure, 1); } while (exec_result < 0 && errno == EINTR);
    close(exec_status[0]);
    if (exec_result != 0) return FAILURE;

    sigset_t wait_mask = prior;
    sigdelset(&wait_mask, SIGCHLD);
    struct pollfd fds[2] = {{output[0], POLLIN, 0}, {error[0], POLLIN, 0}};
    uint64_t counts[2] = {0, 0};
    int code = -1;
    while (code < 0 || fds[0].fd >= 0 || fds[1].fd >= 0) {
        int status;
        pid_t reaped;
        while ((reaped = waitpid(-1, &status, WNOHANG)) > 0) {
            if (reaped != child) continue;
            if (WIFEXITED(status)) code = WEXITSTATUS(status);
            else if (WIFSIGNALED(status)) code = 128 + WTERMSIG(status);
            else return FAILURE;
            /* Preserve the ordinary container lifetime when its main command
             * exits with background descendants still holding output pipes.
             * main() required PID 1 in this container's private namespace. */
            if (kill(-1, SIGKILL) < 0 && errno != ESRCH) return FAILURE;
        }
        if (code >= 0 && fds[0].fd < 0 && fds[1].fd < 0) break;
        if (ppoll(fds, 2, NULL, &wait_mask) < 0) {
            if (errno == EINTR) continue;
            return FAILURE;
        }
        for (int i = 0; i < 2; ++i) {
            if (fds[i].revents & (POLLERR | POLLNVAL)) return FAILURE;
            if (fds[i].revents & (POLLIN | POLLHUP)) copy_output(&fds[i], (uint8_t)(i + 1), &counts[i]);
        }
    }
    put_count(end + NONCE_SIZE, counts[0]);
    put_count(end + NONCE_SIZE + 8, counts[1]);
    end[sizeof(end) - 1] = (uint8_t)code;
    write_frame(3, end, sizeof(end));
    return code;
}
