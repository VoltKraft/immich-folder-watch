using System.Globalization;
using System.Threading;
using ImmichFolderWatch.App.Resources;

namespace ImmichFolderWatch.App.Services;

public sealed class LocalizationService
{
    public const string LanguageAuto = "auto";
    public const string LanguageEnglish = "en";
    public const string LanguageGerman = "de";

    private static readonly CultureInfo EnglishCulture = CultureInfo.GetCultureInfo("en-US");
    private static readonly CultureInfo GermanCulture = CultureInfo.GetCultureInfo("de-DE");

    public static LocalizationService Instance { get; } = new();

    private string _currentLanguage = LanguageAuto;
    private CultureInfo _currentCulture = EnglishCulture;

    public event EventHandler? LanguageChanged;

    public string CurrentLanguage => _currentLanguage;

    public CultureInfo CurrentCulture => _currentCulture;

    public static CultureInfo ResolveCulture(string? code)
    {
        var normalized = NormalizeCode(code);
        return normalized switch
        {
            LanguageEnglish => EnglishCulture,
            LanguageGerman => GermanCulture,
            _ => ResolveAutoCulture(),
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

    private static CultureInfo ResolveAutoCulture()
    {
        var os = CultureInfo.CurrentUICulture;
        return IsGerman(os) ? GermanCulture : EnglishCulture;
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
