#include "../melonDS/src/Platform.h"
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cstdarg>
#include <chrono>
#include <thread>
#include <mutex>
#include <condition_variable>
#include <string>

using namespace melonDS;
using namespace melonDS::Platform;

void Platform::Log(LogLevel level, const char* fmt, ...)
{
    if (level < LogLevel::Error) return;
    va_list args;
    va_start(args, fmt);
    vfprintf(stderr, fmt, args);
    va_end(args);
}

struct PlatformThread     { std::thread t; };
struct PlatformSemaphore  { std::mutex m; std::condition_variable cv; int count = 0; };
struct PlatformMutex      { std::mutex m; };

Thread* Platform::Thread_Create(std::function<void()> fn)
{
    auto* t = new PlatformThread;
    t->t = std::thread(fn);
    return reinterpret_cast<Thread*>(t);
}

void Platform::Thread_Free(Thread* th)
{
    auto* t = reinterpret_cast<PlatformThread*>(th);
    if (t->t.joinable()) t->t.detach();
    delete t;
}

void Platform::Thread_Wait(Thread* th)
{
    auto* t = reinterpret_cast<PlatformThread*>(th);
    if (t->t.joinable()) t->t.join();
}

Semaphore* Platform::Semaphore_Create()
{
    return reinterpret_cast<Semaphore*>(new PlatformSemaphore);
}

void Platform::Semaphore_Free(Semaphore* s)
{
    delete reinterpret_cast<PlatformSemaphore*>(s);
}

void Platform::Semaphore_Reset(Semaphore* s)
{
    auto* ps = reinterpret_cast<PlatformSemaphore*>(s);
    std::lock_guard<std::mutex> lk(ps->m);
    ps->count = 0;
}

void Platform::Semaphore_Wait(Semaphore* s)
{
    auto* ps = reinterpret_cast<PlatformSemaphore*>(s);
    std::unique_lock<std::mutex> lk(ps->m);
    ps->cv.wait(lk, [ps]{ return ps->count > 0; });
    ps->count--;
}

bool Platform::Semaphore_TryWait(Semaphore* s, int timeout_ms)
{
    auto* ps = reinterpret_cast<PlatformSemaphore*>(s);
    std::unique_lock<std::mutex> lk(ps->m);
    auto dl = std::chrono::steady_clock::now() + std::chrono::milliseconds(timeout_ms);
    bool got = ps->cv.wait_until(lk, dl, [ps]{ return ps->count > 0; });
    if (got) ps->count--;
    return got;
}

void Platform::Semaphore_Post(Semaphore* s, int count)
{
    auto* ps = reinterpret_cast<PlatformSemaphore*>(s);
    { std::lock_guard<std::mutex> lk(ps->m); ps->count += count; }
    if (count == 1) ps->cv.notify_one();
    else            ps->cv.notify_all();
}

Mutex* Platform::Mutex_Create()  { return reinterpret_cast<Mutex*>(new PlatformMutex); }
void   Platform::Mutex_Free(Mutex* m)   { delete reinterpret_cast<PlatformMutex*>(m); }
void   Platform::Mutex_Lock(Mutex* m)   { reinterpret_cast<PlatformMutex*>(m)->m.lock(); }
void   Platform::Mutex_Unlock(Mutex* m) { reinterpret_cast<PlatformMutex*>(m)->m.unlock(); }
bool   Platform::Mutex_TryLock(Mutex* m){ return reinterpret_cast<PlatformMutex*>(m)->m.try_lock(); }

void Platform::Sleep(u64 usecs)
{
    std::this_thread::sleep_for(std::chrono::microseconds(usecs));
}

u64 Platform::GetMSCount()
{
    using namespace std::chrono;
    return duration_cast<milliseconds>(steady_clock::now().time_since_epoch()).count();
}

u64 Platform::GetUSCount()
{
    using namespace std::chrono;
    return duration_cast<microseconds>(steady_clock::now().time_since_epoch()).count();
}

FileHandle* Platform::OpenFile(const std::string& path, FileMode mode)
{
    const char* fmode;
    switch (mode) {
        case FileMode::Read:              fmode = "rb";  break;
        case FileMode::Write:             fmode = "wb";  break;
        case FileMode::ReadWrite:         fmode = "r+b"; break;
        case FileMode::ReadWriteExisting: fmode = "r+b"; break;
        case FileMode::Append:            fmode = "ab";  break;
        default:                          fmode = "rb";  break;
    }
    FILE* f = fopen(path.c_str(), fmode);
    return reinterpret_cast<FileHandle*>(f);
}

FileHandle* Platform::OpenLocalFile(const std::string& path, FileMode mode)
{
    return OpenFile(path, mode);
}

bool Platform::CloseFile(FileHandle* fh)
{
    if (!fh) return false;
    return fclose(reinterpret_cast<FILE*>(fh)) == 0;
}

bool Platform::FileExists(const std::string& name)
{
    FILE* f = fopen(name.c_str(), "rb");
    if (f) { fclose(f); return true; }
    return false;
}

bool Platform::LocalFileExists(const std::string& name)
{
    return FileExists(name);
}

bool Platform::FileSeek(FileHandle* fh, s64 offset, FileSeekOrigin origin)
{
    if (!fh) return false;
    int whence;
    switch (origin) {
        case FileSeekOrigin::Start:   whence = SEEK_SET; break;
        case FileSeekOrigin::Current: whence = SEEK_CUR; break;
        case FileSeekOrigin::End:     whence = SEEK_END; break;
        default:                      whence = SEEK_SET; break;
    }
    return fseeko(reinterpret_cast<FILE*>(fh), offset, whence) == 0;
}

void Platform::FileRewind(FileHandle* fh)
{
    if (fh) rewind(reinterpret_cast<FILE*>(fh));
}

u64 Platform::FileRead(void* data, u64 size, u64 count, FileHandle* fh)
{
    if (!fh) return 0;
    return fread(data, size, count, reinterpret_cast<FILE*>(fh));
}

bool Platform::FileReadLine(char* str, int count, FileHandle* fh)
{
    if (!fh) return false;
    return fgets(str, count, reinterpret_cast<FILE*>(fh)) != nullptr;
}

u64 Platform::FileWrite(const void* data, u64 size, u64 count, FileHandle* fh)
{
    if (!fh) return 0;
    return fwrite(data, size, count, reinterpret_cast<FILE*>(fh));
}

u64 Platform::FileWriteFormatted(FileHandle* fh, const char* fmt, ...)
{
    if (!fh) return 0;
    va_list args;
    va_start(args, fmt);
    int r = vfprintf(reinterpret_cast<FILE*>(fh), fmt, args);
    va_end(args);
    return r >= 0 ? (u64)r : 0;
}

u64 Platform::FileLength(FileHandle* fh)
{
    if (!fh) return 0;
    FILE* f = reinterpret_cast<FILE*>(fh);
    long cur = ftell(f);
    fseek(f, 0, SEEK_END);
    long len = ftell(f);
    fseek(f, cur, SEEK_SET);
    return (u64)len;
}

void Platform::SignalStop(StopReason reason, void* userdata) { (void)reason; (void)userdata; }

void Platform::WriteNDSSave(const u8* savedata, u32 savelen, u32 writeoffset, u32 writelen, void* userdata)
{ (void)savedata; (void)savelen; (void)writeoffset; (void)writelen; (void)userdata; }

void Platform::WriteGBASave(const u8* savedata, u32 savelen, u32 writeoffset, u32 writelen, void* userdata)
{ (void)savedata; (void)savelen; (void)writeoffset; (void)writelen; (void)userdata; }

void Platform::WriteFirmware(const Firmware& firmware, u32 writeoffset, u32 writelen, void* userdata)
{ (void)firmware; (void)writeoffset; (void)writelen; (void)userdata; }

void Platform::WriteDateTime(int year, int month, int day, int hour, int minute, int second, void* userdata)
{ (void)year; (void)month; (void)day; (void)hour; (void)minute; (void)second; (void)userdata; }

void Platform::MP_Begin(void* userdata) { (void)userdata; }
void Platform::MP_End(void* userdata)   { (void)userdata; }

int Platform::MP_SendPacket(u8* data, int len, u64 timestamp, void* userdata)
{ (void)data; (void)len; (void)timestamp; (void)userdata; return 0; }

int Platform::MP_RecvPacket(u8* data, u64* timestamp, void* userdata)
{ (void)data; (void)timestamp; (void)userdata; return 0; }

int Platform::MP_SendCmd(u8* data, int len, u64 timestamp, void* userdata)
{ (void)data; (void)len; (void)timestamp; (void)userdata; return 0; }

int Platform::MP_SendReply(u8* data, int len, u64 timestamp, u16 aid, void* userdata)
{ (void)data; (void)len; (void)timestamp; (void)aid; (void)userdata; return 0; }

int Platform::MP_SendAck(u8* data, int len, u64 timestamp, void* userdata)
{ (void)data; (void)len; (void)timestamp; (void)userdata; return 0; }

int Platform::MP_RecvHostPacket(u8* data, u64* timestamp, void* userdata)
{ (void)data; (void)timestamp; (void)userdata; return 0; }

u16 Platform::MP_RecvReplies(u8* data, u64 timestamp, u16 aidmask, void* userdata)
{ (void)data; (void)timestamp; (void)aidmask; (void)userdata; return 0; }

void Platform::Camera_Start(int num, void* userdata) { (void)num; (void)userdata; }
void Platform::Camera_Stop(int num, void* userdata)  { (void)num; (void)userdata; }
void Platform::Camera_CaptureFrame(int num, u32* frame, int width, int height, bool yuv, void* userdata)
{
    if (frame) memset(frame, 0, width * height * sizeof(u32));
    (void)num; (void)yuv; (void)userdata;
}

bool Platform::IsEndOfFile(FileHandle* fh)
{
    if (!fh) return true;
    return feof(reinterpret_cast<FILE*>(fh)) != 0;
}

u64 Platform::FilePosition(FileHandle* fh)
{
    if (!fh) return 0;
    return (u64)ftell(reinterpret_cast<FILE*>(fh));
}

bool Platform::FileFlush(FileHandle* fh)
{
    if (!fh) return false;
    return fflush(reinterpret_cast<FILE*>(fh)) == 0;
}

int Platform::Net_SendPacket(u8* data, int len, void* userdata)
{ (void)data; (void)len; (void)userdata; return 0; }

int Platform::Net_RecvPacket(u8* data, void* userdata)
{ (void)data; (void)userdata; return 0; }

void Platform::Mic_Start(void* userdata) { (void)userdata; }
void Platform::Mic_Stop(void* userdata)  { (void)userdata; }
int  Platform::Mic_ReadInput(s16* data, int samples, void* userdata)
{ if (data) memset(data, 0, samples * sizeof(s16)); (void)userdata; return samples; }

void Platform::Addon_RumbleStart(u32 len, void* userdata) { (void)len; (void)userdata; }
void Platform::Addon_RumbleStop(void* userdata) { (void)userdata; }
bool Platform::Addon_KeyDown(KeyType key, void* userdata) { (void)key; (void)userdata; return false; }
float Platform::Addon_MotionQuery(MotionQueryType query, void* userdata)
{ (void)query; (void)userdata; return 0.0f; }

Platform::AACDecoder* Platform::AAC_Init()
{ return nullptr; }

void Platform::AAC_DeInit(AACDecoder* dec)
{ (void)dec; }

bool Platform::AAC_Configure(AACDecoder* dec, int frequency, int channels)
{ (void)dec; (void)frequency; (void)channels; return false; }

bool Platform::AAC_DecodeFrame(AACDecoder* dec, const void* input, int inputlen, void* output, int outputlen)
{ (void)dec; (void)input; (void)inputlen; (void)output; (void)outputlen; return false; }