using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Interfaces;
using ImmichFolderWatch.Core.Services;

namespace ImmichFolderWatch.Tests.Services;

public sealed class ConfigVerificationServiceTests
{
    [Fact]
    public async Task VerifyAsync_ReturnsValidationErrorsWithoutPing()
    {
        var connectivityVerifier = new FakeConnectivityVerifier();
        var service = new ConfigVerificationService(connectivityVerifier);
        var config = new AppConfig();

        var result = await service.VerifyAsync(config, CancellationToken.None);

        Assert.False(result.Success);
        Assert.NotEmpty(result.Errors);
        Assert.Equal(0, connectivityVerifier.PingCallCount);
    }

    [Fact]
    public async Task VerifyAsync_ReturnsConnectivityFailure()
    {
        var tempDirectory = Directory.CreateTempSubdirectory("ifw-verify-");

        try
        {
            var connectivityVerifier = new FakeConnectivityVerifier
            {
                ExceptionToThrow = new HttpRequestException("Timed out"),
            };

            var service = new ConfigVerificationService(connectivityVerifier);
            var config = CreateValidConfig(tempDirectory.FullName);

            var result = await service.VerifyAsync(config, CancellationToken.None);

            Assert.False(result.Success);
            Assert.Single(result.Errors);
            Assert.Contains("Timed out", result.Errors[0]);
            Assert.Equal(1, connectivityVerifier.PingCallCount);
        }
        finally
        {
            tempDirectory.Delete(recursive: true);
        }
    }

    [Fact]
    public async Task VerifyAsync_RejectsRelativeLogDirectoryWithoutPing()
    {
        var tempDirectory = Directory.CreateTempSubdirectory("ifw-verify-relative-log-");

        try
        {
            var connectivityVerifier = new FakeConnectivityVerifier();
            var service = new ConfigVerificationService(connectivityVerifier);
            var config = CreateValidConfig(tempDirectory.FullName);
            config.Logging.LogDirectory = "logs";

            var result = await service.VerifyAsync(config, CancellationToken.None);

            Assert.False(result.Success);
            Assert.Contains("logging.logDirectory must be an absolute path.", result.Errors);
            Assert.Equal(0, connectivityVerifier.PingCallCount);
        }
        finally
        {
            tempDirectory.Delete(recursive: true);
        }
    }

    [Fact]
    public async Task VerifyAsync_RejectsExampleApiKeyWithoutPing()
    {
        var tempDirectory = Directory.CreateTempSubdirectory("ifw-verify-placeholder-key-");

        try
        {
            var connectivityVerifier = new FakeConnectivityVerifier();
            var service = new ConfigVerificationService(connectivityVerifier);
            var config = CreateValidConfig(tempDirectory.FullName);
            config.Immich.ApiKey = "REPLACE_WITH_IMMICH_API_KEY";

            var result = await service.VerifyAsync(config, CancellationToken.None);

            Assert.False(result.Success);
            Assert.Contains("immich.apiKey must be replaced with a real Immich API key.", result.Errors);
            Assert.Equal(0, connectivityVerifier.PingCallCount);
        }
        finally
        {
            tempDirectory.Delete(recursive: true);
        }
    }

    [Fact]
    public async Task VerifyAsync_ReturnsSuccessForValidConfig()
    {
        var tempDirectory = Directory.CreateTempSubdirectory("ifw-verify-success-");

        try
        {
            var connectivityVerifier = new FakeConnectivityVerifier();
            var service = new ConfigVerificationService(connectivityVerifier);
            var config = CreateValidConfig(tempDirectory.FullName);

            var result = await service.VerifyAsync(config, CancellationToken.None);

            Assert.True(result.Success);
            Assert.Empty(result.Errors);
            Assert.Equal(1, connectivityVerifier.PingCallCount);
        }
        finally
        {
            tempDirectory.Delete(recursive: true);
        }
    }

    private static AppConfig CreateValidConfig(string watchDirectory)
    {
        return new AppConfig
        {
            Immich = new ImmichSettings
            {
                ServerApiUrl = "https://immich.example.com/api",
                ApiKey = "demo-key",
            },
            Watch = new WatchSettings
            {
                Sources =
                {
                    new WatchSourceSettings
                    {
                        Path = watchDirectory,
                        AlbumName = "Screenshots",
                        IncludeSubdirectories = false,
                        Extensions =
                        {
                            ".png",
                        },
                    },
                },
                BatchIntervalSeconds = 5,
                MaxBatchSize = 25,
                FileReadyTimeoutSeconds = 30,
            },
            Retry = new RetrySettings
            {
                MaxAttempts = 5,
                BaseDelayMilliseconds = 500,
            },
            Logging = new LoggingSettings
            {
                Level = "Information",
                LogDirectory = Path.Combine(watchDirectory, "logs"),
            },
        };
    }

    private sealed class FakeConnectivityVerifier : IImmichConnectivityVerifier
    {
        public int PingCallCount { get; private set; }

        public Exception? ExceptionToThrow { get; init; }

        public Task PingAsync(CancellationToken cancellationToken)
        {
            PingCallCount++;

            if (ExceptionToThrow is not null)
            {
                throw ExceptionToThrow;
            }

            return Task.CompletedTask;
        }
    }
}
