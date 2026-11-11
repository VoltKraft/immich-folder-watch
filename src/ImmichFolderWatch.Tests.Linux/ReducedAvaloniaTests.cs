using Avalonia.Controls;
using Xunit;

namespace ImmichFolderWatch.Tests.Linux;

public sealed class ReducedAvaloniaTests
{
    [Theory]
    [InlineData("Avalonia.Controls.Calendar")]
    [InlineData("Avalonia.Controls.CalendarDatePicker")]
    [InlineData("Avalonia.Controls.AutoCompleteBox")]
    [InlineData("Avalonia.Controls.LayoutTransformControl")]
    [InlineData("Avalonia.Controls.Primitives.CalendarItem")]
    public void LoadedControlsAssembly_ExcludesIncompatibleImplementations(string typeName)
    {
        // Check the assembly actually loaded by the application tests. Package
        // metadata alone cannot detect an upstream binary restored from cache.
        Assert.Null(typeof(Control).Assembly.GetType(typeName, throwOnError: false));
    }
}
