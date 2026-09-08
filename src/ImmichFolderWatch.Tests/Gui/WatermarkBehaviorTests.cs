using System.Runtime.ExceptionServices;
using System.Windows;
using System.Windows.Controls;
using System.Windows.Documents;
using System.Windows.Media;
using System.Windows.Media.Imaging;
using System.Windows.Threading;
using ImmichFolderWatch.App.Services;

namespace ImmichFolderWatch.Tests.Gui;

public sealed class WatermarkBehaviorTests
{
    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void Watermark_TracksEmptyInputAndChangedHint(bool passwordInput)
    {
        RunOnStaThread(() =>
        {
            var control = CreateInput(passwordInput);
            var surface = new TestSurface(control);
            var withoutHint = surface.Render();
            SetHint(control, "Enter a value");
            var emptyWithHint = surface.Render();
            Assert.False(withoutHint.AsSpan().SequenceEqual(emptyWithHint));

            SetInput(control, "example");
            var filledWithHint = surface.Render();
            SetHint(control, string.Empty);
            Assert.Equal(filledWithHint, surface.Render());

            SetInput(control, string.Empty);
            SetHint(control, "Updated hint");
            var updatedHint = surface.Render();
            Assert.False(withoutHint.AsSpan().SequenceEqual(updatedHint));
            Assert.False(emptyWithHint.AsSpan().SequenceEqual(updatedHint));

            SetHint(control, string.Empty);
            Assert.Equal(withoutHint, surface.Render());
        });
    }

    [Theory]
    [InlineData(false, false)]
    [InlineData(false, true)]
    [InlineData(true, false)]
    [InlineData(true, true)]
    public void Watermark_IsNotRendered_WhenInputOrExpanderIsCollapsed(bool passwordInput, bool collapseExpander)
    {
        RunOnStaThread(() =>
        {
            var control = CreateInput(passwordInput);
            var expander = new Expander { Header = "Advanced options", Content = control, IsExpanded = true };
            var surface = new TestSurface(expander);
            SetHint(control, "This hint must stay inside its input");
            surface.Render();

            if (collapseExpander)
            {
                expander.IsExpanded = false;
            }
            else
            {
                control.Visibility = Visibility.Collapsed;
            }

            var hiddenWithHint = surface.Render();
            SetHint(control, string.Empty);
            Assert.Equal(hiddenWithHint, surface.Render());
        });
    }

    [Theory]
    [InlineData(false)]
    [InlineData(true)]
    public void Watermark_IsClipped_WhenInputScrollsOutsideViewport(bool passwordInput)
    {
        RunOnStaThread(() =>
        {
            var control = CreateInput(passwordInput);
            var surface = new TestSurface(control);
            SetHint(control, "This hint must not cover the header");
            surface.Render();
            surface.ScrollViewer.ScrollToVerticalOffset(170);
            var scrolledWithHint = surface.Render();
            Assert.True(surface.ScrollViewer.VerticalOffset >= 170);

            SetHint(control, string.Empty);
            Assert.Equal(scrolledWithHint, surface.Render());
        });
    }

    [Fact]
    public void Watermark_DoesNotLeaveAdorners_AfterRepeatedVisibilityAndTextChanges()
    {
        RunOnStaThread(() =>
        {
            var control = CreateInput(false);
            var expander = new Expander { Header = "Advanced options", Content = control, IsExpanded = true };
            var surface = new TestSurface(expander);
            for (var index = 0; index < 5; index++)
            {
                SetHint(control, "Hint " + index);
                SetInput(control, "value");
                surface.Render();
                SetInput(control, string.Empty);
                expander.IsExpanded = false;
                surface.Render();
                expander.IsExpanded = true;
                surface.Render();
            }

            Assert.Empty(surface.AdornerDecorator.AdornerLayer.GetAdorners(control) ?? []);
        });
    }

    private static Control CreateInput(bool passwordInput)
    {
        Control control = passwordInput ? new PasswordBox() : new TextBox();
        control.Height = 50;
        control.Width = 340;
        control.HorizontalAlignment = HorizontalAlignment.Left;
        return control;
    }

    private static void SetInput(Control control, string value)
    {
        if (control is TextBox textBox)
        {
            textBox.Text = value;
        }
        else
        {
            ((PasswordBox)control).Password = value;
        }
    }

    private static void SetHint(Control control, string value)
    {
        WatermarkBehavior.SetWatermark(control, value);
        // This offscreen surface does not create a native window. Deliver the
        // normal load notification so implementations that initialize on load
        // participate in the same rendering regression checks.
        control.RaiseEvent(new RoutedEventArgs(FrameworkElement.LoadedEvent, control));
    }

    private static void RunOnStaThread(Action action)
    {
        ExceptionDispatchInfo? failure = null;
        var thread = new Thread(() =>
        {
            try
            {
                action();
            }
            catch (Exception exception)
            {
                failure = ExceptionDispatchInfo.Capture(exception);
            }
            finally
            {
                Dispatcher.CurrentDispatcher.InvokeShutdown();
            }
        }) { IsBackground = true };
        thread.SetApartmentState(ApartmentState.STA);
        thread.Start();
        Assert.True(thread.Join(TimeSpan.FromSeconds(30)), "The WPF rendering check timed out.");
        failure?.Throw();
    }

    private sealed class TestSurface
    {
        public TestSurface(UIElement input)
        {
            var content = new StackPanel();
            content.Children.Add(new Border { Height = 100 });
            content.Children.Add(input);
            content.Children.Add(new Border { Height = 400 });
            ScrollViewer = new ScrollViewer
            {
                Content = content,
                VerticalScrollBarVisibility = ScrollBarVisibility.Hidden,
                HorizontalScrollBarVisibility = ScrollBarVisibility.Disabled,
            };
            var grid = new Grid { Background = Brushes.White };
            foreach (var filename in new[] { "PaletteDark.xaml", "Styles.xaml" })
            {
                grid.Resources.MergedDictionaries.Add(new ResourceDictionary
                {
                    Source = new Uri($"pack://application:,,,/ImmichFolderWatch;component/Styles/{filename}"),
                });
            }
            grid.RowDefinitions.Add(new RowDefinition { Height = new GridLength(60) });
            grid.RowDefinitions.Add(new RowDefinition());
            grid.Children.Add(new Border { Background = Brushes.LightBlue });
            Grid.SetRow(ScrollViewer, 1);
            grid.Children.Add(ScrollViewer);
            AdornerDecorator = new AdornerDecorator { Child = grid };
            Render();
        }

        public AdornerDecorator AdornerDecorator { get; }

        public ScrollViewer ScrollViewer { get; }

        public byte[] Render()
        {
            AdornerDecorator.Measure(new Size(400, 260));
            AdornerDecorator.Arrange(new Rect(0, 0, 400, 260));
            AdornerDecorator.UpdateLayout();
            Dispatcher.CurrentDispatcher.Invoke(() => { }, DispatcherPriority.ApplicationIdle);
            AdornerDecorator.UpdateLayout();
            var bitmap = new RenderTargetBitmap(400, 260, 96, 96, PixelFormats.Pbgra32);
            bitmap.Render(AdornerDecorator);
            var pixels = new byte[400 * 260 * 4];
            bitmap.CopyPixels(pixels, 400 * 4, 0);
            return pixels;
        }
    }
}
