using PhoneBox.Agent;
using Xunit;

public sealed class PwaSessionsTests
{
    private sealed class Clock : TimeProvider
    {
        internal DateTimeOffset Now = DateTimeOffset.UtcNow;
        public override DateTimeOffset GetUtcNow() => Now;
    }

    [Fact]
    public void PairingIsSingleUseExpiresAndNeverPersistsTheCookie()
    {
        var path = System.IO.Path.Combine(System.IO.Path.GetTempPath(), $"pwa-{Guid.NewGuid():N}.json");
        try
        {
            var clock = new Clock();
            var sessions = new PwaSessions(path, clock);
            var old = sessions.StartPairing();
            clock.Now += TimeSpan.FromMinutes(5);
            Assert.Null(sessions.Claim(old, "expired", null));

            var code = sessions.StartPairing();
            var first = sessions.Claim(code, "iPad", null);
            Assert.NotNull(first);
            Assert.Null(sessions.Claim(code, "another", null));
            Assert.DoesNotContain(first.Value.Token, File.ReadAllText(path));

            var reloaded = new PwaSessions(path, clock);
            Assert.Equal(first.Value.Device.Id, reloaded.Authenticate(first.Value.Token)?.Id);
            clock.Now += PwaSessions.SessionLifetime;
            Assert.Null(reloaded.Authenticate(first.Value.Token));
        }
        finally { File.Delete(path); }
    }

    [Fact]
    public void RePairingRotatesTheCredentialAndRevocationCancelsActiveRequests()
    {
        var path = System.IO.Path.Combine(System.IO.Path.GetTempPath(), $"pwa-{Guid.NewGuid():N}.json");
        try
        {
            var sessions = new PwaSessions(path);
            var first = sessions.Claim(sessions.StartPairing(), "iPad", null)!.Value;
            var second = sessions.Claim(sessions.StartPairing(), "iPad new", first.Token)!.Value;
            var other = sessions.Claim(sessions.StartPairing(), "iPhone", null)!.Value;
            Assert.Equal(first.Device.Id, second.Device.Id);
            Assert.True(first.Device.Revoked.IsCancellationRequested);
            Assert.Null(sessions.Authenticate(first.Token));

            sessions.Revoke(second.Device.Id);
            Assert.True(second.Device.Revoked.IsCancellationRequested);
            Assert.Null(sessions.Authenticate(second.Token));
            Assert.NotNull(sessions.Authenticate(other.Token));
            Assert.Null(new PwaSessions(path).Authenticate(second.Token));
        }
        finally { File.Delete(path); }
    }
}
