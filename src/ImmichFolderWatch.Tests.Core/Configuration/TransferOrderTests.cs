using ImmichFolderWatch.Core.Configuration;

namespace ImmichFolderWatch.Tests.Core.Configuration;

public sealed class TransferOrderTests
{
    [Theory]
    [InlineData(null, TransferOrders.NewestFirst)]
    [InlineData("", TransferOrders.NewestFirst)]
    [InlineData("unknown", TransferOrders.NewestFirst)]
    [InlineData(" NEWESTFIRST ", TransferOrders.NewestFirst)]
    [InlineData(" OLDESTFIRST ", TransferOrders.OldestFirst)]
    public void NormalizeForRuntime_NormalizesTransferOrder(string? input, string expected)
    {
        var config = new AppConfig();
        config.Watch.TransferOrder = input!;

        var normalized = AppConfigLoader.NormalizeForRuntime(config, Path.GetTempPath());

        Assert.Equal(expected, normalized.Watch.TransferOrder);
        Assert.Equal(input, config.Watch.TransferOrder);
    }

    [Theory]
    [InlineData(TransferOrders.NewestFirst)]
    [InlineData(TransferOrders.OldestFirst)]
    public void Serialize_PreservesTransferOrderThroughEditingAndRuntimeLoad(string order)
    {
        var config = new AppConfig();
        config.Watch.TransferOrder = order;
        var directory = Directory.CreateTempSubdirectory("ifw-config-order-");
        try
        {
            var path = Path.Combine(directory.FullName, "config.yaml");
            File.WriteAllText(path, new AppConfigWriter().Serialize(config));

            Assert.Equal(order, new AppConfigLoader().LoadForEditing(path).Watch.TransferOrder);
            Assert.Equal(order, new AppConfigLoader().Load(path).Watch.TransferOrder);
        }
        finally
        {
            directory.Delete(recursive: true);
        }
    }

    [Fact]
    public void Load_LegacyConfigDefaultsToNewestFirst()
    {
        var directory = Directory.CreateTempSubdirectory("ifw-config-order-");
        try
        {
            var path = Path.Combine(directory.FullName, "config.yaml");
            File.WriteAllText(path, "watch: {}\n");

            Assert.Equal(TransferOrders.NewestFirst, new AppConfigLoader().Load(path).Watch.TransferOrder);
            Assert.Equal(TransferOrders.NewestFirst, new WatchSettings().TransferOrder);
        }
        finally
        {
            directory.Delete(recursive: true);
        }
    }
}
