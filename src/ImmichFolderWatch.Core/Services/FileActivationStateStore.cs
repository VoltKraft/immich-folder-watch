using System.Text.Json;
using ImmichFolderWatch.Core.Interfaces;

namespace ImmichFolderWatch.Core.Services;

public sealed class FileActivationStateStore : IActivationStateStore
{
    private readonly string _stateFilePath;

    public FileActivationStateStore(string stateFilePath)
    {
        ArgumentException.ThrowIfNullOrWhiteSpace(stateFilePath);
        _stateFilePath = Path.GetFullPath(stateFilePath);
    }

    public bool IsInitialVerificationCompleted()
    {
        if (!File.Exists(_stateFilePath))
        {
            return false;
        }

        try
        {
            var json = File.ReadAllText(_stateFilePath);
            var state = JsonSerializer.Deserialize<ActivationStateDocument>(json);
            return state?.InitialVerificationCompleted ?? false;
        }
        catch
        {
            return false;
        }
    }

    public void MarkInitialVerificationCompleted()
    {
        var directory = Path.GetDirectoryName(_stateFilePath);
        if (!string.IsNullOrWhiteSpace(directory))
        {
            Directory.CreateDirectory(directory);
        }

        var json = JsonSerializer.Serialize(
            new ActivationStateDocument
            {
                InitialVerificationCompleted = true,
                VerifiedAtUtc = DateTimeOffset.UtcNow,
            },
            new JsonSerializerOptions
            {
                WriteIndented = true,
            });

        File.WriteAllText(_stateFilePath, json);
    }

    private sealed class ActivationStateDocument
    {
        public bool InitialVerificationCompleted { get; set; }

        public DateTimeOffset? VerifiedAtUtc { get; set; }
    }
}
