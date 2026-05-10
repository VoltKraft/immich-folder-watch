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
    public void ResolveCultureForSystem_AutoPicksGerman_WhenSystemCultureIsGerman()
    {
        var resolved = LocalizationService.ResolveCultureForSystem(
            CultureInfo.GetCultureInfo("de-DE"),
            "auto");
        Assert.Equal("de-DE", resolved.Name);
    }

    [Fact]
    public void ResolveCultureForSystem_AutoPicksEnglish_WhenSystemCultureIsNotGerman()
    {
        var resolved = LocalizationService.ResolveCultureForSystem(
            CultureInfo.GetCultureInfo("fr-FR"),
            "auto");
        Assert.Equal("en-US", resolved.Name);
    }

    [Fact]
    public void ResolveCultureForSystem_ExplicitCodeIgnoresSystemCulture()
    {
        // Manual selection beats system detection — picking "en" on a
        // German system still yields English.
        var resolved = LocalizationService.ResolveCultureForSystem(
            CultureInfo.GetCultureInfo("de-DE"),
            "en");
        Assert.Equal("en-US", resolved.Name);
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
