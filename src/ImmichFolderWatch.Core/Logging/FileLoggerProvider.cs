using Microsoft.Extensions.Logging;

namespace ImmichFolderWatch.Core.Logging;

public sealed class FileLoggerProvider : ILoggerProvider
{
    private readonly StreamWriter _writer;

    private readonly object _syncLock = new();

    private readonly LogLevel _minimumLevel;

    private bool _disposed;

    public FileLoggerProvider(string logDirectory, LogLevel minimumLevel)
    {
        Directory.CreateDirectory(logDirectory);

        var filePath = Path.Combine(logDirectory, $"immich-folder-watch-{DateTime.UtcNow:yyyyMMdd}.log");
        var stream = new FileStream(
            filePath,
            FileMode.Append,
            FileAccess.Write,
            FileShare.ReadWrite | FileShare.Delete);

        _writer = new StreamWriter(stream)
        {
            AutoFlush = true,
        };

        _minimumLevel = minimumLevel;
    }

    public ILogger CreateLogger(string categoryName)
    {
        ThrowIfDisposed();
        return new FileLogger(categoryName, _writer, _syncLock, _minimumLevel);
    }

    public void Dispose()
    {
        if (_disposed)
        {
            return;
        }

        _disposed = true;
        _writer.Dispose();
    }

    private void ThrowIfDisposed()
    {
        if (_disposed)
        {
            throw new ObjectDisposedException(nameof(FileLoggerProvider));
        }
    }
}

internal sealed class FileLogger : ILogger
{
    private readonly string _categoryName;

    private readonly StreamWriter _writer;

    private readonly object _syncLock;

    private readonly LogLevel _minimumLevel;

    public FileLogger(string categoryName, StreamWriter writer, object syncLock, LogLevel minimumLevel)
    {
        _categoryName = categoryName;
        _writer = writer;
        _syncLock = syncLock;
        _minimumLevel = minimumLevel;
    }

    public IDisposable BeginScope<TState>(TState state)
        where TState : notnull
    {
        return NullScope.Instance;
    }

    public bool IsEnabled(LogLevel logLevel)
    {
        return logLevel >= _minimumLevel;
    }

    public void Log<TState>(
        LogLevel logLevel,
        EventId eventId,
        TState state,
        Exception? exception,
        Func<TState, Exception?, string> formatter)
    {
        if (!IsEnabled(logLevel))
        {
            return;
        }

        var message = formatter(state, exception);
        if (string.IsNullOrWhiteSpace(message) && exception is null)
        {
            return;
        }

        var line = $"{DateTimeOffset.Now:yyyy-MM-dd HH:mm:ss.fff zzz} [{logLevel}] {_categoryName}: {message}";

        if (exception is not null)
        {
            line = $"{line}{Environment.NewLine}{exception}";
        }

        lock (_syncLock)
        {
            _writer.WriteLine(line);
        }
    }

    private sealed class NullScope : IDisposable
    {
        public static NullScope Instance { get; } = new();

        public void Dispose()
        {
        }
    }
}
