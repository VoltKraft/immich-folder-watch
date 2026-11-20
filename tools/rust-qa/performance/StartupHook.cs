using System;
using System.Diagnostics.Metrics;
using System.Globalization;
using System.IO;
using Microsoft.Win32.SafeHandles;

// Loaded only in the separate, instrumented Avalonia reference process.
internal static class StartupHook
{
    private static readonly MeterListener Listener = new();
    private static FileStream counter;

    public static void Initialize()
    {
        var fd = int.Parse(Environment.GetEnvironmentVariable("IFW_QA_RENDER_FD"), CultureInfo.InvariantCulture);
        counter = new FileStream(new SafeFileHandle((IntPtr)fd, ownsHandle: false), FileAccess.Write, bufferSize: 1);
        AppContext.SetSwitch("Avalonia.Diagnostics.Diagnostic.IsEnabled", true);
        Listener.InstrumentPublished = (instrument, listener) =>
        {
            if (instrument.Meter.Name == "Avalonia.Diagnostic.Meter" && instrument.Name == "avalonia.comp.render.time")
            {
                listener.EnableMeasurementEvents(instrument);
                Emit((byte)'R');
            }
        };
        Listener.SetMeasurementEventCallback<double>((instrument, measurement, tags, state) => Emit((byte)'F'));
        Listener.Start();
    }

    private static void Emit(byte value)
    {
        lock (counter)
        {
            counter.WriteByte(value);
        }
    }
}
