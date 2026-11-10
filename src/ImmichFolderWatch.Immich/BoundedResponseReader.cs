using System.Text;

namespace ImmichFolderWatch.Immich;

internal static class BoundedResponseReader
{
    public static async Task<string> ReadAsync(
        HttpContent content,
        int maximumBytes,
        bool truncate,
        TimeSpan inactivityTimeout,
        CancellationToken cancellationToken)
    {
        if (!truncate && content.Headers.ContentLength > maximumBytes)
        {
            throw new HttpRequestException("Immich response exceeds the metadata size limit.");
        }

        using var overall = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
        overall.CancelAfter(TimeSpan.FromMinutes(5));
        using var deadline = CancellationTokenSource.CreateLinkedTokenSource(overall.Token);
        deadline.CancelAfter(inactivityTimeout);
        await using var input = await content.ReadAsStreamAsync(deadline.Token);
        using var output = new MemoryStream();
        var buffer = new byte[Math.Min(8192, maximumBytes)];
        while (output.Length < maximumBytes)
        {
            deadline.CancelAfter(inactivityTimeout);
            var count = await input.ReadAsync(buffer.AsMemory(0, (int)Math.Min(buffer.Length, maximumBytes - output.Length)), deadline.Token);
            if (count == 0)
            {
                return Decode(content, output);
            }

            output.Write(buffer, 0, count);
        }

        // A diagnostic is only a prefix. Metadata must be complete before parsing it.
        if (!truncate)
        {
            deadline.CancelAfter(inactivityTimeout);
            if (await input.ReadAsync(buffer.AsMemory(0, 1), deadline.Token) != 0)
            {
                throw new HttpRequestException("Immich response exceeds the metadata size limit.");
            }
        }

        return Decode(content, output);
    }

    private static string Decode(HttpContent content, MemoryStream stream)
    {
        var charset = content.Headers.ContentType?.CharSet?.Trim('"');
        var encoding = string.IsNullOrWhiteSpace(charset) ? Encoding.UTF8 : Encoding.GetEncoding(charset);
        return encoding.GetString(stream.GetBuffer(), 0, checked((int)stream.Length)).TrimStart('\uFEFF');
    }
}
