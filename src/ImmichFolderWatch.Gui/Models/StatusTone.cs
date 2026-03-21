namespace ImmichFolderWatch.Gui.Models;

/// <summary>
/// Represents the semantic tone to use for status indicators and short feedback messages in the UI.
/// </summary>
public enum StatusTone
{
    /// <summary>
    /// Indicates a default status with no special emphasis.
    /// </summary>
    Neutral,

    /// <summary>
    /// Indicates an informational or in-progress state.
    /// </summary>
    Info,

    /// <summary>
    /// Indicates that an operation completed successfully.
    /// </summary>
    Success,

    /// <summary>
    /// Indicates a cautionary state that needs attention but is not a failure.
    /// </summary>
    Warning,

    /// <summary>
    /// Indicates a failure or error state.
    /// </summary>
    Error,
}
