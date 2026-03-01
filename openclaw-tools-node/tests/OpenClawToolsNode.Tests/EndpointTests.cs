namespace OpenClawToolsNode.Tests;

using System.Net.Http.Json;
using Microsoft.AspNetCore.Mvc.Testing;
using Xunit;
using OpenClawToolsNode.Models;

public class EndpointTests : IClassFixture<WebApplicationFactory<Program>>
{
    private readonly WebApplicationFactory<Program> _factory;

    public EndpointTests(WebApplicationFactory<Program> factory)
    {
        _factory = factory;
    }

    [Fact]
    public async Task HealthEndpoint_ReturnsOk()
    {
        var client = _factory.CreateClient();
        var response = await client.GetAsync("/health");

        response.EnsureSuccessStatusCode();
        var content = await response.Content.ReadAsStringAsync();
        Assert.Contains("healthy", content);
    }
    
    [Fact]
    public async Task ShellTool_Returns401_WithoutToken()
    {
        var client = _factory.CreateClient();
        var response = await client.PostAsJsonAsync("/tools/run-shell", new ShellRequest { Command = "echo hello" });

        Assert.Equal(System.Net.HttpStatusCode.Unauthorized, response.StatusCode);
    }

    [Fact]
    public async Task FileTool_Returns401_WithoutToken()
    {
        var client = _factory.CreateClient();
        var response = await client.PostAsJsonAsync("/tools/file-read", new FileRequest { Path = "test.txt" });

        Assert.Equal(System.Net.HttpStatusCode.Unauthorized, response.StatusCode);
    }
}
