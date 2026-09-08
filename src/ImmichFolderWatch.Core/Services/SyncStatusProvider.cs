using System.ComponentModel;
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
    private string? _currentlyDownloadingFile;
    private int _downloadedInCurrentPull;
    private int _currentPullSize;
    private int _pendingCount;
    private ServerConnectionState _serverConnection = ServerConnectionState.Unknown;
    private string? _lastErrorMessage;
    private string? _lastServerErrorMessage;
    private string? _lastSyncErrorMessage;
    private int _processedFileCount;
    private int _totalFileCount;
    private bool _pullCycleInProgress;
    private bool _pullCycleHasFailure;
    private bool _pullCycleHasTransfers;
    private bool _lastSyncErrorWasPull;
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

    public string? CurrentlyDownloadingFile
    {
        get => _currentlyDownloadingFile;
        private set => SetField(ref _currentlyDownloadingFile, value);
    }

    public int DownloadedInCurrentPull
    {
        get => _downloadedInCurrentPull;
        private set => SetField(ref _downloadedInCurrentPull, value);
    }

    public int CurrentPullSize
    {
        get => _currentPullSize;
        private set => SetField(ref _currentPullSize, value);
    }

    public int PendingCount
    {
        get => _pendingCount;
        private set => SetField(ref _pendingCount, value);
    }

    public ServerConnectionState ServerConnection
    {
        get => _serverConnection;
        private set => SetField(ref _serverConnection, value);
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

    /// <summary>Files attempted (including failures and skips) in the current or most recent transfer operation.</summary>
    public int ProcessedFileCount
    {
        get => _processedFileCount;
        private set => SetField(ref _processedFileCount, value);
    }

    /// <summary>Known files in the current or most recent operation; grows as a pull discovers more albums.</summary>
    public int TotalFileCount
    {
        get => _totalFileCount;
        private set => SetField(ref _totalFileCount, value);
    }

    public string? LastSyncErrorMessage
    {
        get => _lastSyncErrorMessage;
        private set => SetField(ref _lastSyncErrorMessage, value);
    }

    public string? LastServerErrorMessage
    {
        get => _lastServerErrorMessage;
        private set => SetField(ref _lastServerErrorMessage, value);
    }

    /// <summary>Starts an upload batch. Continue progress only for subsequent batches in the same queue flush.</summary>
    public void ReportBatchStarted(int batchSize, bool continueProgress = false)
    {
        lock (_gate)
        {
            CurrentBatchSize = batchSize;
            UploadedInCurrentBatch = 0;
            if (!continueProgress)
            {
                ProcessedFileCount = 0;
                LastSyncErrorMessage = null;
                LastErrorMessage = null;
                _lastSyncErrorWasPull = false;
            }
            TotalFileCount = ProcessedFileCount + batchSize;
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
            ProcessedFileCount++;
            CurrentlyUploadingFile = null;
            LastSyncCompletedUtc = DateTimeOffset.UtcNow;
        }
    }

    public void ReportUploadFailed(string filePath, string? errorMessage)
    {
        lock (_gate)
        {
            CurrentlyUploadingFile = null;
            ProcessedFileCount++;
            LastSyncErrorMessage = string.IsNullOrWhiteSpace(errorMessage) ? Path.GetFileName(filePath) : errorMessage;
            LastErrorMessage = LastSyncErrorMessage;
            _lastSyncErrorWasPull = false;
        }
    }

    public void ReportUploadSkipped()
    {
        lock (_gate)
        {
            ProcessedFileCount++;
        }
    }

    /// <summary>Reports an operation-level failure without counting an additional file attempt.</summary>
    public void ReportSyncFailed(string errorMessage)
    {
        lock (_gate)
        {
            CurrentlyUploadingFile = null;
            CurrentlyDownloadingFile = null;
            LastSyncErrorMessage = errorMessage;
            LastErrorMessage = errorMessage;
            _lastSyncErrorWasPull = _pullCycleInProgress;
            _pullCycleHasFailure |= _pullCycleInProgress;
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

    /// <summary>Begins a scan of all sync sources. Empty scans preserve the most recent file counters.</summary>
    public void ReportPullCycleStarted()
    {
        lock (_gate)
        {
            _pullCycleInProgress = true;
            _pullCycleHasFailure = false;
            _pullCycleHasTransfers = false;
        }
    }

    /// <summary>
    /// Ends the scan and clears an earlier pull error only after a complete successful scan.
    /// An empty scan does not clear an upload error or reset file counters.
    /// </summary>
    public void ReportPullCycleCompleted(bool completed)
    {
        lock (_gate)
        {
            if (completed && !_pullCycleHasFailure && _lastSyncErrorWasPull)
            {
                LastSyncErrorMessage = null;
                LastErrorMessage = null;
                _lastSyncErrorWasPull = false;
            }
            _pullCycleInProgress = false;
        }
    }

    /// <summary>
    /// Starts one album's downloads, accumulating progress and retaining errors inside an active pull cycle.
    /// Without an enclosing cycle, starts a standalone transfer operation.
    /// </summary>
    public void ReportPullStarted(int pullSize)
    {
        lock (_gate)
        {
            CurrentPullSize = pullSize;
            DownloadedInCurrentPull = 0;
            if (!_pullCycleInProgress || !_pullCycleHasTransfers)
            {
                if (!_pullCycleInProgress || !_pullCycleHasFailure)
                {
                    LastErrorMessage = null;
                    LastSyncErrorMessage = null;
                    _lastSyncErrorWasPull = false;
                }
                ProcessedFileCount = 0;
                TotalFileCount = 0;
            }
            TotalFileCount += pullSize;
            _pullCycleHasTransfers = true;
        }
    }

    public void ReportDownloadStarted(string filePath)
    {
        CurrentlyDownloadingFile = filePath;
    }

    public void ReportDownloadCompleted(string filePath)
    {
        lock (_gate)
        {
            DownloadedInCurrentPull++;
            ProcessedFileCount++;
            CurrentlyDownloadingFile = null;
            LastSyncCompletedUtc = DateTimeOffset.UtcNow;
        }
    }

    public void ReportDownloadFailed(string filePath, string? errorMessage)
    {
        lock (_gate)
        {
            CurrentlyDownloadingFile = null;
            ProcessedFileCount++;
            LastSyncErrorMessage = string.IsNullOrWhiteSpace(errorMessage) ? Path.GetFileName(filePath) : errorMessage;
            LastErrorMessage = LastSyncErrorMessage;
            _lastSyncErrorWasPull = true;
            _pullCycleHasFailure = true;
        }
    }

    public void ReportPullCompleted()
    {
        lock (_gate)
        {
            CurrentPullSize = 0;
            DownloadedInCurrentPull = 0;
            CurrentlyDownloadingFile = null;
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
            LastServerErrorMessage = reachable ? null : errorMessage;
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
        return true;
    }

    private void OnPropertyChanged([CallerMemberName] string? propertyName = null)
    {
        PropertyChanged?.Invoke(this, new PropertyChangedEventArgs(propertyName));
    }
}
