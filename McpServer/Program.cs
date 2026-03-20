using Microsoft.AspNetCore.Authentication.JwtBearer;
using Microsoft.IdentityModel.Tokens;
using System.Security.Claims;
using System.Text.Json;

var builder = WebApplication.CreateBuilder(args);

// Configure Authentication with Keycloak
builder.Services.AddAuthentication(JwtBearerDefaults.AuthenticationScheme)
    .AddJwtBearer(options =>
    {
        options.Authority = "http://localhost:8080/realms/myrealm";
        options.RequireHttpsMetadata = false; // For development
        options.TokenValidationParameters = new TokenValidationParameters
        {
            ValidateAudience = false,
            RoleClaimType = ClaimTypes.Role,
            NameClaimType = "preferred_username"
        };

        options.Events = new JwtBearerEvents
        {
            OnTokenValidated = context =>
            {
                var claimsIdentity = context.Principal?.Identity as ClaimsIdentity;
                var realmAccess = claimsIdentity?.FindFirst("realm_access");
                if (realmAccess != null)
                {
                    try
                    {
                        var content = JsonDocument.Parse(realmAccess.Value);
                        if (content.RootElement.TryGetProperty("roles", out var roles))
                        {
                            foreach (var role in roles.EnumerateArray())
                            {
                                var roleValue = role.GetString();
                                if (!string.IsNullOrEmpty(roleValue))
                                {
                                    claimsIdentity.AddClaim(new Claim(ClaimTypes.Role, roleValue));
                                }
                            }
                        }
                    }
                    catch (Exception ex)
                    {
                        Console.WriteLine($"Error parsing realm_access: {ex.Message}");
                    }
                }
                return Task.CompletedTask;
            }
        };
    });

builder.Services.AddAuthorization();

var app = builder.Build();

app.UseAuthentication();
app.UseAuthorization();

// MACHINE-LEVEL TOOL PROTECTION (MCP Endpoints)
// In a real implementation, these would be part of the MCP protocol handler
app.MapPost("/mcp/run_dotnet_build", () => Results.Ok(new { message = "Build Started...", status = "success" }))
   .RequireAuthorization(policy => policy.RequireRole("Manager", "Developer"));

app.MapPost("/mcp/deploy_prod", () => Results.Ok(new { message = "Deploying to Production...", status = "success" }))
   .RequireAuthorization(policy => policy.RequireRole("Manager"));

// Default health check
app.MapGet("/", () => "MCP Server with RBAC is running.");

app.Run();
