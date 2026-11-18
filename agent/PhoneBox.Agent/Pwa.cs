using System.Net;
using System.Reflection;
using System.Security.Cryptography.X509Certificates;
using System.Text.Json;
using Microsoft.AspNetCore.Http.Features;

namespace PhoneBox.Agent;

public sealed class PwaConfig
{
    public bool Enabled { get; set; }
    public string? Host { get; set; }
    public string? BindAddress { get; set; }
    public int Port { get; set; } = 8767;
    public string? CertificatePath { get; set; }
    public string? CertificateThumbprint { get; set; }
}

internal sealed class Pwa
{
    private const string Cookie = "__Host-phonebox";
    private const string PanelHeader = "X-PhoneBox-Panel";
    private static readonly HashSet<string> Images = new(StringComparer.OrdinalIgnoreCase)
    {
        "/api/art", "/api/procs/icon", "/api/shortcuts/icon", "/api/apps/icon",
        "/api/controls/radio-logo", "/api/discord/img",
    };
    private static readonly Assembly Assembly = typeof(Pwa).Assembly;
    private static readonly string[] ShellFiles = Assembly.GetManifestResourceNames()
        .Where(name => name.StartsWith("www/", StringComparison.Ordinal) && !name.EndsWith(".html", StringComparison.Ordinal))
        .Select(name => "/panel/" + name[4..])
        .Concat(["/panel/", "/panel/manifest.webmanifest", "/panel/icon-192.png", "/panel/icon-512.png", "/panel/apple-touch-icon.png",
            "/panel/pwa.js", "/panel/pwa.css"]).Order(StringComparer.Ordinal).ToArray();

    internal int Port { get; }
    internal IPAddress Address { get; }
    internal string Origin { get; }
    internal X509Certificate2 Certificate { get; }
    internal X509Certificate2Collection Chain { get; }
    private readonly PwaSessions sessions;

    internal Pwa(PwaConfig config, string configPath, int localPort, int? lanPort)
    {
        if (string.IsNullOrWhiteSpace(config.Host) || Uri.CheckHostName(config.Host) != UriHostNameType.Dns ||
            !IPAddress.TryParse(config.BindAddress, out var address) || address.AddressFamily != System.Net.Sockets.AddressFamily.InterNetwork ||
            address.Equals(IPAddress.Any) || config.Port is < 1024 or > 65535 || config.Port == localPort || config.Port == lanPort ||
            string.IsNullOrWhiteSpace(config.CertificatePath) == string.IsNullOrWhiteSpace(config.CertificateThumbprint))
            throw new ArgumentException("PWA requires a DNS host, a specific IPv4 bind address, a distinct port and one certificate source.");

        Port = config.Port;
        Address = address;
        Origin = new UriBuilder("https", config.Host, Port).Uri.GetLeftPart(UriPartial.Authority);
        if (string.IsNullOrWhiteSpace(config.CertificateThumbprint))
        {
            var certPath = Path.GetFullPath(config.CertificatePath!, Path.GetDirectoryName(configPath)!);
            Chain = X509CertificateLoader.LoadPkcs12CollectionFromFile(certPath, Environment.GetEnvironmentVariable("PHONEBOX_PWA_PFX_PASSWORD"),
                X509KeyStorageFlags.UserKeySet);
        }
        else
        {
            using var store = new X509Store(StoreName.My, StoreLocation.CurrentUser);
            store.Open(OpenFlags.ReadOnly | OpenFlags.OpenExistingOnly);
            Chain = store.Certificates.Find(X509FindType.FindByThumbprint, config.CertificateThumbprint, validOnly: false);
        }
        Certificate = Chain.Cast<X509Certificate2>().SingleOrDefault(cert => cert.HasPrivateKey && DateTime.Now >= cert.NotBefore &&
            DateTime.Now < cert.NotAfter && cert.MatchesHostname(config.Host, allowCommonName: false))
            ?? throw new ArgumentException("The PWA certificate needs a private key, current validity and a SAN matching the PWA host.");
        Chain.Remove(Certificate);
        if (config.CertificateThumbprint is { Length: > 0 })
        {
            using var chain = new X509Chain();
            chain.ChainPolicy.RevocationMode = X509RevocationMode.Offline;
            chain.ChainPolicy.DisableCertificateDownloads = true;
            // Send locally available intermediates. The browser still performs its own trust and validity checks.
            chain.Build(Certificate);
            foreach (var element in chain.ChainElements.Cast<X509ChainElement>().Skip(1))
                if (!element.Certificate.SubjectName.RawData.SequenceEqual(element.Certificate.IssuerName.RawData))
                    Chain.Add(X509CertificateLoader.LoadCertificate(element.Certificate.RawData));
        }

        sessions = new(configPath + ".pwa-sessions.json");
    }

    internal static bool Allows(string method, PathString path)
    {
        if (HttpMethods.IsGet(method) && path == "/api/push") return true;
        if ((!HttpMethods.IsGet(method) && !HttpMethods.IsPost(method)) || Lan.IsWebhook(path) ||
            path.StartsWithSegments("/api/pair") || path.StartsWithSegments("/api/phone")) return false;
        return Lan.AllowedOverLan(path);
    }

    // Before routing: only the browser alias is eligible for the existing panel handlers.
    internal async Task Handle(HttpContext ctx, RequestDelegate next)
    {
        var request = ctx.Request;
        var response = ctx.Response;
        response.Headers.CacheControl = "no-store";
        response.Headers["X-Content-Type-Options"] = "nosniff";
        response.Headers["Referrer-Policy"] = "no-referrer";
        response.Headers["Cross-Origin-Resource-Policy"] = "same-origin";
        response.Headers["X-Frame-Options"] = "DENY";
        response.Headers.ContentSecurityPolicy = "base-uri 'none'; object-src 'none'; frame-ancestors 'none'; form-action 'self'";

        if (!request.IsHttps || !string.Equals("https://" + request.Host, Origin, StringComparison.OrdinalIgnoreCase) ||
            (request.Headers.Origin.Count > 0 && request.Headers.Origin != Origin) ||
            BrowserGuard.IsForeign(request.Headers["Sec-Fetch-Site"], request.Headers["Sec-Fetch-Mode"], request.Method, request.Path.StartsWithSegments("/agent") || request.Path.StartsWithSegments("/pwa") ? "/api" : request.Path))
        {
            response.StatusCode = 403;
            return;
        }

        var path = request.Path;
        var panelRequest = request.Headers[PanelHeader] == "1";
        if (HttpMethods.IsGet(request.Method) && (path == "/" || path == "/panel"))
        {
            response.Redirect("/panel/");
            return;
        }
        if (HttpMethods.IsGet(request.Method) && path.StartsWithSegments("/panel", out var file))
        {
            await Asset(ctx, file.Value!);
            return;
        }

        var cookie = request.Cookies[Cookie];
        if (path == "/pwa/session" && panelRequest)
        {
            if (HttpMethods.IsGet(request.Method))
            {
                response.StatusCode = sessions.Authenticate(cookie) is null ? 401 : 204;
                return;
            }
            if (HttpMethods.IsPost(request.Method) && request.Headers.Origin == Origin && request.HasJsonContentType())
            {
                ctx.Features.Get<IHttpMaxRequestBodySizeFeature>()!.MaxRequestBodySize = 2048;
                PairRequest? pair;
                try { pair = await request.ReadFromJsonAsync<PairRequest>(ctx.RequestAborted); }
                catch (JsonException) { response.StatusCode = 400; return; }
                var claim = sessions.Claim(pair?.Code, pair?.Name, cookie);
                if (claim is null) { response.StatusCode = 403; return; }
                response.Cookies.Append(Cookie, claim.Value.Token, new CookieOptions
                {
                    Secure = true, HttpOnly = true, SameSite = SameSiteMode.Strict, Path = "/", Expires = claim.Value.Device.Expires,
                    IsEssential = true,
                });
                response.StatusCode = 204;
                return;
            }
        }

        if (!path.StartsWithSegments("/agent/api", out var rest) || !Allows(request.Method, "/api" + rest))
        {
            response.StatusCode = 404;
            return;
        }
        var target = new PathString("/api" + rest);
        var eventStream = target == "/api/stream" && HttpMethods.IsGet(request.Method) &&
            request.Headers.Accept == "text/event-stream";
        var image = HttpMethods.IsGet(request.Method) && Images.Contains(target.Value!) && request.Headers["Sec-Fetch-Dest"] == "image";
        if ((!panelRequest && !eventStream && !image) ||
            (!HttpMethods.IsGet(request.Method) && request.Headers.Origin != Origin))
        {
            response.StatusCode = 403;
            return;
        }
        var device = sessions.Authenticate(cookie);
        if (device is null) { response.StatusCode = 401; return; }

        if (target == "/api/state" || eventStream) Heartbeat(device);
        request.Headers["X-PhoneBox-Device"] = device.Id;
        request.Headers.Remove("X-PhoneBox-App");
        ctx.Items[typeof(Pwa)] = device;
        request.Path = target;
        using var lifetime = CancellationTokenSource.CreateLinkedTokenSource(ctx.RequestAborted, device.Revoked.Token);
        var remaining = device.Expires - DateTimeOffset.UtcNow;
        lifetime.CancelAfter(remaining > TimeSpan.FromDays(1) ? TimeSpan.FromDays(1) : TimeSpan.FromTicks(Math.Max(0, remaining.Ticks)));
        var originalAbort = ctx.RequestAborted;
        ctx.RequestAborted = lifetime.Token;
        try { await next(ctx); }
        finally { ctx.RequestAborted = originalAbort; }
    }

    internal static void Heartbeat(PwaSessions.Device device)
    {
        PhoneRegistry.Touch(device.Id, device.Name, "PWA");
        Interlocked.Exchange(ref ApprovalStore.PhoneLastSeen, DateTimeOffset.UtcNow.ToUnixTimeMilliseconds());
    }

    private sealed record PairRequest(string? Code, string? Name);

    private static async Task Asset(HttpContext ctx, string file)
    {
        if (file == "/sw.js")
        {
            using var src = new StreamReader(AppPaths.Resource("pwa/sw.js")!);
            var js = (await src.ReadToEndAsync(ctx.RequestAborted))
                .Replace("__CACHE__", Assembly.ManifestModule.ModuleVersionId.ToString("N"))
                .Replace("__ASSETS__", JsonSerializer.Serialize(ShellFiles));
            await Results.Text(js, "text/javascript; charset=utf-8").ExecuteAsync(ctx);
            return;
        }
        if (file == "/" || file == "/index.html")
        {
            using var src = new StreamReader(AppPaths.Resource("www/index.html")!);
            var html = (await src.ReadToEndAsync(ctx.RequestAborted))
                .Replace("initial-scale=1, maximum-scale=1, user-scalable=no", "initial-scale=1")
                .Replace("<body>", "<body class=\"pwa\">")
                .Replace("</head>", """
                    <meta name="theme-color" content="#06080b">
                    <meta name="apple-mobile-web-app-capable" content="yes">
                    <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
                    <link rel="manifest" href="manifest.webmanifest">
                    <link rel="apple-touch-icon" href="apple-touch-icon.png">
                    <link rel="stylesheet" href="pwa.css">
                    </head>
                    """)
                .Replace("src=\"main.js\"", "src=\"pwa.js\"");
            await Results.Content(html, "text/html; charset=utf-8").ExecuteAsync(ctx);
            return;
        }

        if (!ShellFiles.Contains("/panel" + file, StringComparer.Ordinal))
        {
            ctx.Response.StatusCode = 404;
            return;
        }
        var extension = Path.GetExtension(file);
        var type = extension switch
        {
            ".js" => "text/javascript; charset=utf-8", ".css" => "text/css; charset=utf-8",
            ".webmanifest" => "application/manifest+json", ".png" => "image/png",
            _ => "application/octet-stream",
        };
        var folder = file.StartsWith("/pwa.", StringComparison.Ordinal) || extension is ".png" or ".webmanifest" ? "pwa" : "www";
        await Results.Stream(AppPaths.Resource(folder + file)!, type).ExecuteAsync(ctx);
    }

    internal void MapManagement(WebApplication app, int localPort)
    {
        bool Local(HttpContext ctx) => ctx.Connection.LocalPort == localPort;
        app.MapGet("/pwa/setup", (HttpContext ctx) => Local(ctx)
            ? Results.Stream(AppPaths.Resource("pwa/manage.html")!, "text/html; charset=utf-8") : Results.NotFound());
        app.MapGet("/pwa/manage", (HttpContext ctx) => Local(ctx)
            ? Results.Json(new { url = Origin + "/panel/", certificateExpires = Certificate.NotAfter, devices = sessions.List() }) : Results.NotFound());
        app.MapPost("/pwa/manage/pair", (HttpContext ctx) =>
        {
            if (!Local(ctx) || ctx.Request.Headers[PanelHeader] != "1") return Results.StatusCode(403);
            var code = sessions.StartPairing();
            var link = Origin + "/panel/#pair=" + code;
            return Results.Json(new { code, link, qr = PairingCodes.Svg(link) });
        });
        app.MapDelete("/pwa/manage/{id}", (string id, HttpContext ctx) =>
        {
            if (!Local(ctx) || ctx.Request.Headers[PanelHeader] != "1") return Results.StatusCode(403);
            sessions.Revoke(id);
            return Results.NoContent();
        });
    }
}
