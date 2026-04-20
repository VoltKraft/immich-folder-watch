using System.Windows;
using System.Windows.Controls;

namespace ImmichFolderWatch.App.Services;

public static class PasswordBoxHelper
{
    public static readonly DependencyProperty BindablePasswordProperty = DependencyProperty.RegisterAttached(
        "BindablePassword",
        typeof(string),
        typeof(PasswordBoxHelper),
        new FrameworkPropertyMetadata(string.Empty, FrameworkPropertyMetadataOptions.BindsTwoWayByDefault, OnBindablePasswordChanged));

    private static readonly DependencyProperty SuppressUpdateProperty = DependencyProperty.RegisterAttached(
        "SuppressUpdate",
        typeof(bool),
        typeof(PasswordBoxHelper),
        new PropertyMetadata(false));

    private static readonly DependencyProperty HandlerAttachedProperty = DependencyProperty.RegisterAttached(
        "HandlerAttached",
        typeof(bool),
        typeof(PasswordBoxHelper),
        new PropertyMetadata(false));

    public static string GetBindablePassword(DependencyObject obj)
    {
        return (string)obj.GetValue(BindablePasswordProperty);
    }

    public static void SetBindablePassword(DependencyObject obj, string value)
    {
        obj.SetValue(BindablePasswordProperty, value);
    }

    private static void OnBindablePasswordChanged(DependencyObject d, DependencyPropertyChangedEventArgs e)
    {
        if (d is not PasswordBox passwordBox)
        {
            return;
        }

        if (!(bool)passwordBox.GetValue(HandlerAttachedProperty))
        {
            passwordBox.PasswordChanged += OnPasswordChanged;
            passwordBox.SetValue(HandlerAttachedProperty, true);
        }

        if ((bool)passwordBox.GetValue(SuppressUpdateProperty))
        {
            return;
        }

        var newPassword = e.NewValue as string ?? string.Empty;
        if (!string.Equals(passwordBox.Password, newPassword))
        {
            passwordBox.Password = newPassword;
        }
    }

    private static void OnPasswordChanged(object sender, RoutedEventArgs e)
    {
        if (sender is not PasswordBox passwordBox)
        {
            return;
        }

        passwordBox.SetValue(SuppressUpdateProperty, true);
        try
        {
            SetBindablePassword(passwordBox, passwordBox.Password);
        }
        finally
        {
            passwordBox.SetValue(SuppressUpdateProperty, false);
        }
    }
}
