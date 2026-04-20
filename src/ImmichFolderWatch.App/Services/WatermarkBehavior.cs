using System.Windows;
using System.Windows.Controls;
using System.Windows.Documents;
using System.Windows.Media;
using Control = System.Windows.Controls.Control;
using Size = System.Windows.Size;
using Point = System.Windows.Point;
using Brush = System.Windows.Media.Brush;
using Brushes = System.Windows.Media.Brushes;
using TextBox = System.Windows.Controls.TextBox;
using HorizontalAlignment = System.Windows.HorizontalAlignment;
using VerticalAlignment = System.Windows.VerticalAlignment;

namespace ImmichFolderWatch.App.Services;

public static class WatermarkBehavior
{
    public static readonly DependencyProperty WatermarkProperty = DependencyProperty.RegisterAttached(
        "Watermark",
        typeof(string),
        typeof(WatermarkBehavior),
        new PropertyMetadata(string.Empty, OnWatermarkChanged));

    public static string GetWatermark(DependencyObject obj)
    {
        return (string)obj.GetValue(WatermarkProperty);
    }

    public static void SetWatermark(DependencyObject obj, string value)
    {
        obj.SetValue(WatermarkProperty, value);
    }

    private static void OnWatermarkChanged(DependencyObject d, DependencyPropertyChangedEventArgs e)
    {
        switch (d)
        {
            case TextBox textBox:
                textBox.Loaded -= OnTextBoxLoaded;
                textBox.GotFocus -= OnTextBoxFocusChanged;
                textBox.LostFocus -= OnTextBoxFocusChanged;
                textBox.TextChanged -= OnTextBoxTextChanged;
                textBox.Loaded += OnTextBoxLoaded;
                textBox.GotFocus += OnTextBoxFocusChanged;
                textBox.LostFocus += OnTextBoxFocusChanged;
                textBox.TextChanged += OnTextBoxTextChanged;
                if (textBox.IsLoaded)
                {
                    UpdateAdornerFor(textBox);
                }
                break;
            case PasswordBox passwordBox:
                passwordBox.Loaded -= OnPasswordBoxLoaded;
                passwordBox.GotFocus -= OnPasswordBoxFocusChanged;
                passwordBox.LostFocus -= OnPasswordBoxFocusChanged;
                passwordBox.PasswordChanged -= OnPasswordBoxPasswordChanged;
                passwordBox.Loaded += OnPasswordBoxLoaded;
                passwordBox.GotFocus += OnPasswordBoxFocusChanged;
                passwordBox.LostFocus += OnPasswordBoxFocusChanged;
                passwordBox.PasswordChanged += OnPasswordBoxPasswordChanged;
                if (passwordBox.IsLoaded)
                {
                    UpdateAdornerFor(passwordBox);
                }
                break;
        }
    }

    private static void OnTextBoxLoaded(object sender, RoutedEventArgs e) => UpdateAdornerFor((Control)sender);

    private static void OnTextBoxFocusChanged(object sender, RoutedEventArgs e) => UpdateAdornerFor((Control)sender);

    private static void OnTextBoxTextChanged(object sender, TextChangedEventArgs e) => UpdateAdornerFor((Control)sender);

    private static void OnPasswordBoxLoaded(object sender, RoutedEventArgs e) => UpdateAdornerFor((Control)sender);

    private static void OnPasswordBoxFocusChanged(object sender, RoutedEventArgs e) => UpdateAdornerFor((Control)sender);

    private static void OnPasswordBoxPasswordChanged(object sender, RoutedEventArgs e) => UpdateAdornerFor((Control)sender);

    private static void UpdateAdornerFor(Control control)
    {
        var layer = AdornerLayer.GetAdornerLayer(control);
        if (layer is null)
        {
            return;
        }

        var existing = layer.GetAdorners(control);
        if (existing is not null)
        {
            foreach (var adorner in existing)
            {
                if (adorner is WatermarkAdorner)
                {
                    layer.Remove(adorner);
                }
            }
        }

        if (ShouldShowWatermark(control))
        {
            var watermark = GetWatermark(control);
            if (!string.IsNullOrEmpty(watermark))
            {
                layer.Add(new WatermarkAdorner(control, watermark));
            }
        }
    }

    private static bool ShouldShowWatermark(Control control)
    {
        return control switch
        {
            TextBox textBox => string.IsNullOrEmpty(textBox.Text),
            PasswordBox passwordBox => string.IsNullOrEmpty(passwordBox.Password),
            _ => false,
        };
    }

    private sealed class WatermarkAdorner : Adorner
    {
        private readonly TextBlock _textBlock;

        public WatermarkAdorner(UIElement adornedElement, string text)
            : base(adornedElement)
        {
            IsHitTestVisible = false;
            _textBlock = new TextBlock
            {
                Text = text,
                Foreground = TryResolveBrush(adornedElement, "AppSecondaryText") ?? Brushes.Gray,
                VerticalAlignment = VerticalAlignment.Center,
                HorizontalAlignment = HorizontalAlignment.Left,
                Padding = new Thickness(12, 0, 8, 0),
                IsHitTestVisible = false,
            };
        }

        protected override int VisualChildrenCount => 1;

        protected override Visual GetVisualChild(int index) => _textBlock;

        protected override Size MeasureOverride(Size constraint)
        {
            _textBlock.Measure(constraint);
            return ((FrameworkElement)AdornedElement).RenderSize;
        }

        protected override Size ArrangeOverride(Size finalSize)
        {
            _textBlock.Arrange(new Rect(new Point(0, 0), finalSize));
            return finalSize;
        }

        private static Brush? TryResolveBrush(DependencyObject context, string resourceKey)
        {
            if (context is FrameworkElement fe && fe.TryFindResource(resourceKey) is Brush feBrush)
            {
                return feBrush;
            }

            if (Application.Current?.TryFindResource(resourceKey) is Brush appBrush)
            {
                return appBrush;
            }

            return null;
        }
    }
}
