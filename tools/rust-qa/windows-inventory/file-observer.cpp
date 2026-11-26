// Decode one private fixture's synchronous file operations from a PID-filtered ETW session.
#include <algorithm>
#include <array>
#include <cstddef>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cwchar>
#include <iterator>
#include <map>
#include <string>
#include <unordered_map>
#include <vector>

#ifndef IFW_LEDGER_SELFTEST
#include <windows.h>
#include <evntrace.h>
#include <evntcons.h>
#include <tdh.h>
#include "../windows-performance/etw-owned.h"
static constexpr GUID kernel_file = {0xedd08927, 0x9cc4, 0x4e65, {0xb9, 0x70, 0xc2, 0x56, 0x0f, 0xb5, 0xc2, 0x89}};
static ULONG owner;
static std::vector<std::wstring> roots;
static uint64_t starts, ends, schema_errors;
#else
using LONGLONG = long long;
using USHORT = unsigned short;
#endif
static constexpr unsigned directories = 100, per_directory = 1000, no_file = per_directory;
static bool wpf;
static uint64_t failed, unmatched;

struct PathIndex { unsigned dir, file; };
struct Handle { PathIndex path; unsigned pass, identity_queries; bool enum_data; };
struct Operation { USHORT id; uint64_t object; PathIndex path; LONGLONG started; };
static std::unordered_map<uint64_t, Handle> handles;
static std::unordered_map<uint64_t, Operation> pending;
struct Sweep {
    std::array<LONGLONG, directories> enumerated{};
    std::array<LONGLONG, directories * per_directory> files{};
};
static std::array<Sweep, 2> sweeps;
static std::array<unsigned, directories> enumerations{};
static unsigned duplicates, impossible_order;

static void complete(const Operation& op, uint32_t status, LONGLONG at) {
    if (at < op.started) { ++impossible_order; return; }
    if (op.id == 12) {
        if (status) { ++failed; return; }
        unsigned pass = enumerations[op.path.dir];
        if (op.path.file != no_file && !pass) { ++impossible_order; return; }
        handles[op.object] = {op.path, pass, 0, false};
        return;
    }
    auto it = handles.find(op.object);
    if (it == handles.end()) { ++unmatched; return; }
    auto& h = it->second;
    if (op.id == 20) {
        if (status == 0) { h.enum_data = true; return; }
        if (status != 0x80000006U || !h.enum_data) { ++failed; return; } // STATUS_NO_MORE_FILES
        h.enum_data = false;
        auto& number = enumerations[h.path.dir];
        if (++number <= sweeps.size()) sweeps[number-1].enumerated[h.path.dir] = at;
        else ++impossible_order;
    } else if (op.id == 22) {
        if (status) { ++failed; return; }
        ++h.identity_queries;
        // On NTFS the reference checks FileIdInfo when opening, reading size, and reading modification time.
        // The Rust lease checks its identity once. Its complete snapshot separately attests size and mtime.
        if (h.identity_queries == (wpf ? 3U : 1U) && h.pass >= 1 && h.pass <= sweeps.size()) {
            auto& stamp = sweeps[h.pass-1].files[h.path.dir * per_directory + h.path.file];
            if (stamp) ++duplicates;
            else stamp = at;
        }
    }
}

#ifdef IFW_LEDGER_SELFTEST
int main() {
    wpf = true;
    const Operation directory{12, 100, {0, no_file}, 1}, enumeration{20, 100, {0, no_file}, 2};
    const Operation lease{12, 101, {0, 0}, 4}, identity_query{22, 101, {0, 0}, 5};
    complete(directory, 0, 1);
    complete(enumeration, 0, 2);
    complete(enumeration, 0x80000006U, 3);
    if (enumerations[0] != 1 || sweeps[0].enumerated[0] != 3) return 1;
    complete(lease, 0xc0000022U, 5);
    if (handles.count(101) || !failed || sweeps[0].files[0]) return 2;
    complete(lease, 0, 6);
    complete(identity_query, 0, 7);
    complete(identity_query, 0, 8);
    if (sweeps[0].files[0]) return 3;
    complete(identity_query, 0, 9);
    if (sweeps[0].files[0] != 9 || sweeps[1].files[0]) return 4;
    complete(directory, 0, 10);
    complete(enumeration, 0, 11);
    complete(enumeration, 0x80000006U, 12);
    complete(lease, 0, 13);
    complete(identity_query, 0, 14);
    complete(identity_query, 0xc0000001U, 15);
    complete(identity_query, 0, 16);
    if (sweeps[1].files[0] || failed != 2) return 5;
    complete(identity_query, 0, 17);
    if (sweeps[1].files[0] != 17 || unmatched || duplicates || impossible_order) return 6;
    complete(lease, 0, 18);
    for (int at = 19; at <= 21; ++at) complete(identity_query, 0, at);
    if (duplicates != 1) return 7;
    return 0;
}
#else
struct Layout { int irp = -1, object = -1, options = -1, info = -1, status = -1, name = -1; };
static std::map<unsigned, Layout> layouts;

// TDH supplies the installed provider's packed manifest layout once per event version.
static Layout layout(EVENT_RECORD* record) {
    ULONG size = 0;
    if (TdhGetEventInformation(record, 0, nullptr, nullptr, &size) != ERROR_INSUFFICIENT_BUFFER || size > 262144)
        return {};
    std::vector<BYTE> bytes(size);
    auto* info = reinterpret_cast<TRACE_EVENT_INFO*>(bytes.data());
    if (TdhGetEventInformation(record, 0, nullptr, info, &size) != ERROR_SUCCESS) return {};
    Layout fields;
    int offset = 0;
    for (ULONG i = 0; i < info->TopLevelPropertyCount; ++i) {
        const auto& p = info->EventPropertyInfoArray[i];
        if (p.Flags & (PropertyStruct | PropertyParamCount | PropertyParamLength) || p.count != 1) break;
        PCWSTR name = reinterpret_cast<PCWSTR>(bytes.data() + p.NameOffset);
        const auto type = p.nonStructType.InType;
        if (type == TDH_INTYPE_UNICODESTRING) {
            if (!wcscmp(name, L"FileName") || !wcscmp(name, L"OpenPath")) fields.name = offset;
            break;
        }
        const bool pointer = type == TDH_INTYPE_POINTER;
        const bool word = type == TDH_INTYPE_UINT32 || type == TDH_INTYPE_HEXINT32 || type == TDH_INTYPE_INT32;
        if (pointer && !wcscmp(name, L"Irp")) fields.irp = offset;
        if (pointer && !wcscmp(name, L"FileObject")) fields.object = offset;
        if (word && !wcscmp(name, L"CreateOptions")) fields.options = offset;
        if (word && !wcscmp(name, L"InfoClass")) fields.info = offset;
        if (word && (!wcscmp(name, L"Status") || !wcscmp(name, L"NtStatus"))) fields.status = offset;
        if (pointer || type == TDH_INTYPE_UINT64 || type == TDH_INTYPE_HEXINT64 || type == TDH_INTYPE_INT64) offset += 8;
        else if (word) offset += 4;
        else break;
    }
    return fields;
}

template<class T>
static bool field(EVENT_RECORD* r, int offset, T& out) {
    if (offset < 0 || static_cast<size_t>(offset) + sizeof(T) > r->UserDataLength) return false;
    std::memcpy(&out, static_cast<const BYTE*>(r->UserData) + offset, sizeof(T));
    return true;
}

static bool digits(PCWSTR text, unsigned& value) {
    value = 0;
    for (unsigned i = 0; i < 4; ++i) {
        if (text[i] < L'0' || text[i] > L'9') return false;
        value = value * 10 + static_cast<unsigned>(text[i] - L'0');
    }
    return true;
}

static bool fixture_path(EVENT_RECORD* r, int offset, PathIndex& p) {
    if (offset < 0 || offset >= r->UserDataLength) return false;
    const auto* name = reinterpret_cast<PCWSTR>(static_cast<const BYTE*>(r->UserData) + offset);
    const size_t limit = (r->UserDataLength - offset) / sizeof(wchar_t);
    size_t n = 0;
    while (n < limit && name[n]) ++n;
    if (n == limit) return false;
    while (n && name[n-1] == L'\\') --n;
    for (const auto& root : roots) {
        if (n <= root.size() || _wcsnicmp(name, root.c_str(), root.size())) continue;
        const auto* child = name + root.size();
        size_t rest = n - root.size();
        if ((rest != 5 && rest != 15) || child[0] != L'd' || !digits(child+1, p.dir) || p.dir >= directories) return false;
        if (rest == 5) { p.file = no_file; return true; }
        return child[5] == L'\\' && child[6] == L'f' && digits(child+7, p.file) && p.file < per_directory &&
               !_wcsnicmp(child+11, L".jpg", 4);
    }
    return false;
}

static void WINAPI event_record(EVENT_RECORD* r) {
    const auto& header = r->EventHeader;
    if (header.ProcessId != owner || !IsEqualGUID(header.ProviderId, kernel_file)) return;
    const auto id = header.EventDescriptor.Id;
    if (header.Flags & EVENT_HEADER_FLAG_32_BIT_HEADER) { ++schema_errors; return; }
    const unsigned key = id | (static_cast<unsigned>(header.EventDescriptor.Version) << 16);
    auto cached = layouts.find(key);
    if (cached == layouts.end()) cached = layouts.emplace(key, layout(r)).first;
    const auto& f = cached->second;
    uint64_t irp{}, object{};
    uint32_t value{};
    if (!field(r, f.irp, irp)) { ++schema_errors; return; }
    const LONGLONG at = header.TimeStamp.QuadPart;
    if (id == 24) {
        ++ends;
        if (!irp) return;
        auto it = pending.find(irp);
        if (it == pending.end()) return;
        if (!field(r, f.status, value)) { ++schema_errors; return; }
        complete(it->second, value, at);
        pending.erase(it);
        return;
    }
    if (!field(r, f.object, object)) { ++schema_errors; return; }
    if (!object) return;
    if (id == 13 || id == 14) { handles.erase(object); return; }
    if (pending.count(irp)) { ++unmatched; pending.erase(irp); }
    PathIndex path{};
    if (id == 12) {
        ++starts;
        // Any new use of a kernel object address invalidates the old association.
        handles.erase(object);
        if (f.name < 0 || !field(r, f.options, value)) { ++schema_errors; return; }
        if (!fixture_path(r, f.name, path)) return;
        if (path.file == no_file ? !(value & 1U) : !(value & 0x40U)) return;
    } else {
        auto it = handles.find(object);
        if (it == handles.end()) return;
        path = it->second.path;
        if (id == 20 && path.file != no_file) return;
        if (id == 22) {
            if (path.file == no_file) return;
            if (!field(r, f.info, value)) { ++schema_errors; return; }
            if (value != 59) return; // native FileIdInformation on the actual regular-file lease
        }
    }
    if (!irp || pending.size() >= 16384 || handles.size() >= 16384) { ++unmatched; return; }
    pending.emplace(irp, Operation{id, object, path, at});
}

static ULONG enable(TRACEHANDLE session) {
    struct Ids { BOOLEAN include; UCHAR reserved; USHORT count; USHORT ids[6]; };
    Ids ids{TRUE, 0, 6, {12, 13, 14, 20, 22, 24}};
    static_assert(offsetof(Ids, ids) == offsetof(EVENT_FILTER_EVENT_ID, Events));
    EVENT_FILTER_DESCRIPTOR filters[2]{};
    filters[0].Type = EVENT_FILTER_TYPE_PID;
    filters[0].Ptr = reinterpret_cast<ULONGLONG>(&owner);
    filters[0].Size = sizeof(owner);
    filters[1].Type = EVENT_FILTER_TYPE_EVENT_ID;
    filters[1].Ptr = reinterpret_cast<ULONGLONG>(&ids);
    filters[1].Size = sizeof(ids);
    ENABLE_TRACE_PARAMETERS param{};
    param.Version = ENABLE_TRACE_PARAMETERS_VERSION_2;
    param.EnableFilterDesc = filters;
    param.FilterDescCount = 2;
    return EnableTraceEx2(session, &kernel_file, EVENT_CONTROL_CODE_ENABLE_PROVIDER, TRACE_LEVEL_VERBOSE,
                          0xe0ULL, 0, 5000, &param); // FILEIO | OP_END | CREATE
}

struct TraceProperties {
    EVENT_TRACE_PROPERTIES p{};
    wchar_t logger[1024]{};
    wchar_t filename[2048]{};
    TraceProperties() {
        p.Wnode.BufferSize = sizeof(*this);
        p.LoggerNameOffset = offsetof(TraceProperties, logger);
        p.LogFileNameOffset = offsetof(TraceProperties, filename);
    }
};

// Loss counters from this sparse trial's own session, before and after the two observed passes.
static bool sparse_counters(const char* phase, const EVENT_TRACE_PROPERTIES& p) {
    LARGE_INTEGER at{};
    if (!QueryPerformanceCounter(&at)) return false;
    std::printf("MSI_ETW %s pid=%lu qpc=%lld mode=%lu eventsLost=%lu logLost=%lu realtimeLost=%lu allocated=%lu written=%lu\n",
                phase, owner, at.QuadPart, p.LogFileMode, p.EventsLost, p.LogBuffersLost, p.RealTimeBuffersLost,
                p.NumberOfBuffers, p.BuffersWritten);
    constexpr ULONG modes = EVENT_TRACE_FILE_MODE_SEQUENTIAL | EVENT_TRACE_INDEPENDENT_SESSION_MODE;
    return (p.LogFileMode & modes) == modes && !p.EventsLost && !p.LogBuffersLost && !p.RealTimeBuffersLost;
}

static bool sparse_query(TRACEHANDLE session, const GUID& id, const char* phase) {
    TraceProperties snapshot;
    snapshot.p.Wnode.Guid = id;
    snapshot.p.Wnode.Flags = WNODE_FLAG_TRACED_GUID;
    ULONG result = ControlTraceW(session, nullptr, &snapshot.p, EVENT_TRACE_CONTROL_QUERY);
    if (result != ERROR_SUCCESS) {
        std::printf("MSI_QUERY_ERROR %s %lu\n", phase, result);
        return false;
    }
    return IsEqualGUID(snapshot.p.Wnode.Guid, id) && sparse_counters(phase, snapshot.p);
}

int wmain(int argc, wchar_t** argv) {
    if (argc < 4) return 2;
    if (!wcscmp(argv[1], L"--stop-owned") && argc == 4)
        return ifw_etw::stop_owned(argv[3], argv[2], L"IFW-Files-", L"files.etl");
    if (argc != 6) return 2;
    const std::wstring name = argv[2], etl = argv[3], subject = argv[5];
    GUID guid{};
    const bool sparse = subject == L"msi-rust";
    if (!ifw_etw::identity(name, L"IFW-Files-", guid) || (!sparse && subject != L"wpf" && subject != L"rust")) return 2;
    wpf = subject == L"wpf";
    owner = std::wcstoul(argv[1], nullptr, 10);
    const std::wstring dos = argv[4];
    if (!owner || dos.size() < 4 || dos[1] != L':' || etl.size() >= 2048) return 2;
    wchar_t device[1024]{};
    if (!QueryDosDeviceW(dos.substr(0, 2).c_str(), device, static_cast<DWORD>(std::size(device)))) return 2;
    roots = {dos + L"\\", std::wstring(device) + dos.substr(2) + L"\\", L"\\??\\" + dos + L"\\", L"\\\\?\\" + dos + L"\\"};
    TraceProperties q;
    auto& p = q.p;
    p.Wnode.Guid = guid;
    p.Wnode.Flags = WNODE_FLAG_TRACED_GUID;
    p.Wnode.ClientContext = 1;
    p.BufferSize = 256;
    // Reserve space before the sustained 100,000-file workload starts on either subject.
    p.MinimumBuffers = 128;
    p.MaximumBuffers = 512;
    p.MaximumFileSize = 3072;
    p.LogFileMode = EVENT_TRACE_FILE_MODE_SEQUENTIAL;
    if (sparse) p.LogFileMode |= EVENT_TRACE_INDEPENDENT_SESSION_MODE;
    std::copy(name.begin(), name.end(), q.logger);
    std::copy(etl.begin(), etl.end(), q.filename);
    TRACEHANDLE session{};
    ULONG status = StartTraceW(&session, name.c_str(), &p);
    if (status != ERROR_SUCCESS) { std::printf("START_ERROR %lu\n", status); return 3; }
    status = enable(session);
    bool intact = true;
    if (status == ERROR_SUCCESS && sparse) intact = sparse_query(session, guid, "attached");
    if (status == ERROR_SUCCESS && intact) {
        std::printf("READY %lu %s\n", owner, wpf ? "wpf" : "rust");
        std::fflush(stdout);
        (void)std::getchar();
    }
    if (status == ERROR_SUCCESS && sparse) {
        const bool captured = sparse_query(session, guid, "captured");
        // Stop delivery to this handle while its buffers are still live, after the parent's second acknowledgment.
        status = EnableTraceEx2(session, &kernel_file, EVENT_CONTROL_CODE_DISABLE_PROVIDER, 0, 0, 0, 5000, nullptr);
        std::printf("MSI_DISABLE %lu\n", status);
        const bool disabled = sparse_query(session, guid, "disabled");
        intact = intact && captured && disabled;
    }
    ULONG stopped = ControlTraceW(session, nullptr, &p, EVENT_TRACE_CONTROL_STOP);
    if (sparse && stopped == ERROR_SUCCESS) intact = sparse_counters("stopped", p) && intact;
    if (status || stopped || !intact || p.EventsLost || p.LogBuffersLost) {
        std::printf("TRACE_ERROR %lu %lu %lu %lu\n", status, stopped, p.EventsLost, p.LogBuffersLost);
        if (stopped == ERROR_SUCCESS) {
            std::printf("BUFFER_STATS sizeKiB=%lu minimum=%lu maximum=%lu allocated=%lu written=%lu\n",
                        p.BufferSize, p.MinimumBuffers, p.MaximumBuffers, p.NumberOfBuffers, p.BuffersWritten);
        }
        return 4;
    }
    EVENT_TRACE_LOGFILEW input{};
    input.LogFileName = argv[3];
    input.ProcessTraceMode = PROCESS_TRACE_MODE_EVENT_RECORD | PROCESS_TRACE_MODE_RAW_TIMESTAMP;
    input.EventRecordCallback = event_record;
    TRACEHANDLE trace = OpenTraceW(&input);
    if (trace == INVALID_PROCESSTRACE_HANDLE) return 5;
    const ULONG header_events_lost = input.LogfileHeader.EventsLost;
    const ULONG header_buffers_lost = input.LogfileHeader.BuffersLost;
    status = ProcessTrace(&trace, 1, nullptr, nullptr);
    CloseTrace(trace);
    if (sparse) {
        std::printf("MSI_DECODE %lu %lu %lu\n", status, header_events_lost, header_buffers_lost);
        if (status || header_events_lost || header_buffers_lost) return 6;
    } else if (status || input.EventsLost) {
        std::printf("DECODE_ERROR %lu %lu\n", status, input.EventsLost);
        return 6;
    }
    std::printf("COUNTS %llu %llu %llu %llu %llu %zu %u %u\n", starts, ends, failed, unmatched, schema_errors,
                pending.size(), duplicates, impossible_order);
    for (unsigned pass = 0; pass < sweeps.size(); ++pass) {
        auto& sweep = sweeps[pass];
        std::vector<LONGLONG> times;
        for (unsigned d = 0; d < directories; ++d) {
            const auto begin = sweep.files.begin() + d * per_directory;
            const auto end = begin + per_directory;
            const auto count = std::count_if(begin, end, [](LONGLONG t) { return t > 0; });
            std::printf("D %u %u %lld %zu\n", pass, d, sweep.enumerated[d], static_cast<size_t>(count));
            std::copy_if(begin, end, std::back_inserter(times), [](LONGLONG t) { return t > 0; });
        }
        std::sort(times.begin(), times.end());
        for (size_t i = 0; i < times.size(); i += 32) {
            const auto next = (std::min)(i + 32, times.size());
            std::printf("B %u %lld %lld %zu\n", pass, times[i], times[next-1], next-i);
        }
    }
    std::puts("COMPLETE");
    return 0;
}
#endif
