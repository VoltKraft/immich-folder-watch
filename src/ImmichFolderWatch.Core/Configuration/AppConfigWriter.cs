using YamlDotNet.Serialization;
using YamlDotNet.Serialization.NamingConventions;

namespace ImmichFolderWatch.Core.Configuration;

public sealed class AppConfigWriter
{
    public string Serialize(AppConfig config)
    {
        ArgumentNullException.ThrowIfNull(config);

        var serializer = new SerializerBuilder()
            .WithNamingConvention(CamelCaseNamingConvention.Instance)
            .Build();

        var yaml = serializer.Serialize(config);
        return yaml.EndsWith(Environment.NewLine, StringComparison.Ordinal)
            ? yaml
            : $"{yaml}{Environment.NewLine}";
    }
}
