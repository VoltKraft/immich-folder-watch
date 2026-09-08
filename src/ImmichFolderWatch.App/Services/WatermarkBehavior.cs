using System.Windows;
using System.Windows.Controls;
using PasswordBox = System.Windows.Controls.PasswordBox;
using TextBox = System.Windows.Controls.TextBox;

namespace ImmichFolderWatch.App.Services;

/// <summary>
/// Supplies placeholder text and empty-input state to the text/password control templates.
/// Placeholders belong inside the templates so ancestor visibility and scroll clipping apply.
/// </summary>
public static class WatermarkBehavior
{
    public static readonly DependencyProperty WatermarkProperty = DependencyProperty.RegisterAttached(
        "Watermark",
        typeof(string),
        typeof(WatermarkBehavior),
        new PropertyMetadata(string.Empty, OnWatermarkChanged));

    private static readonly DependencyPropertyKey ShowWatermarkPropertyKey = DependencyProperty.RegisterAttachedReadOnly(
        "ShowWatermark",
        typeof(bool),
        typeof(WatermarkBehavior),
        new PropertyMetadata(false));

    public static readonly DependencyProperty ShowWatermarkProperty = ShowWatermarkPropertyKey.DependencyProperty;

    public static string GetWatermark(DependencyObject obj) => (string)obj.GetValue(WatermarkProperty);

    public static void SetWatermark(DependencyObject obj, string value) => obj.SetValue(WatermarkProperty, value);

    public static bool GetShowWatermark(DependencyObject obj) => (bool)obj.GetValue(ShowWatermarkProperty);

    private static void OnWatermarkChanged(DependencyObject sender, DependencyPropertyChangedEventArgs e)
    {
        var hasWatermark = !string.IsNullOrEmpty(GetWatermark(sender));
        switch (sender)
        {
            case TextBox textBox:
                textBox.TextChanged -= OnTextChanged;
                if (hasWatermark)
                {
                    textBox.TextChanged += OnTextChanged;
                }
                UpdateShowWatermark(textBox);
                break;
            case PasswordBox passwordBox:
                passwordBox.PasswordChanged -= OnPasswordChanged;
                if (hasWatermark)
                {
                    passwordBox.PasswordChanged += OnPasswordChanged;
                }
                UpdateShowWatermark(passwordBox);
                break;
        }
    }

    private static void OnTextChanged(object sender, TextChangedEventArgs e) => UpdateShowWatermark((TextBox)sender);

    private static void OnPasswordChanged(object sender, RoutedEventArgs e) => UpdateShowWatermark((PasswordBox)sender);

    private static void UpdateShowWatermark(TextBox textBox) =>
        textBox.SetValue(ShowWatermarkPropertyKey,
            !string.IsNullOrEmpty(GetWatermark(textBox)) && string.IsNullOrEmpty(textBox.Text));

    private static void UpdateShowWatermark(PasswordBox passwordBox)
    {
        using var password = passwordBox.SecurePassword;
        passwordBox.SetValue(ShowWatermarkPropertyKey,
            !string.IsNullOrEmpty(GetWatermark(passwordBox)) && password.Length == 0);
    }
}
