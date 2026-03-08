namespace ImmichFolderWatch.Core.Models;

public sealed class VerificationResult
{
    private VerificationResult(bool success, IReadOnlyList<string> errors)
    {
        Success = success;
        Errors = errors;
    }

    public bool Success { get; }

    public IReadOnlyList<string> Errors { get; }

    public static VerificationResult Passed()
    {
        return new VerificationResult(true, Array.Empty<string>());
    }

    public static VerificationResult Failed(IEnumerable<string> errors)
    {
        ArgumentNullException.ThrowIfNull(errors);
        return new VerificationResult(false, errors.ToArray());
    }
}
