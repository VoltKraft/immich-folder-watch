// Cleanup for the recorder's own session after its controller has exited.
#pragma once
#include <windows.h>
#include <evntrace.h>
#include <cwchar>
#include <string>
#include <vector>

namespace ifw_etw {
inline bool identity(const std::wstring& name, const std::wstring& prefix, GUID& guid) {
    if (name.size() != prefix.size() + 32 || name.compare(0, prefix.size(), prefix)) return false;
    auto* bytes = reinterpret_cast<BYTE*>(&guid);
    for (size_t i = 0; i < sizeof(GUID); ++i) {
        unsigned value = 0;
        for (size_t half = 0; half < 2; ++half) {
            const auto c = name[prefix.size() + 2 * i + half];
            if (c >= L'0' && c <= L'9') value = value * 16 + static_cast<unsigned>(c - L'0');
            else if (c >= L'a' && c <= L'f') value = value * 16 + static_cast<unsigned>(c - L'a') + 10;
            else return false;
        }
        bytes[i] = static_cast<BYTE>(value);
    }
    return true;
}

inline bool matches(const std::vector<BYTE>& storage, ULONG offset, const std::wstring& expected) {
    if (offset < sizeof(EVENT_TRACE_PROPERTIES) || offset > storage.size() || offset % sizeof(wchar_t)) return false;
    if ((storage.size() - offset) / sizeof(wchar_t) < expected.size() + 1) return false;
    const auto* found = reinterpret_cast<const wchar_t*>(storage.data() + offset);
    return !found[expected.size()] && !_wcsnicmp(found, expected.c_str(), expected.size());
}

inline int stop_owned(const std::wstring& name, const std::wstring& file,
                      const std::wstring& prefix, const std::wstring& filename) {
    GUID expected{};
    std::vector<wchar_t> cwd(32768);
    const auto length = GetCurrentDirectoryW(static_cast<DWORD>(cwd.size()), cwd.data());
    if (!identity(name, prefix, expected) || !length || length >= cwd.size() ||
            _wcsicmp(file.c_str(), (std::wstring(cwd.data(), length) + L"\\" + filename).c_str())) return 2;
    const ULONG name_offset = static_cast<ULONG>(sizeof(EVENT_TRACE_PROPERTIES));
    const ULONG file_offset = name_offset + static_cast<ULONG>(1025 * sizeof(wchar_t));
    std::vector<BYTE> storage(file_offset + 1025 * sizeof(wchar_t));
    auto* settings = reinterpret_cast<EVENT_TRACE_PROPERTIES*>(storage.data());
    for (unsigned attempt = 0; attempt < 30; ++attempt) {
        ZeroMemory(settings, storage.size());
        settings->Wnode.BufferSize = static_cast<ULONG>(storage.size());
        settings->Wnode.Flags = WNODE_FLAG_TRACED_GUID;
        settings->Wnode.Guid = expected;
        settings->LoggerNameOffset = name_offset;
        settings->LogFileNameOffset = file_offset;
        const ULONG query = ControlTraceW(0, name.c_str(), settings, EVENT_TRACE_CONTROL_QUERY);
        if (query == ERROR_WMI_INSTANCE_NOT_FOUND) return 0;
        if (query || !IsEqualGUID(settings->Wnode.Guid, expected) || !settings->Wnode.HistoricalContext ||
                !matches(storage, settings->LoggerNameOffset, name) || !matches(storage, settings->LogFileNameOffset, file)) return 3;
        // The query returns the session handle in HistoricalContext. Stop by that handle only.
        const TRACEHANDLE session = settings->Wnode.HistoricalContext;
        ZeroMemory(settings, storage.size());
        settings->Wnode.BufferSize = static_cast<ULONG>(storage.size());
        settings->Wnode.Flags = WNODE_FLAG_TRACED_GUID;
        settings->Wnode.Guid = expected;
        settings->LoggerNameOffset = name_offset;
        settings->LogFileNameOffset = file_offset;
        const ULONG stop = ControlTraceW(session, nullptr, settings, EVENT_TRACE_CONTROL_STOP);
        if (stop != ERROR_SUCCESS && stop != ERROR_WMI_INSTANCE_NOT_FOUND && stop != ERROR_ACTIVE_CONNECTIONS) return 4;
        Sleep(50);
    }
    return 5;  // Absence was never confirmed.
}
}
