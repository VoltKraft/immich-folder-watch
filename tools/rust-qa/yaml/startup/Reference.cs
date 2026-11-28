using System;
using System.Globalization;
using System.IO;
using System.Text.Json;
using ImmichFolderWatch.App.Shared.Services;
using ImmichFolderWatch.Core.Configuration;
using ImmichFolderWatch.Core.Platform;

// The caller supplies an isolated HOME and XDG_CONFIG_HOME for each new process.
var path = new XdgPlatformPaths().GetConfigPath();
var system = CultureInfo.CurrentUICulture.Name;
string preference = "auto";
string read = "missing";
if (File.Exists(path))
{
    try
    {
        preference = new AppConfigLoader().LoadForEditing(path).Localization.Language;
        read = "loaded";
    }
    catch
    {
        read = "failed";
    }
}
var localization = LocalizationService.Instance;
localization.SetLanguage(preference);
var setting = localization.CurrentLanguage;
var language = localization.CurrentCulture.TwoLetterISOLanguageName;
localization.SetLanguage(language == "de" ? "en" : "de");
localization.SetLanguage("auto");
Console.WriteLine(JsonSerializer.Serialize(new { path, system, read, setting, language,
    systemLanguage = localization.CurrentCulture.TwoLetterISOLanguageName }));
