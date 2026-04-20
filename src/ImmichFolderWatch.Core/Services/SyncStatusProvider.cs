using System.ComponentModel;
using System.Globalization;
using System.Runtime.CompilerServices;

namespace ImmichFolderWatch.Core.Services;

public enum ServerConnectionState
{
    Unknown,
    Checking,
    Ok,
    Error,
}

public sealed class SyncStatusProvider : INotifyPropertyChanged
{
    private readonly object _gate = new();

    private DateTimeOffset? _lastSyncCompletedUtc;
    private string? _currentlyUploadingFile;
    private int _uploadedInCurrentBatch;
    private int _currentBatchSize;
    private int _pendingCount;
    private ServerConnectionState _serverConnection = ServerConnectionState.Unknown;
    private string? _lastErrorMessage;
    private DateTimeOffset? _lastServerCheckUtc;

    public event PropertyChangedEventHandler? PropertyChanged;

    public DateTimeOffset? LastSyncCompletedUtc
    {
        get => _lastSyncCompletedUtc;
        private set => SetField(ref _lastSyncCompletedUtc, value);
    }

    public string? CurrentlyUploadingFile
    {
        get => _currentlyUploadingFile;
        private set => SetField(ref _currentlyUploadingFile, value);
    }

    public int UploadedInCurrentBatch
    {
        get => _uploadedInCurrentBatch;
        private set => SetField(ref _uploadedInCurrentBatch, value);
    }

    public int CurrentBatchSize
    {
        get => _currentBatchSize;
        private set => SetField(ref _currentBatchSize, value);
    }

    public int PendingCount
    {
        get => _pendingCount;
        private set => SetField(ref _pendingCount, value);
    }

    public ServerConnectionState ServerConnection
    {
        get => _serverConnection;
        private set
        {
            if (SetField(ref _serverConnection, value))
            {
                OnPropertyChanged(nameof(TooltipText));
            }
        }
    }

    public string? LastErrorMessage
    {
        get => _lastErrorMessage;
        private set => SetField(ref _lastErrorMessage, value);
    }

    public DateTimeOffset? LastServerCheckUtc
    {
        get => _lastServerCheckUtc;
        private set => SetField(ref _lastServerCheckUtc, value);
    }

    public string TooltipText
    {
        get
        {
            var server = ServerConnection switch
            {
                ServerConnectionState.Ok => "OK",
                ServerConnectionState.Error => "Fehler",
                ServerConnectionState.Checking => "Prüfe…",
                _ => "Unbekannt",
            };

            var lastSync = LastSyncCompletedUtc.HasValue
                ? LastSyncCompletedUtc.Value.ToLocalTime().ToString("HH:mm", CultureInfo.CurrentCulture)
                : "—";

            var line = $"Immich Folder Watch\nServer: {server}\nLetzter Sync: {lastSync}\nWarteschlange: {PendingCount}";
            return line.Length > 127 ? line[..127] : line;
        }
    }

    public void ReportBatchStarted(int batchSize)
    {
        lock (_gate)
        {
            CurrentBatchSize = batchSize;
            UploadedInCurrentBatch = 0;
            LastErrorMessage = null;
        }
    }

    public void ReportUploadStarted(string filePath)
    {
        CurrentlyUploadingFile = filePath;
    }

    public void ReportUploadCompleted(string filePath)
    {
        lock (_gate)
        {
            UploadedInCurrentBatch++;
            CurrentlyUploadingFile = null;
            LastSyncCompletedUtc = DateTimeOffset.UtcNow;
        }
    }

    public void ReportUploadFailed(string filePath, string? errorMessage)
    {
        lock (_gate)
        {
            CurrentlyUploadingFile = null;
            LastErrorMessage = errorMessage;
        }
    }

    public void ReportBatchCompleted()
    {
        lock (_gate)
        {
            CurrentBatchSize = 0;
            UploadedInCurrentBatch = 0;
            CurrentlyUploadingFile = null;
        }
    }

    public void ReportPendingCount(int count)
    {
        PendingCount = count;
    }

    public void ReportServerReachable(bool reachable, string? errorMessage = null)
    {
        lock (_gate)
        {
            ServerConnection = reachable ? ServerConnectionState.Ok : ServerConnectionState.Error;
            LastServerCheckUtc = DateTimeOffset.UtcNow;
            if (!reachable)
            {
                LastErrorMessage = errorMessage;
            }
        }
    }

    public void ReportServerChecking()
    {
        ServerConnection = ServerConnectionState.Checking;
    }

    private bool SetField<T>(ref T field, T value, [CallerMemberName] string? propertyName = null)
    {
        if (EqualityComparer<T>.Default.Equals(field, value))
        {
            return false;
        }

        field = value;
        OnPropertyChanged(propertyName);
        if (propertyName is nameof(LastSyncCompletedUtc) or nameof(PendingCount))
        {
            OnPropertyChanged(nameof(TooltipText));
        }

        return true;
    }

    private void OnPropertyChanged([CallerMemberName] string? propertyName = null)
    {
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(propertyName));
    }
}
