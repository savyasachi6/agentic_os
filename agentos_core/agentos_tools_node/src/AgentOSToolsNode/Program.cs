using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.IdentityModel.Tokens;
using AgentOSToolsNode.Middleware;
using AgentOSToolsNode.Endpoints;

var builder = WebApplication.CreateBuilder(args);

// Add services to the container.
builder.Services.AddAuthentication(JwtBearerDefaults.AuthenticationScheme)
    .AddJwtBearer(options =>
    {
        options.Audience = "agentos-tools";
        
        var secretKey = builder.Configuration["Jwt:SecretKey"];
        if (!string.IsNullOrEmpty(secretKey))
        {
            options.TokenValidationParameters = new TokenValidationParameters
            {
                ValidateIssuerSigningKey = true,
                IssuerSigningKey = new SymmetricSecurityKey(System.Text.Encoding.UTF8.GetBytes(secretKey)),
                ValidateIssuer = false, // We mint it locally in python without strict issuer
                ValidateAudience = true,
                ValidAudience = "agentos-tools",
            };
        }
    });

builder.Services.AddAuthorizationBuilder()
    .AddPolicy("ToolCaller", policy =>
    {
        policy.RequireAuthenticatedUser();
        policy.RequireClaim("scope", "tool.invoke");
    })
    .AddPolicy("HighRiskTool", policy =>
    {
        policy.RequireAuthenticatedUser();
        // High risk requires BOTH standard invoke and highrisk scopes for safety, or just highrisk
        policy.RequireClaim("scope", "tool.invoke.highrisk");
    });

var app = builder.Build();

app.UseAuthentication();
app.UseAuthorization();
app.UseAuditLogging(); // Capture tool executions in the log

// Basic health check endpoint
app.MapGet("/health", () => new { status = "healthy", timestamp = DateTime.UtcNow })
    .AllowAnonymous();

app.MapShellEndpoints();
app.MapFileEndpoints();

app.Run();

public partial class Program { }
