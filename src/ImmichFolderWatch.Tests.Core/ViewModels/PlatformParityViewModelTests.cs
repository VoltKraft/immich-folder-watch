using ImmichFolderWatch.App.Shared.Services;
using ImmichFolderWatch.App.Shared.ViewModels;
using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Logging;
using ImmichFolderWatch.Core.Platform;
using ImmichFolderWatch.Core.Services;

namespace ImmichFolderWatch.Tests.Core.ViewModels;

[Collection("Localization")]
public sealed class PlatformParityViewModelTests
{
    [Fact]
    public void Load_PreservesYamlHttpExceptionAcrossAccessCheckAndSave()
    {
        var vm = CreateViewModel(new FakeAutoStartManager());
        vm.Load(new AppConfig { Immich = new ImmichSettings { AllowInsecureHttp = true } });

        Assert.True(vm.CreateImmichCheckConfig().Immich.AllowInsecureHttp);
        Assert.True(vm.TryCreateConfig(out var config, out var errors), string.Join(Environment.NewLine, errors));
        Assert.True(config.Immich.AllowInsecureHttp);

        vm.Load(new AppConfig());
        Assert.False(vm.CreateImmichCheckConfig().Immich.AllowInsecureHttp);
    }

    [Fact]
    public void Constructor_UsesSuppliedPlatformLogDirectoryForInitialAndAccessCheckDefaults()
    {
        var paths = new TestPlatformPaths();
        var vm = CreateViewModel(new FakeAutoStartManager(), platformPaths: paths);

        Assert.Equal(paths.GetLogDirectory(), vm.LogDirectory);
        Assert.Equal(paths.GetLogDirectory(), vm.CreateImmichCheckConfig().Logging.LogDirectory);
    }

    [Fact]
    public void Load_BlankLogDirectory_UsesSuppliedPlatformDefault()
    {
        var paths = new TestPlatformPaths();
        var vm = CreateViewModel(new FakeAutoStartManager(), platformPaths: paths);
        vm.LogDirectory = Path.Combine(Path.GetTempPath(), "previous-logs");

        vm.Load(new AppConfig { Logging = new LoggingSettings { LogDirectory = " " } });

        Assert.Equal(paths.GetLogDirectory(), vm.LogDirectory);
    }

    [Fact]
    public void TryCreateConfig_BlankNonFileLogDirectory_UsesSuppliedPlatformDefault()
    {
        var paths = new TestPlatformPaths();
        var vm = CreateViewModel(new FakeAutoStartManager(), platformPaths: paths);
        vm.LoggingTarget = LogTargets.Journald;
        vm.LogDirectory = " ";

        Assert.True(vm.TryCreateConfig(out var config, out var errors), string.Join(Environment.NewLine, errors));

        Assert.Equal(paths.GetLogDirectory(), config.Logging.LogDirectory);
    }

    [Theory]
    [InlineData("de", "de")]
    [InlineData("en", "en")]
    [InlineData("auto", "auto")]
    [InlineData(" DE ", "de")]
    [InlineData("unsupported", "auto")]
    public void Load_AppliesConfiguredLanguageAndPreservesItAcrossSaveReload(string configured, string expected)
    {
        var localization = new LocalizationService();
        var vm = CreateViewModel(new FakeAutoStartManager(), localization);
        var path = Path.Combine(Path.GetTempPath(), $"ifw-language-{Guid.NewGuid():N}.yaml");
        try
        {
            var source = new AppConfig { Localization = new LocalizationSettings { Language = configured } };
            var original = new AppConfigWriter().Serialize(source);
            File.WriteAllText(path, original);

            vm.Load(new AppConfigLoader().LoadForEditing(path));

            Assert.Equal(expected, localization.CurrentLanguage);
            Assert.Equal(expected, vm.SelectedLanguage.Code);
            Assert.Equal(original, File.ReadAllText(path));
            Assert.True(vm.TryCreateConfig(out var saved, out var errors), string.Join(Environment.NewLine, errors));
            File.WriteAllText(path, new AppConfigWriter().Serialize(saved));
            var reloaded = new AppConfigLoader().LoadForEditing(path);
            Assert.Equal(expected, reloaded.Localization.Language);
            vm.Load(reloaded);
            Assert.Equal(expected, vm.SelectedLanguage.Code);
        }
        finally
        {
            File.Delete(path);
            localization.SetLanguage(LocalizationService.LanguageEnglish);
        }
    }

    [Fact]
    public void TryCreateConfig_PreservesLanguageSelectedAfterLoading()
    {
        var localization = new LocalizationService();
        var vm = CreateViewModel(new FakeAutoStartManager(), localization);
        try
        {
            vm.Load(new AppConfig { Localization = new LocalizationSettings { Language = "en" } });
            vm.SelectedLanguage = vm.AvailableLanguages.Single(language => language.Code == "de");

            Assert.True(vm.TryCreateConfig(out var saved, out _));
            Assert.Equal("de", saved.Localization.Language);
            Assert.Equal("de", localization.CurrentLanguage);
        }
        finally
        {
            localization.SetLanguage(LocalizationService.LanguageEnglish);
        }
    }

    [Fact]
    public async Task SetAutostartAsync_DeniedRequest_RestoresPlatformFlagAndReportsFailure()
    {
        await SingleThreadUiContext.RunAsync(async dispatcher =>
        {
            var manager = new FakeAutoStartManager { EnableException = new InvalidOperationException("Permission denied") };
            var vm = CreateViewModel(manager, dispatcher: dispatcher);

            Assert.False(await vm.SetAutostartAsync(true));

            Assert.False(vm.AutostartEnabled);
            Assert.False(vm.IsAutostartChangeInProgress);
            Assert.Contains("Permission denied", vm.OperationMessage);
            Assert.Equal(new[] { "enable" }, manager.Changes);
        });
    }

    [Fact]
    public async Task AutostartSetter_PendingPermissionRequest_DoesNotBlockTheCaller()
    {
        await SingleThreadUiContext.RunAsync(async dispatcher =>
        {
            var completion = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
            var manager = new FakeAutoStartManager { EnableCompletion = completion.Task };
            var vm = CreateViewModel(manager, dispatcher: dispatcher);
            var finished = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
            vm.PropertyChanged += (_, args) =>
            {
                if (args.PropertyName == nameof(vm.IsAutostartChangeInProgress) && !vm.IsAutostartChangeInProgress)
                {
                    finished.TrySetResult();
                }
            };

            vm.AutostartEnabled = true;

            Assert.True(vm.IsAutostartChangeInProgress);
            Assert.False(manager.Enabled);
            completion.SetResult();
            await finished.Task.WaitAsync(TimeSpan.FromSeconds(5));
            Assert.True(vm.AutostartEnabled);
            Assert.True(manager.Enabled);
        });
    }

    [Fact]
    public async Task SetAutostartAsync_ConcurrentChanges_RunInOrderWithoutOverlappingPlatformRequests()
    {
        await SingleThreadUiContext.RunAsync(async dispatcher =>
        {
            var completion = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
            var manager = new FakeAutoStartManager { EnableCompletion = completion.Task };
            var vm = CreateViewModel(manager, dispatcher: dispatcher);

            var enable = vm.SetAutostartAsync(true);
            var disable = vm.SetAutostartAsync(false);

            Assert.True(vm.IsAutostartChangeInProgress);
            Assert.False(enable.IsCompleted);
            Assert.False(disable.IsCompleted);
            Assert.Equal(new[] { "enable" }, manager.Changes);
            completion.SetResult();
            Assert.True(await enable.WaitAsync(TimeSpan.FromSeconds(5)));
            Assert.True(await disable.WaitAsync(TimeSpan.FromSeconds(5)));
            Assert.Equal(new[] { "enable", "disable" }, manager.Changes);
            Assert.False(manager.Enabled);
            Assert.False(vm.AutostartEnabled);
            Assert.False(vm.IsAutostartChangeInProgress);
        });
    }

    [Fact]
    public async Task RefreshAutostartFromDiskAsync_RefreshesExternalChangesWithoutWritingThem()
    {
        await SingleThreadUiContext.RunAsync(async dispatcher =>
        {
            var manager = new FakeAutoStartManager();
            var vm = CreateViewModel(manager, dispatcher: dispatcher);
            manager.Enabled = true;

            await vm.RefreshAutostartFromDiskAsync();

            Assert.True(vm.AutostartEnabled);
            Assert.Empty(manager.Changes);
        });
    }

    [Fact]
    public async Task InitializeAutostartAsync_DisablesToggleAndSerializesLaterChanges()
    {
        await SingleThreadUiContext.RunAsync(async dispatcher =>
        {
            var completion = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
            var manager = new FakeAutoStartManager();
            var vm = CreateViewModel(manager, dispatcher: dispatcher);

            var initialize = vm.InitializeAutostartAsync(async _ =>
            {
                manager.Changes.Add("initialize");
                await completion.Task;
                manager.Enabled = true;
            });
            var disable = vm.SetAutostartAsync(false);

            Assert.True(vm.IsAutostartChangeInProgress);
            Assert.False(initialize.IsCompleted);
            Assert.False(disable.IsCompleted);
            Assert.Equal(new[] { "initialize" }, manager.Changes);
            completion.SetResult();
            await initialize.WaitAsync(TimeSpan.FromSeconds(5));
            Assert.True(await disable.WaitAsync(TimeSpan.FromSeconds(5)));
            Assert.Equal(new[] { "initialize", "disable" }, manager.Changes);
            Assert.False(vm.AutostartEnabled);
            Assert.False(vm.IsAutostartChangeInProgress);
        });
    }

    [Fact]
    public async Task InitializeAutostartAsync_CancelledDuringSetup_ReleasesGateAndClearsBusyFlag()
    {
        await SingleThreadUiContext.RunAsync(async dispatcher =>
        {
            var manager = new FakeAutoStartManager();
            var vm = CreateViewModel(manager, dispatcher: dispatcher);
            using var cancellation = new CancellationTokenSource();
            var initialize = vm.InitializeAutostartAsync(token => Task.Delay(Timeout.InfiniteTimeSpan, token), cancellation.Token);
            Assert.True(vm.IsAutostartChangeInProgress);

            cancellation.Cancel();

            await Assert.ThrowsAnyAsync<OperationCanceledException>(() => initialize);
            Assert.False(vm.IsAutostartChangeInProgress);
            Assert.True(await vm.SetAutostartAsync(true).WaitAsync(TimeSpan.FromSeconds(5)));
            Assert.True(vm.AutostartEnabled);
        });
    }

    [Fact]
    public async Task InitializeAutostartAsync_CancelledWhileQueued_DoesNotReleaseActiveOperationGate()
    {
        await SingleThreadUiContext.RunAsync(async dispatcher =>
        {
            var completion = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
            var manager = new FakeAutoStartManager { EnableCompletion = completion.Task };
            var vm = CreateViewModel(manager, dispatcher: dispatcher);
            var enable = vm.SetAutostartAsync(true);
            using var cancellation = new CancellationTokenSource();
            var initialized = false;
            var initialize = vm.InitializeAutostartAsync(_ =>
            {
                initialized = true;
                return Task.CompletedTask;
            }, cancellation.Token);

            cancellation.Cancel();

            await Assert.ThrowsAnyAsync<OperationCanceledException>(() => initialize);
            Assert.False(initialized);
            Assert.True(vm.IsAutostartChangeInProgress);
            var disable = vm.SetAutostartAsync(false);
            Assert.False(disable.IsCompleted);
            completion.SetResult();
            Assert.True(await enable.WaitAsync(TimeSpan.FromSeconds(5)));
            Assert.True(await disable.WaitAsync(TimeSpan.FromSeconds(5)));
            Assert.False(vm.IsAutostartChangeInProgress);
            Assert.False(vm.AutostartEnabled);
        });
    }

    [Fact]
    public async Task UiContext_KeepsAwaitContinuationsAndPostedCallbacksOnItsThread()
    {
        await SingleThreadUiContext.RunAsync(async dispatcher =>
        {
            var uiThreadId = Environment.CurrentManagedThreadId;
            await Task.Yield();
            Assert.Equal(uiThreadId, Environment.CurrentManagedThreadId);
            var posted = new TaskCompletionSource(TaskCreationOptions.RunContinuationsAsynchronously);
            await Task.Run(() =>
            {
                Assert.False(dispatcher.IsOnUiThread);
                dispatcher.Post(() =>
                {
                    Assert.True(dispatcher.IsOnUiThread);
                    Assert.Equal(uiThreadId, Environment.CurrentManagedThreadId);
                    posted.SetResult();
                });
            });
            await posted.Task.WaitAsync(TimeSpan.FromSeconds(5));
            Assert.Equal(uiThreadId, Environment.CurrentManagedThreadId);
        });
    }

    [Fact]
    public async Task UiContext_PropagatesAnAsyncFailureAfterStoppingItsPump()
    {
        var expected = new InvalidOperationException("Expected UI test failure.");
        var actual = await Assert.ThrowsAsync<InvalidOperationException>(() =>
            SingleThreadUiContext.RunAsync(async _ =>
            {
                await Task.Yield();
                throw expected;
            }));
        Assert.Same(expected, actual);
    }

    private static MainWindowViewModel CreateViewModel(IAutoStartManager manager, LocalizationService? localization = null,
        IPlatformPaths? platformPaths = null, IUiDispatcher? dispatcher = null)
    {
        localization ??= new LocalizationService();
        localization.SetLanguage(LocalizationService.LanguageEnglish);
        dispatcher ??= new InlineUiDispatcher();
        var vm = new MainWindowViewModel(new SyncStatusProvider(), manager, localization,
            dispatcher, new LinuxLoggingCapabilities(), platformPaths);
        vm.PropertyChanged += (_, _) => Assert.True(dispatcher.IsOnUiThread);
        return vm;
    }

    private sealed class TestPlatformPaths : IPlatformPaths
    {
        private readonly string _root = Path.Combine(Path.GetTempPath(), $"ifw-platform-{Guid.NewGuid():N}");
        public string ProductFolderName => "immich-folder-watch";
        public string GetUserDataRoot() => Path.Combine(_root, "data", ProductFolderName);
        public string GetConfigPath() => Path.Combine(_root, "config", ProductFolderName, "config.yaml");
        public string GetSyncDatabasePath() => Path.Combine(GetUserDataRoot(), "sync-state.db");
        public string GetLogDirectory() => Path.Combine(_root, "state", ProductFolderName, "logs");
    }

    private sealed class FakeAutoStartManager : IAutoStartManager
    {
        private readonly int _threadId = Environment.CurrentManagedThreadId;
        private bool _enabled;
        public bool Enabled
        {
            get { Assert.Equal(_threadId, Environment.CurrentManagedThreadId); return _enabled; }
            set { Assert.Equal(_threadId, Environment.CurrentManagedThreadId); _enabled = value; }
        }
        public Task EnableCompletion { get; init; } = Task.CompletedTask;
        public Exception? EnableException { get; init; }
        public List<string> Changes { get; } = [];

        public Task<bool> IsEnabledAsync(CancellationToken cancellationToken = default) => Task.FromResult(Enabled);

        public async Task EnableAsync(CancellationToken cancellationToken = default)
        {
            Assert.Equal(_threadId, Environment.CurrentManagedThreadId);
            Changes.Add("enable");
            await EnableCompletion;
            Assert.Equal(_threadId, Environment.CurrentManagedThreadId);
            if (EnableException is not null)
            {
                throw EnableException;
            }
            Enabled = true;
        }

        public Task DisableAsync(CancellationToken cancellationToken = default)
        {
            Assert.Equal(_threadId, Environment.CurrentManagedThreadId);
            Changes.Add("disable");
            Enabled = false;
            return Task.CompletedTask;
        }
    }

    private sealed class InlineUiDispatcher : IUiDispatcher
    {
        private readonly int _threadId = Environment.CurrentManagedThreadId;
        public bool IsOnUiThread => Environment.CurrentManagedThreadId == _threadId;
        public void Post(Action action)
        {
            Assert.True(IsOnUiThread);
            action();
        }
    }
}
