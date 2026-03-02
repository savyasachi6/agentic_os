using System.Security.Claims;

namespace OpenClawToolsNode.Middleware;

public class AuditLoggingMiddleware
{
    private readonly RequestDelegate _next;
    private readonly ILogger<AuditLoggingMiddleware> _logger;

    public AuditLoggingMiddleware(RequestDelegate next, ILogger<AuditLoggingMiddleware> logger)
    {
        _next = next;
        _logger = logger;
    }

    public async Task InvokeAsync(HttpContext context)
    {
        // 1. Let the request process
        await _next(context);

        // 2. Log after the request so we know the status code
        if (context.Request.Path.StartsWithSegments("/tools"))
        {
            var user = context.User;
            var isAuth = user.Identity?.IsAuthenticated ?? false;

            // Extract claims if present
            var sessionId = user.FindFirst("session_id")?.Value ?? "unknown";
            var userId = user.FindFirst("user_id")?.Value ?? "unknown";
            var agentId = user.FindFirst("agent_id")?.Value ?? "unknown";
            var toolName = context.Request.Path.Value?.Split('/').LastOrDefault() ?? "unknown";
            var statusCode = context.Response.StatusCode;

            if (isAuth)
            {
                _logger.LogInformation(
                    "AUDIT: [Session:{SessionId}] [User:{UserId}] [Agent:{AgentId}] Tool '{ToolName}' executed. Result: {StatusCode}",
                    sessionId, userId, agentId, toolName, statusCode);
            }
            else
            {
                _logger.LogWarning(
                    "AUDIT [UNAUTHENTICATED]: Attempt to access tool '{ToolName}'. Result: {StatusCode}",
                    toolName, statusCode);
            }
        }
    }
}

public static class AuditLoggingMiddlewareExtensions
{
    public static IApplicationBuilder UseAuditLogging(this IApplicationBuilder builder)
    {
        return builder.UseMiddleware<AuditLoggingMiddleware>();
    }
}
