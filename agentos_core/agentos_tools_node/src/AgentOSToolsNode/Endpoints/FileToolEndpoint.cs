namespace AgentOSToolsNode.Endpoints;

using Microsoft.AspNetCore.Mvc;
using AgentOSToolsNode.Models;

public static class FileToolEndpoint
{
    public static void MapFileEndpoints(this IEndpointRouteBuilder app)
    {
        app.MapPost("/tools/file-read", ReadFileAsync)
           .RequireAuthorization("HighRiskTool");

        app.MapPost("/tools/file-write", WriteFileAsync)
           .RequireAuthorization("HighRiskTool");
    }

    private static async Task<IResult> ReadFileAsync([FromBody] FileRequest request, CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(request.Path)) return Results.BadRequest("Path is required.");
        
        try
        {
            if (!File.Exists(request.Path)) return Results.NotFound("File not found.");

            var content = await File.ReadAllTextAsync(request.Path, cancellationToken);
            return Results.Ok(new FileResponse { Content = content });
        }
        catch (Exception ex)
        {
            return Results.Problem(ex.Message);
        }
    }

    private static async Task<IResult> WriteFileAsync([FromBody] FileRequest request, CancellationToken cancellationToken)
    {
        if (string.IsNullOrWhiteSpace(request.Path)) return Results.BadRequest("Path is required.");
        if (request.Content == null) return Results.BadRequest("Content is required for writing.");

        try
        {
            var dir = Path.GetDirectoryName(request.Path);
            if (!string.IsNullOrEmpty(dir) && !Directory.Exists(dir))
            {
                Directory.CreateDirectory(dir);
            }

            await File.WriteAllTextAsync(request.Path, request.Content, cancellationToken);
            return Results.Ok(new { status = "success" });
        }
        catch (Exception ex)
        {
            return Results.Problem(ex.Message);
        }
    }
}
