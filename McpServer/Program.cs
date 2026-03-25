using System;
using System.IO;
using System.Text.Json;
using System.Threading.Tasks;

namespace McpServer
{
    class Program
    {
        static async Task Main(string[] args)
        {
            // Use Asynchronous Streams for standard I/O to prevent blocking bottleneck
            using var stdin = new StreamReader(Console.OpenStandardInput());
            using var stdout = new StreamWriter(Console.OpenStandardOutput()) { AutoFlush = true };

            while (true)
            {
                // Non-blocking read line-by-line asynchronously
                var line = await stdin.ReadLineAsync();
                if (line == null) break;

                // Handle concurrent requests by spawning worker tasks
                _ = Task.Run(async () =>
                {
                    try
                    {
                        var response = await HandleJsonRpcAsync(line);
                        if (response != null)
                        {
                            // Output back cleanly enforcing synchronized writes to stdout
                            lock (stdout)
                            {
                                stdout.WriteLine(response);
                            }
                        }
                    }
                    catch (Exception ex)
                    {
                        // Global Exception Handling: Return as JSON-RPC error
                        var errRpc = new { jsonrpc = "2.0", error = new { code = -32603, message = ex.Message } };
                        lock (stdout)
                        {
                            stdout.WriteLine(JsonSerializer.Serialize(errRpc));
                        }
                    }
                });
            }
        }

        private static async Task<string?> HandleJsonRpcAsync(string jsonLine)
        {
            // Parse JSON-RPC
            try
            {
                var doc = JsonDocument.Parse(jsonLine);
                if (doc.RootElement.TryGetProperty("method", out var methodProp))
                {
                    var method = methodProp.GetString();
                    object result = null;

                    // Simulated endpoints protecting via RBAC
                    if (method == "run_dotnet_build")
                    {
                        await Task.Delay(100); // Simulate build work
                        result = new { message = "Build Started...", status = "success" };
                    }
                    else if (method == "deploy_prod")
                    {
                        await Task.Delay(200); // Simulate deploy work
                        result = new { message = "Deploying to Production...", status = "success" };
                    }
                    else if (method == "tools/list")
                    {
                        result = new { tools = new[] { new { name = "run_dotnet_build" }, new { name = "deploy_prod" } } };
                    }
                    else
                    {
                        throw new Exception("Method not found");
                    }

                    var id = doc.RootElement.TryGetProperty("id", out var idProp) ? idProp.GetInt32() : 0;
                    return JsonSerializer.Serialize(new { jsonrpc = "2.0", id, result });
                }
            }
            catch (JsonException) { /* Invalid JSON */ }
            
            return null; // Ignore invalid format or notifications quietly
        }
    }
}
