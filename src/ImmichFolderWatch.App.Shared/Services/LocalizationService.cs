using System.Globalization;
using System.Threading;
using ImmichFolderWatch.App.Shared.Resources;

namespace ImmichFolderWatch.App.Shared.Services;

public sealed class LocalizationService
{
    public const string LanguageAuto = "auto";
    public const string LanguageEnglish = "en";
    public const string LanguageGerman = "de";

    private static readonly CultureInfo EnglishCulture = CultureInfo.GetCultureInfo("en-US");
    private static readonly CultureInfo GermanCulture = CultureInfo.GetCultureInfo("de-DE");

    /// <summary>
    /// Snapshot of the OS UI culture the process was launched with.
    /// Captured once at type-init and never updated; used by the
    /// "auto" resolver so a previous explicit SetLanguage("de") doesn't
    /// poison <see cref="CultureInfo.CurrentUICulture"/> and trick a
    /// later switch back to "auto" into staying on the manually-picked
    /// language (user-reported: "auf System gestellt, ändert sich nichts"
    /// after first picking Deutsch on an English system).
    /// </summary>
    private static readonly CultureInfo SystemCultureSnapshot = CultureInfo.CurrentUICulture;

    public static LocalizationService Instance { get; } = new();

    private string _currentLanguage = LanguageAuto;
    private CultureInfo _currentCulture = EnglishCulture;

    public event EventHandler? LanguageChanged;

    public string CurrentLanguage => _currentLanguage;

    public CultureInfo CurrentCulture => _currentCulture;

    public static CultureInfo ResolveCulture(string? code)
    {
        return ResolveCultureForSystem(SystemCultureSnapshot, code);
    }

    /// <summary>
    /// Resolution helper exposed for testing — production code uses
    /// <see cref="ResolveCulture(string?)"/> which feeds in
    /// <see cref="SystemCultureSnapshot"/>. Tests can pass any culture
    /// to validate the auto-detect branch without having to reach
    /// through reflection.
    /// </summary>
    public static CultureInfo ResolveCultureForSystem(CultureInfo systemCulture, string? code)
    {
        ArgumentNullException.ThrowIfNull(systemCulture);

        var normalized = NormalizeCode(code);
        return normalized switch
        {
            LanguageEnglish => EnglishCulture,
            LanguageGerman => GermanCulture,
            _ => IsGerman(systemCulture) ? GermanCulture : EnglishCulture,
        };
    }

    public static string NormalizeCode(string? code)
    {
        if (string.IsNullOrWhiteSpace(code))
        {
            return LanguageAuto;
        }

        var trimmed = code.Trim().ToLowerInvariant();
        return trimmed switch
        {
            LanguageEnglish or LanguageGerman or LanguageAuto => trimmed,
            _ => LanguageAuto,
        };
    }

    public void SetLanguage(string? code)
    {
        var normalized = NormalizeCode(code);
        var culture = ResolveCulture(normalized);

        if (_currentLanguage == normalized && Equals(_currentCulture, culture))
        {
            return;
        }

        _currentLanguage = normalized;
        _currentCulture = culture;

        Thread.CurrentThread.CurrentUICulture = culture;
        Thread.CurrentThread.CurrentCulture = culture;
        CultureInfo.DefaultThreadCurrentUICulture = culture;
        CultureInfo.DefaultThreadCurrentCulture = culture;
        Strings.Culture = culture;

        LanguageChanged?.Invoke(this, EventArgs.Empty);
    }

    private static bool IsGerman(CultureInfo culture)
    {
        if (culture is null)
        {
            return false;
        }

        var name = culture.TwoLetterISOLanguageName;
        return string.Equals(name, "de", StringComparison.OrdinalIgnoreCase);
    }
}
