// Count successful DXGI and D3D9 present calls from one owned process using Windows SDK ETW.
#include <windows.h>
#include <evntrace.h>
#include <evntcons.h>
#include <tdh.h>
#include <cstddef>
#include <climits>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cwchar>
#include <map>
#include <string>
#include <vector>
#include "etw-owned.h"

static const GUID dxgi = {0xca11c036, 0x0102, 0x4a2d, {0xa6, 0xad, 0xf0, 0x3c, 0xfe, 0xd5, 0xd3, 0xc9}};
static const GUID d3d9 = {0x783aca0a, 0x790e, 0x4d7f, {0x84, 0x51, 0xaa, 0x85, 0x05, 0x11, 0xc6, 0xb9}};
static ULONG subject{};
static ULONG missing_metadata{};
static bool record_timing{};
struct PresentStart { ULONG flags; ULONG sync_interval; LONGLONG tick; };
static std::map<std::pair<USHORT, ULONG>, PresentStart> outstanding;

static bool property(EVENT_RECORD* record, PCWSTR name, ULONG* value) {
    PROPERTY_DATA_DESCRIPTOR field{};
    field.PropertyName = reinterpret_cast<ULONGLONG>(name);
    field.ArrayIndex = ULONG_MAX;
    const ULONG result = TdhGetProperty(record, 0, nullptr, 1, &field, sizeof(*value), reinterpret_cast<PBYTE>(value));
    if (result != ERROR_SUCCESS) ++missing_metadata;
    return result == ERROR_SUCCESS;
}

static void WINAPI event_record(EVENT_RECORD* record) {
    const auto& h = record->EventHeader;
    const bool is_dxgi = IsEqualGUID(h.ProviderId, dxgi);
    if (h.ProcessId != subject || (!is_dxgi && !IsEqualGUID(h.ProviderId, d3d9))) return;
    const USHORT id = h.EventDescriptor.Id;
    const bool starting = (is_dxgi && (id == 42 || id == 55)) || (!is_dxgi && id == 1);
    if (!starting && !((is_dxgi && (id == 43 || id == 56)) || (!is_dxgi && id == 2))) return;
    const auto key = std::make_pair(static_cast<USHORT>(starting ? id : id - 1), h.ThreadId);
    if (starting) {
        PresentStart start{0, 0, h.TimeStamp.QuadPart};
        if (property(record, L"Flags", &start.flags) &&
            (!record_timing || id != 42 || property(record, L"SyncInterval", &start.sync_interval))) {
            outstanding[key] = start;
        }
        return;
    }
    const auto start = outstanding.find(key);
    if (start == outstanding.end()) return;
    const auto call = start->second;
    const bool test_only = is_dxgi && (call.flags & 1U) != 0;
    outstanding.erase(start);
    ULONG result{};
    if (property(record, L"Result", &result) && !test_only && result == 0) {
        std::printf("P %s %lld\n", is_dxgi ? "DXGI" : "D3D9", static_cast<long long>(h.TimeStamp.QuadPart));
        if (record_timing && id == 43) {
            std::printf("DXGI %lu %lu %lu %lu %lld %lld\n", subject, h.ThreadId, call.sync_interval, call.flags,
                        static_cast<long long>(call.tick), static_cast<long long>(h.TimeStamp.QuadPart));
        }
    }
}

static ULONG enable(TRACEHANDLE session, const GUID& provider, USHORT* ids, USHORT count) {
    struct EventIds { BOOLEAN include; UCHAR reserved; USHORT count; USHORT ids[4]; };
    EventIds chosen{TRUE, 0, count, {}};
    std::memcpy(chosen.ids, ids, count * sizeof(*ids));
    EVENT_FILTER_DESCRIPTOR filter[2]{};
    filter[0].Type = EVENT_FILTER_TYPE_PID;
    filter[0].Ptr = reinterpret_cast<ULONGLONG>(&subject);
    filter[0].Size = sizeof(subject);
    filter[1].Type = EVENT_FILTER_TYPE_EVENT_ID;
    filter[1].Ptr = reinterpret_cast<ULONGLONG>(&chosen);
    filter[1].Size = static_cast<ULONG>(offsetof(EventIds, ids) + count * sizeof(*ids));
    ENABLE_TRACE_PARAMETERS options{};
    options.Version = ENABLE_TRACE_PARAMETERS_VERSION_2;
    options.EnableFilterDesc = filter;
    options.FilterDescCount = 2;
    return EnableTraceEx2(session, &provider, EVENT_CONTROL_CODE_ENABLE_PROVIDER, TRACE_LEVEL_VERBOSE,
                          0x8000000000000002ULL, 0, 5000, &options);
}

int wmain(int argc, wchar_t** argv) {
    if (argc == 4 && !wcscmp(argv[1], L"--stop-owned")) return ifw_etw::stop_owned(argv[3], argv[2], L"IFW-RW02-", L"subject.etl");
    record_timing = argc == 5 && !wcscmp(argv[4], L"--timings");
    if (argc != 4 && !record_timing) return 2;
    subject = std::wcstoul(argv[1], nullptr, 10);
    if (!subject) return 2;
    const std::wstring file = argv[2], name = argv[3];
    GUID identity{};
    if (!ifw_etw::identity(name, L"IFW-RW02-", identity)) return 2;
    const auto offset = sizeof(EVENT_TRACE_PROPERTIES);
    const auto path_offset = offset + (name.size() + 1) * sizeof(wchar_t);
    const auto bytes = path_offset + (file.size() + 1) * sizeof(wchar_t);
    std::vector<BYTE> storage(bytes);
    auto* settings = reinterpret_cast<EVENT_TRACE_PROPERTIES*>(storage.data());
    settings->Wnode.BufferSize = static_cast<ULONG>(bytes);
    settings->Wnode.Flags = WNODE_FLAG_TRACED_GUID;
    settings->Wnode.Guid = identity;
    settings->Wnode.ClientContext = 1;  // QueryPerformanceCounter, shared with the native measurement driver.
    settings->BufferSize = 64;
    settings->MinimumBuffers = 4;
    settings->MaximumBuffers = 32;
    settings->MaximumFileSize = 32;
    settings->LogFileMode = EVENT_TRACE_FILE_MODE_SEQUENTIAL;
    settings->LoggerNameOffset = static_cast<ULONG>(offset);
    settings->LogFileNameOffset = static_cast<ULONG>(path_offset);
    std::memcpy(storage.data() + offset, name.c_str(), (name.size() + 1) * sizeof(wchar_t));
    std::memcpy(storage.data() + path_offset, file.c_str(), (file.size() + 1) * sizeof(wchar_t));
    TRACEHANDLE session{};
    ULONG status = StartTraceW(&session, name.c_str(), settings);
    if (status != ERROR_SUCCESS) { std::printf("START_ERROR %lu\n", status); return 3; }
    USHORT dxgi_ids[] = {42, 43, 55, 56}, d3d9_ids[] = {1, 2};
    status = enable(session, dxgi, dxgi_ids, 4);
    if (status == ERROR_SUCCESS) status = enable(session, d3d9, d3d9_ids, 2);
    if (status == ERROR_SUCCESS) {
        std::puts("READY");
        std::fflush(stdout);
        (void)std::getchar();  // EOF also drains the session when the owner exits early.
    } else {
        std::printf("ENABLE_ERROR %lu\n", status);
    }
    const ULONG stop = ControlTraceW(session, name.c_str(), settings, EVENT_TRACE_CONTROL_STOP);
    if (status != ERROR_SUCCESS || stop != ERROR_SUCCESS || settings->EventsLost || settings->LogBuffersLost) {
        std::printf("TRACE_ERROR %lu %lu %lu\n", stop, settings->EventsLost, settings->LogBuffersLost);
        return 4;
    }
    EVENT_TRACE_LOGFILEW input{};
    input.LogFileName = argv[2];
    input.ProcessTraceMode = PROCESS_TRACE_MODE_EVENT_RECORD | PROCESS_TRACE_MODE_RAW_TIMESTAMP;
    input.EventRecordCallback = event_record;
    TRACEHANDLE trace = OpenTraceW(&input);
    if (trace == INVALID_PROCESSTRACE_HANDLE) return 5;
    if (record_timing) {
        LARGE_INTEGER frequency{};
        if (!QueryPerformanceFrequency(&frequency) || input.LogfileHeader.PerfFreq.QuadPart != frequency.QuadPart) {
            CloseTrace(trace);
            return 5;
        }
        std::printf("QPC %lu %lld\n", subject, static_cast<long long>(frequency.QuadPart));
    }
    status = ProcessTrace(&trace, 1, nullptr, nullptr);
    CloseTrace(trace);
    if (status != ERROR_SUCCESS || missing_metadata) {
        std::printf("DECODE_ERROR %lu %lu\n", status, missing_metadata);
        return 6;
    }
    std::puts("COMPLETE");
    return 0;
}
