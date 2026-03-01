namespace OpenClawToolsNode.Endpoints;

using System.Diagnostics;
using Microsoft.AspNetCore.Mvc;
using OpenClawToolsNode.Models;

public static class ShellToolEndpoint
{
    public static void MapShellEndpoints(this IEndpointRouteBuilder app)
    {
        app.MapPost("/tools/run-shell", RunShellAsync)
           .RequireAuthorization("ToolCaller");

        app.MapPost("/tools/run-shell-elevated", RunShellAsync)
           .RequireAuthorization("HighRiskTool");
    }

    private static async Task<IResult> RunShellAsync([FromBody] ShellRequest request, CancellationToken cancellationToken)
    {
        try
        {
            var isWindows = OperatingSystem.IsWindows();
            var fileName = isWindows ? "cmd.exe" : "/bin/bash";
            var arguments = isWindows ? $"/c \"{request.Command}\"" : $"-c \"{request.Command}\"";

            var processStartInfo = new ProcessStartInfo
            {
                FileName = fileName,
                Arguments = arguments,
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                UseShellExecute = false,
                CreateNoWindow = true,
                WorkingDirectory = request.WorkingDirectory ?? Environment.CurrentDirectory
            };

            using var process = new Process { StartInfo = processStartInfo };
            process.Start();

            // Wait with timeout
            using var cts = CancellationTokenSource.CreateLinkedTokenSource(cancellationToken);
            cts.CancelAfter(request.TimeoutMs);

            await process.WaitForExitAsync(cts.Token);

            var stdout = await process.StandardOutput.ReadToEndAsync(cancellationToken);
            var stderr = await process.StandardError.ReadToEndAsync(cancellationToken);

            return Results.Ok(new ShellResponse
            {
                ExitCode = process.ExitCode,
                Stdout = stdout,
                Stderr = stderr
            });
        }
        catch (OperationCanceledException)
        {
            return Results.StatusCode(408); // Request Timeout
        }
        catch (Exception ex)
        {
            return Results.Problem(ex.Message);
        }
    }
}
