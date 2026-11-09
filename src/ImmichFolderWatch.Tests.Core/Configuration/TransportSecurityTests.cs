using ImmichFolderWatch.App.Shared.Services;
using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Models;
using ImmichFolderWatch.Immich;
using Microsoft.Extensions.Logging.Abstractions;

namespace ImmichFolderWatch.Tests.Core.Configuration;

public sealed class TransportSecurityTests
{
    [Theory]
    [InlineData("https://immich.example.test/api", false, true)]
    [InlineData("http://immich.example.test/api", false, false)]
    [InlineData("http://127.0.0.1:2283/api", false, false)]
    [InlineData("http://immich.example.test/api", true, true)]
    [InlineData("ftp://immich.example.test/api", true, false)]
    [InlineData("https://user:password@immich.example.test/api", false, false)]
    [InlineData("https://immich.example.test/api?secret=value", false, false)]
    public void ValidateServerApiUrl_RequiresExplicitHttpException(string url, bool allowHttp, bool allowed)
    {
        Assert.Equal(allowed, AppConfigValidator.ValidateServerApiUrl(url, allowHttp) is null);
    }

    [Fact]
    public async Task Verification_RejectsHttpBeforeContactingServer()
    {
        var config = new AppConfig { Immich = new ImmichSettings { ServerApiUrl = "http://127.0.0.1:1/api", ApiKey = "synthetic-test-key" } };
        var result = await new ConfigVerificationRunner().CheckImmichAccessAsync(config, Path.Combine(Path.GetTempPath(), "config.yaml"), CancellationToken.None);
        Assert.Equal(CheckState.Failed, result.UrlState);
        Assert.Contains("allowInsecureHttp", result.UrlMessage);
    }

    [Fact]
    public async Task Realtime_RejectsHttpBeforeConnecting()
    {
        var config = new AppConfig { Immich = new ImmichSettings { ServerApiUrl = "http://127.0.0.1:1/api" } };
        await using var client = new ImmichRealtimeClient(config, NullLogger<ImmichRealtimeClient>.Instance);
        var error = await Assert.ThrowsAsync<InvalidOperationException>(() => client.StartAsync(CancellationToken.None));
        Assert.Contains("allowInsecureHttp", error.Message);
    }

    [Fact]
    public void NormalizeAndSerialize_PreserveExplicitHttpException()
    {
        var config = new AppConfig { Immich = new ImmichSettings { ServerApiUrl = "http://immich.example.test/api", AllowInsecureHttp = true } };
        var normalized = AppConfigLoader.NormalizeForRuntime(config, Path.GetTempPath());
        Assert.True(normalized.Immich.AllowInsecureHttp);
        Assert.Contains("allowInsecureHttp: true", new AppConfigWriter().Serialize(normalized));
        Assert.False(new ImmichSettings().AllowInsecureHttp);
    }
}
