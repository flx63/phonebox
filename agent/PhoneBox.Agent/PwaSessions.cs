using System.Security.Cryptography;
using System.Text.Json;

namespace PhoneBox.Agent;

internal sealed class PwaSessions
{
    private static readonly TimeSpan PairLifetime = TimeSpan.FromMinutes(5);
    internal static readonly TimeSpan SessionLifetime = TimeSpan.FromDays(90);
    private const int MaxDevices = 32;
    private readonly Lock gate = new();
    private readonly string path;
    private readonly TimeProvider clock;
    private readonly List<Device> devices;
    private (string Code, DateTimeOffset Expires)? pair;

    internal sealed record Device(string Id, string Name, string Digest, DateTimeOffset Expires)
    {
        internal CancellationTokenSource Revoked { get; } = new();
        internal DateTimeOffset? LastSeen { get; set; }
    }

    internal PwaSessions(string path, TimeProvider? clock = null)
    {
        this.path = path;
        this.clock = clock ?? TimeProvider.System;
        AppPaths.RestrictToOwner(path);
        devices = File.Exists(path) ? JsonSerializer.Deserialize<List<Device>>(File.ReadAllText(path)) ?? [] : [];
    }

    internal string StartPairing()
    {
        lock (gate)
        {
            var code = Convert.ToHexStringLower(RandomNumberGenerator.GetBytes(16));
            pair = (code, clock.GetUtcNow() + PairLifetime);
            return code;
        }
    }

    internal (Device Device, string Token)? Claim(string? code, string? name, string? previousToken)
    {
        lock (gate)
        {
            var now = clock.GetUtcNow();
            if (pair is not { } attempt || attempt.Expires <= now || !Matches(code, attempt.Code)) return null;
            var previous = Find(previousToken);
            var next = devices.Where(d => d.Expires > now && d != previous).ToList();
            if (next.Count >= MaxDevices) return null;
            var token = Convert.ToHexStringLower(RandomNumberGenerator.GetBytes(32));
            var label = new string((name ?? "").Where(c => !char.IsControl(c)).Take(40).ToArray()).Trim();
            var device = new Device(previous?.Id ?? "pwa" + Convert.ToHexStringLower(RandomNumberGenerator.GetBytes(12)),
                label.Length == 0 ? "PhoneBox web app" : label, Digest(token), now + SessionLifetime);
            next.Add(device);
            Commit(next);
            pair = null;
            previous?.Revoked.Cancel();
            return (device, token);
        }
    }

    internal Device? Authenticate(string? token)
    {
        lock (gate)
        {
            var device = Find(token);
            if (device is not null) device.LastSeen = clock.GetUtcNow();
            return device;
        }
    }

    internal object List()
    {
        lock (gate) return devices.Where(d => d.Expires > clock.GetUtcNow())
            .Select(d => new { d.Id, d.Name, d.Expires, d.LastSeen }).ToArray();
    }

    internal void Revoke(string id)
    {
        lock (gate)
        {
            var device = devices.Find(d => d.Id == id);
            if (device is null) return;
            Commit(devices.Where(d => d != device).ToList());
            device.Revoked.Cancel();
        }
    }

    private Device? Find(string? token)
    {
        if (token?.Length != 64) return null;
        var digest = Digest(token);
        return devices.Find(d => d.Expires > clock.GetUtcNow() && Matches(digest, d.Digest));
    }

    private void Commit(List<Device> next)
    {
        var temporary = path + ".tmp";
        using (var stream = AppPaths.CreatePrivate(temporary)) JsonSerializer.Serialize(stream, next);
        File.Move(temporary, path, overwrite: true);
        devices.Clear();
        devices.AddRange(next);
    }

    private static string Digest(string value) => Convert.ToHexStringLower(SHA256.HashData(System.Text.Encoding.UTF8.GetBytes(value)));
    private static bool Matches(string? value, string expected) => value?.Length == expected.Length &&
        CryptographicOperations.FixedTimeEquals(System.Text.Encoding.UTF8.GetBytes(value), System.Text.Encoding.UTF8.GetBytes(expected));
}
