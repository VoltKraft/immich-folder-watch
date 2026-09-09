using Microsoft.Extensions.Logging;

namespace ImmichFolderWatch.App.Linux.Logging;

/// <summary>
/// Bounded, process-local copy of emitted logs for the Flatpak-safe log viewer.
/// Shared by startup and worker providers, so restarting synchronization retains history.
/// Access is thread-safe; persistent history remains in the configured log target.
/// </summary>
public sealed class SessionLogBuffer
{
    private const int MaximumCharactersPerEntry = 8192;
    private readonly Queue<string> _entries = new();
    private readonly object _gate = new();
    private readonly int _capacity;

    public SessionLogBuffer(int capacity = 500)
    {
        ArgumentOutOfRangeException.ThrowIfLessThan(capacity, 1);
        _capacity = capacity;
    }

    public void Append(string entry)
    {
        ArgumentNullException.ThrowIfNull(entry);
        lock (_gate)
        {
            if (_entries.Count == _capacity)
            {
                _entries.Dequeue();
            }

            _entries.Enqueue(entry.Length <= MaximumCharactersPerEntry
                ? entry
                : entry[..MaximumCharactersPerEntry] + "…");
        }
    }

    public string GetText()
    {
        lock (_gate)
        {
            return string.Join(Environment.NewLine, _entries);
        }
    }
}

public sealed class SessionLoggerProvider(SessionLogBuffer buffer) : ILoggerProvider
{
    public ILogger CreateLogger(string categoryName) => new SessionLogger(buffer, categoryName);

    // The buffer belongs to the application, not to an individual worker host.
    public void Dispose() { }

    private sealed class SessionLogger(SessionLogBuffer buffer, string category) : ILogger
    {
        public IDisposable? BeginScope<TState>(TState state) where TState : notnull => null;

        public bool IsEnabled(LogLevel logLevel) => logLevel != LogLevel.None;

        public void Log<TState>(LogLevel logLevel, EventId eventId, TState state,
            Exception? exception, Func<TState, Exception?, string> formatter)
        {
            if (!IsEnabled(logLevel))
            {
                return;
            }

            var message = formatter(state, exception);
            buffer.Append($"{DateTimeOffset.Now:yyyy-MM-dd HH:mm:ss zzz} [{logLevel}] {category}: {message}"
                + (exception is null ? string.Empty : $"{Environment.NewLine}{exception}"));
        }
    }
}
