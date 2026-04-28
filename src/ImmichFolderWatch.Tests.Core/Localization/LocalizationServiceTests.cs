using System.Globalization;
using ImmichFolderWatch.App.Shared.Services;

namespace ImmichFolderWatch.Tests.Core.Localization;

public sealed class LocalizationServiceTests
{
    [Fact]
    public void ResolveCulture_EnglishCode_ReturnsEnUs()
    {
        var culture = LocalizationService.ResolveCulture("en");
        Assert.Equal("en-US", culture.Name);
    }

    [Fact]
    public void ResolveCulture_GermanCode_ReturnsDeDe()
    {
        var culture = LocalizationService.ResolveCulture("de");
        Assert.Equal("de-DE", culture.Name);
    }

    [Fact]
    public void ResolveCulture_UnknownCode_FallsBackToAuto()
    {
        var culture = LocalizationService.ResolveCulture("xx");
        Assert.Contains(culture.Name, new[] { "en-US", "de-DE" });
    }

    [Fact]
    public void ResolveCulture_NullOrWhitespace_FallsBackToAuto()
    {
        var nullCulture = LocalizationService.ResolveCulture(null);
        var emptyCulture = LocalizationService.ResolveCulture("   ");

        Assert.Contains(nullCulture.Name, new[] { "en-US", "de-DE" });
        Assert.Equal(nullCulture.Name, emptyCulture.Name);
    }

    [Fact]
    public void ResolveCulture_IsCaseInsensitive()
    {
        Assert.Equal("en-US", LocalizationService.ResolveCulture("EN").Name);
        Assert.Equal("de-DE", LocalizationService.ResolveCulture("DE").Name);
    }

    [Fact]
    public void ResolveCulture_AutoPicksGerman_WhenOsUiCultureIsGerman()
    {
        var previous = CultureInfo.CurrentUICulture;
        try
        {
            CultureInfo.CurrentUICulture = CultureInfo.GetCultureInfo("de-DE");
            Assert.Equal("de-DE", LocalizationService.ResolveCulture("auto").Name);
        }
        finally
        {
            CultureInfo.CurrentUICulture = previous;
        }
    }

    [Fact]
    public void ResolveCulture_AutoPicksEnglish_WhenOsUiCultureIsNotGerman()
    {
        var previous = CultureInfo.CurrentUICulture;
        try
        {
            CultureInfo.CurrentUICulture = CultureInfo.GetCultureInfo("fr-FR");
            Assert.Equal("en-US", LocalizationService.ResolveCulture("auto").Name);
        }
        finally
        {
            CultureInfo.CurrentUICulture = previous;
        }
    }

    [Theory]
    [InlineData(null, "auto")]
    [InlineData("", "auto")]
    [InlineData("  ", "auto")]
    [InlineData("auto", "auto")]
    [InlineData("AUTO", "auto")]
    [InlineData("en", "en")]
    [InlineData("EN", "en")]
    [InlineData(" de ", "de")]
    [InlineData("xx", "auto")]
    [InlineData("fr", "auto")]
    public void NormalizeCode_MapsKnownValuesAndFallsBackToAuto(string? input, string expected)
    {
        Assert.Equal(expected, LocalizationService.NormalizeCode(input));
    }
}
